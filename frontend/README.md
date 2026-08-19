# AI Dialogue Enhancer — Dashboard

The web dashboard (Module 8) for the AI Dialogue Enhancer. A calm, focused, single-user interface where the author reviews shortlisted conversations, approves or edits AI-generated response drafts grounded in their own writing, manages their knowledge base, and monitors feedback history.

## Prerequisites

- Node.js 18 or higher
- The backend API running (see the backend README in the project root) — by default at `http://localhost:8000`

## Installation

```bash
npm install
```

## Environment Setup

```bash
cp .env.local.example .env.local
```

Set `NEXT_PUBLIC_API_URL` to your backend URL (default `http://localhost:8000`).

## Development

```bash
npm run dev
```

Open http://localhost:3000 — it redirects to `/feed`.

## Production Build

```bash
npm run build
npm start
```

## Pages

| Route | Purpose |
|---|---|
| `/feed` | Today's Feed — analysed conversations with pending drafts, sorted by relevance. Review or dismiss each one. Polls every 60 seconds. |
| `/conversations` | Full searchable, filterable list of every conversation ever submitted. |
| `/conversations/[id]` | The core working view — conversation thread and AI analysis on the left, all four response drafts with approve/edit/reject/save actions on the right. Keyboard shortcuts: A approve, R reject first pending draft. |
| `/submit` | Manually submit a conversation for analysis and draft generation. |
| `/knowledge` | Upload documents (PDF, DOCX, HTML, TXT, MD), watch processing status, view chunks, reindex, or delete. |
| `/history` | Approval/edit/rejection rates, style performance, top rejection reasons, and decision history. |
| `/community` | Working list of communities and keywords to monitor (stored in localStorage for now). |
| `/settings` | Local preferences (stored in localStorage for now). |

## Connecting to the Backend

All API calls go through the centralised client in `lib/api.ts`, which reads `NEXT_PUBLIC_API_URL`. Every backend response uses a `{ success, data, error, timestamp }` envelope; the client unwraps it and throws descriptive errors that surface as toasts.

The sidebar shows a live API connection indicator (polled every 60 seconds).

## Known Limitations

- **Community Manager** and **Settings** store data in browser localStorage — automatic community discovery (Module 3) and backend-persisted settings (Module 11) are future builds.
- The **decision history table** on `/history` is reconstructed from decided drafts across recent conversations, because the backend does not yet expose a feedback-log list endpoint (only the summary).
- No authentication — this is a single-user private tool by design for the MVP.
