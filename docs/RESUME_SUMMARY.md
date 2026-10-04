# EV NEXUS — Resume Summary

## 1. Project Title

**EV NEXUS — LLM-Assisted EV Charging Negotiator**

## 2. One-Line Description

An EV charging scheduler that recovers the deadline hidden in a driver's sentence
("my flight leaves in 2 hours and the airport is 40 minutes away" = 80 minutes),
cross-checks it against telemetry so nobody can lie their way to the front of the
queue, and schedules the station around it — beating conventional policies by up to
32 percentage points on deadline adherence in a 30-seed paired benchmark, with the
ablation that proves the gain comes from language rather than tuning.

**Live:** [ev-nexus.pages.dev](https://ev-nexus.pages.dev) ·
[github.com/Karthik705/ev-nexus](https://github.com/Karthik705/ev-nexus)

## 3. Technology Stack

Python, FastAPI, Pydantic, Google Gemini API (`google-genai`), NumPy, PyTorch,
Gymnasium, React 19, TypeScript, Vite, Recharts, pytest, Playwright. Deployed on
Render + Cloudflare Pages (free tier, ₹0).

## 4. Three Resume Bullets

- **Designed a deadline-aware EV charging scheduler that outperforms conventional
  policies by +32.0 pp (vs FIFO) and +13.7 pp (vs Shortest-Job-First) on deadline
  adherence**, winning 29–30 of 30 paired seeds with bootstrap CIs excluding zero —
  while simultaneously serving more vehicles (98.5%) using less port time (76.0%).
  The scheduler performs greedy maximum-weight matching over (vehicle, port) pairs
  scored on deadline feasibility, slack, telemetry-validated urgency, achieved power
  and queue aging.
- **Built the evaluation that makes the result defensible**, after auditing the
  previous benchmark and finding it was both unfair and measuring the wrong thing:
  the budget constraint was enforced only for the LLM policies, arrival streams
  silently diverged between policies despite a shared seed, and deadline adherence —
  the only metric language can influence — was never measured. Rebuilt it with
  common-random-number pairing, hand-authored ground truth used strictly for grading,
  and an ablation showing the agent collapses from 61.6% to 51.2% when the
  language-derived deadline is withheld, proving the gain is the information and not
  the scoring function.
- **Shipped and deployed the full stack** — FastAPI backend and React/TypeScript
  dashboard with a custom SVG schedule visualisation that renders both policies on a
  shared time axis — verified by 40 Python tests (including fairness invariants and a
  causal test that perturbs ground truth to prove it never leaks into decisions) and
  9 Playwright tests that pass against the live production site. Found and fixed two
  genuine defects in my own scheduler during calibration, including one that made it
  *worse* than every baseline at low load.

## 5. Six Technical Interview Talking Points

1. **Why deterministic validation, not just prompting the LLM to "be safe"?** An LLM's output is fundamentally untrustworthy for safety-critical decisions because it can be socially engineered (a fake "emergency" claim) or simply wrong. The design puts a non-LLM code path between the model's output and any action that affects charging speed, budget, or port assignment — the LLM can only ever *downgrade* a claim relative to telemetry, never upgrade past what physical state allows.
2. **How do you know the improvement comes from the LLM and not from a better-tuned
   scheduler?** That is exactly what the ablation controls for. "Agent (no deadlines)"
   is the identical scheduler — same weights, same matching, same physics — with only
   the language-derived deadline withheld. It drops from 61.6% to 51.2%, falling back
   toward the conventional policies. If it had not dropped, the advantage would be
   coming from somewhere other than language and the central claim would be false. I
   also hold this as a regression test, so the claim cannot silently stop being true.
3. **How do you stop ground truth leaking into the agent's decisions?** The deadline
   labels are the answer key, so if the scheduler could read them the whole result
   would be circular. A naive "assert believed != true_value" check does not work —
   the agent maps CRITICAL to an implied 15-minute deadline, and one scenario
   genuinely has a 15-minute deadline, so equality there is coincidence, not leakage.
   The only sound test is causal: perturb every ground-truth deadline by +997 minutes
   and assert the agent's decisions are byte-identical. That distinguishes the two.
4. **What did you find when you audited your own earlier benchmark?** Three defects,
   and two of them were biased *against* my own method: the budget constraint was
   enforced only for the LLM policies (so only they ever turned a customer away), and
   the arrival streams diverged between policies despite a shared seed, because the
   LLM path consumed extra random draws. The third was that deadline adherence was
   never measured at all. I kept the old results for provenance, marked them
   superseded, and rebuilt the evaluation rather than quietly restating the numbers.
5. **Tell me about a bug you introduced yourself.** My scheduler's power-matching term
   used the ratio `min(port_kw, car_kw) / port_kw`, which scores a 50 kW car on a 7 kW
   port as *perfectly* efficient — 7/7 = 1.0. So it parked fast cars on the slow port,
   charging them seven times slower, and the agent was measurably **worse than every
   baseline** at low congestion. No test caught it; I found it by sweeping congestion
   levels and noticing it lost where it should have tied. Fixed by rewarding achieved
   power and penalising over-provisioning separately.
6. **What's still explicitly unverified?** The live Gemini call path. The key
   authenticates correctly against Google's API, but the one controlled smoke test hit
   a transient 503 from the model itself, so end-to-end live extraction has not been
   confirmed. The benchmark deliberately replays captured outputs instead — thousands
   of live calls would make API latency a confound in a *scheduling* comparison — and
   deterministic fallback carries production. All of this is stated in the README
   rather than glossed over.

## 6. 60-Second Project Explanation

"If a driver tells a charging station 'my flight leaves in two hours and the airport is
forty minutes away', that's an eighty-minute deadline — and it exists nowhere in the
telemetry. Not in state of charge, not in battery size. So a conventional scheduler,
FIFO or shortest-job-first, physically cannot act on it. EV NEXUS recovers that
constraint from the sentence with Gemini, checks it against the car's actual battery so
nobody can fake an emergency to jump the queue, and schedules the station around it.
On a thirty-seed paired benchmark it hits 61.6% of deadlines where FIFO hits 29.6% and
shortest-job-first hits 47.9% — and it does that while serving more cars and using less
port time, so it isn't trading throughput for fairness. The part I'd point at is the
control: I run the identical scheduler with the deadline withheld, and it collapses
back toward the conventional policies. That's what tells you the gain is the
information, not a better-tuned scoring function."

## 7. 2-Minute Technical Explanation

"The core architectural bet in EV NEXUS is separating *interpretation* from *enforcement*. A driver's natural-language message goes to Gemini, which returns structured JSON — urgency level, deadline, reason category — but that's treated as a claim, not a fact. A separate deterministic validator, `ConstraintValidator`, takes that claim plus the vehicle's actual telemetry — real state of charge, real battery capacity, real budget — and is the only thing that can compute a final priority score. If the LLM's urgency claim is inconsistent with telemetry — say, `CRITICAL` urgency at 85% state of charge — the validator forces it back down and flags the contradiction. Structurally, the LLM's fields never even reach the parts of the code that decide budget or charging speed; those always come straight from the request's telemetry.

On the backend side, this runs through FastAPI with per-session simulation state, a scheduler that matches EVs to the closest-speed compatible port, and graceful, tested fallback to a telemetry-only heuristic whenever Gemini is unavailable, rate-limited, or returns malformed output — the failure is classified, not swallowed.

The scheduler itself does greedy maximum-weight matching over (vehicle, port) pairs
every minute. Each pair is scored on whether finishing on that port actually lands
before the deadline — which dominates everything else — then least-slack-first, then
validated urgency, then power matching so a 7 kW car doesn't squat a 150 kW port, plus
aging so nobody starves. I kept it greedy rather than Hungarian because with a handful
of ports the difference is negligible and greedy stays explainable, which matters for a
system that has to justify its decisions to a driver.

The evaluation is the part I'd defend hardest, because I had to throw the first one
away. Auditing my own earlier benchmark, I found the budget constraint was enforced
only for the LLM policies — so only they ever turned a customer away — and the arrival
streams silently diverged between policies despite a shared seed, because the LLM path
consumed extra random draws. Both of those were biased against my own method. The third
defect was worse: deadline adherence was never measured, so the one thing language
actually buys you was invisible. I rebuilt it with common random numbers so every
policy sees a byte-identical arrival stream, hand-authored ground truth used strictly
for grading, and paired bootstrap confidence intervals. The old results are kept for
provenance and marked superseded rather than quietly restated.

Two things I'd flag as intellectually honest rather than flattering. First, the
validator — the lie detector — measurably does nothing when nobody games the system.
It's worth six points when half the drivers fake an emergency, and roughly zero at
zero, which is correct behaviour for an integrity mechanism, so I report it as
anti-gaming rather than as a performance win. Second, my own scheduler had a bug that
made it worse than every baseline at low load: the power term rated a 50 kW car on a
7 kW port as perfectly efficient, because the ratio was seven over seven. No test
caught that; I found it by sweeping congestion levels and noticing it lost where it
should have tied."

## 8. Likely Interview Questions and Concise Answers

**Q: Why not just let the LLM decide priority directly?**
A: Because it can be gamed by phrasing, and because charging infrastructure decisions (who gets a fast port, whether someone's within budget) need to be auditable and consistent — an LLM's output isn't guaranteed to be either. The LLM is a translator from language to structured intent; a separate, testable, deterministic function makes the actual decision.

**Q: What happens if Gemini is down or the key is invalid?**
A: The negotiator classifies the failure type and the system falls back to a telemetry-only heuristic based purely on state-of-charge tiers — this path is unit-tested and can also be forced on-demand via a UI toggle, so a demo doesn't depend on Gemini being reachable.

**Q: Is the DQN agent actually used anywhere live?**
A: No — it's isolated to the offline benchmark script; the interactive app's code never imports the DQN module at all. It's presented purely as an experimental baseline with a documented negative result, not as a production component.

**Q: How confident are you in the benchmark numbers?**
A: Every figure published in the README and the experiments doc is parsed back out of
those documents by a test and checked against the results JSON. That test caught a real
error — after I regenerated the benchmark following an engine fix, the low-congestion
row in both documents was still quoting the previous run. I also verified the deployed
backend reproduces the local engine byte-identically for the same seed, down to every
port assignment and start time, so the website isn't showing something different from
what the benchmark measured.

**Q: Isn't a 30-car demo sample too noisy to prove anything?**
A: Yes, and that bit me — in one sample an ablation beat the full agent by chance. So
the live page averages over up to fifteen arrival patterns and says so on screen, and
if you set it to one pattern it warns you the result is noisy and points at the 30-seed
benchmark. I'd rather surface the noise than let someone screenshot a lucky run.

**Q: What are the honest limits of this?**
A: It's a simulation — plausible distributions, not real station data — so the
*comparison* between policies is sound because every policy faces an identical world,
but the absolute percentages aren't a claim about a real forecourt. The scenario mix is
twenty fixed messages; a population that never states deadlines would see no benefit,
which is visible in the low-congestion row. And the deadline labels involve judgement:
I encoded "immediately" as ten minutes, someone could argue for five.

**Q: What would you do differently with more time?**
A: Replace greedy matching with optimal assignment and measure whether it's actually
worth it; drive the remaining static checkmarks in the validation panel from real
backend fields; move session state to a persistent store for multi-user deployment; and
get a confirmed live-Gemini end-to-end run, which is still the one unverified link.
