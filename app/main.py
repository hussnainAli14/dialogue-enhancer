"""AI Dialogue Enhancer — FastAPI backend entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from app.envelope import fail, ok
from app.routers import connections, conversations, discovery, drafts, knowledge


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start the Module 4 discovery scheduler inside the event loop.
    from app.services.discovery.scheduler import start_scheduler, stop_scheduler

    try:
        start_scheduler()
    except Exception:
        # Discovery is optional — never block server startup on it.
        pass
    yield
    try:
        stop_scheduler()
    except Exception:
        pass


app = FastAPI(
    title="AI Dialogue Enhancer API",
    description="Backend for knowledge base ingestion, retrieval-grounded "
    "response generation, and the approval workflow.",
    version="1.0.0",
    lifespan=lifespan,
)

# Allow local dev plus the deployed frontend (FRONTEND_URL) and any extra
# comma-separated origins in CORS_ALLOW_ORIGINS.
from app.config import settings as _settings  # noqa: E402

_origins = {"http://localhost:3000", "http://127.0.0.1:3000"}
if _settings.FRONTEND_URL:
    _origins.add(_settings.FRONTEND_URL.rstrip("/"))
for _o in _settings.CORS_ALLOW_ORIGINS.split(","):
    if _o.strip():
        _origins.add(_o.strip().rstrip("/"))

app.add_middleware(
    CORSMiddleware,
    allow_origins=sorted(_origins),
    allow_origin_regex=r"https://.*\.vercel\.app",  # Vercel preview deploys
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(knowledge.router)
app.include_router(conversations.router)
app.include_router(drafts.router)
app.include_router(connections.router)
app.include_router(discovery.router)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return fail(f"Validation error: {exc.errors()}", 422)


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    return fail("Internal server error", 500)


@app.get("/")
async def health():
    return ok({"service": "AI Dialogue Enhancer API", "status": "running"})
