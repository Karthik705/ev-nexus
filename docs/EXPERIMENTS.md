# EV NEXUS — Experiments & Reproducibility

> **Current benchmark: v2** (`benchmark_v2.py` → `benchmark_v2_results.json`).
> Everything below the "Phase 5 (superseded)" heading describes the earlier
> benchmark, which is retained for provenance but whose comparison was not sound.

---

# Part 1 — The v2 benchmark (current)

## What is being measured, and why

**Deadline adherence.** Did the car receive the energy it needed before the driver
had to leave?

This metric was chosen because it is the only one where an LLM-assisted scheduler has
a *structural* advantage rather than a tuning advantage. A driver who says "my flight
leaves in 2 hours and the airport is 40 minutes away" has an 80-minute deadline. That
number is not derivable from state of charge, battery capacity, arrival time, or any
other telemetry channel. A conventional scheduler cannot act on it at any price.

The v1 benchmark never measured this, which is why it could not demonstrate the
method's actual value and instead rested on a satisfaction score that was easy to
attack.

## Ground truth

`scenario_library.py` defines, for each of the 20 canonical driver messages, the
constraint a careful human reader would infer from the text: `true_deadline_min`,
`true_urgency`, `required_kwh`, and whether the message is an *unverifiable claim*.
The reasoning for every label is recorded in a `notes` field, so the labels can be
argued with rather than taken on trust.

Two properties make these labels safe to use:

1. **Authored independently of the model's output.** They are derived from the message
   text, not from `llm_fixtures.json`. This makes extraction quality measurable:
   Gemini recovered 8/12 deadlines (66.7% recall) and agreed on urgency 100% of the
   time, missing the four cases with no explicit number in the sentence
   (`E_GENUINE_EMERGENCY`, `L_BABY_IN_CAR`, `T_WIFE_LABOR`, `J_NIGHT_SHIFT`).
2. **Used only for grading.** No policy reads them. This is enforced by a test, not by
   convention: `test_agent_beliefs_are_causally_independent_of_ground_truth` shifts
   every ground-truth deadline by +997 minutes and asserts the agent's beliefs and
   decisions are byte-identical. A naive "believed == true" check would not work —
   the agent maps CRITICAL to an implied 15-minute deadline and `L_BABY_IN_CAR`
   genuinely has a 15-minute deadline, so equality there is coincidence, not leakage.
   Only the causal test distinguishes the two.

## Fairness guarantees

Every policy in `schedule_engine.py` shares, bit for bit:

| Shared | Why it matters |
|---|---|
| Charging physics (power limits, taper above 80% SOC) | — |
| Pricing: energy × port tier, **no urgency multiplier** | Otherwise the agent could inflate revenue purely by knowing urgency |
| Budget enforcement | v1 enforced this *only* for agent policies and let the heuristics ignore it, so the agent was the only policy that ever turned a customer away |
| Energy requirement per car | A property of the world, not of beliefs |
| Best-fit port heuristic for all conventional baselines | Keeps baselines competitive; only queue *ordering* differs |
| The arrival stream | Generated once per seed, replayed verbatim |

Each of these is covered by a test in `tests/test_schedule_engine.py` so the v1 class
of defect cannot reappear unnoticed.

## Pairing and statistics

One arrival stream per seed, replayed to every policy — common random numbers, so the
per-seed difference between two policies is a genuine paired observation. 30 seeds per
congestion level. Confidence intervals are **paired percentile bootstrap**, 10 000
resamples, no distributional assumption and no external dependency.

Reported alongside each interval: how many of the 30 seeds the agent won, and whether
the interval excludes zero.

## Results

Deadline adherence (on-time rate):

| Policy | LOW (3/hr) | MEDIUM (5/hr) | HIGH (6.5/hr) |
|---|---|---|---|
| FIFO | 74.5% | 51.4% | 29.6% |
| Lowest-SOC-first | 75.0% | 56.9% | 39.4% |
| Shortest-Job-First | 74.7% | 59.7% | 47.9% |
| **Agent** | **76.7%** | **65.7%** | **61.6%** |
| Agent, no validator | 76.6% | 65.6% | 61.6% |
| Agent, **no deadlines** | 76.0% | 61.4% | 51.2% |

Paired deltas vs each baseline at HIGH congestion:

| vs | Δ on-time | 95% CI | Seeds won |
|---|---|---|---|
| FIFO | +32.0 pp | [+28.3, +35.6] | 30/30 |
| Shortest-Job-First | +13.7 pp | [+11.1, +16.2] | 29/30 |
| Lowest-SOC-first | +22.2 pp | [+19.1, +25.2] | 30/30 |

The agent simultaneously serves more cars (98.5% vs 96.8–97.8%) using less port time
(76.0% vs 82.4–83.7%), so this is not deadline adherence purchased with throughput.

## Ablations — the actual scientific control

| Ablation | Δ vs full agent (HIGH) | Reading |
|---|---|---|
| No language-derived deadline | **−10.3 pp** [−12.9, −7.6] | The improvement comes from the information, not the scoring function |
| No validator | −0.0 pp [−1.1, +1.1] | Validation is neutral when nobody games the system |

The no-deadline ablation is the load-bearing result. It is the identical scheduler —
same weights, same matching, same physics — with only the language-derived deadline
withheld. It falls back toward the conventional policies. If it did not, the agent's
advantage would be coming from somewhere other than language, and the central claim
would be false.

## Adversarial sweep — what the validator is worth

| Drivers faking urgency | Agent | No validator | Paired Δ | Significant? |
|---|---|---|---|---|
| 0% | 58.0% | 57.1% | +0.9 pp | no |
| 10% | 58.7% | 59.3% | −0.5 pp | no |
| 20% | 57.4% | 54.5% | +2.9 pp | yes |
| 35% | 58.6% | 56.0% | +2.6 pp | no |
| 50% | 56.2% | 49.9% | +6.3 pp | yes |

Stated plainly: **validation does not improve aggregate performance when nobody is
gaming the system**, and the 10% and 35% rows are not significant. The effect emerges
under heavy gaming pressure. The honest framing is that the validator is an
anti-gaming / integrity property, not a throughput optimisation — it stops a driver
talking their way to the front, which matters more the more people try it.

An earlier version of this experiment showed almost no effect at any level. The reason
was an artifact: the unverifiable-claim driver arrived at 62–88% SOC and so needed only
~3 kWh, making it a trivial job with nothing to displace. A driver actually gaming the
system would claim an emergency to obtain a *large* fast charge, so the scenario was
changed to request a full charge. That change is recorded in `scenario_library.py`.

## Reproducing

No API key and no network required — the benchmark replays captured Gemini output.

```bash
python benchmark_v2.py          # full sweep -> benchmark_v2_results.json (~3 min)
python scenario_library.py      # extraction quality vs ground truth
python schedule_engine.py       # one arrival stream through every policy
pytest tests/test_schedule_engine.py -v
```

## Known limitations of this benchmark

- Arrival times, battery sizes and accepted rates are drawn from plausible
  distributions, not real station data. The policy *comparison* is sound because every
  policy faces the identical world; the absolute percentages are not a claim about any
  real forecourt.
- The scenario mix is fixed at 20 messages. A population that never states deadlines
  would see no benefit — visible in the LOW-congestion and no-deadline rows.
- Deadline labels involve judgement ("immediately" → 10 min). Reasoning is recorded
  per label so the choices are auditable.
- Greedy matching, not optimal (Hungarian) assignment. With ≤8 ports the difference is
  small, and greedy keeps the decision explainable — which matters for a system that
  has to justify itself to drivers.

---

# Part 2 — Phase 5 (superseded)

**These results are retained for provenance only. The comparison was not sound.**

Three defects, found by auditing the harness:

1. **Budget parity.** `simple_ev_simulation.py` enforced the budget constraint only
   for `LLM_DETERMINISTIC` / `DETERMINISTIC_TELEMETRY_ONLY`, with the comment "Ignore
   budget constraints for heuristics so they don't break". FIFO/SJF/PRIORITY therefore
   served customers the agent was forced to turn away, directly penalising the agent on
   throughput and revenue.
2. **Broken pairing.** Runs were seeded identically, but the agent policies consumed
   additional random draws (fixture selection, negotiator bookkeeping), so the RNG
   streams diverged and the policies did not actually face the same arrivals.
3. **No deadline metric,** and a satisfaction score averaged over *completed* EVs only,
   which flatters a policy that serves few cars quickly. Ground-truth deadlines were
   also randomised independently of the message text, so deadline accuracy was not even
   measurable.

The original Phase 5 methodology notes follow, unaltered.

## Methodology

Phase 5 (the current, active benchmark) compares six scheduling policies — FIFO, PRIORITY, SJF, TELEMETRY_ONLY, LLM_NEGOTIATOR, DQN — across three congestion levels (LOW 2.5 EVs/hr, MEDIUM 5.0 EVs/hr, HIGH 8.5 EVs/hr), 30 runs per policy per scenario, 24-simulated-hours per run.

**Fixture-based LLM replay**, not live calls during the benchmark: `generate_fixtures.py` captures one real Gemini response per canonical driver-message scenario (20 scenarios, `A_HARD_DEADLINE` through `T_WIFE_LABOR`, defined in `generate_fixtures.py:38-59`), with exponential-backoff retry (`generate_fixtures.py:91-114`). Those captured responses are stored in `llm_fixtures.json` and replayed deterministically by `experiment_comparison.py` across all 30×3 runs. This is a deliberate design choice, not a degraded substitute for live calls: it removes API quota exhaustion, network latency, and Gemini's own nondeterminism as confounds in a *scheduling-policy* comparison, while still exercising real captured Gemini outputs rather than synthetic ones.

## Fixture Provenance

`llm_fixtures.json` currently has all 20 entries labelled `"source": "gemini_live"` (verified directly in this pass — `python -c "import json; d=json.load(open('llm_fixtures.json')); print({v['source'] for v in d.values()})"` → `{'gemini_live'}`). An earlier state of this file (documented in `generate_fixtures.py`'s module docstring) had 5 entries (`P_MOVIE`, `Q_UBER_DRIVER`, `R_DELIVERY`, `S_CASUAL_COFFEE`, `T_WIFE_LABOR`) hand-authored as `synthetic_manual` placeholders, from a period when the configured API key was an OAuth2 token rather than a Gemini API key. Those have since been backfilled with live output.

**Honesty caveat, stated plainly:** the `"source"` field is a label written by the fixture-generation script at the time it made the call — this repository does not independently cryptographically prove each fixture was produced by a genuine API response versus being hand-edited afterward. It should be read as "the generation script's own record of how it obtained this value," which is standard practice for this kind of experiment, not as an externally-audited guarantee.

## Which Results Files Are What

| File | Status |
|---|---|
| `benchmark_v2_results.json` | **Current, active benchmark.** Produced by `benchmark_v2.py`, served by `/api/benchmarks`, rendered on the Benchmarks page. |
| `phase5_results.json` | Superseded Phase 5 output. Still served and still in the repository so the earlier, unsound comparison stays auditable — but it is no longer rendered, and its figures are not restated anywhere. |
| `archive/dqn_comparison_results.json`, `archive/phase3_results.json`, `archive/experiment_results.json` | Retired. `archive/dqn_comparison_results.json` was directly inspected and confirmed to contain the documented `avg_satisfaction: 0.0` bug in its `FIFO` raw results. Not served by any route; kept because the DQN provenance investigation cites them as evidence. |

Three further Phase 5-era outputs (`phase4_results.json`, `phase4c5_results.json`,
`phase5_sensitivity_results.json`) were **removed** during repository cleanup. Nothing
read them, no document cited their contents as evidence, and together they were roughly
0.6 MB of superseded output. They remain recoverable from git history.

## Reproducing the Benchmark

No live Gemini calls are required to reproduce `phase5_results.json` — it replays cached fixtures:

```bash
python experiment_comparison.py
```

This was **not** re-run to regenerate `phase5_results.json` in this pass (doing so would overwrite the historical file with a new run under a fixed random seed sequence, and the instructions for this pass were explicit: do not alter historical benchmark results). Instead, the existing file's numbers were **spot-checked for internal consistency** using `scripts/read_results.py`, which reads `phase5_results.json` directly and prints the same LOW/MEDIUM/HIGH comparison table shown in the README — confirmed to match the README's published numbers exactly during this pass.

To regenerate fixtures from a fresh Gemini key (this was **not** done in this pass — no live Gemini calls were made):

```bash
echo "GEMINI_API_KEY=AIza..." > .env
python generate_fixtures.py --force-all
```

## What Was Re-Verified in This Pass vs. What Was Not

| Claim | Status this pass |
|---|---|
| `llm_fixtures.json` has 20/20 `gemini_live` entries | **Re-verified directly** by loading and inspecting the file. |
| `phase5_results.json` numbers match README | **Re-verified** via `scripts/read_results.py` against the live file on disk. |
| DQN checkpoint `ev_dqn_model_v5.pth` architecture matches `ev_gym_env.py` | **Re-verified** by loading its `state_dict` and test-loading into the current `DQN(42,26)` class (see `docs/DQN_PROVENANCE.md`). |
| A live Gemini call succeeds with the current `.env` key today | **Not tested.** No live API calls were made in this pass, per explicit instruction. This is the single largest unverified claim in the whole project — see `docs/TEST_REPORT.md`. |
| The `avg_satisfaction: 0.0` bug in archived results | **Re-verified** by directly inspecting `archive/dqn_comparison_results.json`'s raw data this pass. |
| Historical benchmark numbers are unaltered by this finalization pass | **True** — no JSON result file was edited in this pass. Two simulator bugs affecting *future* runs were fixed (target SOC, budget-rejection reporting); neither touches the historical JSON files already on disk. |

## Known Trade-offs (from the data, not re-derived)

- **SJF vs. fairness:** SJF has the highest throughput/revenue at every congestion level, but critical-EV wait times are 76–149% worse than LLM_NEGOTIATOR under MEDIUM/HIGH congestion.
- **DQN underperformance:** lowest satisfaction across all scenarios (0.09–0.13), consistent with the documented value-hoarding reward-hacking failure mode (`ev_gym_env.py:89-90` reward-shaping comment).

These are presented in the README and the Benchmarks page exactly as they appear in `phase5_results.json` — no numbers were adjusted to look more favorable.
