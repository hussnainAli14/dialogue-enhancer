"""Environment variable loading and LLM provider selection."""

import os
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()


class Settings:
    SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
    SUPABASE_ANON_KEY: str = os.getenv("SUPABASE_ANON_KEY", "")
    SUPABASE_SERVICE_ROLE_KEY: str = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")

    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "ollama").lower()
    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "llama3")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o")

    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
    EMBEDDING_DIMENSIONS: int = int(os.getenv("EMBEDDING_DIMENSIONS", "1536"))

    CHUNK_SIZE: int = int(os.getenv("CHUNK_SIZE", "800"))
    CHUNK_OVERLAP: int = int(os.getenv("CHUNK_OVERLAP", "150"))

    RETRIEVAL_TOP_K: int = int(os.getenv("RETRIEVAL_TOP_K", "10"))
    RETRIEVAL_RERANK_TOP_K: int = int(os.getenv("RETRIEVAL_RERANK_TOP_K", "5"))
    SIMILARITY_THRESHOLD: float = float(os.getenv("SIMILARITY_THRESHOLD", "0.65"))

    MAX_DRAFT_WORDS: int = int(os.getenv("MAX_DRAFT_WORDS", "200"))
    MIN_DRAFT_WORDS: int = int(os.getenv("MIN_DRAFT_WORDS", "80"))

    STORAGE_BUCKET: str = "documents"

    # ── Module 2 — platform connections ──────────────────
    TOKEN_ENCRYPTION_KEY: str = os.getenv("TOKEN_ENCRYPTION_KEY", "")
    APP_BASE_URL: str = os.getenv("APP_BASE_URL", "http://localhost:8000")
    FRONTEND_URL: str = os.getenv("FRONTEND_URL", "http://localhost:3000")
    CORS_ALLOW_ORIGINS: str = os.getenv("CORS_ALLOW_ORIGINS", "")

    REDDIT_CLIENT_ID: str = os.getenv("REDDIT_CLIENT_ID", "")
    REDDIT_CLIENT_SECRET: str = os.getenv("REDDIT_CLIENT_SECRET", "")
    REDDIT_REDIRECT_URI: str = os.getenv("REDDIT_REDIRECT_URI", "")
    REDDIT_USER_AGENT: str = os.getenv("REDDIT_USER_AGENT", "AI Dialogue Enhancer/1.0")

    BLUESKY_HANDLE: str = os.getenv("BLUESKY_HANDLE", "")
    BLUESKY_APP_PASSWORD: str = os.getenv("BLUESKY_APP_PASSWORD", "")

    MASTODON_CLIENT_ID: str = os.getenv("MASTODON_CLIENT_ID", "")
    MASTODON_CLIENT_SECRET: str = os.getenv("MASTODON_CLIENT_SECRET", "")
    MASTODON_REDIRECT_URI: str = os.getenv("MASTODON_REDIRECT_URI", "")
    MASTODON_INSTANCE_URL: str = os.getenv("MASTODON_INSTANCE_URL", "https://mastodon.social")

    DISCORD_CLIENT_ID: str = os.getenv("DISCORD_CLIENT_ID", "")
    DISCORD_CLIENT_SECRET: str = os.getenv("DISCORD_CLIENT_SECRET", "")
    DISCORD_BOT_TOKEN: str = os.getenv("DISCORD_BOT_TOKEN", "")
    DISCORD_REDIRECT_URI: str = os.getenv("DISCORD_REDIRECT_URI", "")

    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_BOT_USERNAME: str = os.getenv("TELEGRAM_BOT_USERNAME", "")

    THREADS_APP_ID: str = os.getenv("THREADS_APP_ID", "")
    THREADS_APP_SECRET: str = os.getenv("THREADS_APP_SECRET", "")
    THREADS_REDIRECT_URI: str = os.getenv("THREADS_REDIRECT_URI", "")

    YOUTUBE_CLIENT_ID: str = os.getenv("YOUTUBE_CLIENT_ID", "")
    YOUTUBE_CLIENT_SECRET: str = os.getenv("YOUTUBE_CLIENT_SECRET", "")
    YOUTUBE_REDIRECT_URI: str = os.getenv("YOUTUBE_REDIRECT_URI", "")

    # ── Module 4 — discovery (fallbacks; DB discovery_settings wins) ──
    DISCOVERY_ENABLED: bool = os.getenv("DISCOVERY_ENABLED", "true").lower() == "true"
    DISCOVERY_SCHEDULE_MINUTES: int = int(os.getenv("DISCOVERY_SCHEDULE_MINUTES", "30"))
    MAX_POSTS_PER_RUN: int = int(os.getenv("MAX_POSTS_PER_RUN", "50"))
    MAX_CONVERSATIONS_PER_DAY: int = int(os.getenv("MAX_CONVERSATIONS_PER_DAY", "5"))
    MIN_RELEVANCE_SCORE: float = float(os.getenv("MIN_RELEVANCE_SCORE", "0.65"))


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()


def get_llm(temperature: float = 0.7):
    """Return the active chat model based on LLM_PROVIDER.

    Swapping providers is a single env var change — callers never
    know which provider is active.
    """
    if settings.LLM_PROVIDER == "openai":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=settings.OPENAI_MODEL,
            temperature=temperature,
            api_key=settings.OPENAI_API_KEY,
        )

    from langchain_ollama import ChatOllama

    return ChatOllama(
        model=settings.OLLAMA_MODEL,
        temperature=temperature,
        base_url=settings.OLLAMA_BASE_URL,
    )


def get_embeddings():
    """Embeddings are always OpenAI text-embedding-3-small, in dev and prod."""
    from langchain_openai import OpenAIEmbeddings

    return OpenAIEmbeddings(
        model=settings.EMBEDDING_MODEL,
        dimensions=settings.EMBEDDING_DIMENSIONS,
        api_key=settings.OPENAI_API_KEY,
    )
