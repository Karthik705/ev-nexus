# EV NEXUS — Deployment Notes

**Current status: not deployed.** No live URL exists for this project as of this pass. This document describes what has been prepared for deployment and what a human operator still needs to do. No deployment was performed, no hosting account was created or configured, and no money was spent, per the explicit constraints of this work.

## What's Already Prepared

- **Configurable frontend backend URL** — `frontend/src/api.ts` reads `VITE_API_BASE` at build time, defaulting to `http://127.0.0.1:8000/api` only when unset. A production build can point at any deployed backend by setting this one environment variable before `npm run build`. Verified this pass: building with `VITE_API_BASE=https://example-deployed-backend.com/api` correctly bakes that URL into the output bundle.
- **Environment-based secrets** — `GEMINI_API_KEY` is read from the environment (or a local `.env`, gitignored), never hardcoded. `.env.example` (root) documents the required variable with a placeholder.
- **Configurable CORS** — `ALLOWED_ORIGINS` env var (comma-separated) controls the backend's CORS allowlist, defaulting to localhost-only. **Must be set to the real deployed frontend origin before any deployment** — the default will reject requests from a production frontend domain, which is the correct, safe behavior (fail closed, not open).
- **Health endpoint** — `GET /api/health` returns `{"status": "ok"}` with no side effects, suitable for a hosting platform's health-check probe.

## Suggested Low-Cost Hosting (not provisioned)

These are suggestions based on the project's shape (a stateless-ish FastAPI backend + a static React build), not commitments — no account was created for any of them in this pass:

- **Backend (FastAPI):** a platform with a free/low-cost tier for small Python web services (e.g. Render, Railway, Fly.io). Needs: `GEMINI_API_KEY` and `ALLOWED_ORIGINS` set as environment secrets, `uvicorn app:app --host 0.0.0.0 --port $PORT` as the start command, and `pip install -r requirements.txt`-equivalent dependency install (`fastapi`, `uvicorn`, `google-genai`, `torch`, `pydantic`, `numpy`, `gymnasium` — note `torch`/`gymnasium` are only required because `simple_ev_simulation.py` imports `dqn_agent`/`ev_gym_env` at module scope for the DQN policy path; a minimal deployment that never uses the DQN policy could in principle stub this out, but that would be a real code change, not attempted here).
- **Frontend (static build):** any static-site host (e.g. Vercel, Netlify, Cloudflare Pages, GitHub Pages) serving `frontend/dist/` after `npm run build` with `VITE_API_BASE` set to the deployed backend's URL.

## Steps a Human Needs to Perform (outside this session's scope)

1. Confirm the Gemini API key's status (valid/revoked) directly in Google AI Studio — not verifiable from this repository.
2. Choose and provision a backend host; set `GEMINI_API_KEY` and `ALLOWED_ORIGINS` as that platform's environment secrets (never commit them).
3. Choose and provision a static frontend host; set `VITE_API_BASE` to the backend's deployed URL at build time.
4. Deploy both, then run a production smoke test: `GET /api/health` from the public backend URL, and a full negotiate → station → step → reset cycle from the public frontend URL (with `force_fallback` if the live Gemini path isn't being tested yet).
5. Record the actual URLs and smoke-test results in this file once deployment happens — this document intentionally does not fabricate a URL or claim a deployment that hasn't occurred.
6. Consider adding a persistent session store (Redis/DB) before any multi-user production use — the current per-session in-process dict does not survive a restart or scale across replicas (documented in the README's Limitations section).

## What This Session Explicitly Did Not Do

- Did not create any hosting account or deploy anything.
- Did not push this repository to a remote (GitHub or otherwise).
- Did not spend any money or provision any paid service.
- Did not perform a production smoke test (none exists yet to test).
