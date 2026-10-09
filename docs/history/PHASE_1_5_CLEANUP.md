# Phase 1.5 — Pre-Implementation Cleanup Log

> **Historical record — do not read as current state.** A dated log from 2026-09-28,
> kept unedited. Some files referenced here have since been removed in a later cleanup
> pass. Current state: `docs/history/CURRENT_PROJECT_STATUS.md`.

Date: 2026-09-28. Scope: resolve confirmed P0/P1 hygiene items from `docs/history/PROJECT_STATUS_AUDIT.md` only. No git repository was initialized, no commits made, no deployment performed, no live Gemini/API calls made, no secret values inspected or printed.

---

## Task 1 — `.env` Security Hygiene

Checks performed (no secret values read or printed):

- `.env` exists at repo root: **yes**.
- `.env` covered by `.gitignore`: **yes** (`.gitignore:1`).
- Secret scan for `AIza[A-Za-z0-9_-]{20,}`-style key patterns across the whole repo (excluding `node_modules`/`.git`), including `frontend/src` and `frontend/dist`: **zero matches** — no Gemini key material found in any source or build output.
- Files containing the literal string `GEMINI_API_KEY=` (name only, not value): `.env`, `.env.example`, `acceptance_test.py`, `app.py`, `generate_fixtures.py`, `llm_negotiator.py`, `README.md`, `docs/history/PROJECT_STATUS_AUDIT.md` — all of these reference the *variable name* only (code reading `os.environ`, or documentation), not an actual key value.
- `.env.example` content confirmed to be a safe placeholder only: `GEMINI_API_KEY=YOUR_API_KEY_HERE`.
- **Bug found and fixed:** `.gitignore` incorrectly listed `.env.example` itself (`.gitignore:5` in the pre-cleanup version), which would have prevented the safe placeholder template from ever being committed to version control — the opposite of intended behavior. Removed that line; `.env` (the real secret file) remains ignored, `.env.example` (the safe template) no longer is.
- `.env` was **not** deleted — left in place for local development as instructed.

**Result:** exists: yes · ignored: yes · exposed elsewhere: no · safe placeholder exists: yes.

---

## Task 2 — Removed Dead Frontend Copy

Verified before deletion:
- No file in the active app (`app.py`, `frontend/vite.config.ts`, `frontend/package.json`, any `frontend/src/**`) referenced `frontend-temp` in any way; the only repo hit was the audit report's own description of it.
- Diffed the 2 files that differed between `frontend/src` and `frontend/frontend-temp/src`: both differences showed `frontend-temp` was an **older, less-complete** snapshot (its `ArchitecturePage.tsx` documented only 4 API routes vs. the current app's 6; its `BenchmarksPage.tsx` was a pre-reformatting version of the same logic, no unique functionality).

Actions taken:
- Deleted `frontend/frontend-temp/` (directory).
- Deleted `frontend/frontend-temp.zip`.
- Active frontend (`frontend/src`, `frontend/package.json`, etc.) untouched.
- Rebuilt the real frontend afterward (`npm run build` from `frontend/`): succeeded with identical output hashes to the pre-cleanup build (`dist/assets/index-93z_AmtT.css`, `dist/assets/index-DsvwwbNf.js`), confirming `frontend-temp` was never part of the build graph.

---

## Task 3 — README Consistency Fix

`README.md`'s "Project Structure" section previously read:

> `llm_fixtures.json               # 20 fixtures (15 gemini_live + 5 synthetic_manual)`

This contradicted the file's actual current state (verified in Phase 1: all 20 entries have `"source": "gemini_live"`) and contradicted two other lines in the same README that already stated "all 20 entries are `gemini_live`". Corrected to:

> `llm_fixtures.json               # 20 fixtures, all "source": "gemini_live"`

No experimental results, numbers, or claims were invented — this is a wording-only fix to match evidence already gathered in Phase 1 (`docs/history/PROJECT_STATUS_AUDIT.md`, Section D).

---

## Task 4 — Regression Results

| Check | Command | Result |
|---|---|---|
| Backend unit tests | `python -m pytest tests/ -v` | **10/10 passed** (10.11s) |
| Frontend TypeScript/build | `cd frontend && npm run build` | **Success**, 0 errors, identical output artifacts to pre-cleanup build (only the pre-existing >500KB bundle-size warning, unchanged) |
| FastAPI startup | `uvicorn app:app --port 8124` | **Started successfully** |
| API smoke test — `GET /api/station` | curl | **200 OK**, correct JSON (3 ports, empty queue) |
| API smoke test — `POST /api/negotiate` with `force_fallback: true` | curl | **200 OK**, correctly used telemetry fallback path (`fallback_used: true`, `parsing_success: false`), no LLM call made |
| API smoke test — `GET /api/benchmarks` | curl | **200 OK**, both allowlisted files (`phase4c5_results.json`, `phase5_results.json`) loaded as dicts |
| Live Gemini call | — | **Not performed** (explicitly out of scope for this cleanup pass) |

Test server process was located via `netstat` and terminated by PID after verification in both smoke-test runs.

---

## Still Unresolved (carried forward from `docs/history/PROJECT_STATUS_AUDIT.md`)

- **P0** — Whether the previously-exposed Gemini key was ever revoked cannot be verified from the repo; this requires direct action in the Google AI Studio console, outside the scope of any code-level cleanup.
- **P0** — No git repository exists yet. `git init` + first commit was deliberately not performed in this pass (out of scope; also `.env` handling and `.pth` checkpoint tracking policy should be decided before that commit).
- **P0** — A real live Gemini call through `/api/negotiate` has still never been exercised in an audited session; this remains the single biggest open question about whether the AI integration works end-to-end today.
- **P1** — Orphaned DQN checkpoints `ev_dqn_model.pth`, `_v2`, `_v3`, `_v4` still have no established provenance and are not referenced by any current code path (only `_v5` is loaded).
- **P2** — No timeout is set on the Gemini SDK call in `llm_negotiator.py`.
- **P2** — No browser/E2E test coverage exists.
- **P2** — Frontend bundle size warning (686KB) unchanged; not addressed in this pass (explicitly P2/optional).

No new issues were introduced by this cleanup pass; all changes were additive/subtractive hygiene fixes with no behavioral changes to the running application, confirmed by identical regression results and identical build artifacts.
