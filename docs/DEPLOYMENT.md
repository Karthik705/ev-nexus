# EV NEXUS — Deployment

Deployed on free tiers at no cost.

| Service | Provider | URL |
|---|---|---|
| Frontend (static Vite build) | Cloudflare Pages | [ev-nexus.pages.dev](https://ev-nexus.pages.dev) |
| Backend (FastAPI) | Render | [ev-nexus-backend.onrender.com](https://ev-nexus-backend.onrender.com) |
| Health check | | [/api/health](https://ev-nexus-backend.onrender.com/api/health) → `{"status":"ok"}` |

> Render's free tier sleeps after 15 minutes without traffic. The first request after a
> quiet period can take 30–60 seconds while the backend wakes up; after that it is fast.

## Why these providers

| Layer | Provider | Reason |
|---|---|---|
| Backend | Render | Free web service without a card, native Python support, auto-deploy from GitHub. Trade-off: cold starts on the free tier. |
| Frontend | Cloudflare Pages | Unlimited bandwidth on the free tier and no overage billing. |

## Configuration

| Variable | Where | Value in production |
|---|---|---|
| `ALLOWED_ORIGINS` | Render | `https://ev-nexus.pages.dev` (exact origin, no wildcard) |
| `GEMINI_API_KEY` | Render (secret) | Set in the dashboard, never in the repository |
| `VITE_API_BASE` | Frontend build | `https://ev-nexus-backend.onrender.com/api` |

The Gemini key exists only on the backend; a Playwright test asserts that no key appears
in any script served to the browser. Each browser session gets its own isolated
simulation state.

## Files that support deployment

- `requirements.txt` — pinned backend dependencies.
- `render.yaml` — Render Blueprint (build and start commands, health-check path, secrets
  marked `sync: false` so they are entered in the dashboard).
- `frontend/src/api.ts` — reads `VITE_API_BASE`, defaulting to `http://127.0.0.1:8000/api`.
- `app.py` — `ALLOWED_ORIGINS` CORS allowlist and `GET /api/health`.

## Deploying your own copy

**Backend (Render):** New → Blueprint → select this repository; Render reads
`render.yaml`. Set `ALLOWED_ORIGINS` to your frontend URL and, optionally,
`GEMINI_API_KEY`. Without a key the app runs on telemetry-only scheduling.

**Frontend (Cloudflare Pages):**

```bash
cd frontend
VITE_API_BASE=https://<your-backend>.onrender.com/api npm run build
npx wrangler pages deploy dist --project-name <your-project>
```

Both services redeploy automatically on push to `main` once connected to GitHub.

## Production checks

| Check | Result |
|---|---|
| `GET /api/health` | `{"status":"ok"}` |
| CORS preflight from the frontend origin | Exact-origin `access-control-allow-origin` |
| `POST /api/negotiate` with forced fallback | Correct telemetry-fallback response, 80% charge target |
| `POST /api/step`, `GET /api/station`, `POST /api/reset` | Correct state transitions |
| `GET /api/benchmarks` | Allow-listed result files served |
| Live Gemini call | Key authenticates; on the recorded test Google returned a transient 503, and the system correctly fell back to telemetry |
| Browser E2E against the deployed site | `E2E_BASE_URL=https://ev-nexus.pages.dev npm run test:e2e` |

## Deployment note: Git Bash on Windows

Git Bash rewrites arguments that look like Unix paths. Passing `/api/health` to the
Render CLI from Git Bash turned it into `C:/Program Files/Git/api/health`, and the health
check failed. Prefix such commands with `MSYS_NO_PATHCONV=1`. After changing the
health-check path, restart the service: the running instance keeps the old path until
it restarts.

The original step-by-step deployment log is in
[`docs/history/DEPLOYMENT_LOG.md`](history/DEPLOYMENT_LOG.md).
