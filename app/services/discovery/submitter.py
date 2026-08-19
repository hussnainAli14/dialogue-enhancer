"""Submits a discovered post into the Module 7 pipeline (no internal HTTP)."""

from __future__ import annotations

import asyncio

from app.database import get_supabase, log_task
from app.services.analysis import run_pipeline
from app.services.connections.base import UniversalPost


class Submitter:
    def __init__(self):
        self.supabase = get_supabase()

    async def submit(self, post: UniversalPost) -> str:
        """Insert a conversation from a post and kick off the RAG pipeline.
        Returns the new conversation_id. Re-raises on failure."""
        try:
            record = (
                self.supabase.table("conversations")
                .insert(
                    {
                        "platform": post.platform,
                        "post_url": post.post_url,
                        "post_author": post.author_name,
                        "original_post": post.content,
                        "full_thread": post.thread_content,
                        "analysis_status": "pending",
                    }
                )
                .execute()
            ).data[0]
            conversation_id = record["id"]
            log_task("analysis", conversation_id, "started", f"Discovery submit from {post.platform}")
            # Run the Module 7 pipeline in the background on the event loop.
            asyncio.create_task(run_pipeline(conversation_id))
            return conversation_id
        except Exception as exc:
            log_task("analysis", None, "failed", f"Discovery submit failed: {exc}")
            raise
