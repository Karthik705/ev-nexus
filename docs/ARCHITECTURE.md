# EV NEXUS — Architecture

> **Two engines live in this repository, deliberately.**
>
> | | `simple_ev_simulation.py` (v1) | `schedule_engine.py` (v2) |
> |---|---|---|
> | Backs | `/api/negotiate`, Overview & Charging pages | `/api/compare`, Scheduler & Benchmarks pages, `benchmark_v2.py` |
> | Purpose | Interactive single-request demo | Policy comparison and the benchmark |
> | Status | Working, kept for the live negotiation demo | Current evaluation engine |
>
> v2 was written rather than retrofitted because the v1 engine had fairness defects
> baked into its dispatch loop (budget enforced only for agent policies, arrival
> streams diverging between policies). Rewriting those in place would have silently
> changed the historical results; keeping them separate preserves provenance and lets
> the old numbers stay auditable. The v2 engine backs **both** the benchmark and the
> live comparison page, so the website demonstrates the identical computation the
> benchmark reports.
>
> ## v2 data flow
>
> ```
> scenario_library.py          20 driver messages + hand-authored ground truth
>         |                    + deterministic arrival-stream generator
>         v
> llm_fixtures.json            captured Gemini extractions (the agent's only language input)
>         |
>         v
> schedule_engine.py           one stream -> every policy, identical physics
>   |-- _apply_agent_beliefs()   language + telemetry -> validated urgency, deadline
>   |-- _dispatch_conventional() FIFO / SJF / lowest-SOC, best-fit port
>   |-- _dispatch_agent()        greedy max-weight (car, port) matching
>   '-- _summarise()             metrics + Gantt timeline
>         |
>         +--> benchmark_v2.py -> benchmark_v2_results.json  (paired bootstrap)
>         '--> app.py /api/compare -> Scheduler page         (live, same code)
> ```
>
> Ground truth flows only into `_summarise()` (grading), never into
> `_apply_agent_beliefs()` (deciding). A test enforces this causally.

---


This document traces the actual, current data flow through the system, with file paths and line references. It reflects the code as of this finalization pass, not aspirational design.

## High-Level Flow

```
┌─────────────┐     ┌──────────────┐     ┌────────────────┐     ┌──────────────┐
│  React UI   │───▶│  FastAPI     │───▶│  Gemini (or     │───▶│  Deterministic│
│  (frontend/)│◀───│  app.py      │◀───│  fallback)      │◀───│  Validator    │
└─────────────┘     └──────┬───────┘     └────────────────┘     └──────┬───────┘
                            │                                            │
                            ▼                                            ▼
                    ┌───────────────┐                          ┌────────────────┐
                    │  Simulation   │◀─────────────────────────│  Scheduler /   │
                    │  State        │                           │  Port Assign   │
                    └───────────────┘                           └────────────────┘
```

## Frontend

- Entry: `frontend/src/main.tsx` → `App.tsx` (React Router shell, sidebar nav, live health indicator).
- Pages: `frontend/src/pages/{Overview,Charging,Analytics,Benchmarks,Architecture}Page.tsx`.
- API client: `frontend/src/api.ts` — single module, all backend calls go through it. Base URL is `import.meta.env.VITE_API_BASE`, falling back to `http://127.0.0.1:8000/api` for local dev.
- No page calls Gemini directly; no Gemini key or SDK reference exists anywhere in `frontend/` (verified by repository-wide grep in this pass).

## Backend Entry — `app.py`

FastAPI app. Routes (all under `/api`):

| Route | Handler | Notes |
|---|---|---|
| `GET /health` | `health_check()` | Added this pass. Pure liveness check, touches no state, no Gemini. |
| `POST /negotiate` | `negotiate()` | The core pipeline entry point (see below). |
| `GET /station` | `get_station_status()` | Ports, queue, metrics for a session. |
| `POST /step` | `step_simulation()` | Advances simulated time without new arrivals. |
| `POST /reset` | `reset_simulation()` | Replaces a session's simulation with a fresh one. |
| `POST /new-session` | `create_session()` | Issues a new UUID session. |
| `GET /benchmarks` | `get_benchmarks()` | Serves an explicit allowlist of 2 JSON files — `app.py` comments document that this replaced an earlier unauthenticated glob-over-`*.json` design. |

State: `_SESSIONS: Dict[str, EVChargingSimulation]` (`app.py:63`), an in-process dict keyed by `session_id`. No persistence, no TTL — documented as a known limitation, not silently hidden.

## The `/api/negotiate` Pipeline

1. **Intent extraction** — `GeminiNegotiator.negotiate()` (`llm_negotiator.py:48-124`). Sends the driver's raw message to Gemini (`gemini-flash-latest`, `temperature=0.0`), requests strict JSON matching `LLMParsedRequest`. On any exception, `_classify_error()` (`llm_negotiator.py:126-171`) labels the failure (`AUTH_ERROR`, `MODEL_NOT_FOUND`, `RATE_LIMIT`, `PARSE_ERROR`, `TIMEOUT`, `UNKNOWN_ERROR`) and the call returns `(None, latency, False)` rather than raising uncontrolled.
2. **Validation** — `ConstraintValidator.validate_request()` (`constraint_validator.py:8-64`). Telemetry fields (`actual_soc`, `battery_capacity`, `max_charging_speed`, `budget`) come only from the caller's request body, never from the LLM. The LLM's `urgency_level` becomes a numeric score, then the lie detector (`constraint_validator.py:36-39`) forces it down if it's inconsistent with actual SOC. If parsing failed or was bypassed, `_create_fallback_request()` (`constraint_validator.py:66-102`) computes urgency purely from SOC tiers.
3. **EV creation and dispatch** — `app.py` builds an `EVAgent` with `target_battery = 0.8 * req.battery_capacity` (fixed this pass — previously a hardcoded absolute `80`, see `docs/TEST_REPORT.md`), adds it to `sim.scheduler.queue`, and calls `sim.step()`.
4. **Scheduling** — `EVChargingSimulation.step()` (`simple_ev_simulation.py:293-374`). For the interactive UI, `policy='LLM_DETERMINISTIC'` (set in `app.py`'s `_new_sim()`), which takes the deterministic dispatch branch (`simple_ev_simulation.py:343-372`): finds feasible ports from `validated_request.feasible_ports`, picks the closest-speed match, and — this pass's fix — no longer silently drops an over-budget EV without telling the caller (`app.py` now inspects post-dispatch state and returns `status: "REJECTED_BUDGET"` instead of a misleading `"WAITING"`).
5. **Response** — `ev_id`, `llm_result`, `validation_result`, `assigned_port`, `status` (`CHARGING` / `WAITING` / `REJECTED_BUDGET`), `fallback_used`, `priority_score`.

## Simulation Core

- `simple_ev_simulation.py` — canonical simulator: `EVAgent`, `ChargingPort`, `ChargingStation`, `Scheduler`, `EVChargingSimulation`. All other simulation-adjacent scripts import from this file rather than reimplementing it.
- `visual_ev_simulation.py` — a terminal-dashboard wrapper around the same canonical simulation (`visual_ev_simulation.py:15` imports `EVChargingSimulation`), used for CLI demos before the React UI existed. Not a competing implementation.
- `ev_gym_env.py` — Gymnasium wrapper (`EVChargingEnv`) around the same simulator, used only for DQN training/inference. 42-dim observation space, 26-action discrete action space (`ev_gym_env.py:23-29`).

## DQN Path (Experimental, Isolated)

`app.py` never imports `dqn_agent` or `ev_gym_env` — the interactive demo cannot invoke DQN. DQN is only reachable via:
- `simple_ev_simulation.py:206-214` — if `policy == 'DQN'`, loads `ev_dqn_model_v5.pth` into a `DQNAgent(42, 26)`, used by `experiment_comparison.py`'s benchmark runs.
- `dqn_agent.py`'s own `__main__` training loop.
- `controlled_scenarios.py` — a standalone manual demo script, loads `ev_dqn_model_v4.pth` by default.

Full checkpoint provenance: `docs/DQN_PROVENANCE.md`.

## Experiment / Benchmark Pipeline

`experiment_comparison.py` loads `llm_fixtures.json`, replays cached (not live) Gemini outputs across FIFO/PRIORITY/SJF/TELEMETRY_ONLY/LLM_NEGOTIATOR/DQN policies, 30 runs × 3 congestion scenarios, and writes `phase5_results.json`. `app.py`'s `/api/benchmarks` route serves this file (plus `phase4c5_results.json`) to the frontend's Benchmarks page, which renders it with an explicit "source: phase5_results.json" / "Fixture-based LLM replay" label — never presented as live data.

## Security Boundary

- Gemini API key: read from `GEMINI_API_KEY` env var or `.env` (`app.py:20-27`, `llm_negotiator.py:23-32`) — server-side only. Never sent to, or present in, any frontend file or build artifact (verified by repository-wide secret scan this pass).
- CORS: `ALLOWED_ORIGINS` env var, defaults to localhost dev origins only (`app.py:46-55`).
- `/api/benchmarks` uses an explicit allowlist, not a directory glob (`app.py:280-298`).
