# EV NEXUS — Test Report

All commands below were actually executed during this finalization pass. No result is reported as passing without having run. No live Gemini API calls were made anywhere in this report.

## Backend — pytest

```
$ python -m pytest tests/ -v
```

Result (re-run multiple times throughout this pass, after each backend code change, to confirm no regression):

```
tests/test_core.py::test_lie_detector_contradiction_triggered PASSED
tests/test_core.py::test_lie_detector_boundary_60pct_medium_no_contradiction PASSED
tests/test_core.py::test_lie_detector_boundary_just_above_60pct_high_contradiction PASSED
tests/test_core.py::test_fallback_telemetry_tiers[10.0-0.9-TELEMETRY_CRITICAL] PASSED
tests/test_core.py::test_fallback_telemetry_tiers[35.0-0.5-TELEMETRY_MEDIUM] PASSED
tests/test_core.py::test_fallback_telemetry_tiers[70.0-0.2-TELEMETRY_LOW] PASSED
tests/test_core.py::test_budget_rejection_drops_ev PASSED
tests/test_core.py::test_resource_aware_port_matching PASSED
tests/test_core.py::test_fixture_negotiate_returns_correct_request PASSED
tests/test_core.py::test_negotiate_no_client_returns_fallback PASSED

10 passed
```

10/10, consistently, before and after all code changes in this pass.

## Backend — Live API Smoke Tests (via `curl` against a locally started `uvicorn` instance)

All requests used `"force_fallback": true` or unit-level calls — **no live Gemini calls were made**.

| # | Scenario | Command | Result |
|---|---|---|---|
| 1 | Reset | `POST /api/reset` | `{"status":"ok",...}` |
| 2 | Empty station | `GET /api/station` | 3 ports, empty queue, `completed:0` |
| 3 | Normal negotiation (fallback) | `POST /api/negotiate` (soc=40, cap=75, force_fallback) | `status:"CHARGING"`, `validated_urgency_score:0.5`, assigned a port |
| 4 | Fake-emergency / high-SOC contradiction | Direct call to `ConstraintValidator.validate_request()` with claimed `CRITICAL` at 85% SOC | `urgency_score:0.2`, `contradiction_found:True` — lie detector fires correctly |
| 5 | Malformed input (missing fields) | `POST /api/negotiate` with only `driver_message` | `HTTP 422` |
| 6 | Invalid value (SOC > 100) | `POST /api/negotiate` with `soc:150` | `HTTP 422` |
| 7 | Invalid value (blank message) | `POST /api/negotiate` with `driver_message:"   "` | `HTTP 422` |
| 8 | Invalid value (negative budget) | `POST /api/negotiate` with `budget:-5` | `HTTP 422` |
| 9 | Resource-aware scheduling | 3 EVs (7kW/150kW/150kW) queued against SLOW/FAST/ULTRA ports | Correctly matched: slow→SLOW, first fast→ULTRA, second fast→FAST (closest available) |
| 10 | Queueing | 4th EV submitted with all 3 ports full | `assigned_port:null`, `status:"WAITING"`, appeared in `/api/station`'s `queue` array |
| 11 | Charging completion | Stepped simulation repeatedly after fixing the target-SOC bug (see below) | EV reached target and was marked `completed:1`, port freed, no SOC overshoot past 100% |
| 12 | Reset after activity | `POST /api/reset` | Station returned to 3 empty ports, `completed:0`, `revenue:0.0` |
| 13 | Health check | `GET /api/health` | `{"status":"ok"}` |
| 14 | Budget rejection truthfulness (new endpoint behavior, see bug below) | `POST /api/negotiate` with `budget:1` for a 100 kWh charge | `status:"REJECTED_BUDGET"` (previously incorrectly `"WAITING"`) |
| 15 | Genuine queueing still distinguished from rejection | Normal-budget request submitted after ports fill | `status:"WAITING"`, correctly distinct from case 14 |

## Real Bugs Found and Fixed This Pass

### Bug 1 — Target SOC exceeded 100% for any battery smaller than 80 kWh

**Found via:** live API testing (case 3 above), then confirmed as systemic by reading `simple_ev_simulation.py:250-256`'s `generate_random_ev()`, which independently randomizes `max_battery` (from `{40, 60, 75, 100}`) and `target_battery` (`random.randint(70, 100)`, an **absolute kWh value**) — so any EV with `max_battery` in `{40, 60, 75}` got a target it could exceed its own capacity to reach, producing SOC readings above 100% while charging.

**Confirmed intended design** by checking the frontend: `frontend/src/pages/ChargingPage.tsx:75` and `OverviewPage.tsx:187` both fall back to `?? '80'`**%**` when `target_soc` is missing — proving the UI's own assumption is "80% of capacity," not "80 kWh absolute."

**Fix:** `app.py`'s `/api/negotiate` handler now computes `target_battery=0.8 * req.battery_capacity`; `simple_ev_simulation.py`'s `generate_random_ev()` now computes `target_battery = max_battery * random.uniform(0.70, 1.00)`.

**Verified fixed:** re-ran the API smoke test with a 40 kWh battery — `target_soc` now reads `80.0` (previously would have been `200.0`); stepped the simulation to completion and confirmed the EV reached `completed:1` without exceeding 100% SOC.

**Not changed:** `EVAgent.__init__`'s default parameter (`target_battery=80`) and `tests/test_core.py:195`'s explicit `target_battery=95` (paired with `max_battery=100` in that same test — already a valid 95% target) were left untouched; only the two call sites that computed a target independent of the vehicle's own capacity were fixed.

### Bug 2 — Over-budget requests were silently dropped but reported as "WAITING"

**Found via:** live API testing (case 14 above) and reading `simple_ev_simulation.py:363-367`, where the deterministic dispatcher drops an EV from the queue entirely (`pass`, no re-queue) if its calculated price exceeds its budget — but `app.py`'s `/api/negotiate` only checked `assigned_port is None` to decide between `"CHARGING"` and `"WAITING"`, so a rejected EV looked identical to a genuinely queued one.

**Fix:** `app.py` now checks whether the EV is actually still present in `sim.scheduler.queue` after dispatch; if not, and it wasn't assigned a port either, the response reports `status: "REJECTED_BUDGET"`. The frontend's `SchedulerPanel` (`OverviewPage.tsx`) now renders a distinct "Rejected" badge and explanatory text for this case, and no longer starts the charging-simulation polling loop or shows the "Charging Session Complete" banner for a request that was never actually charging.

**Verified fixed:** re-ran the API smoke test with `budget:1` for a 100 kWh charge — response changed from `status:"WAITING"` (misleading) to `status:"REJECTED_BUDGET"` (accurate); confirmed a normal-budget request in the same session still correctly returns `"WAITING"` when ports are full.

### Truthfulness fix (not a bug, a mock-data gap) — hardcoded "System Online" indicator

**Found via:** reading `App.tsx`'s sidebar and top bar, which unconditionally rendered a green dot and "System Online" / "OPERATIONAL" text regardless of actual backend reachability.

**Fix:** added `GET /api/health` (backend) and `api.checkHealth()` (frontend), polled every 5s from `App.tsx`; both indicators now reflect a real, current health-check result (`null` while checking, red "Backend Unreachable"/"UNREACHABLE" if the poll fails).

## Frontend — TypeScript / Build

```
$ cd frontend && npm run build
> tsc -b && vite build
✓ 2468 modules transformed.
✓ built in <1s
```

Run repeatedly after every frontend change in this pass (VITE_API_BASE wiring, AnalyticsPage error state, SchedulerPanel rejection state, App.tsx health indicator, ArchitecturePage route-list update) — **0 TypeScript errors** every time. One pre-existing, non-blocking warning: main JS chunk is ~687 KB (Vite's 500 KB advisory threshold), not code-split.

No automated frontend test suite exists (`*.test.tsx` / `*.spec.tsx` — none found). This is an accurate limitation, not an oversight hidden from this report.

## Browser / End-to-End Testing

**Not performed — no browser automation tooling was available in this environment.** Checked explicitly this pass: `which playwright` → not found; `frontend/node_modules` has no `playwright`/`puppeteer` package; no MCP browser tool was available to this session. This is stated plainly rather than claimed as passing.

What **was** verified as a substitute, and its limits:
- Every API call the frontend makes (`frontend/src/api.ts`) was independently exercised via `curl` against a running backend (see smoke tests above), covering the same request/response shapes the UI depends on.
- Every page's source was read directly to confirm it (a) calls real endpoints rather than rendering mock data, (b) has a loading and/or error state, and (c) doesn't reference Gemini or any secret.
- This is **not equivalent** to verifying actual rendering, click interactions, navigation, or visual regressions in a real browser. That remains genuinely untested.

## Security Scan

Performed via targeted `grep` across the whole repository (excluding `node_modules`, `.git`), without printing any secret value:

| Check | Result |
|---|---|
| `AIza[A-Za-z0-9_-]{20,}`-style key pattern anywhere in repo | **0 matches** |
| `AQ\.AQ\.`-style OAuth token pattern (mentioned in `generate_fixtures.py`'s docstring as a past mistake) anywhere in repo | **0 matches** |
| `GEMINI_API_KEY=` followed by a real-looking value outside `.env` | **0 matches** — every hit was either `.env` itself, `.env.example`'s placeholder, or code reading the variable name |
| Secrets in `frontend/dist` build output | **0 matches** |
| Secrets in any `*.json` fixture/result file or `tests/` | **0 matches** |
| Unnecessary local machine paths (`C:\Users\...`) in README/docs | **0 matches** |
| `.env` gitignored | **yes** (`.env` and `.env.*` patterns, with `!.env.example` / `!frontend/.env.example` exceptions) |
| `.env.example` (root and frontend) trackable, safe placeholder only | **yes** — confirmed content is a placeholder in both |

## Regression Summary (final state of this pass)

| Area | Command | Result |
|---|---|---|
| Backend tests | `pytest tests/ -v` | 10/10 pass |
| Backend boots | `uvicorn app:app` | Starts cleanly, all 7 routes respond |
| Frontend build | `npm run build` | 0 errors, succeeds |
| Security scan | repo-wide grep | 0 findings |
