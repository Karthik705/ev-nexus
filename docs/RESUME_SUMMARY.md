# EV NEXUS — Resume Summary

## 1. Project Title

**EV NEXUS — LLM-Assisted EV Charging Negotiator**

## 2. One-Line Description

A full-stack EV charging simulator where a FastAPI backend uses Gemini to parse natural-language driver requests into structured intent, validates that intent against real telemetry so the LLM can never override safety constraints, and dispatches vehicles with a resource-aware scheduler — benchmarked against five other scheduling policies (including an experimental DQN baseline) across a reproducible, fixture-based experiment suite, with a React operations dashboard on top.

## 3. Technology Stack

Python, FastAPI, Pydantic, Google Gemini API (`google-genai`), PyTorch, Gymnasium, NumPy, React 19, TypeScript, Vite, React Router, Recharts, pytest.

## 4. Three Resume Bullets

- Built a FastAPI backend that extracts structured intent from natural-language EV charging requests via the Gemini API, then enforces a deterministic validation layer that overrides LLM-claimed urgency when it contradicts live battery telemetry — preventing the LLM from ever bypassing safety constraints — with automatic, tested fallback to telemetry-only priority when the LLM is unavailable.
- Designed and ran a reproducible, fixture-based benchmark comparing 6 scheduling policies (FIFO, Priority, SJF, telemetry-only, LLM-driven, and an experimental DQN agent) across 3 congestion levels and 30 runs each, replaying captured Gemini outputs to remove API latency/cost as a confound — and diagnosed the DQN agent's reward-hacking failure mode (value-hoarding) directly from its training reward formulation.
- Shipped a production-shaped React/TypeScript dashboard (5 pages: live negotiation console, charging monitor, analytics, benchmark comparisons, architecture docs) wired end-to-end to real backend state with proper loading/error/rejection states, a live backend health check, and a configurable deployment target — found and fixed two real correctness bugs (an SOC-overflow bug and a silently-misreported budget rejection) during a systematic finalization pass with full test-backed verification.

## 5. Five Technical Interview Talking Points

1. **Why deterministic validation, not just prompting the LLM to "be safe"?** An LLM's output is fundamentally untrustworthy for safety-critical decisions because it can be socially engineered (a fake "emergency" claim) or simply wrong. The design puts a non-LLM code path between the model's output and any action that affects charging speed, budget, or port assignment — the LLM can only ever *downgrade* a claim relative to telemetry, never upgrade past what physical state allows.
2. **Why fixture-based replay instead of live calls in the benchmark?** A 30-run × 3-scenario × 6-policy ablation would mean thousands of live Gemini calls, introducing API latency and rate-limit variance as a confound in what's supposed to be a *scheduling-policy* comparison, plus real cost and quota risk. Capturing each of 20 canonical scenarios once and replaying deterministically isolates the variable actually being measured.
3. **What did the DQN experiment actually teach you?** The agent found a way to maximize discounted reward by refusing to dispatch (avoiding the reward penalties tied to real actions), rather than learning to schedule well — a classic reward-hacking failure. Diagnosing this meant reading the actual reward shaping in the Gym environment, not just noting that the metric was bad.
4. **How did you find and fix real bugs, not just add tests until things passed?** Two examples: (a) live-testing the negotiate endpoint with a battery smaller than the hardcoded 80 kWh charge target revealed SOC readings above 100%, traced to a target computed as an absolute value instead of a percentage of that vehicle's own capacity; (b) testing an intentionally-impossible budget revealed the scheduler silently dropped the request while the API still reported "waiting," which would mislead a user watching the UI. Both were root-caused in the actual dispatch code, not patched over in the response layer.
5. **What's still explicitly unverified, and why does that matter?** Live Gemini calls were never made during this project's automated testing or its most recent finalization pass — by design, to avoid unpredictable cost/availability in CI-like conditions. That's stated directly in the README and test report rather than glossed over, because claiming a live integration is tested when it wasn't is exactly the kind of overclaim a technical interviewer will probe for.

## 6. 60-Second Project Explanation

"EV NEXUS is an EV charging station simulator where drivers describe what they need in plain English — 'I need to leave in 15 minutes' — and a backend uses Gemini to turn that into structured urgency and deadline data. The key design decision is that the LLM only *interprets* — it can never override what the car's actual battery sensor says. If someone claims a fake emergency but their battery's nearly full, a deterministic validator catches the contradiction and downgrades them. I built the full pipeline — intent extraction, validation, a resource-aware scheduler that matches EVs to the right charging port, and a React dashboard — plus a benchmark comparing that approach against five other scheduling strategies, including an experimental reinforcement-learning agent that I diagnosed as failing due to reward hacking. I also did a full finalization pass where I found and fixed two real bugs through direct API testing rather than just running the existing test suite."

## 7. 2-Minute Technical Explanation

"The core architectural bet in EV NEXUS is separating *interpretation* from *enforcement*. A driver's natural-language message goes to Gemini, which returns structured JSON — urgency level, deadline, reason category — but that's treated as a claim, not a fact. A separate deterministic validator, `ConstraintValidator`, takes that claim plus the vehicle's actual telemetry — real state of charge, real battery capacity, real budget — and is the only thing that can compute a final priority score. If the LLM's urgency claim is inconsistent with telemetry — say, `CRITICAL` urgency at 85% state of charge — the validator forces it back down and flags the contradiction. Structurally, the LLM's fields never even reach the parts of the code that decide budget or charging speed; those always come straight from the request's telemetry.

On the backend side, this runs through FastAPI with per-session simulation state, a scheduler that matches EVs to the closest-speed compatible port, and graceful, tested fallback to a telemetry-only heuristic whenever Gemini is unavailable, rate-limited, or returns malformed output — the failure is classified, not swallowed.

For evaluation, I built a benchmark comparing six policies — including the LLM-driven one and an experimental DQN agent — using captured, replayed Gemini outputs rather than live calls during the benchmark itself, which keeps the comparison reproducible and removes API variance as a confound. The DQN agent consistently underperformed every heuristic; digging into its reward formulation showed it had learned to avoid dispatching at all to dodge negative rewards, a textbook reward-hacking outcome, which I documented rather than tried to mask by retraining until the number looked better.

Finally, I did a systematic finalization pass — full security scan, dead-code cleanup, and live endpoint testing across normal, adversarial, malformed, and edge-case inputs — which is how I actually found two real bugs: an SOC-overflow issue from a hardcoded absolute charge target, and a case where budget-rejected requests were silently dropped by the scheduler but still reported to the frontend as 'waiting.' Both are fixed and covered by re-verification in the test report, and everything that's genuinely still unverified — like a live Gemini call in this exact environment — is stated as such rather than assumed to work."

## 8. Likely Interview Questions and Concise Answers

**Q: Why not just let the LLM decide priority directly?**
A: Because it can be gamed by phrasing, and because charging infrastructure decisions (who gets a fast port, whether someone's within budget) need to be auditable and consistent — an LLM's output isn't guaranteed to be either. The LLM is a translator from language to structured intent; a separate, testable, deterministic function makes the actual decision.

**Q: What happens if Gemini is down or the key is invalid?**
A: The negotiator classifies the failure type and the system falls back to a telemetry-only heuristic based purely on state-of-charge tiers — this path is unit-tested and can also be forced on-demand via a UI toggle, so a demo doesn't depend on Gemini being reachable.

**Q: Is the DQN agent actually used anywhere live?**
A: No — it's isolated to the offline benchmark script; the interactive app's code never imports the DQN module at all. It's presented purely as an experimental baseline with a documented negative result, not as a production component.

**Q: How confident are you in the benchmark numbers?**
A: I re-verified they're internally consistent with the checked-in results file and match what's published in the README, using a small script that reads the JSON directly. I did not re-run the full 30×3×6 experiment in this pass (that would take real compute time and wasn't necessary to confirm the numbers weren't altered) and I'm explicit that a live-Gemini path is unverified in my most recent pass — I don't claim more certainty than I actually have.

**Q: What would you do differently with more time?**
A: Add real browser/E2E test coverage (none exists — I was honest about that rather than claiming it), make the budget/speed/port validation checks in the UI dynamically driven by backend response fields instead of a couple of them being static illustrative checkmarks, and move session state to a persistent store for real multi-user deployment.
