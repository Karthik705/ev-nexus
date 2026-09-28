# EV NEXUS — Experiments & Reproducibility

## Methodology

Phase 5 (the current, active benchmark) compares six scheduling policies — FIFO, PRIORITY, SJF, TELEMETRY_ONLY, LLM_NEGOTIATOR, DQN — across three congestion levels (LOW 2.5 EVs/hr, MEDIUM 5.0 EVs/hr, HIGH 8.5 EVs/hr), 30 runs per policy per scenario, 24-simulated-hours per run.

**Fixture-based LLM replay**, not live calls during the benchmark: `generate_fixtures.py` captures one real Gemini response per canonical driver-message scenario (20 scenarios, `A_HARD_DEADLINE` through `T_WIFE_LABOR`, defined in `generate_fixtures.py:38-59`), with exponential-backoff retry (`generate_fixtures.py:91-114`). Those captured responses are stored in `llm_fixtures.json` and replayed deterministically by `experiment_comparison.py` across all 30×3 runs. This is a deliberate design choice, not a degraded substitute for live calls: it removes API quota exhaustion, network latency, and Gemini's own nondeterminism as confounds in a *scheduling-policy* comparison, while still exercising real captured Gemini outputs rather than synthetic ones.

## Fixture Provenance

`llm_fixtures.json` currently has all 20 entries labelled `"source": "gemini_live"` (verified directly in this pass — `python -c "import json; d=json.load(open('llm_fixtures.json')); print({v['source'] for v in d.values()})"` → `{'gemini_live'}`). An earlier state of this file (documented in `generate_fixtures.py`'s module docstring) had 5 entries (`P_MOVIE`, `Q_UBER_DRIVER`, `R_DELIVERY`, `S_CASUAL_COFFEE`, `T_WIFE_LABOR`) hand-authored as `synthetic_manual` placeholders, from a period when the configured API key was an OAuth2 token rather than a Gemini API key. Those have since been backfilled with live output.

**Honesty caveat, stated plainly:** the `"source"` field is a label written by the fixture-generation script at the time it made the call — this repository does not independently cryptographically prove each fixture was produced by a genuine API response versus being hand-edited afterward. It should be read as "the generation script's own record of how it obtained this value," which is standard practice for this kind of experiment, not as an externally-audited guarantee.

## Which Results Files Are What

| File | `experiment_config` says | Status |
|---|---|---|
| `phase5_results.json` | `num_runs: 30`, `methodology: "fixture_based_llm"`, `fixture_count: 20` | **Current, active benchmark.** Served by `/api/benchmarks`, rendered on the Benchmarks page. |
| `phase5_sensitivity_results.json` | `methodology: "fixture_based_llm_live_only"`, `fixture_count: 15`, explicit `excluded_synthetic` list | A sensitivity check restricted to only the fixtures that were `gemini_live` *at the time it was generated* (predates the full 20-fixture backfill). Historical — not served by any API route. |
| `phase4c5_results.json` | `num_runs: 30` | An earlier fixture-based run, predates the `"source"` field entirely. Historical — still served by `/api/benchmarks` for comparison, but the frontend's primary display is `phase5_results.json`. |
| `phase4_results.json` | `num_runs: 30` | Earliest phase-4 run. Not served by any API route. Historical. |
| `archive/dqn_comparison_results.json`, `archive/phase3_results.json`, `archive/experiment_results.json` | — | Retired — `archive/dqn_comparison_results.json` was directly inspected in this pass and confirmed to contain the documented `avg_satisfaction: 0.0` bug in its `FIFO` raw results. Not served by any API route, kept only for provenance. |

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
