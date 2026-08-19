# Deployment Guide

Target setup:
- **Backend (FastAPI)** → **Render** (Web Service)
- **Frontend (Next.js)** → **Vercel**
- **Database + storage** → **Supabase** (already cloud — no change)

Both hosts deploy from a **GitHub repo**, so step 0 is getting the code on GitHub.

---

## 0. Push to GitHub (once)

```bash
cd "E:/David Lasser AI Automation"
git init
git add .
git commit -m "Initial commit"
# create an empty repo on github.com, then:
git remote add origin https://github.com/<you>/dialogue-enhancer.git
git branch -M main
git push -u origin main
```

The `.gitignore` already excludes `.env`, `node_modules`, `.venv`, `.next`, and logs — so **no secrets are committed**. Double-check `git status` does not list `.env` before pushing.

---

## 1. Backend on Render

You can use the included **`render.yaml`** (New → Blueprint) or set it up manually:

- **New → Web Service** → connect the repo.
- **Runtime**: Python 3
- **Build command**: `pip install -r requirements.txt`
- **Start command**: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- **Instance type**: **Starter** recommended. (Free works but **sleeps when idle**, which pauses the discovery scheduler and makes the first request slow — see Notes.)

### Environment variables (Render dashboard → Environment)

Copy every value from your local `.env`, with these production differences:

| Variable | Value |
|---|---|
| `PYTHON_VERSION` | `3.12.7` |
| `LLM_PROVIDER` | **`openai`** (Ollama can't run on Render) |
| `OPENAI_API_KEY` | your key |
| `OPENAI_MODEL` | `gpt-4o` |
| `SUPABASE_URL` / `SUPABASE_ANON_KEY` / `SUPABASE_SERVICE_ROLE_KEY` | from Supabase |
| `TOKEN_ENCRYPTION_KEY` | **the same key as local** (or tokens won't decrypt) |
| `APP_BASE_URL` | your Render URL, e.g. `https://dialogue-enhancer-api.onrender.com` |
| `FRONTEND_URL` | your Vercel URL, e.g. `https://dialogue-enhancer.vercel.app` |
| Platform creds (`BLUESKY_*`, `MASTODON_*`, etc.) | as needed |

> `FRONTEND_URL` is what lets the browser call the API (CORS). Vercel preview URLs (`*.vercel.app`) are already allowed by a regex; set `FRONTEND_URL` to your main production URL.

Deploy, then confirm: open `https://<render-url>/` → should return `{"success":true,...}` and `/docs` shows the API.

---

## 2. Frontend on Vercel

- **New Project** → import the same GitHub repo.
- **Root Directory**: `frontend`
- Framework preset: **Next.js** (auto-detected).
- **Environment variable**:
  - `NEXT_PUBLIC_API_URL` = your Render backend URL (e.g. `https://dialogue-enhancer-api.onrender.com`)
- Deploy.

After the first deploy you'll get a URL like `https://dialogue-enhancer.vercel.app`. Put that into the Render `FRONTEND_URL` env var (step 1) and redeploy the backend so CORS allows it.

---

## 3. Reconnect platforms (OAuth redirect URIs)

The tokens live in Supabase, but OAuth apps point at redirect URLs. After deploy:

- **Update each platform's developer app** redirect URI to the Render callback, e.g.
  `https://<render-url>/connections/mastodon/callback`
  (Reddit, Mastodon, Discord, Threads, YouTube — whichever you use).
- Set the matching `*_REDIRECT_URI` env vars on Render to the same values.
- In the **deployed** dashboard → Settings → Connections → **Disconnect then Connect** each OAuth platform to mint fresh tokens for the new domain.
- **Bluesky / Telegram** are direct (no redirect): just set `BLUESKY_HANDLE` + `BLUESKY_APP_PASSWORD` (and/or reconnect Bluesky from the dashboard) and `TELEGRAM_BOT_TOKEN`.

---

## 4. Sanity checks

1. `https://<render-url>/discovery/status` → `success:true`, `scheduler_running:true`.
2. Dashboard loads on Vercel, no CORS errors in the browser console.
3. Upload a doc, submit a conversation → drafts generate (now via OpenAI, fast + granular).

---

## Notes & gotchas

- **Ollama → OpenAI is required** in production. Render has no GPU/Ollama. This also fixes the coarse-score and JSON issues you saw locally.
- **Render Free sleeps.** The APScheduler discovery worker only runs while the service is awake. For reliable scheduled discovery use **Starter**, or move discovery to a Render **Cron Job** hitting `POST /discovery/trigger` (can add later).
- **`.doc` parsing** relies on MS Word/LibreOffice and won't work on Render Linux (no Word). PDF/DOCX/HTML/TXT/MD all work. Add LibreOffice via a Dockerfile later if you need `.doc`.
- **Keep `TOKEN_ENCRYPTION_KEY` identical** between environments, or previously stored platform tokens can't be decrypted (you'd just reconnect).
- **Supabase**: no change — same project, same migrations already applied. Add the Render/Vercel domains to Supabase Auth allowed URLs only if you later add Supabase auth (not used now).
