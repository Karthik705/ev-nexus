"""
tests/test_core.py — Automated regression tests for the EV Charging Negotiator.

Replaces print-based acceptance_test.py, test_negotiator.py, and scratch_test.py
with real pytest assertions. Run with:

    pytest tests/test_core.py -v

All tests are deterministic (no live Gemini calls, no network I/O).
"""

import sys
import os
import typing
from collections import deque

# Ensure project root is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from simple_ev_simulation import (
    EVChargingSimulation, EVAgent, ChargingPort, ChargingSpeed, UrgencyLevel
)
from constraint_validator import ConstraintValidator
from negotiation_types import LLMParsedRequest, ValidatedChargingRequest
from llm_negotiator import GeminiNegotiator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ports(*speeds: ChargingSpeed) -> list[ChargingPort]:
    """Create a list of unoccupied ChargingPort objects."""
    return [ChargingPort(i, s, is_occupied=False) for i, s in enumerate(speeds)]


def _llm_request(
    urgency: str = "HIGH",
    deadline: int | None = 20,
    reason: str = "LATE",
    constraints: list[str] | None = None,
    port_type: str | None = None,
    confidence: float = 0.9,
    explanation: str = "test",
) -> LLMParsedRequest:
    return LLMParsedRequest(
        urgency_level=urgency,
        deadline_minutes=deadline,
        reason_category=reason,
        claimed_constraints=constraints or [],
        requested_port_type=port_type,
        confidence=confidence,
        explanation=explanation,
    )


# ---------------------------------------------------------------------------
# Test 1: Lie detector — HIGH urgency + SOC > 60% → contradiction
# ---------------------------------------------------------------------------

def test_lie_detector_contradiction_triggered():
    """
    Core 'lie detector': driver claims HIGH urgency but SOC > 60%.
    Expected: urgency_score forced to 0.2 (LOW), contradiction_found=True.
    """
    ports = _make_ports(ChargingSpeed.FAST)
    llm_req = _llm_request(urgency="HIGH", deadline=20)

    result = ConstraintValidator.validate_request(
        llm_req,
        actual_soc=85.0,        # well above 60% threshold
        battery_capacity=80.0,
        max_charging_speed=50.0,
        budget=50.0,
        available_ports=ports,
        llm_latency=0.1,
        parsing_success=True,
    )

    assert result.contradiction_found is True, "Contradiction should be flagged"
    assert result.validated_urgency_score == 0.2, (
        f"Urgency should be forced to 0.2 (LOW), got {result.validated_urgency_score}"
    )
    assert result.fallback_used is False, "Not a fallback — LLM parsed successfully"


# ---------------------------------------------------------------------------
# Test 2: SOC boundary — exactly 60% with urgency_score 0.5 (MEDIUM)
# The condition is `urgency_score > 0.5 AND actual_soc > 60.0`.
# At exactly SOC=60.0 and MEDIUM urgency (score=0.5) → NO contradiction.
# ---------------------------------------------------------------------------

def test_lie_detector_boundary_60pct_medium_no_contradiction():
    """
    Boundary: SOC exactly 60.0% and urgency MEDIUM (score=0.5).
    Condition is strict >0.5 AND >60.0 — neither met → no contradiction.
    """
    ports = _make_ports(ChargingSpeed.FAST)
    llm_req = _llm_request(urgency="MEDIUM")

    result = ConstraintValidator.validate_request(
        llm_req,
        actual_soc=60.0,
        battery_capacity=80.0,
        max_charging_speed=50.0,
        budget=50.0,
        available_ports=ports,
        llm_latency=0.0,
        parsing_success=True,
    )

    assert result.contradiction_found is False, "At exactly 60% SOC, no contradiction for MEDIUM"
    assert result.validated_urgency_score == 0.5, (
        f"MEDIUM should map to 0.5, got {result.validated_urgency_score}"
    )


# ---------------------------------------------------------------------------
# Test 3: SOC boundary — 60.01% with HIGH urgency → contradiction triggered
# ---------------------------------------------------------------------------

def test_lie_detector_boundary_just_above_60pct_high_contradiction():
    """
    Just above threshold: SOC=60.01%, urgency HIGH (score=0.8 > 0.5).
    Condition is strict > 0.5 AND > 60.0 — both met → contradiction.
    """
    ports = _make_ports(ChargingSpeed.FAST)
    llm_req = _llm_request(urgency="HIGH")

    result = ConstraintValidator.validate_request(
        llm_req,
        actual_soc=60.01,
        battery_capacity=80.0,
        max_charging_speed=50.0,
        budget=50.0,
        available_ports=ports,
        llm_latency=0.0,
        parsing_success=True,
    )

    assert result.contradiction_found is True
    assert result.validated_urgency_score == 0.2


# ---------------------------------------------------------------------------
# Test 4: Fallback triggering — parsing_success=False → telemetry-derived urgency
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("soc,expected_urgency,expected_reason", [
    (10.0, 0.9, "TELEMETRY_CRITICAL"),   # SOC < 20
    (35.0, 0.5, "TELEMETRY_MEDIUM"),    # 20 ≤ SOC < 50
    (70.0, 0.2, "TELEMETRY_LOW"),       # SOC ≥ 50
])
def test_fallback_telemetry_tiers(soc, expected_urgency, expected_reason):
    """
    When LLM parsing fails, urgency must be derived from SOC tiers.
    """
    ports = _make_ports(ChargingSpeed.SLOW, ChargingSpeed.FAST)
    result = ConstraintValidator.validate_request(
        llm_request=None,
        actual_soc=soc,
        battery_capacity=100.0,
        max_charging_speed=50.0,
        budget=50.0,
        available_ports=ports,
        llm_latency=0.0,
        parsing_success=False,
    )

    assert result.fallback_used is True
    assert result.validated_urgency_score == expected_urgency, (
        f"SOC={soc}% should give urgency {expected_urgency}, got {result.validated_urgency_score}"
    )
    assert result.reason_category == expected_reason


# ---------------------------------------------------------------------------
# Test 5: Budget rejection — expensive charge drops EV from queue
# ---------------------------------------------------------------------------

def test_budget_rejection_drops_ev():
    """
    If calculated price exceeds EV budget, EV must not appear in active_evs.
    Uses LLM_DETERMINISTIC policy which enforces budget constraints.
    """
    sim = EVChargingSimulation(simulation_hours=24.0, arrival_rate=0.0,
                               auto_dispatch=True, policy='LLM_DETERMINISTIC')
    sim.station.ports = [ChargingPort(0, ChargingSpeed.ULTRA)]
    sim.scheduler.queue = deque()

    # Create an EV that needs a lot of energy but has a tiny budget
    ev = EVAgent("budget_test", max_battery=100.0, current_battery=5.0,
                 max_charging_speed=150.0, arrival_time=0.0,
                 target_battery=95, budget=1.0)   # $1 budget for 90 kWh — impossible

    # Manually create a validated request so it goes through the LLM path
    llm_req = _llm_request(urgency="LOW")
    ports_list = sim.station.ports
    ev.validated_request = ConstraintValidator.validate_request(
        llm_req, 5.0, 100.0, 150.0, 1.0, ports_list, 0.0, True
    )

    sim.all_evs[ev.id] = ev
    sim.scheduler.add_ev(ev)
    sim.step()

    assert ev not in sim.active_evs, "Over-budget EV must not be assigned to a port"


# ---------------------------------------------------------------------------
# Test 6: Resource-aware port matching
# ---------------------------------------------------------------------------

def test_resource_aware_port_matching():
    """
    7 kW EV should get SLOW port; 150 kW EV should get ULTRA port.
    Both are in the queue; both ports are available.
    """
    sim = EVChargingSimulation(simulation_hours=24.0, arrival_rate=0.0,
                               auto_dispatch=True, policy='FIFO')
    sim.station.ports = [
        ChargingPort(0, ChargingSpeed.SLOW),   # 7 kW
        ChargingPort(1, ChargingSpeed.ULTRA),  # 150 kW
    ]
    sim.scheduler.queue = deque()

    ev_slow = EVAgent("slow_ev", 40.0, 10.0, 7.0, 0)
    ev_fast = EVAgent("fast_ev", 80.0, 20.0, 150.0, 0)

    sim.scheduler.add_ev(ev_slow)
    sim.scheduler.add_ev(ev_fast)
    sim.all_evs[ev_slow.id] = ev_slow
    sim.all_evs[ev_fast.id] = ev_fast

    sim.step()

    # Find which port each EV is on
    # Use Any-keyed dict: EV ids are strings here but current_ev_id is Optional[int];
    # the strings are valid ids at runtime, pyright over-narrows the dict key type.
    assignments: dict[typing.Any, ChargingSpeed] = {
        p.current_ev_id: p.speed for p in sim.station.ports if p.is_occupied
    }

    assert "slow_ev" in assignments, "slow_ev should be assigned"
    assert "fast_ev" in assignments, "fast_ev should be assigned"
    assert assignments["slow_ev"] == ChargingSpeed.SLOW, (
        f"7 kW EV should be on SLOW port, got {assignments['slow_ev']}"
    )
    assert assignments["fast_ev"] == ChargingSpeed.ULTRA, (
        f"150 kW EV should be on ULTRA port, got {assignments['fast_ev']}"
    )


# ---------------------------------------------------------------------------
# Test 7: Fixture-based negotiate mock — returns correct LLMParsedRequest
# ---------------------------------------------------------------------------

def test_fixture_negotiate_returns_correct_request():
    """
    The patched_negotiate (fixture replay) must return a valid LLMParsedRequest
    with success=True when given a known fixture message.
    Uses a minimal mock fixture so no API key is required.
    """
    negotiator = GeminiNegotiator()
    # Ensure client is None so there's no chance of live API call
    negotiator.client = None

    # Inject a minimal fixture directly into the module-level dict
    import experiment_comparison as ec
    test_msg = "__test_fixture_message_xyz__"
    ec._VALID_FIXTURES["__TEST__"] = {
        "urgency_level":      "HIGH",
        "deadline_minutes":   15,
        "reason_category":    "TEST",
        "claimed_constraints": ["test_constraint"],
        "requested_port_type": None,
        "confidence":         0.99,
        "explanation":        "Synthetic test fixture",
    }
    ec._AVAILABLE_SCENARIOS["__TEST__"] = test_msg
    ec._AVAILABLE_KEYS.append("__TEST__")

    req, lat, succ = negotiator.negotiate(test_msg)

    # Cleanup
    del ec._VALID_FIXTURES["__TEST__"]
    del ec._AVAILABLE_SCENARIOS["__TEST__"]
    ec._AVAILABLE_KEYS.remove("__TEST__")

    assert succ is True, "Fixture hit must return success=True"
    assert req is not None
    assert req.urgency_level == "HIGH"
    assert req.deadline_minutes == 15
    assert req.reason_category == "TEST"
    assert req.confidence == 0.99


# ---------------------------------------------------------------------------
# Test 8: Negotiate without client → fallback (None, 0.0, False)
# ---------------------------------------------------------------------------

def test_negotiate_no_client_returns_fallback():
    """
    When Gemini client is not initialised (no API key), the ORIGINAL negotiate()
    must return (None, 0.0, False) and increment fallback_count — never raises.

    Note: we must call the ORIGINAL negotiate, not the monkeypatched one from
    experiment_comparison (which was imported in test_fixture_negotiate_returns_correct_request).
    The original is still accessible via experiment_comparison.original_negotiate.
    """
    negotiator = GeminiNegotiator()
    negotiator.client = None  # Simulate missing / invalid API key

    # original_negotiate is the unbound function saved before experiment_comparison
    # monkeypatches GeminiNegotiator.negotiate. We call it as an unbound function,
    # passing negotiator as self. If experiment_comparison is not importable we fall
    # back to calling the (bound) method directly — one positional arg only.
    try:
        import experiment_comparison as ec
        unbound = ec.original_negotiate          # plain function, takes (self, msg)
        req, lat, succ = unbound(negotiator, "I need a charge.")
    except (ImportError, AttributeError):
        # experiment_comparison not loaded — call the (possibly patched) bound method
        req, lat, succ = negotiator.negotiate("I need a charge.")

    assert req is None
    assert succ is False
    assert lat == 0.0
    assert negotiator.fallback_count == 1
    assert negotiator.success_count == 0
    assert any(t == "NO_CLIENT" for t, _ in negotiator.error_log), (
        "Error log must contain a NO_CLIENT entry"
    )
