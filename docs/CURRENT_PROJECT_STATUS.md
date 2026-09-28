# EV NEXUS — Current Project Status (Checkpoint)

This file is the resumable checkpoint for ongoing implementation work. It supersedes nothing — `PROJECT_STATUS_AUDIT.md` (Phase 1 audit) and `docs/PHASE_1_5_CLEANUP.md` (hygiene cleanup) remain the historical record. This file tracks what's been done *since* those, and what's next, so a new session can resume without replaying this conversation.

`docs/PROJECT_COMPLETION_PLAN.md` referenced by the standing instructions does not exist yet — it will be created once enough phases have run to justify a full forward plan; until then this checkpoint file plus the audit's Section J/K backlog serve that role.

---

## Status as of this checkpoint

- Phase 1 (read-only audit): **complete** — see `PROJECT_STATUS_AUDIT.md`.
- Phase 1.5 (hygiene cleanup): **complete** — see `docs/PHASE_1_5_CLEANUP.md`. Verified still valid (spot-checked: `frontend-temp` absent, `.gitignore` fixed, README fixture line fixed, no git repo yet).
- Implementation Phase 1 ("resolve verified blockers"): **in progress** — one item done this session, see below.

## Change made this session

**Item:** Backlog P1 item #7 — frontend backend URL was hardcoded, blocking any future deployment.

**Files changed:**
- `frontend/src/api.ts` — `API_BASE` now reads `import.meta.env.VITE_API_BASE`, falling back to `http://127.0.0.1:8000/api` when unset.
- `frontend/.env.example` (new) — documents `VITE_API_BASE` as a safe, non-secret placeholder (it's a public URL, not a credential).

**Verification performed:**
- `npm run build` with `VITE_API_BASE` unset → succeeds, output byte-identical to pre-change build (confirms default path unaffected).
- `npm run build` with `VITE_API_BASE=https://example-deployed-backend.com/api` → succeeds, confirmed via grep that the override value is correctly baked into the built JS bundle.
- Rebuilt with default settings afterward to leave the working tree in its normal local-dev state.
- `python -m pytest tests/ -v` → 10/10 passed (backend untouched, run to confirm no unrelated regression).

**Why this item first:** All three P0s from the audit (Gemini key revocation confirmation, `git init`, a live Gemini smoke call) require either your out-of-band action (AI Studio console) or explicit approval not yet given in-session. This was the first P1 that is safe, local, non-destructive, requires no approval, and directly unblocks the later deployment phase (Phase 6 of the standing instructions requires "the frontend uses a configurable public backend URL").

## Still open — P0 (blocked on you, not on code)

1. Confirm/rotate the previously-exposed Gemini key in the Google AI Studio console. Not a code task — cannot be done from this session.
2. `git init` + first commit. Not performed — standing instructions require explicit approval before any git initialization.
3. One live `/api/negotiate` call to confirm the Gemini integration works end-to-end today. Not performed — requires your explicit approval (possible minor API cost). Until authorized, live Gemini status remains **UNVERIFIED**; the deterministic telemetry fallback path is the only Gemini-adjacent behavior verified in this repo so far (Phase 1 + this session both re-confirmed it via `force_fallback: true`).

## Still open — P1 (executable, not yet done)

4. Add screenshots of the running app to `README.md` (Overview, Charging, Benchmarks pages) — requires running the app and capturing images; not done this session.
5. Add a short "AI-assisted development" note to `README.md` describing what was human-verified vs. AI-generated.
6. Orphaned DQN checkpoints `ev_dqn_model.pth`, `_v2.pth`, `_v3.pth`, `_v4.pth` still lack established provenance (only `_v5.pth` is loaded by current code, per `simple_ev_simulation.py:213`). This maps to standing-instructions Phase 3 ("identify the exact DQN model and experiment versions") — next natural step if continuing implementation work.

## Still open — P2 (optional)

7. No timeout set on the Gemini SDK call (`llm_negotiator.py:94-98`).
8. No browser/E2E test coverage exists anywhere in the repo.
9. Frontend bundle-size warning (686KB main chunk) — cosmetic, not urgent.

## DQN checkpoint provenance investigation — COMPLETE

Full findings: `docs/DQN_PROVENANCE.md`. Read-only: no retraining, no reward/simulator changes, no benchmark edits, no renames/deletions, no API calls, no git actions. Method: grepped every reference to each `.pth` filename, then loaded each checkpoint's raw `state_dict` (passive deserialization only) to read actual tensor shapes and test-load them into the current `DQN(42,26)` architecture.

**Results:**
- `ev_dqn_model.pth` (v1): 20-dim state / 6 actions. **ORPHANED** — no current code references it, incompatible with current architecture, training env lost.
- `ev_dqn_model_v2.pth`, `_v3.pth`: 25-dim state / 6 actions (identical to each other). **ORPHANED** — same reasoning.
- `ev_dqn_model_v4.pth`: 42-dim / 26 actions — **matches current architecture and loads successfully.** **New finding:** genuinely referenced by `controlled_scenarios.py:22` (a standalone, non-automated dev-utility script) — not orphaned in the strict sense, but not part of the product or benchmark pipeline either. Weights are numerically distinct from v5 (confirmed via direct tensor diff), so it's a real separate training checkpoint, not a copy. Classified **PARTIALLY VERIFIED**.
- `ev_dqn_model_v5.pth`: 42-dim / 26 actions, loads successfully, produced by `dqn_agent.py`'s training loop, consumed by `simple_ev_simulation.py:213` (the only checkpoint in the live interactive/benchmark path). Phase 1 audit's "VERIFIED, canonical" conclusion **re-confirmed** with harder evidence (direct shape/load test, not just filename inference).
- Circumstantial (not proven) link: `archive/dqn_comparison_results.json` (the retired, `avg_satisfaction=0.0`-bug file) predates v2–v5 by timestamp, making `ev_dqn_model.pth` the only checkpoint that could have produced it — inferred from timeline ordering only, explicitly flagged as unproven in the report.

**Verdict on defensibility (Section F of the report):** the DQN section as currently documented in `README.md` is technically defensible — its "experimental baseline, value-hoarding failure mode" framing is corroborated by code (`ev_gym_env.py:89-90` reward-shaping comment). The only real gap was that 4 undocumented checkpoints existed on disk; that gap is now closed by `docs/DQN_PROVENANCE.md` existing.

**Recommended next task (from the report):** add a short note to `README.md`'s RL Findings section stating `ev_dqn_model_v5.pth` is the sole checkpoint behind the reported results, linking to `docs/DQN_PROVENANCE.md`. 5–10 min, zero risk, no approval needed — not yet done, next up if continuing.

## Still open — P1 (updated)

4. Screenshots — not done.
5. README "AI-assisted development" note — not done.
6. ~~DQN checkpoint provenance~~ — **DONE**, see above. New follow-up: add the short README RL-Findings note described above (small enough it could be folded into item 5's README pass).

No git commits, deployment, key rotation, or live API calls have been made in this session.
