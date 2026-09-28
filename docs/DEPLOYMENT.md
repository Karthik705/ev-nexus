# EV NEXUS — Deployment Guide

**Status: deployed and live, ₹0 total cost.**

| Service | Provider | URL |
|---|---|---|
| GitHub | github.com | [github.com/Karthik705/ev-nexus](https://github.com/Karthik705/ev-nexus) (public) |
| Frontend | Cloudflare Pages (free tier) | [ev-nexus.pages.dev](https://ev-nexus.pages.dev) |
| Backend | Render (free tier) | [ev-nexus-backend.onrender.com](https://ev-nexus-backend.onrender.com) |
| Health check | — | https://ev-nexus-backend.onrender.com/api/health → `{"status":"ok"}` |

No credit card was entered anywhere. No paid plan was selected. Both providers' free tiers were re-verified as genuinely free (no card required) via live research before use — see "Chosen Providers" below.

## How This Was Deployed

Both `gh` (GitHub CLI) and Render's official CLI were installed via `winget` (Windows Package Manager — free, official sources: `GitHub.cli`, `Render.CLI`). Cloudflare's `wrangler` CLI was already available via `npx`. All three support browser-based one-time device-code authentication: running `gh auth login`, `wrangler login`, and `render login` each opened a real browser window on this machine for the account owner to click "Authorize" — no password, token, or secret was ever typed into a terminal or chat. Cloudflare and Render both completed near-instantly since the account owner was already signed into those providers in their browser; GitHub's own push turned out to already be configured from a prior manual push, so no `gh` authentication was actually needed to publish code.

Once authenticated:
- **Cloudflare Pages**: `npx wrangler pages project create ev-nexus --force` (the `--force` flag was required once, to use classic Pages instead of an unwanted auto-delegation to "Pages via Workers," which would have scaffolded unrelated Workers config files into the frontend — those were reverted before proceeding), then `npx wrangler pages deploy dist --project-name ev-nexus`.
- **Render**: `render services create --name ev-nexus-backend --type web_service --repo https://github.com/Karthik705/ev-nexus --runtime python --build-command "pip install -r requirements.txt" --start-command "uvicorn app:app --host 0.0.0.0 --port $PORT" --health-check-path /api/health --plan free --env-var "ALLOWED_ORIGINS=https://ev-nexus.pages.dev"`.

## A Real Gotcha Worth Recording (for future redeploys)

Running Render CLI commands from **Git Bash on Windows** silently mangles any argument that looks like a Unix path — `/api/health` was rewritten to `C:/Program Files/Git/api/health` before Render ever saw it, causing the health check to fail with 404s even though every other setting was correct. Fixed by prefixing the command with `MSYS_NO_PATHCONV=1`. A second subtlety: updating the setting via `render services update` changed the stored config immediately (confirmed via `render services -o json`), but the **already-running instance's internal health-check monitor kept using the old, wrong path** until the service was explicitly restarted with `render restart <service-id>` — redeploying alone was not enough to refresh it. If you ever see health checks failing on Render despite the dashboard showing the correct path, try a restart before assuming something else is wrong.

## Chosen Providers, and Why

Researched live (September 2026), not assumed from older documentation — providers' free tiers are known to shift (multiple sources noted tier changes between Feb–June 2026 alone).

| Layer | Provider | Why |
|---|---|---|
| Backend (FastAPI) | **[Render](https://render.com)** | Free web-service tier, no credit card, native Python auto-detection, GitHub auto-deploy on push. Trade-off (accepted, documented): free instances spin down after 15 min idle, ~30-60s cold start on the next request — Render's own docs say not to use this tier for production traffic, which is fine for a portfolio demo. |
| Frontend (static Vite build) | **[Cloudflare Pages](https://pages.cloudflare.com)** | Unlimited bandwidth and requests on the free tier, no credit card, no known overage-billing exposure — chosen over Vercel specifically because Vercel's Hobby tier has documented surprise-overage-billing risk, which conflicts with the "no unexpected charges" requirement for this project. |

## What's In the Repository to Support This

- **`requirements.txt`** — pinned backend dependencies (`fastapi`, `uvicorn`, `pydantic`, `google-genai`, `numpy`, `torch`, `gymnasium`), verified against the exact versions used in development.
- **`render.yaml`** — a Render Blueprint describing the same service declaratively (build/start commands, health-check path, `GEMINI_API_KEY`/`ALLOWED_ORIGINS` marked `sync: false` so Render prompts for them in its dashboard rather than expecting them in the repo). The actual deployed service was created via direct CLI flags rather than a Blueprint sync (see above), but `render.yaml` remains available and accurate if you ever want to redeploy via Render's "New Blueprint" dashboard flow instead.
- **Configurable frontend backend URL** (`frontend/src/api.ts`, `VITE_API_BASE`) — the deployed build was produced with `VITE_API_BASE=https://ev-nexus-backend.onrender.com/api`; confirmed baked into the shipped JS bundle (grepped the built output directly).
- **Configurable CORS** (`app.py`, `ALLOWED_ORIGINS`) — set to exactly `https://ev-nexus.pages.dev` on the deployed backend. No wildcard.
- **Real health endpoint** (`GET /api/health`) — confirmed live and correct after the gotcha above was fixed.

## GEMINI_API_KEY — the one remaining manual step

**Not set on the deployed backend.** The backend currently runs entirely on deterministic fallback, which was verified working in production (see the smoke test results in `docs/CURRENT_PROJECT_STATUS.md`). Your key was never read, transmitted, or typed into any command in this deployment — by design.

To enable live Gemini on the deployed backend, enter your key **directly into Render's dashboard**, nowhere else:

1. Go to **https://dashboard.render.com/web/srv-dat12fjbc2fs73aot3e0** (the `ev-nexus-backend` service).
2. Open the **Environment** tab.
3. Add a variable named exactly `GEMINI_API_KEY` with your key as the value.
4. Save — Render redeploys automatically.
5. Come back and ask for one controlled live-Gemini smoke test once it's set — that step still requires your explicit go-ahead per the standing instructions for this project, and was not performed automatically.

## Production Smoke Test Results (this pass)

All run directly against the live URLs above:

| Check | Result |
|---|---|
| `GET /api/health` | `{"status":"ok"}` |
| CORS preflight from `https://ev-nexus.pages.dev` | `access-control-allow-origin: https://ev-nexus.pages.dev` (exact match, not `*`) |
| `POST /api/reset` | `{"status":"ok",...}` |
| `POST /api/negotiate` (force_fallback) | Correct telemetry-fallback response, correct `target_soc: 80.0` (bug fix from the prior pass confirmed working in production) |
| `GET /api/station` | Correct port/queue state |
| `POST /api/step` | EV reached target and completed (`completed: 1`) |
| `GET /api/benchmarks` | Both allowlisted files present |
| Frontend loads publicly | `HTTP 200`, correct `<title>EV NEXUS — Charging Negotiator</title>` |
| Frontend → backend wiring | Verified by grepping the shipped JS bundle for the production backend URL |

Browser rendering itself (clicking through the actual UI) was **not verified** — no browser automation tool is available in this session. See `docs/CURRENT_PROJECT_STATUS.md` for the exact scope of what "verified" means here (API-level + build-artifact verification, not visual/interactive browser testing).

## How to Redeploy

Both services auto-deploy on push to `main`:

```bash
git push origin main
```

To manually redeploy the frontend with a new build (e.g., after changing `VITE_API_BASE`):

```bash
cd frontend
VITE_API_BASE=https://ev-nexus-backend.onrender.com/api npm run build
npx wrangler pages deploy dist --project-name ev-nexus --branch main
```

To manually trigger a backend redeploy without a new commit:

```bash
render deploys create srv-dat12fjbc2fs73aot3e0 --confirm
```

(Requires `render login` once per machine; already authenticated on this machine.)

## What Still Requires Your Action

1. **Add `GEMINI_API_KEY` to Render's dashboard** if you want live Gemini — see above. Not done automatically, by design.
2. **Authorize one live Gemini smoke test** once the key is set — ask, and it'll be run as a single controlled request, not an experiment batch.
3. Optional: consider rotating the Render account API key. While automating the Render CLI setup, one internal debug command in this session accidentally displayed that token in the terminal output (not your Gemini key, and not printed anywhere public — this was a local session on your own machine — but rotating it via Render's dashboard under Account Settings → API Keys is a reasonable precaution).
