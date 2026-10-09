# EV NEXUS — Current Project Status

Current as of the v2 scheduling-engine pass. Earlier history:
`docs/history/PROJECT_STATUS_AUDIT.md`, `docs/history/PHASE_1_5_CLEANUP.md`, `docs/DQN_PROVENANCE.md`.

## Live URLs

| Service | URL |
|---|---|
| GitHub | [github.com/Karthik705/ev-nexus](https://github.com/Karthik705/ev-nexus) — public |
| Frontend | [ev-nexus.pages.dev](https://ev-nexus.pages.dev) (Cloudflare Pages, free tier) |
| Backend | [ev-nexus-backend.onrender.com](https://ev-nexus-backend.onrender.com) (Render, free tier) |
| Health | [/api/health](https://ev-nexus-backend.onrender.com/api/health) |

Total hosting cost: **₹0**. No card, no paid plan.

## What this project now claims, and the evidence

**Claim.** A driver's deadline exists only in natural language. Recovering it lets a
scheduler hit deadlines that telemetry-only policies structurally cannot.

**Evidence.** 30 paired seeds per congestion level, identical arrival stream to every
policy, identical physics/pricing/budget rules. At HIGH congestion (6.5 cars/hr):

| Policy | Deadlines met | Avg wait | Served | Port time |
|---|---|---|---|---|
| FIFO | 29.6% | 164 min | 96.8% | 82.4% |
| Lowest-SOC-first | 39.4% | 148 min | 97.3% | 83.7% |
| Shortest-Job-First | 47.9% | 83 min | 97.8% | 82.5% |
| **Agent** | **61.6%** | **53 min** | **98.5%** | **76.0%** |

+32.0 pp vs FIFO (30/30 seeds), +13.7 pp vs SJF (29/30), +22.2 pp vs Lowest-SOC
(30/30). All CIs exclude zero.

**The control.** The identical scheduler with the language-derived deadline withheld
scores 51.2% — it falls back toward the conventional policies. The gain is the
information, not the tuning.

## Status table

| Area | Status | Evidence |
|---|---|---|
| Scheduling engine (v2) | PASS | 22 tests incl. fairness invariants; production verified byte-identical to local for the same seed |
| Benchmark | PASS | `benchmark_v2.py`, 30 paired seeds × 3 levels, bootstrap CIs, reproducible offline |
| Agent algorithm | PASS | Beats every conventional baseline at every congestion level |
| Ablations | PASS | no-deadline −10.3 pp (HIGH); no-validator ≈0 and reported as such |
| Validator | PASS (correctly neutral) | No effect at 0% gaming; +6.3 pp at 50%. Reported as anti-gaming, not throughput |
| Ground-truth hygiene | PASS | Causal test perturbs ground truth by +997 min and asserts decisions unchanged |
| Backend | PASS | All routes live; `/api/compare` and `/api/scenarios` verified in production |
| Frontend | PASS | Scheduler + Benchmarks pages live; 0 TypeScript errors |
| Browser E2E | PASS | 9 Playwright tests, passing **against the live deployed site** |
| Python tests | PASS | 40 tests (10 legacy + 22 engine + 8 doc-drift guards) |
| Documentation accuracy | PASS | 8 tests parse README/EXPERIMENTS and check every figure against the benchmark JSON |
| Security | PASS | No key material in repo or served bundles; E2E asserts no `AIza…` reaches the browser |
| Gemini live call | UNVERIFIED | Key authenticates, but the one smoke test hit a transient Google 503. Not retried; deterministic fallback carries production |
| Legacy v1 engine | RETAINED | Still backs `/api/negotiate` and the Overview/Charging demo pages |
| DQN | EXPERIMENTAL | Unchanged; isolated from production. Not part of the v2 comparison |

## What changed in this pass

**Found: the old benchmark was unfair to the agent and measured the wrong thing.**

1. Budget enforced only for agent policies — heuristics ignored it, so the agent was
   the only policy that ever rejected a customer.
2. Arrival streams diverged between policies despite a shared seed (agent policies
   consumed extra random draws), so the comparison was not paired.
3. Deadline adherence was never measured; ground-truth deadlines were randomised
   independently of the message text, making them unmeasurable anyway.

**Built:** `scenario_library.py` (hand-authored ground truth + deterministic arrival
streams), `schedule_engine.py` (one engine, all policies, identical physics — backs
both the benchmark and the live site), `benchmark_v2.py` (paired bootstrap).

**Fixed, in my own agent, found by calibration not by tests:**
- The power term used `min(port,rate)/port`, scoring a 50 kW car on the 7 kW port as
  perfectly efficient. The agent parked fast cars on slow ports and was *worse than
  every baseline* at low load.
- No short-job preference, so the no-validator ablation beat the full agent.

**Fixed, found by tests:** a port double-booking off-by-one (completion recorded at
`now+step`, port reassigned at `now`).

**Fixed, found by the doc-drift audit:** README and EXPERIMENTS.md were quoting the
LOW-congestion row from the benchmark run *before* the double-booking fix. Now
guarded by `tests/test_published_claims.py`.

## Known limitations

- The simulation is a simulation: plausible distributions, not real station data. The
  policy *comparison* is sound (identical world for every policy); absolute
  percentages are not a claim about a real forecourt.
- Fixed set of 20 driver messages. A population that never states deadlines sees no
  benefit — visible in the LOW-congestion and no-deadline rows.
- Deadline labels involve judgement ("immediately" → 10 min); reasoning is recorded
  per label in `scenario_library.py`.
- Greedy matching, not optimal assignment.
- Render free tier sleeps after 15 min idle; first request can take 30–60 s.
- `docs/RESUME_SUMMARY.md` describes the project at a high level; the v2 results
  supersede any phase-5 figures quoted elsewhere in older docs.

## Remaining actions for the owner

1. Optional: retry the live Gemini smoke test (the earlier failure was a transient
   Google 503, not a configuration problem).
2. Optional: rotate the Render CLI API key — it was briefly displayed in a terminal
   during deployment setup (not your Gemini key, not public).
