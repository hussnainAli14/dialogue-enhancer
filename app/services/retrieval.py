"""Module 6 — knowledge retrieval (RAG).

Internal reusable service — not exposed as a public endpoint.
Pipeline: query extraction → vector search → LLM rerank → context assembly.
"""

import asyncio
import json
import re
from dataclasses import dataclass, field

from app.config import get_embeddings, get_llm, settings
from app.database import get_supabase, log_task
from app.prompts.retrieval import QUERY_EXTRACTION_PROMPT

LLM_MAX_RETRIES = 3


async def call_llm_with_retry(llm, prompt: str) -> str:
    """Shared LLM call helper: 3 retries, exponential backoff 2s/4s/8s."""
    last_exc: Exception | None = None
    for attempt in range(LLM_MAX_RETRIES):
        try:
            result = await llm.ainvoke(prompt)
            return result.content
        except Exception as exc:
            last_exc = exc
            if attempt < LLM_MAX_RETRIES - 1:
                await asyncio.sleep(2 ** (attempt + 1))
    raise last_exc


def extract_json(text: str) -> dict | list:
    """Parse JSON from an LLM response, tolerating markdown fences and
    surrounding prose."""
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"[\[{].*[\]}]", text, re.DOTALL)
        candidate = match.group(0) if match else text
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            # Local models often emit unescaped quotes, trailing commas, or an
            # unclosed brace. Repair tolerantly as a last resort.
            from json_repair import repair_json

            return json.loads(repair_json(candidate))


@dataclass
class SourceChunk:
    chunk_id: str
    document_id: str
    document_title: str
    source_type: str
    content: str
    similarity_score: float
    rerank_score: float = 0.0


@dataclass
class RetrievalResult:
    context_block: str
    source_chunks: list[SourceChunk] = field(default_factory=list)


RERANK_PROMPT = """You are helping select the most useful source material for contributing \
to an online conversation.

CONVERSATION:
{conversation}

CANDIDATE CHUNKS from the author's writing:
{chunks}

Score each chunk from 0 to 10 for how directly and meaningfully it would help the author \
contribute to this specific conversation.

Return ONLY a JSON array, no other text:
[{{"chunk_id": "uuid", "score": 0}}]"""


class RetrievalService:
    def __init__(self):
        self.supabase = get_supabase()

    async def retrieve(self, conversation_text: str) -> RetrievalResult:
        query = await self._extract_query(conversation_text)
        raw_chunks = await self._vector_search(query)
        if not raw_chunks:
            return RetrievalResult(context_block="(No relevant source material found.)")
        reranked = await self._rerank(conversation_text, raw_chunks)
        return self._assemble_context(reranked)

    # STEP 1 — query extraction
    async def _extract_query(self, conversation_text: str) -> str:
        llm = get_llm(temperature=0.3)
        prompt = QUERY_EXTRACTION_PROMPT.format(conversation=conversation_text)
        raw = await call_llm_with_retry(llm, prompt)
        # Model may wrap the query in quotes or add a label — take the last
        # non-empty line and strip decoration.
        lines = [ln.strip().strip('"') for ln in raw.strip().splitlines() if ln.strip()]
        return lines[-1] if lines else conversation_text[:200]

    # STEP 2 — vector search with one threshold-lowering retry
    async def _vector_search(self, query: str) -> list[SourceChunk]:
        embeddings = get_embeddings()
        vector = await embeddings.aembed_query(query)

        results = self._match(vector, settings.SIMILARITY_THRESHOLD)
        if len(results) < 3:
            results = self._match(vector, settings.SIMILARITY_THRESHOLD - 0.05)

        if not results:
            return []

        doc_ids = list({r["document_id"] for r in results})
        docs = (
            self.supabase.table("documents")
            .select("id, title, filename, source_type")
            .in_("id", doc_ids)
            .execute()
        ).data
        doc_map = {d["id"]: d for d in docs}

        chunks = []
        for r in results:
            doc = doc_map.get(r["document_id"], {})
            chunks.append(
                SourceChunk(
                    chunk_id=r["id"],
                    document_id=r["document_id"],
                    document_title=doc.get("title") or doc.get("filename") or "Untitled",
                    source_type=doc.get("source_type") or "other",
                    content=r["content"],
                    similarity_score=r["similarity"],
                )
            )
        return chunks

    def _match(self, vector: list[float], threshold: float) -> list[dict]:
        response = self.supabase.rpc(
            "match_documents",
            {
                "query_embedding": vector,
                "match_threshold": threshold,
                "match_count": settings.RETRIEVAL_TOP_K,
            },
        ).execute()
        return response.data or []

    # STEP 3 — LLM rerank
    async def _rerank(self, conversation_text: str, chunks: list[SourceChunk]) -> list[SourceChunk]:
        llm = get_llm(temperature=0)
        chunk_text = "\n\n".join(
            f"chunk_id: {c.chunk_id}\ncontent: {c.content}" for c in chunks
        )
        prompt = RERANK_PROMPT.format(conversation=conversation_text, chunks=chunk_text)
        try:
            raw = await call_llm_with_retry(llm, prompt)
            scores = extract_json(raw)
            score_map = {s["chunk_id"]: float(s["score"]) for s in scores}
            for c in chunks:
                c.rerank_score = score_map.get(c.chunk_id, 0.0)
        except Exception as exc:
            # Reranking is an optimisation — fall back to similarity order.
            log_task("retrieval", None, "failed", f"rerank fallback: {exc}")
            for c in chunks:
                c.rerank_score = c.similarity_score * 10

        chunks.sort(key=lambda c: c.rerank_score, reverse=True)
        return chunks[: settings.RETRIEVAL_RERANK_TOP_K]

    # STEP 4 — context assembly
    def _assemble_context(self, chunks: list[SourceChunk]) -> RetrievalResult:
        parts = []
        for i, c in enumerate(chunks, start=1):
            parts.append(
                f"[SOURCE {i} — \"{c.document_title}\" ({c.source_type})]\n{c.content}"
            )
        delimiter = "\n\n────────────────────\n\n"
        return RetrievalResult(context_block=delimiter.join(parts), source_chunks=chunks)
