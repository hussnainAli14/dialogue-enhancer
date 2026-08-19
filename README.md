# AI Dialogue Enhancer — Backend

FastAPI backend for an AI-powered dialogue enhancement system. It ingests an author's writing archive into a vector knowledge base, analyses submitted social media conversations, generates response drafts grounded in the author's own writing, and manages the human approval workflow. Nothing is ever posted without the author's explicit approval.

## Architecture

```
POST /conversations/submit
        ↓
Retrieval  — extract query → vector search (pgvector) → LLM rerank → context block
        ↓
Analysis   — dialogue facilitator analysis → COMMENT or DO_NOT_COMMENT
        ↓
Generation — 4 drafts in parallel (insight / question / synthesis / challenge)
        ↓
Approval   — approve / edit / reject / save / mark-posted + feedback logging
```

## Setup

### 1. Create a Supabase project

Go to [supabase.com](https://supabase.com), create a new project, and note your project URL, anon key, and service role key (Project Settings → API).

### 2. Enable pgvector

In the Supabase SQL editor, run:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

### 3. Run the schema

Copy the full contents of `supabase/schema.sql` into the SQL editor and run it. This creates all tables, the vector index, and the `match_documents` RPC function.

Also create a **Storage bucket named `documents`** (Storage → New bucket, private).

### 4. Configure environment variables

```bash
cp .env.example .env
```

Fill in every value. `OPENAI_API_KEY` is required even in development — embeddings always use OpenAI `text-embedding-3-small`.

### 5. Install Ollama (development LLM)

Download from [ollama.ai](https://ollama.ai) and install.

### 6. Pull the model

```bash
ollama pull llama3
```

### 7. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 8. Run the server

```bash
uvicorn app.main:app --reload
```

API docs available at http://localhost:8000/docs

### 9. Test document upload

```bash
curl -X POST http://localhost:8000/knowledge/upload \
  -F "file=@sample.pdf" \
  -F "title=Sample Essay" \
  -F "source_type=article"
```

Then check processing status:

```bash
curl http://localhost:8000/knowledge/documents
```

Status moves from `processing` to `ready` once chunking and embedding complete.

### 10. Test conversation submission

```bash
curl -X POST http://localhost:8000/conversations/submit \
  -H "Content-Type: application/json" \
  -d '{
    "platform": "reddit",
    "post_url": "https://reddit.com/r/leadership/example",
    "post_author": "some_user",
    "original_post": "How do you handle a team member who resists all feedback?",
    "full_thread": null
  }'
```

Then fetch the result (analysis + drafts):

```bash
curl http://localhost:8000/conversations/{conversation_id}
```

### 11. Switch from Ollama to OpenAI (production)

In `.env`, change:

```
LLM_PROVIDER=ollama
```

to:

```
LLM_PROVIDER=openai
```

Nothing else changes. No code changes are required.

## API Overview

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/knowledge/upload` | Upload a document (pdf/docx/html/txt/md) |
| GET | `/knowledge/documents` | List all documents with stats |
| GET | `/knowledge/documents/{id}` | Document details with chunks |
| DELETE | `/knowledge/documents/{id}` | Delete document and file |
| POST | `/knowledge/documents/{id}/reindex` | Re-chunk and re-embed |
| POST | `/conversations/submit` | Submit a conversation for the pipeline |
| GET | `/conversations` | Paginated conversation list |
| GET | `/conversations/{id}` | Conversation with analysis and drafts |
| POST | `/drafts/{id}/approve` | Approve a draft |
| POST | `/drafts/{id}/edit-and-approve` | Approve with edits |
| POST | `/drafts/{id}/reject` | Reject with optional reason |
| POST | `/drafts/{id}/save` | Save for later |
| POST | `/drafts/{id}/mark-posted` | Mark as posted |
| GET | `/drafts/feedback-summary` | Aggregated feedback stats |
| GET | `/connections/status` | Connection status of all 7 platforms |
| GET | `/connections/{platform}/auth-url` | OAuth authorisation URL |
| GET | `/connections/{platform}/callback` | OAuth callback (redirects to dashboard) |
| POST | `/connections/bluesky/connect` | Connect Bluesky (handle + app password) |
| POST | `/connections/telegram/connect` | Connect Telegram (validates bot token) |
| POST | `/connections/{platform}/validate` | Test a connection |
| POST | `/connections/{platform}/refresh` | Manually refresh tokens |
| DELETE | `/connections/{platform}` | Disconnect a platform |
| GET | `/connections/logs` | Recent connection events |

All responses use the envelope:

```json
{
  "success": true,
  "data": {},
  "error": null,
  "timestamp": "2026-01-01T00:00:00Z"
}
```

## Module 2 — Platform Connections

Module 2 connects the author's social accounts (Reddit, Bluesky, Mastodon, Discord, Telegram, Threads, YouTube) so the system can fetch posts and post approved responses. Tokens are stored **Fernet-encrypted** in `platform_connections`; they are never logged, returned in responses, or written as plain text.

### Migration

Run `supabase/migrations/002_platform_connections.sql` in the Supabase SQL editor (creates `platform_connections` and `platform_connection_logs`).

### Encryption key

Generate a Fernet key and set `TOKEN_ENCRYPTION_KEY` in `.env`:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Also set `APP_BASE_URL` (backend, e.g. `http://localhost:8000`) and `FRONTEND_URL` (dashboard, e.g. `http://localhost:3000`).

### Platform Setup Guide

Create a developer app on each platform and fill the matching `.env` values. Every OAuth redirect URI must exactly match the value in `.env`.

**Reddit**
1. Go to reddit.com/prefs/apps → Create App
2. Select **script** type
3. Redirect URI: `APP_BASE_URL/connections/reddit/callback`
4. Copy client ID and client secret → `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`

**Bluesky**
1. Go to bsky.app/settings/app-passwords → Add App Password
2. Name it "AI Dialogue Enhancer", copy the generated password → `BLUESKY_APP_PASSWORD`
3. Set `BLUESKY_HANDLE` to your full handle (e.g. `yourname.bsky.social`)
4. Bluesky has no redirect flow — connect from the dashboard with handle + app password.

**Mastodon**
1. Instance preferences → Development → New Application
2. Redirect URI: `APP_BASE_URL/connections/mastodon/callback`, scopes: `read`
3. Copy client key/secret → `MASTODON_CLIENT_ID`, `MASTODON_CLIENT_SECRET`
4. Set `MASTODON_INSTANCE_URL` (e.g. `https://mastodon.social`)

**Discord**
1. discord.com/developers/applications → New Application
2. Bot section → create bot → copy token → `DISCORD_BOT_TOKEN` (enable the **Message Content** intent)
3. OAuth2 section → copy client ID/secret; redirect URI: `APP_BASE_URL/connections/discord/callback`
4. Add the bot to each server you want to monitor via the invite link shown when connecting.

**Telegram**
1. Message @BotFather → `/newbot` → copy token → `TELEGRAM_BOT_TOKEN`, set `TELEGRAM_BOT_USERNAME`
2. Add the bot as an admin to each channel/group you want to monitor.

**Threads**
1. developers.facebook.com → create app → add the Threads product
2. Redirect URI: `APP_BASE_URL/connections/threads/callback`
3. Copy app ID/secret → `THREADS_APP_ID`, `THREADS_APP_SECRET`

**YouTube**
1. console.cloud.google.com → new project → enable **YouTube Data API v3**
2. Credentials → create OAuth 2.0 client; redirect URI: `APP_BASE_URL/connections/youtube/callback`
3. Copy client ID/secret → `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET`
4. Daily quota is 10,000 units — the connector stops fetching before exhausting it.

### Unified fetch interface (for Module 4)

```python
from datetime import datetime, timedelta, timezone
from app.services.connections.factory import PlatformFetchService

svc = PlatformFetchService()
posts = await svc.fetch_from_all_platforms(
    keywords=["leadership", "coaching"],
    communities={"reddit": ["r/leadership"], "bluesky": ["leadership"]},
    since=datetime.now(timezone.utc) - timedelta(days=1),
    limit_per_platform=20,
)
```

Returns a combined, `posted_at`-desc list of `UniversalPost` objects regardless of source platform.

## Module 4 — Post Discovery & Scoring

Module 4 is the background engine that feeds the whole system. On a schedule it fetches posts from connected platforms, scores them for relevance with the active LLM, filters the best, and submits the top few into the Module 7 pipeline automatically.

### 1. How it works end to end

```
APScheduler (every N min)
   → fetch_from_all_platforms()   (Module 2)
   → deduplicate (platform, post_id)
   → AI relevance score (0–1, four weighted criteria)
   → filter >= min_relevance_score, rank, take remaining daily quota
   → submit top posts to the Module 7 pipeline
   → drafts appear in the Feed for review
```

The scheduler starts automatically with the FastAPI app (lifespan) and runs inside the event loop — no separate worker process.

### 2. Migration + seed

Run in the Supabase SQL editor after migration 002:
- `supabase/migrations/003_discovery.sql` — creates `monitored_communities`, `discovered_posts`, `discovery_runs`, `discovery_settings` (+ a default settings row).
- `supabase/seeds/communities.sql` — optional starter communities (Reddit/Bluesky/Mastodon/YouTube).

### 3. Add communities to monitor

Either use the dashboard (**Discovery → Communities → Add Community**) or insert rows directly into `monitored_communities`. `community_id` format per platform: Reddit = subreddit name, Bluesky/Mastodon = keyword/hashtag, Discord = channel ID, Telegram = channel username, YouTube = search keyword. A community's platform must be connected (Module 2) before it is monitored.

### 4. Trigger a manual run

Dashboard: **Discovery → Overview → Run Discovery Now**, or the refresh icon on the Feed's "Discovered today" chip. API: `POST /discovery/trigger` (returns a `run_id`; runs in the background).

### 5. Pause and resume

Master switch: **Discovery → Overview** toggle, or **Settings → Discovery Settings → Discovery Enabled**, or `POST /discovery/settings {"is_enabled": false}`. When paused, the scheduled job still fires but skips work — no server restart needed.

### 6. Tune the relevance threshold

`min_relevance_score` (0–1) in Discovery Settings. Posts below it are still fetched and stored (status `filtered_out`) but not submitted. Raise it to be more selective, lower it to surface more.

### 7. Daily conversation limit

`max_conversations_per_day` caps how many conversations are submitted to Module 7 per UTC day, regardless of how many score well. The limit is enforced with a live DB count at the start of each run and again before every submission. Well-scoring posts beyond the cap are marked `filtered_out` and can be promoted later via **Submit Anyway**.

### 8. Monitoring

- **Discovery → Overview**: scheduler state, next run, today's submitted/limit, last 5 runs.
- **Discovery → Posts**: every fetched post with its relevance score, four-criteria reasoning, and status.
- **Discovery → Run History**: full audit of every run (fetched/scored/submitted/filtered/duplicates/duration).

### 9. Troubleshooting — no posts discovered

- No **connected platforms** (Module 2) → connect at least one in Settings.
- No **active communities** for a connected platform → add some.
- `min_relevance_score` too high → lower it.
- A platform's API is **network-blocked** (e.g. Telegram on some ISPs) → check `platform_connection_logs` / run history error messages.
- Nothing new since `last_fetched_at` → the worker only fetches posts newer than the last fetch (24h window on first run).

### 10. Troubleshooting — scheduler stopped

The sidebar shows **Scheduler Stopped** (red) if the scheduler isn't running. It starts on app startup — check server logs for a lifespan error, confirm `discovery_settings` exists (migration 003), then restart the backend. Changing the interval in Settings reschedules the job live without a restart.

### Discovery API

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/discovery/status` | Scheduler + today's counts + last run |
| POST | `/discovery/trigger` | Run discovery now (background) |
| GET | `/discovery/runs` | Paginated run history |
| GET | `/discovery/runs/{id}` | One run + its posts |
| GET | `/discovery/posts` | Discovered posts (filters: platform/status/min score/date) |
| GET | `/discovery/posts/{id}` | One discovered post |
| POST | `/discovery/posts/{id}/submit` | Promote a post to Module 7 |
| GET/POST | `/discovery/communities` | List / add monitored communities |
| PATCH/DELETE | `/discovery/communities/{id}` | Update / remove a community |
| GET/POST | `/discovery/settings` | Read / update discovery settings |
