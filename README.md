# EV NEXUS — LLM-Assisted EV Charging Negotiator

An EV charging station simulator that accepts natural-language driver requests, extracts structured intent with Gemini, validates that intent against real telemetry (so the LLM can never override physical safety constraints), and dispatches EVs to charging ports with a resource-aware priority scheduler. Includes a React operations dashboard, a full FastAPI backend, a reproducible policy-comparison benchmark suite, and an experimental DQN baseline.

## Table of Contents

- [Problem Statement](#problem-statement)
- [Key Features](#key-features)
- [Architecture](#architecture)
- [Technology Stack](#technology-stack)
- [How the LLM Is Used](#how-the-llm-is-used)
- [Safety / Validation Architecture](#safety--validation-architecture)
- [Scheduling Algorithms](#scheduling-algorithms)
- [DQN Experimental Findings](#dqn-experimental-findings)
- [Benchmark Methodology](#benchmark-methodology)
- [Important Results](#important-results)
- [Limitations](#limitations)
- [Local Setup](#local-setup)
- [Environment Variables](#environment-variables)
- [API Endpoints](#api-endpoints)
- [Testing](#testing)
- [Deployment](#deployment)
- [Project Structure](#project-structure)
- [Future Improvements](#future-improvements)

---

## Problem Statement

EV charging stations must balance:

- driver urgency (stated in natural language)
- charging deadlines
- battery state (SOC telemetry)
- charging-port compatibility
- station congestion
- driver budgets

Traditional scheduling algorithms cannot interpret natural-language driver requirements. A driver saying "my wife is in labor" carries more scheduling weight than a driver saying "I'm not in a rush" — but only an NL-aware system can distinguish them. At the same time, a system that blindly trusts what a driver *claims* is unsafe: it can be gamed. EV NEXUS's core design bet is that an LLM should **interpret** language, while a deterministic layer **enforces** physical truth.

## Key Features

- Natural-language driver request → structured intent (Gemini 2.5 Flash / `gemini-flash-latest`)
- Deterministic "lie detector": downgrades urgency claims that contradict telemetry (e.g. claiming `CRITICAL` at 85% SOC)
- Automatic, transparent fallback to telemetry-only priority when Gemini is unavailable, rate-limited, or returns malformed output
- Resource-aware port assignment (7 kW / 50 kW / 150 kW ports, matched to vehicle charging capability)
- Budget-aware dispatch — a request whose estimated cost exceeds its budget is honestly reported as **rejected**, not silently queued (see [Limitations](#limitations) for the bug this replaced)
- Six-policy benchmark suite (FIFO, PRIORITY, SJF, TELEMETRY_ONLY, LLM_NEGOTIATOR, DQN) over reproducible fixture-based scenarios
- React dashboard: Overview (interactive negotiation), Charging (live session monitor), Analytics, Benchmarks, Architecture
- Live backend health check surfaced in the UI (not a static "always online" badge)
- Per-session simulation state so concurrent demo users don't corrupt each other's runs

## Architecture

```
Driver NL message
       ↓
  Gemini 2.5 Flash                 (llm_negotiator.py)
  (structured intent extraction)
       ↓
  Deterministic Validator          (constraint_validator.py)
  (SOC contradiction check, budget/port feasibility)
       ↓
  Resource-Aware Priority Scheduler (simple_ev_simulation.py)
  (urgency × wait × deadline pressure)
       ↓
  Charging Station Port Assignment
```

Full component-level data flow, file paths, and the FastAPI route map are in **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)**.

### Safety Invariant

The LLM **interprets** intent; it cannot override physical constraints. The deterministic validation layer always enforces:
- Actual SOC (from telemetry, not self-report)
- Maximum charging speed
- Budget cap
- Port availability

If a driver claims `CRITICAL` urgency but has 85% SOC, the validator downgrades them to `LOW` priority and flags the contradiction. This is directly testable: `tests/test_core.py::test_lie_detector_contradiction_triggered`.

## Technology Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.11, FastAPI, Pydantic, Uvicorn |
| LLM | Google Gemini (`google-genai` SDK, `gemini-flash-latest`) |
| Simulation / RL | NumPy, PyTorch, Gymnasium (DQN experimental baseline) |
| Frontend | React 19, TypeScript, Vite 8, React Router, Recharts, Tailwind |
| Testing | pytest (backend), `tsc` + Vite build (frontend type/build check) |

## How the LLM Is Used

`llm_negotiator.py`'s `GeminiNegotiator.negotiate()` sends the raw driver message to Gemini with a prompt that requests strict JSON: `urgency_level`, `deadline_minutes`, `reason_category`, `claimed_constraints`, `requested_port_type`, `confidence`, `explanation`. The call runs at `temperature=0.0`. Failures are classified (`AUTH_ERROR`, `MODEL_NOT_FOUND`, `RATE_LIMIT`, `PARSE_ERROR`, `TIMEOUT`, `UNKNOWN_ERROR`) rather than swallowed silently, and every classification is logged in `negotiator.error_log`.

**The application has deterministic fallback behavior whenever Gemini is unavailable.** If the call fails for any reason, or `force_fallback` is requested, the system falls back to computing urgency purely from telemetry (SOC tiers: <20% → `TELEMETRY_CRITICAL`, <50% → `TELEMETRY_MEDIUM`, else `TELEMETRY_LOW`). This is exercised by `tests/test_core.py::test_negotiate_no_client_returns_fallback` and is toggleable live in the UI via the "Force fallback" checkbox on the Overview page.

## Safety / Validation Architecture

`constraint_validator.py`'s `ConstraintValidator.validate_request()` is the single point where LLM output meets telemetry:

- `actual_soc`, `battery_capacity`, `max_charging_speed`, `budget` are always taken from the caller-supplied telemetry arguments — **never** from the LLM's parsed output. The LLM cannot set or override any of these fields.
- The LLM's `urgency_level` is mapped to a numeric score, then the **lie detector** fires: if the claimed urgency score is above 0.5 *and* actual SOC is above 60%, the score is forced down to 0.2 and `contradiction_found=True` is set.
- Feasible ports are computed from the actual (not claimed) port occupancy state.

This means a driver cannot talk their way into skipping the queue with a fabricated emergency if their battery telemetry contradicts the claim — verified in `tests/test_core.py` with boundary tests at exactly 60% and 61% SOC.

## Scheduling Algorithms

| Policy | Description |
|---|---|
| **FIFO** | First-In First-Out — fair but ignores urgency |
| **PRIORITY** | Urgency-based — serves critical EVs first |
| **SJF** | Shortest Job First — maximises throughput |
| **TELEMETRY_ONLY** | Deterministic SOC-based urgency, no NL parsing |
| **LLM_NEGOTIATOR** | Full pipeline: Gemini → validator → scheduler |
| **DQN** | Deep Q-Network (**experimental baseline only** — see below) |

## DQN Experimental Findings

DQN was investigated extensively but exhibited reward hacking and value-hoarding behaviour in the discrete-time formulation: the agent learned to defer dispatching indefinitely to avoid negative rewards rather than optimising utilisation. It consistently produced the lowest satisfaction scores across all scenarios (0.09–0.13 vs 0.31–0.61 for heuristics). **DQN is retained as an experimental baseline only — it is not claimed to be competitive with the deterministic schedulers.**

The checkpoint behind the DQN numbers reported below is `ev_dqn_model_v5.pth` (42-dim state, 26-dim action, matching the current `ev_gym_env.py`). Four earlier checkpoints (`ev_dqn_model.pth`, `_v2`, `_v3`, `_v4`) exist on disk from earlier iterations of the environment (some with a 20-dim, some a 25-dim observation space, incompatible with the current architecture) and are kept for historical reference only — they are **not** used in any current result. Full checkpoint-by-checkpoint provenance, including what loads, what doesn't, and what evidence exists for each, is documented in **[docs/DQN_PROVENANCE.md](docs/DQN_PROVENANCE.md)**.

## Benchmark Methodology

Phase 5 uses **fixture-based LLM replay**: real Gemini outputs were captured once per canonical driver-message scenario using `generate_fixtures.py` (with exponential-backoff retry), then replayed deterministically across a 30-run × 3-scenario × 6-policy ablation. This is the intentional experimental design, not a degraded fallback — it removes API quota, latency, and nondeterminism from the throughput benchmark while still exercising real Gemini outputs, and makes the experiment reproducible without network access.

**`llm_fixtures.json` currently contains 20 canonical scenario fixtures, all labelled `"source": "gemini_live"`** — captured from real Gemini Flash responses. (An earlier version of this file had 5 of the 20 as hand-authored `synthetic_manual` placeholders, from a period when the configured API key was an OAuth token rather than a Gemini API key; all 20 have since been backfilled with live Gemini output.) Full methodology, reproduction steps, and what has vs. hasn't been re-verified in the current codebase are in **[docs/EXPERIMENTS.md](docs/EXPERIMENTS.md)**.

**Important scope note:** the numbers below are historical results from a specific run of `experiment_comparison.py` (`phase5_results.json`, generated 2026-09-23) — not a live measurement re-run for this README, and not the output of live per-request Gemini calls during a user's browsing session. The Benchmarks page in the UI itself labels this data as fixture-based and historical, not live production telemetry.

## Important Results

### Phase 5 Results (30 runs × 3 scenarios × 6 policies, historical — see scope note above)

#### LOW congestion (2.5 EVs/hr)

| Policy | Avg Wait | Crit Wait | Satisfaction | EVs Served | Revenue |
|---|---|---|---|---|---|
| **LLM_NEGOTIATOR** | **1.72h** | 3.68h | **0.612** | 18.1 | $1,033 |
| SJF | 1.58h | 5.47h | 0.589 | 24.4 | $1,641 |
| TELEMETRY_ONLY | 2.21h | 3.49h | 0.545 | 18.3 | $1,026 |
| PRIORITY | 3.68h | 5.29h | 0.453 | 17.1 | $1,598 |
| FIFO | 4.21h | 6.74h | 0.382 | 17.2 | $1,472 |
| DQN | 4.34h | 4.79h | 0.134 | 12.7 | $910 |

#### MEDIUM congestion (5.0 EVs/hr)

| Policy | Avg Wait | Crit Wait | Satisfaction | EVs Served | Revenue |
|---|---|---|---|---|---|
| SJF | 1.62h | 7.84h | 0.590 | 34.2 | $3,484 |
| **LLM_NEGOTIATOR** | **2.40h** | **4.45h** | **0.558** | 20.3 | $1,359 |
| TELEMETRY_ONLY | 3.34h | 4.42h | 0.422 | 19.9 | $1,323 |
| PRIORITY | 5.32h | 7.90h | 0.350 | 18.5 | $3,190 |
| FIFO | 5.82h | 9.15h | 0.312 | 18.3 | $2,651 |
| DQN | 4.45h | 4.55h | 0.095 | 15.4 | $1,199 |

#### HIGH congestion (8.5 EVs/hr)

| Policy | Avg Wait | Crit Wait | Satisfaction | EVs Served | Revenue |
|---|---|---|---|---|---|
| SJF | 1.59h | 9.37h | 0.601 | 41.0 | $6,476 |
| **LLM_NEGOTIATOR** | **2.84h** | **3.81h** | **0.507** | 21.8 | $1,550 |
| PRIORITY | 5.82h | 9.61h | 0.348 | 16.5 | $5,031 |
| TELEMETRY_ONLY | 3.68h | 3.85h | 0.313 | 23.0 | $1,621 |
| FIFO | 6.84h | 10.41h | 0.310 | 16.9 | $3,978 |
| DQN | 3.66h | 4.03h | 0.113 | 15.3 | $1,264 |

**LLM_NEGOTIATOR consistently outperforms TELEMETRY_ONLY on driver satisfaction (+11% LOW, +34% MEDIUM, +62% HIGH) and avg wait time**, by using natural-language deadline and reason context to prioritise more accurately than SOC alone. The satisfaction improvement is larger under higher congestion — the NL context matters most when queuing pressure forces hard trade-offs between EVs.

### Known Trade-off: SJF Throughput vs Fairness

SJF achieves the highest throughput and revenue under all congestion levels, but at a significant cost to **critical EV wait times**: 76% worse (MEDIUM) to 149% worse (HIGH) than LLM_NEGOTIATOR. SJF maximises the number of EVs served (more shorter jobs → more completions) but starves high-urgency, high-energy-demand EVs (medical emergencies, dead-battery panics) that take longer to charge. Use PRIORITY or LLM_NEGOTIATOR when driver experience and critical-EV fairness matter; use SJF only in throughput/revenue-maximising settings where all EVs are roughly equivalent.

These numbers were re-verified against the current `phase5_results.json` in this repository via `scripts/read_results.py` during the most recent finalization pass — they were not silently altered.

## Limitations

- **Gemini live calls are not verified as part of this repository's automated testing.** All backend tests and API smoke tests use `force_fallback=True` or cached fixtures, deliberately, to avoid unpredictable API cost/availability during development and CI. The deterministic fallback path is fully tested; the live Gemini call path is exercised only manually (`test_negotiator.py`, `acceptance_test.py`) and its current live status is **unverified** in this audit pass. Do not assume Gemini is always available — the system is designed to degrade gracefully when it isn't.
- **`app.py` uses per-session, in-process state** (keyed by `session_id`), sufficient for a local demo but not production: state is lost on restart and not shared across replicas, and there is no session TTL/cleanup.
- **Fixed bug (this pass):** the target charge level was previously a hardcoded 80 kWh (not 80%), so any vehicle with a battery smaller than 80 kWh would show an SOC reading above 100% while charging. Fixed to be 80% of that vehicle's own capacity in both the interactive `/api/negotiate` path and the simulator's random-EV generator. See `docs/TEST_REPORT.md`.
- **Fixed bug (this pass):** an over-budget request was previously silently dropped by the scheduler but reported to the frontend as `"WAITING"` (indistinguishable from a genuinely queued request). The API now reports `"REJECTED_BUDGET"` and the UI shows an explicit rejection state. See `docs/TEST_REPORT.md`.
- No persistent time-series analytics — the Analytics page is explicit about this in its own UI copy.
- No browser/E2E test suite exists; this has not been added in this pass (no browser automation tooling was available in the environment used for this work — see `docs/TEST_REPORT.md`).
- CORS defaults to `http://localhost:5173` for local development; **must** be set explicitly via `ALLOWED_ORIGINS` for any deployment.
- Frontend bundle is a single ~687 KB chunk (Vite warns above 500 KB) — not code-split. Cosmetic, not a functional issue.

## Local Setup

### Backend Setup

```bash
pip install fastapi uvicorn "google-genai" torch pytest
cp .env.example .env        # then edit .env and set GEMINI_API_KEY
uvicorn app:app --reload
```

### Frontend Setup

```bash
cd frontend
npm install
cp .env.example .env        # optional — only needed to override the backend URL
npm run dev
```

Frontend defaults to `http://127.0.0.1:8000/api` if `VITE_API_BASE` is unset — no `.env` is required for local development against a backend on the default port.

## Environment Variables

| Variable | Where | Purpose | Default |
|---|---|---|---|
| `GEMINI_API_KEY` | backend `.env` | Gemini API key. If unset or invalid, the app deterministically falls back to telemetry-only priority — it does not crash. | none (fallback used) |
| `ALLOWED_ORIGINS` | backend env | Comma-separated CORS allowlist. | `http://localhost:5173,http://127.0.0.1:5173` |
| `VITE_API_BASE` | frontend `.env` (build-time) | Backend API base URL, e.g. `https://your-backend.example.com/api`. | `http://127.0.0.1:8000/api` |

Never commit a real `.env` file — `.env.example` files (root and `frontend/`) contain only safe placeholders and are the ones meant to be tracked in version control.

## API Endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/health` | Liveness probe — used by the frontend's connection indicator and suitable for deployment platform health checks. |
| `POST` | `/api/negotiate` | Full pipeline: LLM (or fallback) → validation → scheduling → dispatch for one driver request. |
| `GET` | `/api/station` | Current port/queue/metrics state for a session. |
| `POST` | `/api/step` | Advance the simulation clock without adding new EVs. |
| `POST` | `/api/reset` | Reset a session's simulation to a clean state. |
| `POST` | `/api/new-session` | Allocate a new isolated `session_id`. |
| `GET` | `/api/benchmarks` | Serves an explicit allowlist of two historical benchmark JSON files (`phase4c5_results.json`, `phase5_results.json`). |

## Testing

```bash
# Backend
pytest tests/ -v

# Frontend type check + production build
cd frontend
npm run build
```

There is no automated frontend test suite (no `*.test.tsx` files) and no browser/E2E suite in this repository. See **[docs/TEST_REPORT.md](docs/TEST_REPORT.md)** for the exact commands run, their results, and what remains explicitly unverified.

## Deployment

This repository is configured for deployment (configurable frontend API URL, environment-based secrets, allowlisted CORS) but **has not been deployed** as of this pass — there is no live URL. See **[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)** for the prepared deployment steps and what remains to be done by a human with hosting-provider access.

## Project Structure

```
├── app.py                          # FastAPI backend (per-session state, health check, hardened CORS)
├── simple_ev_simulation.py         # Core EV charging simulation (canonical scheduler + simulator)
├── llm_negotiator.py               # Gemini API wrapper with call counters and error classification
├── constraint_validator.py         # Lie detector + feasibility/budget checker
├── negotiation_types.py            # Dataclasses: LLMParsedRequest, ValidatedChargingRequest
├── experiment_comparison.py        # Phase 5 ablation runner (fixture-based)
├── sensitivity_experiment.py       # Phase 5 re-run restricted to gemini_live-only fixtures
├── generate_fixtures.py            # Fixture generator with exponential-backoff retry
├── llm_fixtures.json               # 20 fixtures, all "source": "gemini_live"
├── phase5_results.json             # Full ablation (20 fixtures, 30 runs) — historical
├── phase5_sensitivity_results.json # Ablation restricted to 15 gemini_live fixtures — historical
├── phase4c5_results.json           # Earlier fixture-based run — historical
├── dqn_agent.py                    # DQN architecture + training loop (produces ev_dqn_model_v5.pth)
├── ev_gym_env.py                   # Gym environment wrapper (42-dim state, 26-action space)
├── ev_dqn_model_v5.pth             # Canonical DQN checkpoint — see docs/DQN_PROVENANCE.md
├── ev_dqn_model.pth, _v2–_v4.pth   # Historical/orphaned checkpoints — see docs/DQN_PROVENANCE.md
├── visual_ev_simulation.py         # Legacy terminal dashboard (CLI demo, superseded by the React UI)
├── controlled_scenarios.py         # Standalone manual DQN scenario demo (not part of automated tests)
├── acceptance_test.py, test_negotiator.py  # Manual acceptance/demo scripts — some paths make live Gemini calls; not part of pytest (see docs/TEST_REPORT.md)
├── scripts/                        # Ad hoc diagnostic scripts (not automated) — see scripts/README.md
├── tests/
│   └── test_core.py                # pytest suite (10 tests)
├── archive/                        # Retired result files (avg_satisfaction=0.0 bug) — kept for provenance, not used
├── docs/                           # Architecture, experiments, test report, deployment, provenance, resume docs
└── frontend/                       # React + TypeScript UI (Overview, Charging, Analytics, Benchmarks, Architecture)
```

## Future Improvements

- Persistent session store (Redis/DB) with TTL, replacing the in-process dict, for real multi-user/multi-replica deployment.
- Browser/E2E test coverage (Playwright or similar) for the full negotiation → scheduling → charging → reset user journey.
- Per-constraint pass/fail fields returned by `/api/negotiate` (budget, charging-rate, port compatibility) so the frontend's Safety Validation panel can show genuinely dynamic per-request checks instead of illustrative static ones for the non-urgency constraints.
- Code-splitting the frontend bundle.
- A verified, timestamped live-Gemini smoke test recorded in `docs/TEST_REPORT.md` once a key is confirmed valid and the user authorizes a live call.
