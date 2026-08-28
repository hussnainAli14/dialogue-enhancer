# AI Dialogue Enhancer — Session Handoff

This document is a complete handoff for the project. It explains what the system is, everything that has been built so far, the journey we took to get here, the current running state, and exactly how to pick it up and continue — whether that's future-me or a different developer receiving this project as a zip.

> **Read this first if you just received a zip of this project.** Jump to [Getting Started From a Zip](#getting-started-from-a-zip).

---

## 0. Current status (most recent first)

- **DEPLOYED & LIVE in production:**
  - Backend (FastAPI) → **Render**: `https://dialogue-enhancer.onrender.com`
  - Frontend (Next.js) → **Vercel**: `https://dialogue-enhancer.vercel.app`
  - DB/storage → **Supabase** (same project throughout). Production runs `LLM_PROVIDER=openai`.
  - GitHub: `hussnainAli14/dialogue-enhancer` (frontend lives in `frontend/`). Pushed via an SSH alias `github-dlasser`.
- **Git branches:**
  - `main` = what deploys (Render + Vercel auto-deploy from it). Contains Modules 1,2,4,6,7,8,9,10 + posting for Bluesky/Mastodon/Reddit/Discord + all fixes below. Latest deployed commit: `18af134`.
  - `module-3-community-discovery` = **Module 3 (Community Discovery)**, pushed but **intentionally not merged/deployed**. Pull this branch to run Module 3 locally. Commit `8e75914`.
- **Connected platforms (production, in Supabase):** Bluesky + Mastodon (live, verified) and Discord (bot created + code ready). Reddit code is done but **blocked by Reddit's app-approval policy** (a Data API access request form was submitted — awaiting approval). Telegram token set but network-blocked on some local networks.
- **Posting works** for **Bluesky, Mastodon, Reddit, Discord** (Approve & Post / Post Now / Remove Approval). Threads/YouTube not wired for posting.
- **Deferred to the end:** Dockerise the Render backend with LibreOffice so `.doc` uploads work in production (currently `.doc` is cleanly rejected on Render; works locally where MS Word/LibreOffice exist).
- **Working rule:** do **not** `git push`/deploy without explicit approval.
- **Latest working session (24 Aug 2026, local, on `module-3-community-discovery`):** fresh environment set up from scratch, whole stack verified end-to-end, three real bugs fixed, a **Saved for Later** feature added, and a round of UI work. Nothing committed or pushed. See [§14](#14-session-24-aug-2026--environment-fixes-and-new-work) and [§15](#15-session-24-aug-2026--ui-changes).

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

The build is organised into **modules** (numbered per the original specs). `main` contains Modules 1, 2, 4, 6, 7, 8, 9, 10; **Module 3** lives on the `module-3-community-discovery` branch.

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

Original specs live in `Prompt.txt` (Modules 1/6/7/9/10), `Prompt2.txt` (Module 8), `Prompt3.txt` (Module 2), `Prompt4.txt` (Module 4), `Prompt5.txt` (Module 3).

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
- **Post side** (`post_reply` + `post_exists`) implemented for **Bluesky, Mastodon, Reddit, Discord** (`app/services/posting.py`). Endpoints: `POST /drafts/{id}/post`, `/approve-and-post`, `/unapprove`. Per-platform char limits enforced (Bluesky 300, Mastodon 500, Reddit 10000, Discord 2000).
- Also added: source-liveness check (`GET /conversations/{id}/source-status`), delete-conversation, and bulk `POST /conversations/cleanup-deleted` (remove conversations whose source post was deleted).

### Module 4 — Discovery + Scoring (`app/services/discovery/`, `app/routers/discovery.py`)
- APScheduler worker: fetch → dedup → AI relevance score (4 weighted criteria) → filter/rank → submit top N/day to Module 7.
- Fault-isolated per platform/post; DB-level daily-limit enforcement; 120s per-batch scoring timeout.
- Dashboard `/discovery` (Overview / Posts / Communities / Run History), sidebar status indicator, feed "Discovered today" chip, discovery settings on `/settings`.
- Seed communities in `supabase/seeds/communities.sql`.

### Module 3 — Community Discovery (`app/services/community/`, `app/routers/community_discovery.py`) — **on the `module-3-community-discovery` branch, not on `main`/production**
- Adds `search_communities` + `get_person_communities` to all 7 connectors (Reddit/Bluesky/Mastodon/YouTube real; Discord/Telegram/Threads best-effort).
- Services: `community_scorer` (4-criteria weighted + suggested keywords), `keyword_searcher`, `people_tracker`, `discovery_worker` (7-step), `community_scheduler` (24h job added to the existing scheduler).
- Router: 15 endpoints (topics, people, discover, runs, suggestions + approve/reject/bulk, monitored). Extends `/discovery/settings` with community fields.
- Migration `supabase/migrations/004_community_discovery.sql` (**already run on Supabase**) — new tables + `discovery_settings` ALTERs + seed topics.
- Frontend: `/community` rebuilt into 5 tabs (Suggestions / Active Communities / Topics / People / Discovery History), Community Discovery Settings on `/settings`, sidebar pending badge. Replaces the old localStorage page.
- **Verified working** end-to-end on OpenAI (found 27 communities → 22 queued suggestions). On local llama3.2 the community scoring times out → 0 suggestions (use OpenAI).

### Not built (out of scope / future)
- **Module 11** (general settings backend — only discovery settings persist; general Settings still uses browser localStorage). Note: Module 3 already replaced the Community Manager localStorage page with a real backend.
- **Module 5** is folded into Module 7 (already built).
- **Module 12** (SaaS/multi-user/etc).
- Posting for **Threads/YouTube** (Bluesky/Mastodon/Reddit/Discord done).

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
15. Made scoring **granular** (analysis relevance = weighted average of 4 sub-dimensions, 2 decimals) after seeing every feed card show a flat 80%.
16. Added **source-liveness checks** + **bulk cleanup** of conversations whose source post was deleted.
17. **Deployed to production**: GitHub repo (SSH alias for a second account), Render (backend, env-driven CORS, `LLM_PROVIDER=openai`), Vercel (frontend). Verified end-to-end + CORS.
18. Added Bluesky/Mastodon **character-limit** enforcement + platform-aware short-draft generation (Bluesky 300 was rejecting drafts).
19. Fixed the dead `/knowledge/documents/stats` 500 (route ordering) and made `.doc` cleanly reject on hosts without a converter. Deferred true `.doc` support to a Docker/LibreOffice step at the end.
20. Added **Reddit posting** (blocked live by Reddit's app-approval policy — request form submitted) and **Discord posting** (bot created, connected).
21. **Built Module 3** (`Prompt5.txt`, Community Discovery) — verified live on OpenAI — and pushed it to the **`module-3-community-discovery` branch** (deliberately not merged to `main`, so it doesn't deploy; others pull the branch to run locally).

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

---

## 14. Session (24 Aug 2026) — environment, fixes and new work

Everything below was done locally on the `module-3-community-discovery` branch. **Nothing was committed or pushed.**

### 14.1 Getting it running on a clean machine

- Backend venv created with **Python 3.14** (`.venv/`) — the only Python available besides system 3.9. All of `requirements.txt` installed and imported fine, but see the version-drift warning below.
- Frontend `npm install` clean. Created `frontend/.env.local` with `NEXT_PUBLIC_API_URL=http://localhost:8000` (it did not exist; only the `.example` was in the repo).
- Run with `.venv/bin/uvicorn app.main:app --reload --port 8000` and `npm run dev` in `frontend/`.

> ⚠️ **Dependency drift — worth pinning.** `requirements.txt` uses `>=` with no upper bounds. A fresh install now resolves **langchain 1.3.16 / langchain-core 1.6.0** (the code was written against 0.1.x) and **PRAW 8.0.3**. Nothing observed broke at runtime, but PRAW 8 did break Reddit OAuth (see 14.3). Render will drift the same way on its next rebuild.

### 14.2 Full stack verification (all passed)

- All read endpoints 200; CORS preflight from `:3000` OK.
- Live DB at the time: 92 documents / 539 chunks, 110 conversations, 296 drafts, 5 topics, 17 monitored communities, 22 community suggestions.
- Both schedulers running (Module 4 discovery + Module 3 community job).
- **Full pipeline end-to-end**: submitted a conversation → `analysed`, relevance 0.67 → **4 drafts generated**.
- **Module 3 end-to-end**: manual mastodon run, 121s, 27 communities found, 17 new suggestions (0.75–0.78). Dedup correct.
- **Ingestion**: uploaded a test doc → 3 chunks → `ready` → deleted cleanly.
- **Connections**: Mastodon and Discord validate live. **Bluesky is broken** — `ExpiredToken: Token has been revoked`. The app password in `API keys for AI deepner.pdf` was also tried and is dead (`401 Invalid identifier or password`). Needs a **new** app password from bsky.app.

### 14.3 Bugs found and fixed

1. **Reddit OAuth 500** — `Auth.url() takes 1 positional argument but 4 were given`. PRAW 8 made `auth.url` keyword-only. Fixed at `app/services/connections/reddit.py:54` → `auth.url(scopes=SCOPES, state=state, duration="permanent")` (works on 7.x too).

2. **`feedback_log` blocked every conversation delete** — *pre-existing schema defect*. `feedback_log.conversation_id` and `.draft_id` are the only FKs to `conversations` / `response_drafts` **without an `ON DELETE` rule** (`supabase/schema.sql:125-126`); every other reference cascades or sets null. So any conversation you had ever approved/rejected/saved a draft on could not be deleted:
   ```
   violates foreign key constraint "feedback_log_conversation_id_fkey"
   ```
   This is what made **Clean up deleted** fail on confirmation. Fixed with `detach_feedback_log()` in `app/database.py`, called before both the bulk delete (`apply_scan`) and `DELETE /conversations/{id}` (which had the same latent bug). It **nulls** the references rather than deleting the rows, so the approve/reject audit history survives the conversation.
   **Durable fix still open:** a migration adding `ON DELETE SET NULL` to those two FKs, so the DB handles it instead of application code.

3. **Cleanup scan timed out in the browser** — the scan takes ~107s (one live platform call per conversation) but the axios client has a global 30s timeout. Worse, the request kept running server-side, so a timed-out *delete* would still execute while the UI showed an error. Rewritten as a background job (see 14.4).

### 14.4 New: Saved for Later

`Save for Later` always persisted (`response_drafts.status = "saved"`) but was a dead end — no way to find those drafts again except remembering which conversation they came from. `/history` only reconstructs from the first 30 conversations with drafts and does not link anywhere.

- **New endpoint `GET /drafts`** (`app/routers/drafts.py`) — filter by `status` and `platform`, paginated, joins each draft to its parent conversation in one batched lookup. Invalid status → 400.
- **New page `/saved`** (`frontend/app/saved/page.tsx`) — draft text, the original post it replies to, platform + style, with **Open conversation**, **Move back to pending** (calls `unapprove`), and **View original**.
- **Sidebar entry** "Saved for Later" with a live count badge.

### 14.5 New: cleanup scan as a background job

`POST /conversations/cleanup-deleted` no longer blocks. Follows the same pattern as the discovery worker:

| Endpoint | Purpose |
|---|---|
| `POST /conversations/cleanup-deleted` | starts the scan, returns `scan_id` in ~1ms (202) |
| `GET /conversations/cleanup-scans/{id}` | live progress — `status`, `checked`/`total`, flagged list |
| `POST /conversations/cleanup-scans/{id}/apply` | deletes exactly what that scan found |

- **Confirm no longer re-scans.** It previously called `cleanupDeleted(false)`, which repeated the entire 60s pass over every platform before deleting — and could disagree with what you were shown. `apply` reuses the ids the scan already found.
- Scan sped up: concurrency 5 → 10 plus a 10s per-check timeout so one hung platform cannot stall the batch. **107s → 61s** on 115 conversations.
- Scan state is **in-memory** (last 20 scans). A backend restart mid-scan loses it — including `--reload` firing on a file save.
- Verified: progress ticked 0 → 28 → 52 → 76 → 115, `completed` with 2 flagged, apply returned `removed: true, deleted_count: 2`, and all 29 `feedback_log` rows survived. Those 2 rows are backed up in the session scratchpad as `cleanup_backup.json`.

### 14.6 Sidebar counters now sync

Badges polled on a 60s interval with no signal from the pages, so they were routinely stale. Every draft mutation in `draftsApi` now fires a `drafts:changed` window event (`frontend/lib/api.ts`), and the sidebar refreshes on that event, on route change, and on the interval. Doing it at the API layer means no page can forget. This fixed the Today's Feed badge too.

### 14.7 Platform credentials — current state

`.env` has **no** `REDDIT_*`, `YOUTUBE_*`, `THREADS_*` keys, so those Connect buttons build an OAuth URL with an empty `client_id`/`redirect_uri` and the provider rejects it:
- YouTube → `Missing required parameter: redirect_uri`
- Reddit → `invalid client id`

Not a code bug. Each needs a developer app created and its keys added to `.env`, then a **backend restart** (`.env` is read once at import and `Settings` is `lru_cache`d; uvicorn `--reload` only watches `.py` files).

Notes for whoever sets these up:
- **Reddit** app type must be **web app**, not "script" — the code uses the authorization-code redirect flow. (README currently says "script" — wrong.)
- **Mastodon** app needs scopes **`read` and `write`** — write is required for posting. (README says `read` only — now out of date.)
- **YouTube** needs an OAuth 2.0 **Web application** client. The API key in `API keys for AI deepner.pdf` is **not usable** — the connector has no `developerKey` path.
- The Discord app in that PDF (`1535180581346869309`) is **not** the one in `.env` (`1540859843999698994`); the `.env` one is already connected and validating.
- `DISCORD_REDIRECT_URI` in `.env` still points at the Render production URL, so a *local* Discord reconnect would bounce to production.

### 14.8 Still open

- Bluesky needs a fresh app password.
- Telegram still network-blocked here (`api.telegram.org` times out).
- Pin `requirements.txt` versions.
- Migration for the `feedback_log` FKs.
- `/history` (`FeedbackTable`) still reconstructs history from at most 30 conversations and its rows do not link anywhere — it could now use `GET /drafts` for a real query.
- The project has **no ESLint config**; `npx next lint` offers to create one from scratch.

---

## 15. Session (24 Aug 2026) — UI changes

All frontend-only, all typechecked (`tsc --noEmit` clean).

### 15.1 Settings — broken toggle switches

The knob `<span>` was `absolute` with **no `left`**, so it started from the button's default UA padding (~6px) and `translate-x-5` pushed it past the right edge of the track. Fixed in both `DiscoverySettingsSection.tsx` and `CommunityDiscoverySettingsSection.tsx`: added `left-0.5`, `p-0` + `shrink-0` on the track, and off-state `translate-x-0`. Knob now sits at 2px off / 22px on inside the 44px track.

### 15.2 Community Manager (`/community`)

- **Approve → Join, Reject → Ignore** everywhere: item buttons, bulk buttons, threshold labels, counter chips ("Joined"/"Ignored"), toasts and error strings. Ignore had no confirmation toast at all — added one.
- **Relevance score explained.** An amber callout above the list (`bg-warning/20`, `border-l-4`) describes what the percentage is: a weighted average of topic relevance 40%, audience fit 30%, discussion quality 20%, contribution opportunity 10%, with anything under 60% filtered out before it reaches the list. Weights mirror `app/services/community/community_scorer.py` and are duplicated as frontend constants with a keep-in-sync comment — the per-criterion sub-scores are **not** persisted to the DB, only the final `relevance_score`.
- **Hover tooltip on each percentage** — appears on hover *and* keyboard focus (`group-focus-within`, `role="tooltip"`, `aria-describedby`).
- **Community names in Discovery History rows.** Required a backend change: run rows only store counts, the names live in `community_suggestions` linked by `discovery_run_id`. Added `_attach_communities()` in `app/routers/community_discovery.py`, wired into `/discover/runs` and `/discover/runs/{id}`. The expanded row renders them as chips with their scores. Two older runs return no names (their suggestions were superseded by later dedup) and show a clear message.
- **Button and chip styling** pulled into shared constants (`BTN_JOIN`, `BTN_DESTRUCTIVE`, `BTN_ON`, `BTN_OFF`, `CHIP`) so the tabs cannot drift apart. Active/Paused became a `StatusToggle` component that actually shows its state (green fill + dot vs muted outline) — previously both states looked identical apart from the word. Remove/Delete picked up the danger fill. Keyword chips went from invisible grey to accent-blue tags. Applied to Active Communities, Topics **and** People (People has the identical pattern and would have been the only ghost-button tab left).
- Alignment: the platform badge and community name sat ~2px off because the name's line box was sized by the inherited 16px/1.5 strut rather than its own 14px text. Both pinned to a 20px line box; name also got `truncate` so a long one cannot push the score and buttons out of line.

### 15.3 Destructive-action buttons made visible

Several destructive actions were `variant="ghost"` — fully transparent, reading as plain text. All now use the same muted red (`bg-danger/15` + `border-danger/40` + `hover:bg-danger/25`):
- **Dismiss** on the feed card (`ConversationCard.tsx`)
- **Clean up deleted** on `/conversations`
- Ignore / Remove / Delete across Community Manager

**Save for Later** on the draft card got the matching amber treatment, so draft actions now read as a set: blue Approve & Post, amber Save, red Reject.

### 15.4 Draft cards — buttons no longer vanish mid-action

Clicking Save for Later removed *every* button from the card: the page optimistically set `status: "saved"` on click, and the whole action row is gated on `pending`, so it unmounted mid-request. Now `runAction` sets `busy = { id, action }` instead of patching the status, awaits, then applies the real returned draft. All buttons get `disabled` and the clicked one gets `loading`. Applied to Approve, Approve & Post, Edit & Approve, Save for Later, Confirm Reject, Post Now and Remove Approval.

Trade-off: the status badge now appears when the request lands rather than instantly; the spinner covers that window. The rollback-on-error branch was removed with the optimistic update.

### 15.5 Conversations list — filters looked broken

The spinner was gated on `loading && !data`. On a filter change `data` still held the previous page, so it never showed: stale rows stayed on screen and new results silently popped in. The backend was working correctly the whole time.

- New `Skeleton` (`components/shared/Skeleton.tsx`) and `ConversationsSkeleton` (mirrors the real table columns and the mobile card layout).
- Both first load and refetch render the skeleton, sized to the last result count so page height stays steady.
- Platform/Status selects and Previous/Next are disabled during the refetch so a second change cannot stack on an in-flight one. Added `disabled:opacity-50 disabled:cursor-not-allowed` to the shared `Select`, which had no disabled styling at all.
- Search and the date inputs stay live — they filter the loaded page client-side and never hit the API.

### 15.6 Clean up deleted — tooltip and progress

- Replaced the native `title` attribute with a styled tooltip explaining that it checks whether the **original post still exists** on the platform, that it scans first and removes nothing until you confirm, and (in amber) that confirming permanently deletes those conversations and their drafts. The old `title` also said "Bluesky/Mastodon" when `SUPPORTED_POSTING` covers four platforms.
- The button shows live progress from the background job: "Starting scan…" → "Checking 52/115…". The confirm dialog now reads "N of M checked conversation(s)".

> Note: "deleted" here means **the source post was deleted on the platform** — it is unrelated to the `analysis_status` filter (`pending / analysed / skipped / error`), which is where a conversation sits in your own pipeline.
