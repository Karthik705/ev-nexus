# EV NEXUS — Deployment Guide

**Current status: prepared for deployment, not yet deployed.** No GitHub remote, no hosting account, and no live URL exist as of this document. Everything in this file that requires a browser-based signup, clicking through a hosting dashboard, or GitHub OAuth is a step **only you can perform** — this session has no browser, no GitHub CLI (`gh` is not installed), and no hosting-provider credentials, so none of that could be done automatically. Everything that *could* be prepared without those things (deployment config files, environment-variable wiring, CORS support, a health endpoint, dependency pinning) has been done and is described below.

## Chosen Providers, and Why

Researched live (September 2026) rather than assumed from prior knowledge — see sources at the bottom of this section.

| Layer | Provider | Why |
|---|---|---|
| Backend (FastAPI) | **[Render](https://render.com)** | Genuinely free web-service tier, **no credit card required** to sign up or deploy, native Python support with auto-detection, deploys directly from a GitHub repo, has a documented health-check integration. Trade-off: free instances spin down after 15 minutes of inactivity (30–60s cold start on the next request) — acceptable for a portfolio demo, explicitly not recommended by Render for production traffic. |
| Frontend (static Vite build) | **[Cloudflare Pages](https://pages.cloudflare.com)** | Free tier has **unlimited bandwidth and unlimited requests** (500 builds/month), no credit card required, deploys from a GitHub repo automatically on push. Chosen over Vercel specifically because Vercel's Hobby tier has documented unexpected-overage-billing risk ("a single viral moment can turn a $0 bill into a $500+ surprise") which conflicts with this project's "no unexpected charges" requirement; Cloudflare Pages' free tier has no such overage-billing exposure for a static site. |

Both were re-verified as free/no-card as of this pass via live web search, not assumed from older documentation, since providers' free tiers are known to change (multiple sources noted tier changes between Feb–June 2026).

## What's Already Prepared in This Repository

- **`requirements.txt`** (new, this pass) — pinned to the exact versions verified working in this project's development environment: `fastapi==0.141.1`, `uvicorn==0.52.4`, `pydantic==2.13.4`, `google-genai==2.20.0`, `numpy==2.4.4`, `torch==2.11.0`, `gymnasium==1.3.0`. (`torch`/`gymnasium` are required even though DQN isn't used by the interactive app, because `simple_ev_simulation.py` imports `torch` at module scope — see the note in "Known Constraints" below.)
- **`render.yaml`** (new, this pass) — a Render Blueprint that fully describes the backend service: build command (`pip install -r requirements.txt`), start command (`uvicorn app:app --host 0.0.0.0 --port $PORT`), health-check path (`/api/health`), and two secret environment variables (`GEMINI_API_KEY`, `ALLOWED_ORIGINS`) marked `sync: false` — meaning Render will prompt for their values in its dashboard rather than expecting them in the repo. **No secret is contained in this file.**
- **Configurable frontend backend URL** — `frontend/src/api.ts` reads `VITE_API_BASE` at build time. Verified this pass (and the prior pass) that setting it correctly bakes a different backend URL into the build output.
- **Configurable CORS** — `app.py` reads `ALLOWED_ORIGINS` from the environment, defaulting to localhost-only. No code change is needed to point it at a production frontend origin — just set the environment variable.
- **Real health endpoint** — `GET /api/health` → `{"status": "ok"}`, no side effects, matches `render.yaml`'s `healthCheckPath`.
- **No debug/reload flags, no hardcoded host/port** — `app.py` contains no `debug=True`, no `reload=True`, and no `__main__` block hardcoding a port; the start command controls this entirely, so it is safe to run in production as specified in `render.yaml`.

## Known Constraint: `torch` Is a Heavy Dependency

`simple_ev_simulation.py` imports `torch` unconditionally at module scope (used only when `policy == 'DQN'`, but the import itself always runs). This means the backend's dependency footprint includes PyTorch even though the interactive production app never uses the DQN policy. This was **not** refactored to a lazy import in this pass — doing so is a legitimate future improvement but touches import structure used elsewhere (benchmarks, `dqn_agent.py`), and the instruction for this pass was to avoid unnecessary code changes. Practical implication: the Render build may take longer and use more disk than a minimal FastAPI app, which the free tier's build environment should still handle, but is worth knowing if the build times out or is slow.

## Step-by-Step: What You Need To Do

### 1. Create the GitHub repository (cannot be done from this session — no `gh` CLI, no browser)

1. Go to [github.com/new](https://github.com/new).
2. Repository name: `ev-nexus` (fallback: `ev-charging-nexus` if taken).
3. Visibility: **Public**.
4. **Do not** initialize with a README, `.gitignore`, or license — this repo already has all of those; adding GitHub-generated versions would conflict with the existing local history.
5. Click "Create repository." Copy the HTTPS or SSH remote URL it gives you.

Then, from a terminal in this project directory, run (this session cannot run `git push` itself — a push to a new GitHub remote requires an interactive login/OAuth flow neither `gh` nor a stored credential is available for here):

```bash
git remote add origin <the URL GitHub gave you>
git branch -M main
git push -u origin main
```

This will prompt you to authenticate (browser popup or a Personal Access Token, depending on your Git setup) — that's expected and is the part only you can complete.

### 2. Deploy the backend to Render (cannot be done from this session — requires a browser-based account)

1. Go to [render.com](https://render.com) and sign up (GitHub OAuth is the easiest option — no credit card needed).
2. Click "New +" → "Blueprint," and point it at your newly-pushed `ev-nexus` GitHub repo. Render will detect `render.yaml` automatically and propose the `ev-nexus-backend` service.
3. Confirm the blueprint. Render will ask you to fill in the two secret environment variables it found marked `sync: false`:
   - **`GEMINI_API_KEY`** — paste your Gemini API key value directly into Render's environment-variable field in its dashboard. **Do not paste it into this chat, a terminal command, or any file in this repository.** If you don't have a valid key yet, leave this blank or set it to a placeholder — the app is designed to run correctly without it, using deterministic fallback (verified in `docs/TEST_REPORT.md`).
   - **`ALLOWED_ORIGINS`** — leave this blank for now; you'll set it after step 3 (frontend deployment) gives you a real frontend URL. Render will let you edit environment variables and redeploy at any time.
4. Deploy. Once live, Render gives you a URL like `https://ev-nexus-backend.onrender.com`. Test it yourself by visiting `https://ev-nexus-backend.onrender.com/api/health` in a browser — it should return `{"status":"ok"}` (allow up to a minute for the free tier's cold start on the first request).

### 3. Deploy the frontend to Cloudflare Pages (cannot be done from this session — requires a browser-based account)

1. Go to [pages.cloudflare.com](https://pages.cloudflare.com) and sign up (no credit card needed for the free tier).
2. Create a new project, connect your `ev-nexus` GitHub repo.
3. Build settings:
   - **Root directory:** `frontend`
   - **Build command:** `npm run build`
   - **Build output directory:** `dist`
4. Before deploying, add an environment variable: **`VITE_API_BASE`** = `https://ev-nexus-backend.onrender.com/api` (use your actual Render URL from step 2, with `/api` on the end, matching this project's route prefix). This is public configuration — it is not a secret, and it must **never** be `GEMINI_API_KEY` (that key must only ever exist as a backend secret on Render, never as a `VITE_*` variable, since anything prefixed `VITE_` gets bundled into the public JavaScript output).
5. Deploy. Cloudflare gives you a URL like `https://ev-nexus.pages.dev`.

### 4. Lock down production CORS (a 1-minute step back on Render, after step 3)

1. Back in Render's dashboard, edit the `ev-nexus-backend` service's `ALLOWED_ORIGINS` environment variable to your actual Cloudflare Pages URL from step 3, e.g. `https://ev-nexus.pages.dev` (comma-separate additional origins if you add a custom domain later; do **not** use `*`).
2. Save — Render will redeploy automatically.
3. Visit your Cloudflare Pages URL and confirm the app loads and the sidebar's "System Online" indicator (backed by the real `/api/health` poll added this pass) turns green, not red.

### 5. Production Smoke Test (do this yourself once both are live; this session cannot browse to a public URL to do it for you)

- `GET https://<your-render-url>/api/health` → expect `{"status":"ok"}`.
- Open the frontend URL, confirm the Overview page loads, health indicator is green, and a "Force fallback" negotiation completes successfully end-to-end (this proves frontend → backend → validator → scheduler works without needing a Gemini key yet).
- If/when you add a real `GEMINI_API_KEY` to Render, submit one negotiation **without** "Force fallback" checked and confirm the AI Intent panel shows "Live Gemini" rather than "Fallback."

### 6. How to Redeploy

Both Render and Cloudflare Pages auto-deploy on every push to `main` once connected — `git push` is the entire redeploy workflow for both services.

## What This Session Did Not Do, and Why

| Not done | Why |
|---|---|
| Created a GitHub repository | Requires github.com account interaction; no `gh` CLI installed, no browser tool available. |
| Pushed to GitHub | Even with a remote configured, `git push` to a new GitHub repo requires an interactive auth flow (browser OAuth or a token) this session cannot complete headlessly. |
| Created a Render account or deployed the backend | Requires browser-based signup and dashboard interaction. |
| Created a Cloudflare Pages account or deployed the frontend | Same reason. |
| Entered `GEMINI_API_KEY` anywhere | By design — a key must only ever be entered directly into Render's dashboard by you, never pasted into this chat or committed to the repo. |
| A live Gemini smoke test | Depends on the backend being deployed with a real key, which depends on the steps above. |
| Real production browser testing | Depends on both services being live, and no browser automation tool is available in this session regardless. |

## Sources (free-tier research, checked this pass)

- [Render: platforms with a real free tier for developers in 2026](https://render.com/articles/platforms-with-a-real-free-tier-for-developers-in-2026)
- [Render Pricing](https://render.com/pricing)
- [Cloudflare Pages vs Vercel](https://speedvitals.com/blog/cloudflare-pages-vs-vercel/)
- [Vercel vs Netlify vs Cloudflare Pages, 2026 Real Test](https://blog.vibecoder.me/vercel-vs-netlify-vs-cloudflare-pages)
