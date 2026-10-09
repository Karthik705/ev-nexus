# EV NEXUS — Test Report

Last full run: October 2026, on the code in this repository.

| Suite | Command | Result |
|---|---|---|
| Backend unit + invariant tests | `pytest` | **40 passed** |
| Browser end-to-end (Playwright, Chromium) | `cd frontend && npm run test:e2e` | **9 passed** |
| Frontend type check + production build | `cd frontend && npm run build` | 0 TypeScript errors, no oversized chunks |

No test makes a live Gemini call. The backend tests use deterministic fallback or the
captured responses in `llm_fixtures.json`, so they run offline and give the same result
every time.

## 1. Backend (`pytest`, 40 tests)

### `tests/test_core.py` (10): validator and interactive pipeline

| What is checked | Tests |
|---|---|
| The "lie detector" downgrades an urgency claim that contradicts SOC | `test_lie_detector_contradiction_triggered` |
| The rule's boundary: 60% SOC is not a contradiction, 61% is | 2 boundary tests |
| Telemetry-only fallback tiers (<20% critical, <50% medium, else low) | 3 parametrised cases |
| Over-budget requests are rejected, not silently queued | `test_budget_rejection_drops_ev` |
| A car is matched to a port it can actually use | `test_resource_aware_port_matching` |
| Fixture replay and the no-API-key fallback path | 2 tests |

### `tests/test_schedule_engine.py` (22): the v2 engine and benchmark fairness

These lock in the guarantees that the earlier, unsound benchmark violated, so that class
of defect cannot return unnoticed.

- **Determinism and pairing:** the engine is deterministic; a seed always produces the
  same arrival stream; different seeds differ; every policy receives the identical stream.
- **Parity between policies:** identical budget rule; pricing has no urgency component;
  each car's energy requirement does not depend on the policy; conventional policies
  hold no deadline belief at all.
- **Physical correctness:** best-fit port selection never strands a fast car on a slow
  port or wastes a fast port; no port is ever double-booked.
- **Validator behaviour inside the engine:** contradictory claims are downgraded; the
  no-validator ablation trusts them; a genuine low-battery emergency is not downgraded;
  the threshold boundary.
- **Honesty of the evaluation:** ground truth is causally independent of agent
  decisions (every label shifted by +997 minutes leaves decisions byte-identical);
  extraction quality is imperfect and reported (a guard against swapping in an oracle);
  every scenario has a ground-truth label.
- **Headline behaviour:** the agent beats every conventional baseline under congestion,
  and the deadline-withheld ablation does worse than the full agent.

### `tests/test_published_claims.py` (8): documentation cannot drift from data

Every number in the README and `docs/EXPERIMENTS.md` tables is parsed back out of the
Markdown and compared with `benchmark_v2_results.json`. It also asserts the qualitative
claims: the agent wins at every congestion level, the gap widens with congestion, the
agent serves more cars with less port time, the validator is *not* claimed to help when
nobody games the system, and superseded Phase 5 figures are never restated. This suite
exists because it caught a real error: after a benchmark regeneration, one table row
was still quoting the previous run.

## 2. Browser end-to-end (Playwright, 9 tests)

Run against the production bundle (`vite preview`) and a real FastAPI backend.

| Test | Checks |
|---|---|
| scheduler page loads and runs a comparison | Page renders, both schedules draw, no console errors |
| delta cards report the agent against a baseline | Paired-delta cards show values |
| switching the baseline recomputes the comparison | Results change with the selected baseline |
| clicking a request reveals the decision behind it | Decision-detail panel opens |
| per-port view renders without breaking | Alternate Gantt layout |
| changing demand re-runs the schedule | Congestion control triggers a new run |
| all navigation routes render | Every page loads (pages are lazy-loaded) |
| backend health indicator reflects a reachable API | Live health badge is driven by `/api/health` |
| no Gemini credential is exposed to the browser | No `AIza…` key in any served script |

To run locally:

```bash
# terminal 1 (repository root)
ALLOWED_ORIGINS=http://localhost:4173 uvicorn app:app --port 8000
# terminal 2
cd frontend
VITE_API_BASE=http://127.0.0.1:8000/api npm run build
npm run test:e2e
```

Set `E2E_BASE_URL=https://ev-nexus.pages.dev` to run the same suite against the deployed
site. Note: the tests fail on any console error, so they need network access to Google
Fonts, which the dashboard loads.

## 3. Defects found by testing and calibration

| Defect | How it was found | Fix |
|---|---|---|
| Port double-booked for one minute at hand-over | `test_no_port_is_double_booked` | Simulation tick reordered to admit → dispatch → advance |
| Agent parked fast cars on the 7 kW port; worse than every baseline at low load | Sweeping congestion levels | Reward achieved power, penalise over-provisioning separately |
| No short-job preference; the no-validator ablation beat the full agent | Same sweep | Added a short-job term |
| Charge target was a hard-coded 80 kWh, so small batteries showed SOC above 100% | Manual testing | Target is 80% of each car's own capacity |
| Over-budget request silently dropped but shown as "waiting" | Manual testing | API returns `REJECTED_BUDGET`; UI shows the rejection |
| A leakage test flagged a coincidence (implied 15 min = true 15 min) as a leak | Its own false positive | Replaced equality check with the causal perturbation test |

## 4. Not covered by automated tests

- **Live Gemini extraction.** Deliberately excluded: live calls cost money, vary in
  latency and are non-deterministic. The deployed backend's key authenticates correctly,
  and the system falls back to telemetry-only scheduling whenever the model is
  unavailable. That fallback is tested.
- **Visual appearance.** The E2E tests check behaviour and rendering, not pixel layout.

History of earlier test passes: [`docs/history/TEST_LOG.md`](history/TEST_LOG.md).
