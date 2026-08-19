# AI Dialogue Enhancer — Session Handoff

This document is a complete handoff for the project. It explains what the system is, everything that has been built so far, the journey we took to get here, the current running state, and exactly how to pick it up and continue — whether that's future-me or a different developer receiving this project as a zip.

> **Read this first if you just received a zip of this project.** Jump to [Getting Started From a Zip](#getting-started-from-a-zip).

---

## 1. What this project is

The **AI Dialogue Enhancer** helps a coach/author (15 years of published writing) participate more thoughtfully in online conversations across social platforms. It is a **reflective thinking partner**, not a marketing tool. Quality over quantity.

End-to-end vision:

1. Monitor social platforms for relevant conversations.
2. Retrieve the author's own ideas from their writing archive (RAG).
3. Generate 3–4 grounded response drafts in different styles.
4. The author reviews/approves/edits/rejects in a dashboard.
5. Approved responses are posted back to the platform.
6. Every decision is logged so the system learns.

The build is organised into **modules** (numbered per the original specs). This repo now contains Modules 1, 2, 4, 6, 7, 8, 9, 10.

---

## 2. Architecture at a glance

- **Backend**: Python **FastAPI** (`app/`), async. LLM via **LangChain** with a provider switch (`LLM_PROVIDER`: `ollama` for local dev, `openai` for production). Embeddings always OpenAI `text-embedding-3-small` (1536-dim).
- **Database / vector store**: **Supabase** (Postgres + pgvector). One project for everything. File storage in a Supabase `documents` bucket.
- **Frontend**: **Next.js 14** (App Router) + **Tailwind**, in `frontend/`. Custom components only (no UI library). Axios API client. Dark theme.
- **Scheduler**: **APScheduler** (AsyncIOScheduler) started in the FastAPI lifespan for the discovery worker.

```
POST /conversations/submit
  → Retrieval (query → pgvector search → LLM rerank → context)
  → Analysis (COMMENT / DO_NOT_COMMENT)
  → Generation (4 drafts in parallel) [skipped if DO_NOT_COMMENT]
  → Approval workflow + feedback logging
  → (new) Post approved reply back to the platform
```

Module 4 sits in front of this, discovering and scoring posts automatically and calling `submit` for the best ones.

---

## 3. What has been built (module by module)

Original specs live in `Prompt.txt` (Modules 1/6/7/9/10), `Prompt2.txt` (Module 8), `Prompt3.txt` (Module 2), `Prompt4.txt` (Module 4).

### Module 1 — Knowledge Base ingestion (`app/services/ingestion.py`, `app/routers/knowledge.py`)
- Upload → parse → clean → chunk (800/150) → embed (batch 50, retry) → store in `document_chunks`.
- Parsers: PDF (PyMuPDF), DOCX (python-docx), **DOC** (LibreOffice or MS Word COM — added this session), HTML (BeautifulSoup), TXT/MD.
- Endpoints: upload, list (+ stats), detail (with chunks), delete, reindex.
- **Multi-file upload** and **content-hash dedup** were added this session (see §5).

### Module 6 — Retrieval / RAG (`app/services/retrieval.py`)
- Query extraction → pgvector `match_documents` (top 10, threshold 0.65, one lowered retry) → LLM rerank → top 5 → context block. Internal service, not an endpoint.

### Module 7 — Analysis + Generation (`app/services/analysis.py`, `generation.py`)
- Analysis returns strict JSON (topic, tensions, viewpoints, recommendation, relevance, etc.). Skips generation on `DO_NOT_COMMENT`.
- Generation runs 4 styles in parallel (`RunnableParallel`): insightful contribution, facilitative question, synthesis of viewpoints, constructive challenge.
- Endpoints: submit, list, detail.

### Module 8 — Dashboard (`frontend/`)
- Pages: `/feed`, `/conversations`, `/conversations/[id]`, `/knowledge`, `/submit`, `/history`, `/discovery`, `/community`, `/settings`.
- Custom toast system, modals, confirm dialogs, optimistic updates, polling, responsive layout.

### Module 9 — Approval + Posting (`app/routers/drafts.py`)
- approve, edit-and-approve, reject, save, mark-posted, feedback-summary.
- **Posting side added this session** (Bluesky + Mastodon): `POST /drafts/{id}/post`, `POST /drafts/{id}/approve-and-post`, `POST /drafts/{id}/unapprove`. See §6.

### Module 10 — Feedback logging (`app/services/feedback.py`)
- Every decision logged to `feedback_log`; summary stats endpoint.

### Module 2 — Platform connections (`app/routers/connections.py`, `app/services/connections/`)
- OAuth + token layer for **Reddit, Bluesky, Mastodon, Discord, Telegram, Threads, YouTube**.
- Fernet-encrypted token storage (`token_store.py`, `token_encryption.py`).
- Unified fetch interface `PlatformFetchService` returning `UniversalPost` — this is what Module 4 consumes.
- Endpoints: status, auth-url, callback, bluesky/telegram connect, validate, refresh, disconnect, logs.
- **Post side** (`post_reply`) implemented for Bluesky + Mastodon this session.

### Module 4 — Discovery + Scoring (`app/services/discovery/`, `app/routers/discovery.py`)
- APScheduler worker: fetch → dedup → AI relevance score (4 weighted criteria) → filter/rank → submit top N/day to Module 7.
- Fault-isolated per platform/post; DB-level daily-limit enforcement; 120s per-batch scoring timeout.
- Dashboard `/discovery` (Overview / Posts / Communities / Run History), sidebar status indicator, feed "Discovered today" chip, discovery settings on `/settings`.
- Seed communities in `supabase/seeds/communities.sql`.

### Not built (out of scope / future)
- **Module 3** (auto community discovery/joining).
- **Module 11** (general settings backend — only discovery settings persist; the Community Manager page and general Settings still use browser localStorage).
- **Module 5** is folded into Module 7 (already built).
- **Module 12** (SaaS/multi-user/etc).
- Posting for the other 5 platforms (only Bluesky + Mastodon implemented).

---

## 4. The journey (zero → here)

1. **Started with the frontend already scaffolded** (`Prompt2.txt`). Audited it: complete, builds clean.
2. **Ran the stack** and discovered the backend had **no CORS** → added `CORSMiddleware`.
3. Fixed a **frontend crash** on `/conversations`: the list endpoint didn't return `original_post`/`central_topic`; added them backend-side and hardened the frontend.
4. Added **multi-file upload** to the knowledge base.
5. Added **`.doc` support** (legacy Word) via LibreOffice/Word-COM, plus `pywin32`.
6. Added **content-hash deduplication** for uploads (no DB migration — hash embedded in the storage path).
7. Provided a **SQL cleanup query** for existing duplicate documents.
8. Audited backend against `Prompt.txt` — everything present; created the missing `.env.example`.
9. **Built Module 2** (`Prompt3.txt`): all 7 connectors, encrypted token store, OAuth router, factory/fetch service, frontend Connections UI. Installed platform libs.
10. **Connected Bluesky** (app password) and **Mastodon** (OAuth) live and verified real fetches. **Telegram is blocked on this network** (DPI) — code is fine, needs a VPN.
11. **Built Module 4** (`Prompt4.txt`): scheduler, worker, scorer, deduplicator, submitter, router, and full discovery frontend.
12. Ran discovery live. Hit **local-LLM issues** and fixed three robustness problems (see §5): oversized batches saturating Ollama, invalid JSON from llama3.2, incomplete analysis objects.
13. Proved the **full automated loop** live: discovered a Bluesky post → scored 80% → submitted → analysed → **4 drafts generated**.
14. **Built the posting side** (Module 9 write-half) for Bluesky + Mastodon with separate Approve / Approve & Post / Post Now / Remove Approval actions.

---

## 5. Robustness fixes made this session (important context)

These matter because the app is running on a **small local model (Ollama llama3.2)** which is slow and imperfect at JSON:

- **json-repair fallback** in `extract_json` (`app/services/retrieval.py`) — repairs unescaped quotes/trailing commas/missing braces. Benefits analysis, scoring, and rerank.
- **Tolerant analysis** (`_coerce_analysis` in `app/services/analysis.py`) — fills safe defaults for fields the model omits, so a mostly-complete analysis proceeds instead of failing validation.
- **Scoring batch timeout** (120s) in `app/services/discovery/scorer.py` — a slow/hung model can never stall the worker.
- **Discovery tuning**: `max_posts_per_run` set to **8** (was 50). 50 × 2 platforms = 100 posts saturated the single local model for 15+ min. Keep this low on local Ollama; for production use `LLM_PROVIDER=openai`.

---

## 6. Posting feature (read before using)

Bluesky/Mastodon draft cards now show:
- **Approve** — records approval only (no publish).
- **Approve & Post** — approves **and publishes** a public reply to the real post.
- **Post Now** — publishes an already-approved draft.
- **Remove Approval** — reverts an approved/edited/saved/rejected draft back to pending.

> ⚠️ **Approve & Post / Post Now publish a real, public comment using the connected account, and it is irreversible from here (you'd delete it manually on the platform).** Test against **your own** post first (make a throwaway post on your Bluesky/Mastodon, submit its URL via `/submit`, then Approve & Post so the reply lands on your own post).

Only Bluesky and Mastodon are wired for posting. The other platforms return a clear "not supported yet" error.

---

## 7. Current running / connected state (as of this session)

- **Backend**: `uvicorn app.main:app` on `http://localhost:8000`.
- **Frontend**: `next start -p 3000` on `http://localhost:3000` (production build).
- **LLM**: `LLM_PROVIDER=ollama`, model `llama3.2` via local Ollama (`http://localhost:11434`). Embeddings via OpenAI.
- **Supabase**: base schema + migrations **002** (connections) + **003** (discovery) applied; `documents` storage bucket exists; discovery seed communities loaded (12).
- **Connected platforms**: **Bluesky** and **Mastodon** (live, verified). Telegram token set but network-blocked here. Reddit/Discord/Threads/YouTube: code ready, not connected.
- **Discovery**: enabled, 30-min interval, `max_posts_per_run=8`, daily cap 5.

Whoever receives this will need their **own** Supabase project, API keys, and platform accounts — the connected accounts above are specific to the original author.

---

## 8. Getting Started From a Zip

### Prerequisites
- Node.js 18+, Python 3.11+ (developed on 3.13), an Ollama install (or an OpenAI key), a Supabase project.

### Backend
```bash
# from project root
python -m venv .venv && . .venv/Scripts/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env         # then fill in every value (see below)
```

Supabase setup (SQL editor):
1. `CREATE EXTENSION IF NOT EXISTS vector;`
2. Run `supabase/schema.sql` (base tables + `match_documents` RPC).
3. Run `supabase/migrations/002_platform_connections.sql`.
4. Run `supabase/migrations/003_discovery.sql`.
5. (optional) Run `supabase/seeds/communities.sql`.
6. Create a **private Storage bucket named `documents`**.

Generate a token encryption key and put it in `.env` as `TOKEN_ENCRYPTION_KEY`:
```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Local LLM:
```bash
ollama pull llama3.2      # or set LLM_PROVIDER=openai and OPENAI_MODEL=gpt-4o
```

Run:
```bash
uvicorn app.main:app --reload      # http://localhost:8000  (docs at /docs)
```

### Frontend
```bash
cd frontend
npm install
cp .env.local.example .env.local   # set NEXT_PUBLIC_API_URL=http://localhost:8000
npm run dev                         # http://localhost:3000
```

### Connect a platform (easiest: Bluesky)
1. Create a Bluesky app password (bsky.app → Settings → App Passwords).
2. Dashboard → `/settings#connections` → Bluesky → Connect → enter handle + app password.
See `README.md` → *Platform Setup Guide* for every platform's developer-app steps.

---

## 9. Environment variables

All variables are documented in `.env.example` (backend) and `frontend/.env.local.example`. Key groups:
- Supabase URL + anon + service-role keys.
- `OPENAI_API_KEY` (required — embeddings always use OpenAI), `LLM_PROVIDER`, Ollama settings.
- Ingestion/retrieval/generation tuning (chunk size, top-k, thresholds, draft word limits).
- **Module 2**: `TOKEN_ENCRYPTION_KEY`, `APP_BASE_URL`, `FRONTEND_URL`, and per-platform client IDs/secrets/redirect URIs.
- **Module 4**: discovery fallbacks (the `discovery_settings` DB row is authoritative).

---

## 10. Known issues / gaps

- **Local model is slow and inconsistent.** Keep `max_posts_per_run` small on Ollama; expect occasional `DO_NOT_COMMENT` variance. `LLM_PROVIDER=openai` is far more reliable.
- **Telegram Bot API blocked on some networks** (DPI). Needs a VPN; not a code issue.
- **`GET /knowledge/documents/stats`** returns 500 (unused/dead endpoint — the frontend gets stats from `/knowledge/documents`). Harmless; can be removed or fixed.
- **Posting** only implemented for Bluesky + Mastodon.
- **Community Manager page and general Settings** are localStorage-only (Module 11 not built). Discovery settings DO persist server-side.
- The 5 unconnected platforms' connectors are written but **untested against live APIs**.

---

## 11. Suggested next steps

1. Posting for **Reddit** (PRAW `submission.reply`) and the other platforms.
2. **Module 11**: real settings/community backend to replace localStorage.
3. **Module 3**: automatic community discovery.
4. Move to **OpenAI** for production-quality analysis/scoring and speed.
5. Optional: partial-progress reporting in the discovery worker (currently `posts_scored` only updates after the whole batch).

---

## 12. ⚠️ Security note before sharing this project

A zip of this repo **includes the `.env` file with live secrets** — Supabase service-role key, OpenAI key, the Bluesky app password, Mastodon client secret, and the Telegram bot token. Before sending it to anyone:

- **Delete or scrub `.env`** (keep only `.env.example`), OR
- **Rotate/revoke** those credentials (Bluesky app password, Telegram `/revoke` via BotFather, regenerate Supabase/OpenAI keys, delete the Mastodon app).

Never commit `.env` to a public repo. The receiver should create their own Supabase project and their own platform credentials.

---

## 13. Continuity

This handoff document plus the code **is** the continuity — it captures what was built, why, the current state, and where to go next. Read it top to bottom, then follow [Getting Started From a Zip](#getting-started-from-a-zip) to run the project locally.
