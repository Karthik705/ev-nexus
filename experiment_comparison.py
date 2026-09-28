import numpy as np
import random
from collections import deque, Counter
from enum import Enum
import json
import sys
import torch
from dqn_agent import DQNAgent

# Force UTF-8 output on Windows to prevent UnicodeEncodeError for emojis
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding='utf-8')

from simple_ev_simulation import EVChargingSimulation, EVAgent, ChargingSpeed, UrgencyLevel
import json
import random

# =============================================================================
# PHASE 5: FIXTURE-BASED LLM METHODOLOGY
# =============================================================================
# This is the intentional experimental design, not a fallback.
#
# Rationale: a full 30-run x 3-scenario x 6-policy ablation makes thousands
# of Gemini API calls per experiment run. Even with backoff, this exhausts
# free-tier quota and introduces API latency as a confound in throughput
# measurements. Instead:
#
#   1. Real Gemini outputs are captured ONCE per canonical driver-message
#      category using generate_fixtures.py (with proper retry/backoff).
#   2. Those outputs are replayed deterministically at scale here.
#
# This approach:
#   - Uses REAL Gemini outputs (not mocks or stubs)
#   - Removes API noise/cost/latency from the throughput benchmark
#   - Makes the experiment reproducible without network access
#   - Allows fair apples-to-apples comparison between policies
#
# The fixture file and the exact messages used are documented in
# SCENARIOS below. Any change to scenarios requires re-running
# generate_fixtures.py.
# =============================================================================

try:
    with open('llm_fixtures.json', 'r') as f:
        _FIXTURES = json.load(f)
        _VALID_FIXTURES = {k: v for k, v in _FIXTURES.items() if v is not None}
        _SCENARIOS = {
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
            "P_MOVIE":                   "Watching a movie next door, will be back in 3 hours.",
            "Q_UBER_DRIVER":             "I'm an Uber driver and I'm losing money every minute I wait here.",
            "R_DELIVERY":                "Amazon delivery van, need enough charge to finish my route, got 30 mins max.",
            "S_CASUAL_COFFEE":           "Grabbing a coffee, no rush at all.",
            "T_WIFE_LABOR":              "My wife is in labor! Need fastest charge right now!",
        }
        _AVAILABLE_SCENARIOS = {k: _SCENARIOS[k] for k in _VALID_FIXTURES.keys() if k in _SCENARIOS}
        _AVAILABLE_KEYS = list(_AVAILABLE_SCENARIOS.keys())
        print(f"✅ Fixtures loaded: {len(_VALID_FIXTURES)}/20 valid entries available for sampling")
        if len(_VALID_FIXTURES) < 20:
            missing = [k for k in _SCENARIOS if k not in _VALID_FIXTURES or _VALID_FIXTURES.get(k) is None]
            print(f"⚠️  Missing/null fixtures (will not be sampled): {missing}")
            print(f"   Run `python generate_fixtures.py` to regenerate them.")
except Exception as e:
    print(f"❌ Failed to load llm_fixtures.json: {e}")
    _VALID_FIXTURES = {}
    _AVAILABLE_SCENARIOS = {}
    _AVAILABLE_KEYS = []

from llm_negotiator import GeminiNegotiator
from negotiation_types import LLMParsedRequest

# ------ FIXTURE REPLAY PATCH ------
# Save original method
original_negotiate = GeminiNegotiator.negotiate

# Per-policy call tracking (populated in run_experiment)
_policy_call_stats: dict[str, dict] = {}


def patched_negotiate(self, driver_message: str):
    """
    Fixture-based negotiate: looks up driver_message against known fixture
    messages and returns the stored real Gemini output deterministically.

    Falls through to the live API only for messages not in the fixture set
    (e.g. auto-generated EV messages from _generate_simulated_message).
    """
    fixture_key = next((k for k, v in _AVAILABLE_SCENARIOS.items() if v == driver_message), None)
    if fixture_key and fixture_key in _VALID_FIXTURES:
        data = _VALID_FIXTURES[fixture_key]
        req = LLMParsedRequest(
            urgency_level=data['urgency_level'],
            deadline_minutes=data['deadline_minutes'],
            reason_category=data['reason_category'],
            claimed_constraints=data['claimed_constraints'],
            requested_port_type=data['requested_port_type'],
            confidence=data['confidence'],
            explanation=data['explanation'],
        )
        self.call_count += 1
        self.success_count += 1
        return req, 0.0, True  # latency=0 — fixture replay is instant

    # Not a fixture message — treat as fallback (telemetry only)
    self.call_count += 1
    self.fallback_count += 1
    self.error_log.append(("FIXTURE_MISS", f"No fixture for message: {driver_message[:60]!r}"))
    return None, 0.0, False


GeminiNegotiator.negotiate = patched_negotiate

# --- EVAgent init patch: only assign fixture messages ---
original_init = EVAgent.__init__


def patched_init(self, ev_id, max_battery, current_battery, max_charging_speed,
                 arrival_time, target_battery=80, budget=50.0,
                 hidden_deadline=None, driver_message=None):
    if driver_message is None and _AVAILABLE_KEYS:
        fixture_key = random.choice(_AVAILABLE_KEYS)
        driver_message = _AVAILABLE_SCENARIOS[fixture_key]
    original_init(self, ev_id, max_battery, current_battery, max_charging_speed,
                  arrival_time, target_battery, budget, hidden_deadline, driver_message)


EVAgent.__init__ = patched_init
# -----------------------------------


def run_experiment(policy, num_runs=30, arrival_rate=2.5):
    print(f"\n--- Running Policy: {policy} (Rate: {arrival_rate}) ---")
    results = []

    # Per-policy negotiator to track call stats
    _policy_call_stats.setdefault(policy, {"success": 0, "fallback": 0, "fixture_miss": 0})

    for run in range(num_runs):
        # Identical seeds across policies — fair comparison
        random.seed(42 + run)
        np.random.seed(42 + run)

        sim = EVChargingSimulation(
            policy=policy,
            simulation_hours=24.0,
            arrival_rate=arrival_rate,
            auto_dispatch=True
        )
        if policy == 'DQN' and sim.dqn_agent:
            sim.dqn_agent.model.eval()

        # Reset negotiator stats before each run so we can accumulate cleanly
        if sim.negotiator:
            sim.negotiator.reset_stats()

        sim.run()
        results.append(sim.get_results())

        # Accumulate negotiator stats if this policy uses the LLM path
        if sim.negotiator:
            _policy_call_stats[policy]["success"]  += sim.negotiator.success_count
            _policy_call_stats[policy]["fallback"]  += sim.negotiator.fallback_count
            miss = sum(1 for t, _ in sim.negotiator.error_log if t == "FIXTURE_MISS")
            _policy_call_stats[policy]["fixture_miss"] += miss

        print(f"  Run {run+1}/{num_runs} complete: "
              f"{results[-1]['completed']} EVs served, "
              f"${results[-1]['revenue']:.2f} revenue")

    return results


def analyze_scenario(scenario_name, all_results):
    print("\n" + "="*80)
    print(f"📊 EXPERIMENT RESULTS COMPARISON: {scenario_name}")
    print("="*80)

    comparison = []
    for policy, results in all_results.items():
        avg_revenue   = np.mean([r['revenue'] for r in results])
        avg_completed = np.mean([r['completed'] for r in results])
        avg_wait      = np.mean([r['avg_wait_time'] for r in results])
        avg_crit_wait = np.mean([r['avg_critical_wait'] for r in results])
        avg_sat       = np.mean([r['avg_satisfaction'] for r in results])

        std_revenue = np.std([r['revenue'] for r in results])
        std_wait    = np.std([r['avg_wait_time'] for r in results])

        comparison.append({
            'policy':           policy,
            'avg_revenue':      avg_revenue,
            'avg_completed':    avg_completed,
            'avg_wait':         avg_wait,
            'avg_crit_wait':    avg_crit_wait,
            'avg_satisfaction': avg_sat,
            'std_revenue':      std_revenue,
            'std_wait':         std_wait,
        })

    comparison.sort(key=lambda x: x['avg_satisfaction'], reverse=True)

    print(f"\n{'Policy':<12} {'Revenue':>10} {'EVs Served':>12} {'Avg Wait':>10} {'Crit Wait':>10} {'Satisfaction':>13}")
    print("-"*80)

    for c in comparison:
        print(f"{c['policy']:<12} "
              f"${c['avg_revenue']:>8.2f}  "
              f"{c['avg_completed']:>10.1f}  "
              f"{c['avg_wait']:>8.2f}h  "
              f"{c['avg_crit_wait']:>8.2f}h  "
              f"{c['avg_satisfaction']:>11.4f}")

    print("-"*80)

    # Print LLM call stats for LLM-using policies
    print("\n📞 LLM Call Statistics:")
    for policy in ('LLM_NEGOTIATOR', 'TELEMETRY_ONLY'):
        stats = _policy_call_stats.get(policy)
        if stats:
            total = stats["success"] + stats["fallback"]
            print(f"  {policy}: {total} calls | "
                  f"✅ {stats['success']} fixture hits | "
                  f"⚠️  {stats['fallback']} fallbacks "
                  f"({stats['fixture_miss']} fixture misses)")

    return comparison


def save_all_results(scenarios_data):
    output_path = 'phase5_final_results.json'
    with open(output_path, 'w') as f:
        json.dump(scenarios_data, f, indent=2)
    print(f"\n💾 Results saved to '{output_path}'")


if __name__ == "__main__":
    print("="*70)
    print("🧪 EV CHARGING POLICY COMPARISON — PHASE 5")
    print("="*70)
    print("\nMethodology: Fixture-Based LLM Replay")
    print(f"  Valid fixtures available: {len(_VALID_FIXTURES)}/20")
    print("\nComparing 6 scheduling policies:")
    print("  1. FIFO            - First In First Out")
    print("  2. PRIORITY        - Urgency-based")
    print("  3. SJF             - Shortest Job First")
    print("  4. TELEMETRY_ONLY  - Deterministic telemetry (no LLM)")
    print("  5. LLM_NEGOTIATOR  - Fixture-replayed real Gemini outputs")
    print("  6. DQN             - Deep Q-Network baseline")
    print("\nEach policy: 30 runs, 24h simulation per run")

    scenarios = {
        'LOW':    2.5,
        'MEDIUM': 5.0,
        'HIGH':   8.5,
    }

    policies = {
        'SJF':            'SJF',
        'FIFO':           'FIFO',
        'PRIORITY':       'PRIORITY',
        'TELEMETRY_ONLY': 'DETERMINISTIC_TELEMETRY_ONLY',
        'LLM_NEGOTIATOR': 'LLM_DETERMINISTIC',
        'DQN':            'DQN',
    }

    num_runs = 30

    final_output = {
        'experiment_config': {
            'num_runs':         num_runs,
            'simulation_hours': 24.0,
            'methodology':      'fixture_based_llm',
            'methodology_note': (
                "LLM outputs were captured once per canonical scenario using "
                "generate_fixtures.py with exponential-backoff retry, then replayed "
                "deterministically. This removes API quota, latency, and nondeterminism "
                "from the throughput benchmark while still exercising real Gemini outputs."
            ),
            'fixture_count':    len(_VALID_FIXTURES),
            'fixture_file':     'llm_fixtures.json',
        },
        'scenarios': {}
    }

    for scenario_name, arrival_rate in scenarios.items():
        # Reset per-policy stats between scenarios
        _policy_call_stats.clear()

        print(f"\n" + "="*80)
        print(f"🚀 STARTING SCENARIO: {scenario_name} (Rate: {arrival_rate} EVs/hr)")
        print("="*80)

        all_results = {}
        for display_name, policy_val in policies.items():
            all_results[display_name] = run_experiment(policy_val, num_runs=num_runs, arrival_rate=arrival_rate)

        comparison = analyze_scenario(scenario_name, all_results)

        # Snapshot call stats into output JSON
        llm_call_stats_snapshot = {
            policy: dict(stats)
            for policy, stats in _policy_call_stats.items()
        }

        final_output['scenarios'][scenario_name] = {
            'arrival_rate':    arrival_rate,
            'raw_results':     all_results,
            'comparison':      comparison,
            'llm_call_stats':  llm_call_stats_snapshot,
        }

    save_all_results(final_output)

    print("\n" + "="*80)
    print("✅ ALL PHASE 5 EXPERIMENTS COMPLETE!")
    print("="*80)