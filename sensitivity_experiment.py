"""
sensitivity_experiment.py — Phase 5 Sensitivity Check

Reruns the ablation using ONLY the 15 gemini_live fixtures (excludes the 5
synthetic_manual entries: P_MOVIE, Q_UBER_DRIVER, R_DELIVERY, S_CASUAL_COFFEE,
T_WIFE_LABOR).

Saves results to phase5_sensitivity_results.json.
"""

import numpy as np
import random
import json
import sys
from collections import deque

if hasattr(sys.stdout, "reconfigure"):
    import io, typing
    typing.cast(io.TextIOWrapper, sys.stdout).reconfigure(encoding="utf-8")

# ── Load ONLY gemini_live fixtures ──────────────────────────────────────────
with open("llm_fixtures.json", "r") as f:
    _ALL_FIXTURES = json.load(f)

_LIVE_FIXTURES = {
    k: v for k, v in _ALL_FIXTURES.items()
    if v is not None and v.get("source") == "gemini_live"
}

_ALL_SCENARIOS = {
    "A_HARD_DEADLINE":           "I need to leave within 15 minutes.",
    "B_FLEXIBLE":                "I can wait for an hour.",
    "C_FASTEST":                 "I need the fastest charging option available.",
    "D_CHEAPEST":                "I don't mind waiting. Please minimize my charging cost.",
    "E_GENUINE_EMERGENCY":       "I have a medical emergency and need to leave immediately.",
    "F_CONTRADICTORY_EMERGENCY": "This is an emergency and I need priority.",
    "G_AMBIGUOUS_TRADEOFF":      "I'm in a hurry but I don't want to spend too much.",
    "H_LONG_ROADTRIP":           "I am on a long road trip and need a full charge, can wait 2 hours.",
    "I_APPOINTMENT":             "Late for my dentist appointment in 20 minutes, just need a quick top up.",
    "J_NIGHT_SHIFT":             "Working the night shift, I can leave the car here for 8 hours.",
    "K_BUDGET_STRICT":           "I only have $10 to spend, give me what you can.",
    "L_BABY_IN_CAR":             "I have a crying baby in the car, please give me the fastest port so I can leave ASAP.",
    "M_FLIGHT":                  "My flight leaves in 2 hours, I need to reach the airport which is 40 mins away.",
    "N_LOW_BATTERY_PANIC":       "My car says 1% and I'm scared it will die, please help!",
    "O_GROCERY":                 "Going into the grocery store for about 45 minutes.",
}

# Only the 15 live scenarios (A–O) are in _LIVE_FIXTURES
_LIVE_SCENARIOS = {k: _ALL_SCENARIOS[k] for k in _LIVE_FIXTURES if k in _ALL_SCENARIOS}
_LIVE_KEYS = list(_LIVE_SCENARIOS.keys())

print(f"Sensitivity experiment: using {len(_LIVE_FIXTURES)}/20 fixtures (gemini_live only)")
print(f"Excluded (synthetic_manual): {[k for k in _ALL_FIXTURES if _ALL_FIXTURES.get(k, {}).get('source') == 'synthetic_manual']}")

# ── Patch GeminiNegotiator and EVAgent ──────────────────────────────────────
from llm_negotiator import GeminiNegotiator
from negotiation_types import LLMParsedRequest
from simple_ev_simulation import EVChargingSimulation, EVAgent

original_negotiate = GeminiNegotiator.negotiate
original_init = EVAgent.__init__


def patched_negotiate_live_only(self, driver_message: str):
    """Only serves fixtures with source=gemini_live."""
    fixture_key = next((k for k, v in _LIVE_SCENARIOS.items() if v == driver_message), None)
    if fixture_key and fixture_key in _LIVE_FIXTURES:
        data = _LIVE_FIXTURES[fixture_key]
        req = LLMParsedRequest(
            urgency_level=data["urgency_level"],
            deadline_minutes=data["deadline_minutes"],
            reason_category=data["reason_category"],
            claimed_constraints=data["claimed_constraints"],
            requested_port_type=data["requested_port_type"],
            confidence=data["confidence"],
            explanation=data["explanation"],
        )
        self.call_count += 1
        self.success_count += 1
        return req, 0.0, True
    self.call_count += 1
    self.fallback_count += 1
    return None, 0.0, False


def patched_init_live_only(
    self, ev_id, max_battery, current_battery, max_charging_speed,
    arrival_time, target_battery=80, budget=50.0,
    hidden_deadline=None, driver_message=None
):
    if driver_message is None and _LIVE_KEYS:
        driver_message = _LIVE_SCENARIOS[random.choice(_LIVE_KEYS)]
    original_init(self, ev_id, max_battery, current_battery, max_charging_speed,
                  arrival_time, target_battery, budget, hidden_deadline, driver_message)


GeminiNegotiator.negotiate = patched_negotiate_live_only  # type: ignore[method-assign]
EVAgent.__init__ = patched_init_live_only  # type: ignore[method-assign]

# ── Experiment runner ────────────────────────────────────────────────────────

def run_experiment(policy, num_runs=30, arrival_rate=2.5):
    print(f"\n  --- {policy} (rate={arrival_rate}) ---")
    results = []
    for run in range(num_runs):
        random.seed(42 + run)
        np.random.seed(42 + run)
        sim = EVChargingSimulation(
            policy=policy,
            simulation_hours=24.0,
            arrival_rate=arrival_rate,
            auto_dispatch=True,
        )
        if policy == "DQN" and sim.dqn_agent:
            sim.dqn_agent.model.eval()
        if sim.negotiator:
            sim.negotiator.reset_stats()
        sim.run()
        results.append(sim.get_results())
        if (run + 1) % 10 == 0:
            print(f"    run {run+1}/30")
    return results


def summarize(results):
    return {
        "avg_wait":         float(np.mean([r["avg_wait_time"] for r in results])),
        "avg_crit_wait":    float(np.mean([r["avg_critical_wait"] for r in results])),
        "avg_satisfaction": float(np.mean([r["avg_satisfaction"] for r in results])),
        "avg_revenue":      float(np.mean([r["revenue"] for r in results])),
        "avg_completed":    float(np.mean([r["completed"] for r in results])),
    }


scenarios = {"LOW": 2.5, "MEDIUM": 5.0, "HIGH": 8.5}
policies = {
    "SJF":            "SJF",
    "FIFO":           "FIFO",
    "PRIORITY":       "PRIORITY",
    "TELEMETRY_ONLY": "DETERMINISTIC_TELEMETRY_ONLY",
    "LLM_NEGOTIATOR": "LLM_DETERMINISTIC",
    "DQN":            "DQN",
}

final_output = {
    "experiment_config": {
        "num_runs":           30,
        "simulation_hours":   24.0,
        "methodology":        "fixture_based_llm_live_only",
        "fixture_filter":     "gemini_live",
        "fixture_count":      len(_LIVE_FIXTURES),
        "excluded_synthetic": [
            k for k, v in _ALL_FIXTURES.items()
            if v is not None and v.get("source") == "synthetic_manual"
        ],
        "note": (
            "Sensitivity check: only the 15 gemini_live fixtures are eligible "
            "for random selection. The 5 synthetic_manual entries (P-T) are excluded. "
            "Compare LLM_NEGOTIATOR vs TELEMETRY_ONLY here against phase5_results.json."
        ),
    },
    "scenarios": {},
}

for scenario_name, arrival_rate in scenarios.items():
    print(f"\n{'='*60}")
    print(f"SCENARIO: {scenario_name} ({arrival_rate} EVs/hr)")
    all_results = {}
    for display, policy_val in policies.items():
        all_results[display] = run_experiment(policy_val, 30, arrival_rate)

    comparison = []
    for policy, results in all_results.items():
        s = summarize(results)
        s["policy"] = policy
        comparison.append(s)
    comparison.sort(key=lambda x: x["avg_satisfaction"], reverse=True)

    print(f"\n  {'Policy':<14} {'Wait':>8} {'CritWait':>10} {'Sat':>8}")
    print(f"  {'-'*44}")
    for c in comparison:
        print(f"  {c['policy']:<14} {c['avg_wait']:>7.4f}h  {c['avg_crit_wait']:>8.4f}h  {c['avg_satisfaction']:>7.4f}")

    final_output["scenarios"][scenario_name] = {
        "arrival_rate": arrival_rate,
        "comparison":   comparison,
        "raw_results":  all_results,
    }

with open("phase5_sensitivity_results.json", "w") as f:
    json.dump(final_output, f, indent=2)

print("\n\nSaved to phase5_sensitivity_results.json")
print("="*60)
print("SIDE-BY-SIDE: LLM_NEGOTIATOR vs TELEMETRY_ONLY")
print("="*60)

with open("phase5_results.json") as f:
    full = json.load(f)

for sname in ["LOW", "MEDIUM", "HIGH"]:
    full_comp = {c["policy"]: c for c in full["scenarios"][sname]["comparison"]}
    sens_comp = {c["policy"]: c for c in final_output["scenarios"][sname]["comparison"]}

    print(f"\n{sname} congestion:")
    print(f"  {'':18} {'Full (20 fix)':>16}  {'Live-only (15 fix)':>20}  {'Change':>8}")
    for pol in ["LLM_NEGOTIATOR", "TELEMETRY_ONLY"]:
        f_sat = full_comp[pol]["avg_satisfaction"]
        s_sat = sens_comp[pol]["avg_satisfaction"]
        delta = s_sat - f_sat
        sign = "+" if delta >= 0 else ""
        print(f"  {pol:<18} sat={f_sat:.4f}          sat={s_sat:.4f}           {sign}{delta:.4f}")

    llm_full = full_comp["LLM_NEGOTIATOR"]["avg_satisfaction"]
    tel_full = full_comp["TELEMETRY_ONLY"]["avg_satisfaction"]
    llm_sens = sens_comp["LLM_NEGOTIATOR"]["avg_satisfaction"]
    tel_sens = sens_comp["TELEMETRY_ONLY"]["avg_satisfaction"]
    gap_full = (llm_full - tel_full) / tel_full * 100
    gap_sens = (llm_sens - tel_sens) / tel_sens * 100
    print(f"  LLM vs TELEM gap:  Full={gap_full:+.1f}%   Live-only={gap_sens:+.1f}%")
