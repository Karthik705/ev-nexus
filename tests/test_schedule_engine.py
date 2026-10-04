"""
Tests for the v2 scheduling engine.

These lock in the FAIRNESS invariants, not just functionality. The v1 benchmark
was quietly unfair (budget enforced only for the agent, arrival streams that
diverged between policies); these tests exist so that class of bug cannot
return silently.
"""

import pytest

from scenario_library import (
    SCENARIOS, generate_arrival_stream, extraction_quality_report,
    load_extractions, EVSpec,
)
from schedule_engine import (
    run_schedule, run_all_policies, POLICIES, DEFAULT_STATION,
    _price, _affordable, _best_fit_port, Port, EVState, _energy_needed,
    CONTRADICTION_SOC_THRESHOLD,
)


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------

def test_engine_is_deterministic():
    """Same stream + same policy must give byte-identical metrics."""
    stream = generate_arrival_stream(seed=11, horizon_min=600.0, arrivals_per_hour=5.0)
    a = run_schedule(stream, "agent", collect_timeline=False).metrics
    b = run_schedule(stream, "agent", collect_timeline=False).metrics
    assert a == b


def test_arrival_stream_is_reproducible():
    s1 = generate_arrival_stream(seed=99, horizon_min=600.0, arrivals_per_hour=4.0)
    s2 = generate_arrival_stream(seed=99, horizon_min=600.0, arrivals_per_hour=4.0)
    assert [x.__dict__ for x in s1] == [x.__dict__ for x in s2]


def test_different_seeds_give_different_streams():
    s1 = generate_arrival_stream(seed=1, horizon_min=600.0, arrivals_per_hour=4.0)
    s2 = generate_arrival_stream(seed=2, horizon_min=600.0, arrivals_per_hour=4.0)
    assert [x.__dict__ for x in s1] != [x.__dict__ for x in s2]


# ---------------------------------------------------------------------------
# Fairness / parity invariants
# ---------------------------------------------------------------------------

def test_every_policy_sees_the_identical_stream():
    """run_all_policies must not regenerate or mutate the stream per policy."""
    stream = generate_arrival_stream(seed=5, horizon_min=600.0, arrivals_per_hour=5.0)
    before = [x.__dict__.copy() for x in stream]
    results = run_all_policies(stream, collect_timeline=False)
    after = [x.__dict__.copy() for x in stream]

    assert before == after, "engine mutated the shared arrival stream"
    arrived = {r.metrics["arrived"] for r in results.values()}
    assert len(arrived) == 1, f"policies saw different arrival counts: {arrived}"


def test_budget_rule_is_identical_across_policies():
    """The v1 bug: budget was enforced ONLY for agent policies.

    Pricing depends only on energy and port tier, so whether an EV can afford a
    given port must be policy-independent.
    """
    spec = EVSpec(ev_id=0, arrival_min=0.0, battery_kwh=60.0, soc_pct=20.0,
                  max_rate_kw=50.0, budget=5.0, scenario_key="D_CHEAPEST")
    need, target = _energy_needed(spec)
    ev = EVState(spec=spec, energy_needed_kwh=need, target_soc=target, soc_pct=spec.soc_pct)

    # $5 cannot buy a 36 kWh top-up at any tier.
    for kw in DEFAULT_STATION:
        assert not _affordable(ev, Port(0, kw))

    spec_rich = EVSpec(**{**spec.__dict__, "budget": 500.0})
    ev_rich = EVState(spec=spec_rich, energy_needed_kwh=need, target_soc=target,
                      soc_pct=spec_rich.soc_pct)
    for kw in DEFAULT_STATION:
        assert _affordable(ev_rich, Port(0, kw))


def test_pricing_has_no_urgency_component():
    """The agent must not be able to inflate revenue by knowing urgency."""
    energy = 20.0
    for kw in (7.0, 50.0, 150.0):
        p1 = _price(energy, kw)
        p2 = _price(energy, kw)
        assert p1 == p2
    # Strictly increasing in port tier, independent of any EV attribute.
    assert _price(energy, 7.0) < _price(energy, 50.0) < _price(energy, 150.0)


def test_energy_requirement_is_policy_independent():
    """Required energy is a property of the world, not of beliefs."""
    stream = generate_arrival_stream(seed=3, horizon_min=600.0, arrivals_per_hour=5.0)
    per_policy_energy = {}
    for pol in POLICIES:
        res = run_schedule(stream, pol, collect_timeline=True)
        needs = {t["ev_id"]: t["energy_kwh"] for t in res.timeline
                 if t["status"] == "done"}
        per_policy_energy[pol] = needs

    # Any EV completed under two policies must have received the same energy.
    agent = per_policy_energy["agent"]
    for pol, needs in per_policy_energy.items():
        for ev_id, e in needs.items():
            if ev_id in agent:
                assert e == pytest.approx(agent[ev_id], abs=0.05), (
                    f"{pol} delivered different energy to EV {ev_id}"
                )


def test_conventional_policies_cannot_see_language():
    """FIFO/SJF/SOC must hold no deadline belief whatsoever."""
    stream = generate_arrival_stream(seed=8, horizon_min=400.0, arrivals_per_hour=5.0)
    for pol in ("fifo", "sjf", "soc"):
        res = run_schedule(stream, pol, collect_timeline=True)
        for row in res.timeline:
            assert row["believed_deadline_min"] is None, (
                f"{pol} was given a deadline belief; it must be telemetry-only"
            )
            assert row["contradiction_flagged"] is False


# ---------------------------------------------------------------------------
# Port assignment
# ---------------------------------------------------------------------------

def test_best_fit_port_does_not_strand_a_fast_car_on_a_slow_port():
    """A 150 kW car offered all ports must not be given the 7 kW port."""
    spec = EVSpec(ev_id=0, arrival_min=0.0, battery_kwh=80.0, soc_pct=20.0,
                  max_rate_kw=150.0, budget=500.0, scenario_key="C_FASTEST")
    need, target = _energy_needed(spec)
    ev = EVState(spec=spec, energy_needed_kwh=need, target_soc=target, soc_pct=spec.soc_pct)
    ports = [Port(i, kw) for i, kw in enumerate([7.0, 50.0, 150.0])]
    assert _best_fit_port(ev, ports).power_kw == 150.0


def test_best_fit_port_prefers_not_to_waste_a_fast_port():
    """A 7 kW car must take the 7 kW port when one is free."""
    spec = EVSpec(ev_id=0, arrival_min=0.0, battery_kwh=40.0, soc_pct=30.0,
                  max_rate_kw=7.0, budget=500.0, scenario_key="S_CASUAL_COFFEE")
    need, target = _energy_needed(spec)
    ev = EVState(spec=spec, energy_needed_kwh=need, target_soc=target, soc_pct=spec.soc_pct)
    ports = [Port(i, kw) for i, kw in enumerate([7.0, 50.0, 150.0])]
    assert _best_fit_port(ev, ports).power_kw == 7.0


def test_no_port_is_double_booked():
    stream = generate_arrival_stream(seed=21, horizon_min=720.0, arrivals_per_hour=6.5)
    for pol in POLICIES:
        res = run_schedule(stream, pol, collect_timeline=True)
        by_port = {}
        for row in res.timeline:
            if row["start_min"] is None or row["end_min"] is None:
                continue
            by_port.setdefault(row["port_id"], []).append((row["start_min"], row["end_min"]))
        for port_id, spans in by_port.items():
            spans.sort()
            for (s1, e1), (s2, e2) in zip(spans, spans[1:]):
                assert e1 <= s2 + 1e-6, (
                    f"{pol}: port {port_id} double-booked {e1} > {s2}"
                )


# ---------------------------------------------------------------------------
# Validator behaviour
# ---------------------------------------------------------------------------

def test_validator_downgrades_contradictory_claim():
    """A CRITICAL claim from a nearly-full battery must be downgraded."""
    spec = EVSpec(ev_id=0, arrival_min=0.0, battery_kwh=80.0, soc_pct=85.0,
                  max_rate_kw=150.0, budget=500.0,
                  scenario_key="F_CONTRADICTORY_EMERGENCY")
    res = run_schedule([spec], "agent", collect_timeline=True, horizon_min=300.0)
    row = res.timeline[0]
    assert row["believed_urgency"] == "LOW"
    assert row["contradiction_flagged"] is True
    assert res.metrics["contradictions_flagged"] == 1


def test_no_validation_ablation_trusts_the_claim():
    spec = EVSpec(ev_id=0, arrival_min=0.0, battery_kwh=80.0, soc_pct=85.0,
                  max_rate_kw=150.0, budget=500.0,
                  scenario_key="F_CONTRADICTORY_EMERGENCY")
    res = run_schedule([spec], "agent_no_validation", collect_timeline=True,
                       horizon_min=300.0)
    row = res.timeline[0]
    assert row["believed_urgency"] == "CRITICAL"
    assert row["contradiction_flagged"] is False


def test_genuine_low_battery_emergency_is_not_downgraded():
    """The lie detector must not punish a real emergency."""
    spec = EVSpec(ev_id=0, arrival_min=0.0, battery_kwh=80.0, soc_pct=3.0,
                  max_rate_kw=150.0, budget=500.0,
                  scenario_key="N_LOW_BATTERY_PANIC")
    res = run_schedule([spec], "agent", collect_timeline=True, horizon_min=300.0)
    row = res.timeline[0]
    assert row["believed_urgency"] == "CRITICAL"
    assert row["contradiction_flagged"] is False


def test_contradiction_threshold_boundary():
    """Just below the threshold is kept; just above is downgraded."""
    base = dict(ev_id=0, arrival_min=0.0, battery_kwh=80.0, max_rate_kw=150.0,
                budget=500.0, scenario_key="F_CONTRADICTORY_EMERGENCY")
    below = EVSpec(**base, soc_pct=CONTRADICTION_SOC_THRESHOLD - 0.5)
    above = EVSpec(**base, soc_pct=CONTRADICTION_SOC_THRESHOLD + 0.5)

    r_below = run_schedule([below], "agent", collect_timeline=True, horizon_min=300.0)
    r_above = run_schedule([above], "agent", collect_timeline=True, horizon_min=300.0)
    assert r_below.timeline[0]["believed_urgency"] == "CRITICAL"
    assert r_above.timeline[0]["believed_urgency"] == "LOW"


# ---------------------------------------------------------------------------
# Ground truth hygiene
# ---------------------------------------------------------------------------

def test_agent_beliefs_are_causally_independent_of_ground_truth():
    """Perturb the answer key; the agent's beliefs must not move.

    A naive "believed == true_value" check cannot distinguish a leak from a
    coincidence (the agent maps CRITICAL to an implied 15-minute deadline, and
    L_BABY_IN_CAR genuinely has a 15-minute ground-truth deadline). The only
    sound test is causal: change ground truth and confirm nothing downstream
    of the decision path changes.
    """
    keys = [k for k, s in SCENARIOS.items() if s.true_deadline_min is not None]
    assert keys, "no deadline-bearing scenarios to test"

    specs = [
        EVSpec(ev_id=i, arrival_min=float(i * 3), battery_kwh=60.0, soc_pct=20.0,
               max_rate_kw=150.0, budget=500.0, scenario_key=k)
        for i, k in enumerate(keys)
    ]

    def beliefs():
        res = run_schedule(specs, "agent", collect_timeline=True, horizon_min=900.0)
        return {r["ev_id"]: (r["believed_urgency"], r["believed_deadline_min"])
                for r in res.timeline}

    before = beliefs()

    originals = {k: SCENARIOS[k].true_deadline_min for k in keys}
    try:
        for k in keys:
            # Shift every ground-truth deadline well away from its real value.
            SCENARIOS[k].true_deadline_min = originals[k] + 997
        after = beliefs()
    finally:
        for k, v in originals.items():
            SCENARIOS[k].true_deadline_min = v

    assert before == after, (
        "agent beliefs changed when ground truth was perturbed — the answer "
        "key is leaking into the decision path"
    )


def test_extraction_quality_is_imperfect_and_reported():
    """Guards against silently swapping in an oracle for the agent's input."""
    rep = extraction_quality_report()
    assert rep["scenarios_with_true_deadline"] > 0
    assert rep["deadlines_missed"] > 0, (
        "extraction is suspiciously perfect — is ground truth being fed in?"
    )
    assert 0.0 < rep["deadline_recall"] < 1.0


def test_all_scenarios_have_ground_truth_labels():
    for key, sc in SCENARIOS.items():
        assert sc.message, key
        assert sc.true_urgency in ("LOW", "MEDIUM", "HIGH", "CRITICAL"), key
        if sc.true_deadline_min is not None:
            assert sc.true_deadline_min > 0, key
            assert sc.notes, f"{key} has a deadline label but no justification"


# ---------------------------------------------------------------------------
# Performance regression guards (the headline claims)
# ---------------------------------------------------------------------------

def test_agent_beats_conventional_baselines_under_congestion():
    """Headline claim, held as a regression test."""
    on_time = {}
    for seed in range(6):
        stream = generate_arrival_stream(seed=2000 + seed, horizon_min=1440.0,
                                         arrivals_per_hour=6.5)
        res = run_all_policies(stream, policies=["fifo", "sjf", "soc", "agent"],
                               collect_timeline=False)
        for pol, r in res.items():
            on_time.setdefault(pol, []).append(r.metrics["on_time_rate"])

    mean = {p: sum(v) / len(v) for p, v in on_time.items()}
    for baseline in ("fifo", "sjf", "soc"):
        assert mean["agent"] > mean[baseline], (
            f"agent ({mean['agent']:.3f}) no longer beats {baseline} "
            f"({mean[baseline]:.3f}) on deadline adherence"
        )


def test_removing_deadlines_degrades_the_agent():
    """The gain must come from language-derived deadlines, not from tuning.

    If this fails, the agent's advantage is coming from somewhere other than
    the information only language provides — which would invalidate the claim.
    """
    with_dl, without_dl = [], []
    for seed in range(6):
        stream = generate_arrival_stream(seed=2500 + seed, horizon_min=1440.0,
                                         arrivals_per_hour=6.5)
        res = run_all_policies(stream, policies=["agent", "agent_no_deadline"],
                               collect_timeline=False)
        with_dl.append(res["agent"].metrics["on_time_rate"])
        without_dl.append(res["agent_no_deadline"].metrics["on_time_rate"])

    assert sum(with_dl) / len(with_dl) > sum(without_dl) / len(without_dl)


def test_agent_does_not_sacrifice_throughput_for_deadlines():
    """Deadline adherence must not be bought by serving fewer cars."""
    for seed in range(4):
        stream = generate_arrival_stream(seed=3000 + seed, horizon_min=1440.0,
                                         arrivals_per_hour=6.5)
        res = run_all_policies(stream, policies=["sjf", "agent"],
                               collect_timeline=False)
        assert res["agent"].metrics["served"] >= res["sjf"].metrics["served"] * 0.98


def test_metrics_are_internally_consistent():
    stream = generate_arrival_stream(seed=77, horizon_min=720.0, arrivals_per_hour=5.0)
    for pol in POLICIES:
        m = run_schedule(stream, pol, collect_timeline=False).metrics
        assert m["served"] <= m["arrived"]
        assert 0.0 <= m["served_rate"] <= 1.0
        assert 0.0 <= m["on_time_rate"] <= 1.0
        assert 0.0 <= m["port_utilisation"] <= 1.0
        assert m["deadline_on_time"] <= m["deadline_evs"]
        assert abs(m["on_time_rate"] + m["deadline_miss_rate"] - 1.0) < 1e-6
