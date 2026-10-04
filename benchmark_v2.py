"""
EV NEXUS v2 benchmark — paired, seeded comparison of the agent against
conventional scheduling baselines.

WHAT MAKES THIS DIFFERENT FROM THE v1 (phase5) BENCHMARK
--------------------------------------------------------
The v1 numbers are kept in the repository for provenance but have four flaws
that this harness fixes:

1. BUDGET PARITY. v1 enforced the budget constraint only for the agent
   policies and let FIFO/SJF/PRIORITY ignore it entirely, so the agent was the
   only policy that ever dropped a customer. Here the budget rule is identical
   for everyone.

2. TRUE PAIRING. v1 seeded per run, but the agent policies then consumed extra
   random draws, so the arrival streams silently diverged between policies.
   Here each stream is generated once and replayed verbatim to every policy, so
   this is a genuine common-random-numbers paired design and the per-seed
   differences are meaningful.

3. THE METRIC THAT MATTERS. v1 never measured deadline adherence, which is the
   only thing the agent structurally knows more about than a telemetry-only
   scheduler. Deadlines live in language; a conventional scheduler cannot see
   them at any price.

4. HONEST SATISFACTION. v1 averaged a satisfaction score over completed EVs
   only, which flatters a policy that serves few cars quickly. Here the primary
   metrics are objective counts over ALL arrivals.

Statistics are paired bootstrap confidence intervals — no distributional
assumption, no external dependency.
"""

import json
import random
import statistics
import sys
from typing import Dict, List

from scenario_library import (
    generate_arrival_stream, extraction_quality_report, SCENARIOS,
)
from schedule_engine import run_all_policies, POLICIES, DEFAULT_STATION

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

CONGESTION = {
    "LOW":    3.0,
    "MEDIUM": 5.0,
    "HIGH":   6.5,
}

NUM_SEEDS = 30
BASE_SEED = 1000
HORIZON_MIN = 1440.0

AGENT = "agent"
BASELINES = ["fifo", "sjf", "soc"]
ABLATIONS = ["agent_no_validation", "agent_no_deadline"]

# Metrics where a LOWER value is better.
LOWER_IS_BETTER = {"deadline_miss_rate", "avg_wait_min", "p95_wait_min",
                   "max_wait_min", "mean_lateness_min"}

HEADLINE_METRICS = [
    "on_time_rate", "critical_on_time_rate", "served_rate",
    "avg_wait_min", "p95_wait_min", "energy_kwh", "port_utilisation",
]


def bootstrap_ci(samples: List[float], iters: int = 10000,
                 seed: int = 7) -> Dict[str, float]:
    """Percentile bootstrap CI for the mean. Assumption-light, dependency-free."""
    if not samples:
        return {"mean": 0.0, "lo": 0.0, "hi": 0.0}
    rng = random.Random(seed)
    n = len(samples)
    means = []
    for _ in range(iters):
        means.append(sum(rng.choice(samples) for _ in range(n)) / n)
    means.sort()
    return {
        "mean": round(sum(samples) / n, 4),
        "lo": round(means[int(0.025 * iters)], 4),
        "hi": round(means[int(0.975 * iters)], 4),
    }


def run_congestion_level(name: str, rate: float) -> dict:
    print(f"\n{'='*74}")
    print(f"  {name} congestion — {rate} EV/hr, {NUM_SEEDS} paired seeds, 24 h each")
    print(f"{'='*74}")

    # per_policy[policy][metric] = [value per seed]
    per_policy: Dict[str, Dict[str, List[float]]] = {}
    arrivals_per_seed: List[int] = []

    for i in range(NUM_SEEDS):
        seed = BASE_SEED + i
        stream = generate_arrival_stream(seed=seed, horizon_min=HORIZON_MIN,
                                         arrivals_per_hour=rate)
        arrivals_per_seed.append(len(stream))

        # The SAME stream object goes to every policy.
        results = run_all_policies(stream, collect_timeline=False)
        for pol, res in results.items():
            store = per_policy.setdefault(pol, {})
            for k, v in res.metrics.items():
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    store.setdefault(k, []).append(float(v))

        if (i + 1) % 10 == 0:
            print(f"    ...{i+1}/{NUM_SEEDS} seeds")

    # --- Absolute per-policy summaries ---
    summary = {}
    for pol, metrics in per_policy.items():
        summary[pol] = {
            "label": POLICIES[pol]["label"],
            "family": POLICIES[pol]["family"],
            "metrics": {m: bootstrap_ci(vals) for m, vals in metrics.items()
                        if m in HEADLINE_METRICS or m in LOWER_IS_BETTER
                        or m in ("served", "arrived", "deadline_evs",
                                 "unverified_claim_fast_port_minutes")},
        }

    # --- Paired comparisons: agent vs each baseline and ablation ---
    comparisons = {}
    for other in BASELINES + ABLATIONS:
        entry = {}
        for metric in HEADLINE_METRICS:
            a = per_policy[AGENT][metric]
            b = per_policy[other][metric]
            deltas = [x - y for x, y in zip(a, b)]
            ci = bootstrap_ci(deltas)

            better = sum(
                1 for d in deltas
                if (d < 0 if metric in LOWER_IS_BETTER else d > 0)
            )
            ties = sum(1 for d in deltas if abs(d) < 1e-12)

            # Significant when the CI for the paired difference excludes zero.
            significant = (ci["lo"] > 0 and ci["hi"] > 0) or (ci["lo"] < 0 and ci["hi"] < 0)
            favours_agent = (ci["mean"] < 0) if metric in LOWER_IS_BETTER else (ci["mean"] > 0)

            base_mean = sum(b) / len(b)
            rel = (ci["mean"] / base_mean * 100.0) if abs(base_mean) > 1e-9 else None

            entry[metric] = {
                "agent_mean": round(sum(a) / len(a), 4),
                "baseline_mean": round(base_mean, 4),
                "paired_delta": ci,
                "relative_pct": round(rel, 2) if rel is not None else None,
                "seeds_agent_better": better,
                "seeds_tied": ties,
                "seeds_total": len(deltas),
                "significant_at_95": bool(significant),
                "favours_agent": bool(favours_agent),
            }
        comparisons[other] = entry

    # --- Console report ---
    print(f"\n  Mean arrivals/day: {sum(arrivals_per_seed)/len(arrivals_per_seed):.1f}\n")
    hdr = (f"  {'Policy':<24}{'on-time':>9}{'crit':>8}{'served':>8}"
           f"{'wait':>8}{'p95':>8}{'util':>7}")
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))
    order = BASELINES + [AGENT] + ABLATIONS
    for pol in order:
        m = {k: v["mean"] for k, v in summary[pol]["metrics"].items()}
        marker = " <<<" if pol == AGENT else ""
        print(f"  {summary[pol]['label']:<24}"
              f"{m['on_time_rate']*100:>8.1f}%"
              f"{m['critical_on_time_rate']*100:>7.1f}%"
              f"{m['served_rate']*100:>7.1f}%"
              f"{m['avg_wait_min']:>8.1f}"
              f"{m['p95_wait_min']:>8.1f}"
              f"{m['port_utilisation']*100:>6.1f}%{marker}")

    print(f"\n  Paired deltas, agent vs baselines (95% bootstrap CI, n={NUM_SEEDS}):")
    for other in BASELINES:
        c = comparisons[other]["on_time_rate"]
        d = c["paired_delta"]
        sig = "significant" if c["significant_at_95"] else "not significant"
        print(f"    on-time vs {POLICIES[other]['label']:<20} "
              f"{d['mean']*100:+6.1f} pp  "
              f"[{d['lo']*100:+.1f}, {d['hi']*100:+.1f}]  "
              f"won {c['seeds_agent_better']}/{c['seeds_total']} seeds  ({sig})")

    print(f"\n  Ablations (what the agent loses if a component is removed):")
    for abl in ABLATIONS:
        c = comparisons[abl]["on_time_rate"]
        d = c["paired_delta"]
        print(f"    on-time vs {POLICIES[abl]['label']:<22} "
              f"{d['mean']*100:+6.1f} pp  [{d['lo']*100:+.1f}, {d['hi']*100:+.1f}]")

    return {
        "arrivals_per_hour": rate,
        "mean_arrivals_per_day": round(sum(arrivals_per_seed) / len(arrivals_per_seed), 1),
        "policies": summary,
        "paired_vs_agent": comparisons,
    }


def run_adversarial_sweep() -> dict:
    """How much does the deterministic validator buy under gaming pressure?

    Reported separately and honestly: at zero gaming it buys nothing, which is
    the correct behaviour for an integrity mechanism. Its value appears only as
    the share of drivers faking urgency rises.
    """
    print(f"\n{'='*74}")
    print("  ADVERSARIAL SWEEP — value of the deterministic validator")
    print(f"{'='*74}")
    print("  on-time rate measured over GENUINE deadline EVs only.\n")

    fractions = [0.0, 0.1, 0.2, 0.35, 0.5]
    seeds = 12
    out = []

    print(f"  {'liars':>7}{'agent':>10}{'no-validator':>15}{'paired delta':>16}")
    print("  " + "-" * 46)

    for frac in fractions:
        a_vals, nv_vals = [], []
        for i in range(seeds):
            stream = generate_arrival_stream(
                seed=4000 + i, horizon_min=HORIZON_MIN,
                arrivals_per_hour=CONGESTION["HIGH"],
                adversarial_fraction=frac,
            )
            res = run_all_policies(stream, policies=[AGENT, "agent_no_validation"],
                                   collect_timeline=False)
            a_vals.append(res[AGENT].metrics["on_time_rate"])
            nv_vals.append(res["agent_no_validation"].metrics["on_time_rate"])

        deltas = [x - y for x, y in zip(a_vals, nv_vals)]
        ci = bootstrap_ci(deltas)
        a_mean = sum(a_vals) / len(a_vals)
        nv_mean = sum(nv_vals) / len(nv_vals)

        print(f"  {frac*100:6.0f}%{a_mean*100:9.1f}%{nv_mean*100:14.1f}%"
              f"{ci['mean']*100:+11.1f} pp [{ci['lo']*100:+.1f},{ci['hi']*100:+.1f}]")

        out.append({
            "adversarial_fraction": frac,
            "agent_on_time": round(a_mean, 4),
            "no_validator_on_time": round(nv_mean, 4),
            "paired_delta": ci,
            "seeds": seeds,
        })

    return {
        "congestion": "HIGH",
        "arrivals_per_hour": CONGESTION["HIGH"],
        "note": (
            "At 0% gaming the validator is correctly neutral — there is nothing "
            "to catch. Its value grows with the share of drivers asserting "
            "urgency that telemetry contradicts. This is reported as an "
            "integrity/anti-gaming property, NOT as a throughput improvement."
        ),
        "sweep": out,
    }


def main() -> None:
    print("=" * 74)
    print("  EV NEXUS — v2 PAIRED BENCHMARK")
    print("=" * 74)
    print(f"  Station: {DEFAULT_STATION} kW")
    print(f"  Seeds per congestion level: {NUM_SEEDS} (paired across all policies)")
    print(f"  Horizon: {HORIZON_MIN/60:.0f} h")

    extraction = extraction_quality_report()
    print(f"\n  Agent input quality (Gemini vs hand-authored ground truth):")
    print(f"    deadline recall: {extraction['deadline_recall']*100:.1f}% "
          f"({extraction['deadlines_recovered']}/{extraction['scenarios_with_true_deadline']})")
    print(f"    urgency agreement: {extraction['urgency_agreement']*100:.1f}%")
    print(f"    missed deadlines: {', '.join(extraction['deadlines_missed_keys'])}")
    print("    -> the agent is evaluated on IMPERFECT extraction, not an oracle.")

    scenarios_out = {}
    for name, rate in CONGESTION.items():
        scenarios_out[name] = run_congestion_level(name, rate)

    adversarial = run_adversarial_sweep()

    payload = {
        "experiment_config": {
            "version": "v2",
            "num_seeds": NUM_SEEDS,
            "horizon_hours": HORIZON_MIN / 60.0,
            "station_kw": DEFAULT_STATION,
            "congestion_levels": CONGESTION,
            "policies": {k: v for k, v in POLICIES.items()},
            "statistics": "paired percentile bootstrap, 10000 resamples, 95% CI",
            "pairing": (
                "One arrival stream is generated per seed and replayed verbatim "
                "to every policy (common random numbers), so per-seed deltas are "
                "a true paired comparison."
            ),
            "parity_notes": [
                "Identical charging physics, pricing and budget enforcement for all policies.",
                "Pricing has no urgency multiplier, so the agent cannot inflate revenue by knowing urgency.",
                "All conventional baselines use the same best-fit port heuristic; only queue ordering differs.",
                "Ground-truth deadlines/urgency are used only for grading and are never read by any policy.",
            ],
        },
        "agent_input_quality": extraction,
        "scenarios": scenarios_out,
        "adversarial": adversarial,
        "scenario_ground_truth": {
            k: {
                "message": s.message,
                "true_deadline_min": s.true_deadline_min,
                "true_urgency": s.true_urgency,
                "required_kwh": s.required_kwh,
                "wants_full_charge": s.wants_full_charge,
                "is_unverified_claim": s.is_unverified_claim,
                "notes": s.notes,
            } for k, s in SCENARIOS.items()
        },
    }

    with open("benchmark_v2_results.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    print(f"\n{'='*74}")
    print("  Saved to benchmark_v2_results.json")
    print(f"{'='*74}")


if __name__ == "__main__":
    main()
