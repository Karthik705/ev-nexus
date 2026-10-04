"""
Ground-truth scenario library for the EV NEXUS v2 benchmark.

WHY THIS FILE EXISTS
--------------------
The v1 benchmark could not measure the thing that actually distinguishes an
LLM-assisted scheduler from a conventional one. Conventional schedulers (FIFO,
SJF, lowest-SOC-first) have access to telemetry only. The *deadline* a driver is
working against ("my flight leaves in 2 hours and the airport is 40 minutes
away") exists ONLY in natural language. If deadline adherence is never measured,
the agent's single structural advantage is invisible.

So this file defines, for each canonical driver message, the TRUE constraint a
careful human reader would infer from the text. These labels are:

  * authored by hand from the message text, INDEPENDENTLY of what Gemini
    extracted (so extraction accuracy is itself measurable, not assumed), and
  * used ONLY for evaluation. No scheduling policy — including the agent — ever
    reads `true_deadline_min` or `true_urgency` when making decisions.

The agent sees exactly what a deployed system would see: the raw message (via
Gemini's extraction in `llm_fixtures.json`) plus real telemetry. Ground truth is
the answer key, kept strictly on the grading side.
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, List
import json
import os
import random

# Urgency ordering used for scoring. Higher = more urgent.
URGENCY_RANK = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}
URGENCY_SCORE = {"LOW": 0.2, "MEDIUM": 0.5, "HIGH": 0.8, "CRITICAL": 1.0}


@dataclass
class Scenario:
    """One canonical driver request, with hand-authored ground truth."""
    key: str
    message: str

    # --- Ground truth (evaluation only — never visible to any policy) ---
    true_deadline_min: Optional[int]   # real departure deadline, None if genuinely open-ended
    true_urgency: str                  # what the situation actually warrants
    # True when the message asserts urgency it provides no verifiable basis for.
    # Telemetry decides the real answer for these — this is the adversarial case.
    is_unverified_claim: bool = False
    # Driver wants a full charge rather than the standard 80% top-up.
    wants_full_charge: bool = False
    # Fixed energy requirement in kWh, when the driver needs only "enough to
    # get there" rather than a full top-up. This is part of the WORLD, not a
    # belief: it is applied identically to every policy, so it never gives the
    # agent a physics advantage. It exists because a 10-minute deadline paired
    # with a 40 kWh top-up is not a scheduling problem, it is an impossibility —
    # no policy could ever satisfy it and the metric would be degenerate.
    required_kwh: Optional[float] = None
    # Hard spending cap stated in the message itself, if any.
    stated_budget: Optional[float] = None
    notes: str = ""


# ---------------------------------------------------------------------------
# The 20 canonical scenarios. Messages are byte-identical to the strings used
# in generate_fixtures.py, so they map 1:1 onto the captured Gemini outputs in
# llm_fixtures.json.
#
# Deadline reasoning is recorded in `notes` for every labelled deadline so the
# labels are auditable rather than arbitrary.
# ---------------------------------------------------------------------------
SCENARIOS: Dict[str, Scenario] = {
    "A_HARD_DEADLINE": Scenario(
        key="A_HARD_DEADLINE",
        message="I need to leave within 15 minutes.",
        true_deadline_min=15, true_urgency="HIGH",
        required_kwh=8.0,
        notes="Explicit: 'within 15 minutes'. Departing that soon means they "
              "can only take a partial charge (~8 kWh).",
    ),
    "B_FLEXIBLE": Scenario(
        key="B_FLEXIBLE",
        message="I can wait for an hour.",
        true_deadline_min=60, true_urgency="MEDIUM",
        notes="Explicit: 'an hour' = 60 min of available slack.",
    ),
    "C_FASTEST": Scenario(
        key="C_FASTEST",
        message="I need the fastest charging option available.",
        true_deadline_min=None, true_urgency="HIGH",
        notes="Wants speed but states no departure time — no hard deadline.",
    ),
    "D_CHEAPEST": Scenario(
        key="D_CHEAPEST",
        message="I don't mind waiting. Please minimize my charging cost.",
        true_deadline_min=None, true_urgency="LOW",
        notes="Explicitly time-flexible, cost-sensitive.",
    ),
    "E_GENUINE_EMERGENCY": Scenario(
        key="E_GENUINE_EMERGENCY",
        message="I have a medical emergency and need to leave immediately.",
        true_deadline_min=10, true_urgency="CRITICAL",
        required_kwh=8.0,
        notes="'immediately' treated as a 10-minute hard deadline; only enough "
              "charge to reach the hospital is required.",
    ),
    "F_CONTRADICTORY_EMERGENCY": Scenario(
        key="F_CONTRADICTORY_EMERGENCY",
        message="This is an emergency and I need priority.",
        true_deadline_min=None, true_urgency="LOW",
        is_unverified_claim=True,
        wants_full_charge=True,
        notes="Asserts emergency with zero verifiable detail. The adversarial "
              "case: telemetry must decide, not the claim. Modelled as wanting "
              "a full charge, because that is the actual incentive to lie — "
              "jumping the queue for a large charge on the premium port. A "
              "liar who only needed 3 kWh would not be worth validating "
              "against.",
    ),
    "G_AMBIGUOUS_TRADEOFF": Scenario(
        key="G_AMBIGUOUS_TRADEOFF",
        message="I'm in a hurry but I don't want to spend too much.",
        true_deadline_min=None, true_urgency="HIGH",
        notes="Genuine hurry, no stated time; competing cost preference.",
    ),
    "H_LONG_ROADTRIP": Scenario(
        key="H_LONG_ROADTRIP",
        message="I am on a long road trip and need a full charge, can wait 2 hours.",
        true_deadline_min=120, true_urgency="MEDIUM",
        wants_full_charge=True,
        notes="Explicit: 'can wait 2 hours' = 120 min; wants full charge.",
    ),
    "I_APPOINTMENT": Scenario(
        key="I_APPOINTMENT",
        message="Late for my dentist appointment in 20 minutes, just need a quick top up.",
        true_deadline_min=20, true_urgency="HIGH",
        required_kwh=8.0,
        notes="Explicit 20-minute appointment; message says 'quick top up'.",
    ),
    "J_NIGHT_SHIFT": Scenario(
        key="J_NIGHT_SHIFT",
        message="Working the night shift, I can leave the car here for 8 hours.",
        true_deadline_min=480, true_urgency="LOW",
        notes="Explicit: 8 hours = 480 min. Ideal deferrable load.",
    ),
    "K_BUDGET_STRICT": Scenario(
        key="K_BUDGET_STRICT",
        message="I only have $10 to spend, give me what you can.",
        true_deadline_min=None, true_urgency="LOW",
        stated_budget=10.0,
        notes="Hard $10 cap stated in language, not telemetry.",
    ),
    "L_BABY_IN_CAR": Scenario(
        key="L_BABY_IN_CAR",
        message="I have a crying baby in the car, please give me the fastest port so I can leave ASAP.",
        true_deadline_min=15, true_urgency="CRITICAL",
        required_kwh=8.0,
        notes="'ASAP' with a concrete verifiable reason -> 15-minute deadline.",
    ),
    "M_FLIGHT": Scenario(
        key="M_FLIGHT",
        message="My flight leaves in 2 hours, I need to reach the airport which is 40 mins away.",
        true_deadline_min=80, true_urgency="HIGH",
        notes="Requires arithmetic: 120 - 40 = 80 min. Deadline is NOT stated "
              "directly; it must be derived from the sentence.",
    ),
    "N_LOW_BATTERY_PANIC": Scenario(
        key="N_LOW_BATTERY_PANIC",
        message="My car says 1% and I'm scared it will die, please help!",
        true_deadline_min=None, true_urgency="CRITICAL",
        required_kwh=15.0,
        notes="Critical by state of charge, not by departure time. This case is "
              "the one conventional telemetry schedulers already handle well.",
    ),
    "O_GROCERY": Scenario(
        key="O_GROCERY",
        message="Going into the grocery store for about 45 minutes.",
        true_deadline_min=45, true_urgency="LOW",
        notes="Explicit ~45 min errand.",
    ),
    "P_MOVIE": Scenario(
        key="P_MOVIE",
        message="Watching a movie next door, will be back in 3 hours.",
        true_deadline_min=180, true_urgency="LOW",
        notes="Explicit: 3 hours = 180 min.",
    ),
    "Q_UBER_DRIVER": Scenario(
        key="Q_UBER_DRIVER",
        message="I'm an Uber driver and I'm losing money every minute I wait here.",
        true_deadline_min=None, true_urgency="HIGH",
        notes="Economic urgency, genuine but with no hard departure time.",
    ),
    "R_DELIVERY": Scenario(
        key="R_DELIVERY",
        message="Amazon delivery van, need enough charge to finish my route, got 30 mins max.",
        true_deadline_min=30, true_urgency="HIGH",
        required_kwh=12.0,
        notes="Explicit: '30 mins max'; needs 'enough charge to finish my route'.",
    ),
    "S_CASUAL_COFFEE": Scenario(
        key="S_CASUAL_COFFEE",
        message="Grabbing a coffee, no rush at all.",
        true_deadline_min=None, true_urgency="LOW",
        notes="Explicitly no time pressure.",
    ),
    "T_WIFE_LABOR": Scenario(
        key="T_WIFE_LABOR",
        message="My wife is in labor! Need fastest charge right now!",
        true_deadline_min=10, true_urgency="CRITICAL",
        required_kwh=8.0,
        notes="'right now' with a concrete verifiable reason -> 10-minute deadline.",
    ),
}


@dataclass
class LLMExtraction:
    """What the language model actually returned for a scenario.

    This is what the agent is allowed to see. It may be wrong — that is the
    point. `deadline_minutes=None` where a true deadline exists is a miss, and
    the benchmark reports it rather than hiding it.
    """
    urgency_level: str
    deadline_minutes: Optional[int]
    reason_category: str
    claimed_constraints: List[str] = field(default_factory=list)
    confidence: float = 0.5
    explanation: str = ""
    source: str = "unknown"


def load_extractions(path: str = "llm_fixtures.json") -> Dict[str, LLMExtraction]:
    """Load captured Gemini outputs keyed by scenario."""
    here = os.path.dirname(os.path.abspath(__file__))
    full = path if os.path.isabs(path) else os.path.join(here, path)
    with open(full, "r", encoding="utf-8") as f:
        raw = json.load(f)

    out: Dict[str, LLMExtraction] = {}
    for key, val in raw.items():
        if not val:
            continue
        out[key] = LLMExtraction(
            urgency_level=val.get("urgency_level", "MEDIUM"),
            deadline_minutes=val.get("deadline_minutes"),
            reason_category=val.get("reason_category", "UNKNOWN"),
            claimed_constraints=val.get("claimed_constraints", []) or [],
            confidence=float(val.get("confidence", 0.5)),
            explanation=val.get("explanation", ""),
            source=val.get("source", "unknown"),
        )
    return out


def extraction_quality_report(
    extractions: Optional[Dict[str, LLMExtraction]] = None,
) -> dict:
    """Compare Gemini's extraction against the hand-authored ground truth.

    Reported in the benchmark so the agent's inputs are characterised honestly:
    the agent is not assumed to have perfect deadline knowledge, and where the
    model missed a deadline that is counted as a miss.
    """
    if extractions is None:
        extractions = load_extractions()

    with_true_deadline = [s for s in SCENARIOS.values() if s.true_deadline_min is not None]
    recovered, missed, exact, close = [], [], 0, 0

    for sc in with_true_deadline:
        ex = extractions.get(sc.key)
        got = ex.deadline_minutes if ex else None
        if got is None:
            missed.append(sc.key)
            continue
        recovered.append(sc.key)
        if got == sc.true_deadline_min:
            exact += 1
        if abs(got - sc.true_deadline_min) <= max(5, 0.25 * sc.true_deadline_min):
            close += 1

    # Urgency agreement across all scenarios, excluding the adversarial claim
    # (where disagreeing with the stated urgency is the correct behaviour).
    judged = [s for s in SCENARIOS.values() if not s.is_unverified_claim]
    urgency_match = sum(
        1 for s in judged
        if extractions.get(s.key) and extractions[s.key].urgency_level == s.true_urgency
    )

    return {
        "scenarios_total": len(SCENARIOS),
        "scenarios_with_true_deadline": len(with_true_deadline),
        "deadlines_recovered": len(recovered),
        "deadlines_missed": len(missed),
        "deadlines_missed_keys": sorted(missed),
        "deadline_recall": round(len(recovered) / len(with_true_deadline), 4),
        "deadline_exact_matches": exact,
        "deadline_within_tolerance": close,
        "urgency_agreement": round(urgency_match / len(judged), 4),
        "urgency_judged_scenarios": len(judged),
        "note": (
            "Ground truth is hand-authored from the message text and used only "
            "for grading. No policy reads it. The adversarial scenario "
            "F_CONTRADICTORY_EMERGENCY is excluded from urgency agreement "
            "because disagreeing with its stated urgency is correct."
        ),
    }


# ---------------------------------------------------------------------------
# Arrival-stream generation
#
# The v1 harness seeded the RNG per run, but the agent policies then consumed
# extra random draws (fixture selection, negotiator bookkeeping), so the arrival
# streams silently diverged between policies and the comparison was not actually
# paired. Here the stream is generated ONCE and handed to every policy verbatim,
# which gives a true common-random-numbers paired design.
# ---------------------------------------------------------------------------

BATTERY_CHOICES = [40.0, 60.0, 75.0, 100.0]

# Accepted charging rate, weighted to reflect a realistic modern fleet: most
# EVs at a public station accept DC fast charging, and only a minority are
# limited to ~7 kW AC. A uniform 1/3 split over {7, 50, 150} would flood the
# station with 7 kW cars that occupy a port for hours, saturating it regardless
# of scheduling policy and making every policy look equally bad.
RATE_CHOICES = [7.0, 50.0, 150.0]
RATE_WEIGHTS = [0.15, 0.45, 0.40]


@dataclass
class EVSpec:
    """A fully-determined arrival. Identical across all policies."""
    ev_id: int
    arrival_min: float
    battery_kwh: float
    soc_pct: float
    max_rate_kw: float
    budget: float
    scenario_key: str

    @property
    def message(self) -> str:
        return SCENARIOS[self.scenario_key].message


def generate_arrival_stream(
    seed: int,
    horizon_min: float = 1440.0,
    arrivals_per_hour: float = 5.0,
    adversarial_fraction: float = 0.0,
) -> List[EVSpec]:
    """Build one deterministic arrival stream.

    SOC is correlated with the scenario so the world is self-consistent: the
    driver who says "my car says 1%" actually arrives nearly empty, and the
    driver making an unverifiable emergency claim arrives with a comfortably
    full battery (which is what makes the claim checkable at all).

    `adversarial_fraction` forces that share of arrivals to be the unverifiable
    emergency claim, for the gaming-pressure stress test. It defaults to 0 so
    the headline benchmark uses the natural, uniform scenario mix.
    """
    rng = random.Random(seed)
    keys = sorted(SCENARIOS.keys())
    adversarial_keys = [k for k, s in SCENARIOS.items() if s.is_unverified_claim]

    specs: List[EVSpec] = []
    t = 0.0
    ev_id = 0
    mean_gap = 60.0 / arrivals_per_hour

    while True:
        t += rng.expovariate(1.0 / mean_gap)
        if t >= horizon_min:
            break

        if adversarial_keys and rng.random() < adversarial_fraction:
            key = rng.choice(adversarial_keys)
        else:
            key = rng.choice(keys)
        sc = SCENARIOS[key]

        battery = rng.choice(BATTERY_CHOICES)

        # Scenario-consistent state of charge.
        if sc.key == "N_LOW_BATTERY_PANIC":
            soc = rng.uniform(1.0, 5.0)
        elif sc.is_unverified_claim:
            # The liar is comfortably charged. Telemetry can expose the claim.
            soc = rng.uniform(62.0, 88.0)
        elif sc.true_urgency == "CRITICAL":
            soc = rng.uniform(5.0, 25.0)
        elif sc.true_urgency == "HIGH":
            soc = rng.uniform(15.0, 45.0)
        else:
            soc = rng.uniform(25.0, 65.0)

        rate = rng.choices(RATE_CHOICES, weights=RATE_WEIGHTS, k=1)[0]

        if sc.stated_budget is not None:
            budget = sc.stated_budget
        else:
            budget = round(rng.uniform(15.0, 90.0), 2)

        specs.append(EVSpec(
            ev_id=ev_id,
            arrival_min=round(t, 3),
            battery_kwh=battery,
            soc_pct=round(soc, 2),
            max_rate_kw=rate,
            budget=budget,
            scenario_key=key,
        ))
        ev_id += 1

    return specs


if __name__ == "__main__":
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    print("Extraction quality vs hand-authored ground truth:")
    rep = extraction_quality_report()
    for k, v in rep.items():
        if k != "note":
            print(f"  {k}: {v}")

    stream = generate_arrival_stream(seed=42, horizon_min=1440.0, arrivals_per_hour=5.0)
    print(f"\nSample stream (seed=42, 5/hr, 24h): {len(stream)} arrivals")
    for s in stream[:5]:
        print(f"  t={s.arrival_min:7.1f}min  {s.scenario_key:<26} "
              f"soc={s.soc_pct:5.1f}%  {s.battery_kwh:5.1f}kWh  "
              f"{s.max_rate_kw:5.1f}kW  ${s.budget}")
