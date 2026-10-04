"""
Deterministic scheduling engine for the EV NEXUS v2 evaluation.

DESIGN GOAL: a comparison that cannot be accused of favouring the agent.

Every policy in this engine shares, bit for bit:
  * the same charging physics (power limits, taper above 80% SOC),
  * the same pricing model (energy x port-tier multiplier, with NO urgency
    multiplier, so the agent cannot inflate revenue by knowing urgency),
  * the same budget enforcement (an EV is never silently dropped for any
    policy -- the v1 engine enforced budget ONLY for the agent policies and let
    the heuristics ignore it, which penalised the agent's throughput),
  * the same arrival stream (passed in verbatim, never regenerated per policy),
  * the same best-fit port-selection heuristic for all conventional baselines,
    so the baselines are strong rather than strawmen.

Only the *decision* differs. Ground-truth labels in scenario_library are used
exclusively for grading and are never read by any policy.

The same engine backs both the offline benchmark and the live /api/compare
endpoint, so the website shows the identical computation the benchmark reports.
"""

from dataclasses import dataclass, field, asdict
from typing import Optional, Dict, List, Tuple
import math

from scenario_library import (
    SCENARIOS, URGENCY_SCORE, EVSpec, LLMExtraction, load_extractions,
)

# --- Physics / economics (identical for every policy) ----------------------
TIME_STEP_MIN = 1.0
DEFAULT_TARGET_SOC = 80.0        # standard top-up
FULL_CHARGE_TARGET_SOC = 100.0   # only when the driver asks for a full charge
TAPER_START_SOC = 80.0           # charging slows above this, as real packs do
ENERGY_PRICE_PER_KWH = 0.30
PORT_TIER_MULTIPLIER = {7.0: 1.0, 50.0: 1.15, 150.0: 1.3}

# Station layout used by the benchmark: one AC trickle port plus a realistic
# mix of DC fast chargers, as found at a modern public site.
DEFAULT_STATION = [7.0, 50.0, 50.0, 150.0, 150.0]

# --- Agent scoring weights -------------------------------------------------
# Chosen on principle, not swept per scenario: meeting a deadline dominates,
# then urgency, then tightness, then power efficiency, then anti-starvation.
W_DEADLINE_FEASIBLE = 10.0
W_URGENCY = 3.0
W_TIGHTNESS = 2.0
W_ACHIEVED_POWER = 2.0    # charge fast -> finish sooner -> free the port sooner
W_POWER_WASTE = 1.5       # don't squat a 150 kW port with a 7 kW car
W_SHORT_JOB = 1.5         # SJF's real insight: clearing short jobs decongests
W_AGING = 1.0

PEAK_PORT_KW = 150.0      # normaliser for the power terms

# Implied deadline when the driver conveys urgency but states no time. Without
# this, every "my wife is in labor" case (where Gemini returns deadline=None)
# would be treated as having unlimited slack.
IMPLIED_DEADLINE_MIN = {"CRITICAL": 15.0, "HIGH": 45.0, "MEDIUM": 120.0, "LOW": None}

CONTRADICTION_SOC_THRESHOLD = 60.0  # matches constraint_validator.py


@dataclass
class Port:
    port_id: int
    power_kw: float
    busy_until: float = -1.0
    current_ev: Optional[int] = None
    busy_minutes: float = 0.0

    @property
    def is_free(self) -> bool:
        return self.current_ev is None


@dataclass
class EVState:
    spec: EVSpec
    energy_needed_kwh: float
    target_soc: float
    soc_pct: float
    status: str = "waiting"          # waiting | charging | done
    port_id: Optional[int] = None
    start_min: Optional[float] = None
    finish_min: Optional[float] = None
    energy_delivered_kwh: float = 0.0
    cost: float = 0.0

    # Agent-visible beliefs (from language + telemetry). Never ground truth.
    believed_urgency: str = "MEDIUM"
    believed_deadline_min: Optional[float] = None
    contradiction_flagged: bool = False

    @property
    def wait_min(self) -> float:
        if self.start_min is None:
            return 0.0
        return self.start_min - self.spec.arrival_min

    @property
    def true_deadline_abs(self) -> Optional[float]:
        sc = SCENARIOS[self.spec.scenario_key]
        if sc.true_deadline_min is None:
            return None
        return self.spec.arrival_min + sc.true_deadline_min

    @property
    def believed_deadline_abs(self) -> Optional[float]:
        if self.believed_deadline_min is None:
            return None
        return self.spec.arrival_min + self.believed_deadline_min


def _energy_needed(spec: EVSpec) -> Tuple[float, float]:
    """Ground-truth energy requirement for this arrival.

    Applied identically to every policy — this is a property of the driver's
    actual need, not of anyone's beliefs about it.
    """
    sc = SCENARIOS[spec.scenario_key]
    target = FULL_CHARGE_TARGET_SOC if sc.wants_full_charge else DEFAULT_TARGET_SOC
    headroom = max(0.0, (target - spec.soc_pct) / 100.0 * spec.battery_kwh)

    if sc.required_kwh is not None:
        # Driver needs only "enough to get there"; never more than headroom.
        need = min(sc.required_kwh, headroom)
    else:
        need = headroom

    final_soc = spec.soc_pct + (need / spec.battery_kwh) * 100.0 if spec.battery_kwh else target
    return need, min(target, final_soc)


def _price(energy_kwh: float, port_kw: float) -> float:
    mult = PORT_TIER_MULTIPLIER.get(port_kw, 1.0)
    return energy_kwh * ENERGY_PRICE_PER_KWH * mult


def _affordable(ev: EVState, port: Port) -> bool:
    """Identical budget rule for every policy."""
    return _price(ev.energy_needed_kwh, port.power_kw) <= ev.spec.budget + 1e-9


def _est_charge_minutes(ev: EVState, port: Port) -> float:
    power = min(port.power_kw, ev.spec.max_rate_kw)
    if power <= 0:
        return math.inf
    # Planning estimate ignores taper; taper only applies above 80% SOC, which
    # is the target for all but full-charge requests.
    return (ev.energy_needed_kwh / power) * 60.0


# ---------------------------------------------------------------------------
# Belief construction: what each policy family is allowed to know
# ---------------------------------------------------------------------------

def _apply_agent_beliefs(
    ev: EVState,
    extractions: Dict[str, LLMExtraction],
    validate: bool,
    use_deadline: bool,
) -> None:
    """Populate the agent's beliefs from language + telemetry.

    `validate=False` is the ablation that trusts the model's claim outright.
    `use_deadline=False` is the ablation that discards the language-derived
    deadline, isolating how much of the gain comes from deadline recovery.
    """
    ex = extractions.get(ev.spec.scenario_key)
    claimed = ex.urgency_level if ex else "MEDIUM"

    if validate:
        # The deterministic safety layer: a high-urgency claim contradicted by
        # telemetry is downgraded, exactly as constraint_validator.py does in
        # production.
        if URGENCY_SCORE.get(claimed, 0.5) > 0.5 and ev.spec.soc_pct > CONTRADICTION_SOC_THRESHOLD:
            ev.believed_urgency = "LOW"
            ev.contradiction_flagged = True
        else:
            ev.believed_urgency = claimed
    else:
        ev.believed_urgency = claimed

    if not use_deadline:
        ev.believed_deadline_min = None
        return

    stated = ex.deadline_minutes if ex else None
    if stated is not None:
        ev.believed_deadline_min = float(stated)
    else:
        # No explicit time in the text. Infer one from (validated) urgency so
        # that "leave immediately" is not treated as unlimited slack.
        ev.believed_deadline_min = IMPLIED_DEADLINE_MIN.get(ev.believed_urgency)


# ---------------------------------------------------------------------------
# Port selection shared by the conventional baselines (best fit, not a strawman)
# ---------------------------------------------------------------------------

def _best_fit_port(ev: EVState, free_ports: List[Port]) -> Optional[Port]:
    """Pick the port that wastes the least power headroom, then the fastest.

    Given to every conventional baseline so they are competitive: the only
    difference between baselines is queue ordering, not port quality.
    """
    affordable = [p for p in free_ports if _affordable(ev, p)]
    if not affordable:
        return None
    return min(
        affordable,
        key=lambda p: (max(0.0, p.power_kw - ev.spec.max_rate_kw),
                       -min(p.power_kw, ev.spec.max_rate_kw)),
    )


# ---------------------------------------------------------------------------
# Policies
# ---------------------------------------------------------------------------

CONVENTIONAL_ORDERINGS = {
    # First-in first-out: the fairness baseline.
    "fifo": lambda ev, now: (ev.spec.arrival_min,),
    # Shortest job first: the throughput-optimal conventional baseline.
    "sjf": lambda ev, now: (ev.energy_needed_kwh,),
    # Lowest state of charge first: the strongest telemetry-only baseline,
    # and the best a conventional system can do without reading language.
    "soc": lambda ev, now: (ev.spec.soc_pct,),
}


def _dispatch_conventional(
    policy: str, queue: List[EVState], free_ports: List[Port], now: float
) -> List[Tuple[EVState, Port]]:
    keyfn = CONVENTIONAL_ORDERINGS[policy]
    assignments: List[Tuple[EVState, Port]] = []
    remaining = sorted(queue, key=lambda e: keyfn(e, now))
    ports = list(free_ports)

    for ev in remaining:
        if not ports:
            break
        port = _best_fit_port(ev, ports)
        if port is None:
            continue  # cannot afford any free port right now; stays queued
        assignments.append((ev, port))
        ports.remove(port)
    return assignments


def _pair_score(ev: EVState, port: Port, now: float) -> float:
    """Value of committing this EV to this port, right now.

    This is the agent's contribution. Four ideas, in priority order:

    1. Meeting a deadline is worth more than anything else, so an assignment
       that actually lands before the deadline gets a dominant bonus.
    2. Among equals, serve the more urgent driver.
    3. Prefer tight slack over loose slack (least-slack-first), because a
       driver with hours of slack loses nothing by waiting a few minutes.
    4. Match cars to ports on power: charge fast where it helps (the session
       ends sooner and frees the port for the next driver), but do not squat a
       150 kW port with a 7 kW car that cannot use it.
    5. Clear short jobs. This is the one genuinely good idea in SJF, and
       folding it in is what keeps the agent's throughput competitive instead
       of trading throughput away for fairness.

    Plus an aging term so nobody starves.
    """
    est = _est_charge_minutes(ev, port)
    deadline_abs = ev.believed_deadline_abs

    score = 0.0

    if deadline_abs is not None:
        finish = now + est
        slack = deadline_abs - finish
        if slack >= 0:
            # This assignment saves the deadline.
            score += W_DEADLINE_FEASIBLE
            # Tighter slack first: a 5-minute margin is far more urgent to
            # commit than a 5-hour margin.
            score += W_TIGHTNESS * (1.0 / (1.0 + slack / 30.0))
        else:
            # Will miss on this port. Still worth something (partial service,
            # and a faster port may yet rescue it), but it must not outrank a
            # deadline that is still winnable.
            score += W_TIGHTNESS * 0.5 * (1.0 / (1.0 + (-slack) / 30.0))

    score += W_URGENCY * URGENCY_SCORE.get(ev.believed_urgency, 0.5)

    # Achieved power: what this pairing will actually deliver. Rewarding this
    # is what stops a 50 kW car being parked on the 7 kW port, where it would
    # charge seven times slower and hold the slot for hours.
    achieved_kw = min(port.power_kw, ev.spec.max_rate_kw)
    score += W_ACHIEVED_POWER * (achieved_kw / PEAK_PORT_KW)

    # Over-provisioning penalty: headroom this car cannot use is capacity
    # denied to a car that could.
    wasted_kw = max(0.0, port.power_kw - ev.spec.max_rate_kw)
    score -= W_POWER_WASTE * (wasted_kw / PEAK_PORT_KW)

    # Short-job preference: finishing a 10-minute session now shortens the
    # queue for everyone behind it.
    score += W_SHORT_JOB * (1.0 / (1.0 + est / 30.0))

    # Anti-starvation.
    waited = max(0.0, now - ev.spec.arrival_min)
    score += W_AGING * min(waited / 60.0, 3.0)

    return score


def _dispatch_agent(
    queue: List[EVState], free_ports: List[Port], now: float
) -> List[Tuple[EVState, Port]]:
    """Greedy maximum-weight matching over (EV, port) pairs.

    Scores every feasible pair, then commits the best non-conflicting ones.
    Greedy rather than optimal (Hungarian) because the station has a handful of
    ports; with <=8 ports the greedy solution is near-identical and the
    behaviour stays explainable, which matters for a system that has to justify
    its decisions to drivers.
    """
    pairs: List[Tuple[float, int, int, EVState, Port]] = []
    for ev in queue:
        for port in free_ports:
            if not _affordable(ev, port):
                continue
            s = _pair_score(ev, port, now)
            # ev_id / port_id included to make ordering fully deterministic.
            pairs.append((-s, ev.spec.ev_id, port.port_id, ev, port))

    pairs.sort(key=lambda t: (t[0], t[1], t[2]))

    used_evs, used_ports = set(), set()
    assignments: List[Tuple[EVState, Port]] = []
    for _, ev_id, port_id, ev, port in pairs:
        if ev_id in used_evs or port_id in used_ports:
            continue
        used_evs.add(ev_id)
        used_ports.add(port_id)
        assignments.append((ev, port))
    return assignments


POLICIES = {
    "fifo":               {"label": "FIFO",                 "family": "conventional"},
    "sjf":                {"label": "Shortest Job First",   "family": "conventional"},
    "soc":               {"label": "Lowest SOC First",      "family": "conventional"},
    "agent":              {"label": "EV NEXUS Agent",       "family": "agent"},
    "agent_no_validation": {"label": "Agent (no validator)", "family": "ablation"},
    "agent_no_deadline":  {"label": "Agent (no deadlines)", "family": "ablation"},
}


# ---------------------------------------------------------------------------
# Simulation
# ---------------------------------------------------------------------------

@dataclass
class ScheduleResult:
    policy: str
    metrics: dict
    timeline: List[dict] = field(default_factory=list)
    unserved: List[dict] = field(default_factory=list)


def run_schedule(
    specs: List[EVSpec],
    policy: str,
    station: Optional[List[float]] = None,
    horizon_min: Optional[float] = None,
    extractions: Optional[Dict[str, LLMExtraction]] = None,
    collect_timeline: bool = True,
) -> ScheduleResult:
    """Run one policy against a fixed arrival stream."""
    if policy not in POLICIES:
        raise ValueError(f"unknown policy {policy!r}; expected one of {sorted(POLICIES)}")

    station = station or DEFAULT_STATION
    if extractions is None:
        extractions = load_extractions()

    if horizon_min is None:
        last_arrival = max((s.arrival_min for s in specs), default=0.0)
        horizon_min = last_arrival + 720.0  # generous tail so queues can drain

    ports = [Port(port_id=i, power_kw=kw) for i, kw in enumerate(station)]

    evs: List[EVState] = []
    for spec in specs:
        need, target = _energy_needed(spec)
        ev = EVState(spec=spec, energy_needed_kwh=need, target_soc=target,
                     soc_pct=spec.soc_pct)

        if policy.startswith("agent"):
            _apply_agent_beliefs(
                ev, extractions,
                validate=(policy != "agent_no_validation"),
                use_deadline=(policy != "agent_no_deadline"),
            )
        else:
            # Conventional policies read telemetry only. No language at all.
            ev.believed_urgency = "MEDIUM"
            ev.believed_deadline_min = None

        evs.append(ev)

    by_id = {e.spec.ev_id: e for e in evs}
    pending = sorted(evs, key=lambda e: e.spec.arrival_min)
    next_arrival = 0
    queue: List[EVState] = []

    now = 0.0
    while now <= horizon_min:
        # Tick order matters: admit, then dispatch, then advance charging.
        #
        # Charging is advanced over the half-open interval [now, now+step), so a
        # session that completes during this tick finishes at now+step. If
        # dispatch ran after the advance, a port freed at now+step would be
        # reassigned with start=now and the two sessions would overlap by one
        # minute. Dispatching first means a port freed during the advance is
        # reassigned on the next tick, at exactly now+step.
        #
        # 1) Admit arrivals.
        while next_arrival < len(pending) and pending[next_arrival].spec.arrival_min <= now:
            queue.append(pending[next_arrival])
            next_arrival += 1

        # 2) Dispatch into free ports.
        free_ports = [p for p in ports if p.is_free]
        if free_ports and queue:
            if policy in CONVENTIONAL_ORDERINGS:
                assignments = _dispatch_conventional(policy, queue, free_ports, now)
            else:
                assignments = _dispatch_agent(queue, free_ports, now)

            for ev, port in assignments:
                ev.status = "charging"
                ev.port_id = port.port_id
                ev.start_min = now
                port.current_ev = ev.spec.ev_id
                queue.remove(ev)

        # 3) Advance active charging sessions.
        for port in ports:
            if port.current_ev is None:
                continue
            ev = by_id[port.current_ev]
            power = min(port.power_kw, ev.spec.max_rate_kw)
            if ev.soc_pct > TAPER_START_SOC:
                power *= max(0.1, (100.0 - ev.soc_pct) / 20.0)
            delivered = power * (TIME_STEP_MIN / 60.0)
            remaining = max(0.0, ev.energy_needed_kwh - ev.energy_delivered_kwh)
            delivered = min(delivered, remaining)

            ev.energy_delivered_kwh += delivered
            ev.soc_pct = min(ev.target_soc,
                             ev.soc_pct + (delivered / ev.spec.battery_kwh) * 100.0)
            port.busy_minutes += TIME_STEP_MIN

            if ev.energy_delivered_kwh >= ev.energy_needed_kwh - 1e-6:
                ev.status = "done"
                ev.finish_min = now + TIME_STEP_MIN
                ev.cost = _price(ev.energy_delivered_kwh, port.power_kw)
                port.current_ev = None

        now += TIME_STEP_MIN

    return _summarise(policy, evs, ports, horizon_min, collect_timeline)


def _summarise(
    policy: str, evs: List[EVState], ports: List[Port],
    horizon_min: float, collect_timeline: bool,
) -> ScheduleResult:
    arrived = len(evs)
    served = [e for e in evs if e.status == "done"]
    unserved = [e for e in evs if e.status != "done"]

    waits = [e.wait_min for e in served]
    waits_sorted = sorted(waits)

    def pct(p: float) -> float:
        if not waits_sorted:
            return 0.0
        idx = min(len(waits_sorted) - 1, int(math.ceil(p / 100.0 * len(waits_sorted))) - 1)
        return waits_sorted[max(0, idx)]

    # --- Deadline adherence (the metric only language unlocks) -------------
    deadline_evs = [e for e in evs if e.true_deadline_abs is not None]
    on_time, late_amounts = 0, []
    for e in deadline_evs:
        dl = e.true_deadline_abs
        if e.status == "done" and e.finish_min is not None and e.finish_min <= dl + 1e-9:
            on_time += 1
        elif e.status == "done" and e.finish_min is not None:
            late_amounts.append(e.finish_min - dl)

    crit_deadline_evs = [
        e for e in deadline_evs
        if SCENARIOS[e.spec.scenario_key].true_urgency in ("HIGH", "CRITICAL")
    ]
    crit_on_time = sum(
        1 for e in crit_deadline_evs
        if e.status == "done" and e.finish_min is not None
        and e.finish_min <= e.true_deadline_abs + 1e-9
    )

    # --- Concrete cost of trusting an unverified claim ---------------------
    # Minutes that drivers making unverifiable emergency claims spent occupying
    # the station's single fastest port. This is capacity taken from drivers who
    # had a real, verifiable deadline.
    fastest_kw = max(p.power_kw for p in ports)
    fastest_ids = {p.port_id for p in ports if p.power_kw == fastest_kw}
    liar_fast_minutes = sum(
        (e.finish_min - e.start_min)
        for e in served
        if SCENARIOS[e.spec.scenario_key].is_unverified_claim
        and e.port_id in fastest_ids
        and e.start_min is not None and e.finish_min is not None
    )

    energy = sum(e.energy_delivered_kwh for e in served)
    revenue = sum(e.cost for e in served)
    port_minutes = sum(p.busy_minutes for p in ports)
    capacity_minutes = len(ports) * horizon_min

    metrics = {
        "policy": policy,
        "label": POLICIES[policy]["label"],
        "family": POLICIES[policy]["family"],
        "arrived": arrived,
        "served": len(served),
        "served_rate": round(len(served) / arrived, 4) if arrived else 0.0,

        "deadline_evs": len(deadline_evs),
        "deadline_on_time": on_time,
        "on_time_rate": round(on_time / len(deadline_evs), 4) if deadline_evs else 0.0,
        "deadline_miss_rate": round(1 - on_time / len(deadline_evs), 4) if deadline_evs else 0.0,
        "mean_lateness_min": round(sum(late_amounts) / len(late_amounts), 2) if late_amounts else 0.0,

        "critical_deadline_evs": len(crit_deadline_evs),
        "critical_on_time_rate": round(crit_on_time / len(crit_deadline_evs), 4) if crit_deadline_evs else 0.0,

        "avg_wait_min": round(sum(waits) / len(waits), 2) if waits else 0.0,
        "p95_wait_min": round(pct(95), 2),
        "max_wait_min": round(max(waits), 2) if waits else 0.0,

        "energy_kwh": round(energy, 2),
        "revenue": round(revenue, 2),
        "port_utilisation": round(port_minutes / capacity_minutes, 4) if capacity_minutes else 0.0,

        "unverified_claim_fast_port_minutes": round(liar_fast_minutes, 1),
        "contradictions_flagged": sum(1 for e in evs if e.contradiction_flagged),
    }

    timeline: List[dict] = []
    if collect_timeline:
        for e in sorted(served + [x for x in evs if x.status == "charging"],
                        key=lambda x: (x.start_min if x.start_min is not None else 0.0)):
            sc = SCENARIOS[e.spec.scenario_key]
            dl = e.true_deadline_abs
            timeline.append({
                "ev_id": e.spec.ev_id,
                "port_id": e.port_id,
                "start_min": round(e.start_min, 2) if e.start_min is not None else None,
                "end_min": round(e.finish_min, 2) if e.finish_min is not None else None,
                "arrival_min": e.spec.arrival_min,
                "scenario_key": e.spec.scenario_key,
                "message": sc.message,
                "true_urgency": sc.true_urgency,
                "believed_urgency": e.believed_urgency,
                "contradiction_flagged": e.contradiction_flagged,
                "true_deadline_abs": round(dl, 2) if dl is not None else None,
                "believed_deadline_min": e.believed_deadline_min,
                "met_deadline": (
                    None if dl is None
                    else bool(e.status == "done" and e.finish_min is not None and e.finish_min <= dl + 1e-9)
                ),
                "energy_kwh": round(e.energy_delivered_kwh, 2),
                "cost": round(e.cost, 2),
                "wait_min": round(e.wait_min, 2),
                "soc_start": e.spec.soc_pct,
                "status": e.status,
            })

    unserved_out = [{
        "ev_id": e.spec.ev_id,
        "scenario_key": e.spec.scenario_key,
        "arrival_min": e.spec.arrival_min,
        "soc_start": e.spec.soc_pct,
        "budget": e.spec.budget,
        "energy_needed_kwh": round(e.energy_needed_kwh, 2),
        "had_deadline": SCENARIOS[e.spec.scenario_key].true_deadline_min is not None,
        "status": e.status,
    } for e in unserved]

    return ScheduleResult(policy=policy, metrics=metrics,
                          timeline=timeline, unserved=unserved_out)


def run_all_policies(
    specs: List[EVSpec],
    station: Optional[List[float]] = None,
    horizon_min: Optional[float] = None,
    policies: Optional[List[str]] = None,
    collect_timeline: bool = True,
) -> Dict[str, ScheduleResult]:
    """Run the identical arrival stream through every policy."""
    extractions = load_extractions()
    chosen = policies or list(POLICIES.keys())
    return {
        p: run_schedule(specs, p, station=station, horizon_min=horizon_min,
                        extractions=extractions, collect_timeline=collect_timeline)
        for p in chosen
    }


if __name__ == "__main__":
    import sys
    from scenario_library import generate_arrival_stream
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    stream = generate_arrival_stream(seed=7, horizon_min=1440.0, arrivals_per_hour=5.0)
    print(f"Arrival stream: {len(stream)} EVs over 24h, station={DEFAULT_STATION}\n")

    results = run_all_policies(stream, collect_timeline=False)
    hdr = f"{'Policy':<22}{'served':>7}{'on-time':>9}{'crit':>8}{'wait':>8}{'p95':>8}{'util':>7}{'kWh':>9}"
    print(hdr)
    print("-" * len(hdr))
    for p, r in results.items():
        m = r.metrics
        print(f"{m['label']:<22}{m['served']:>7}{m['on_time_rate']*100:>8.1f}%"
              f"{m['critical_on_time_rate']*100:>7.1f}%{m['avg_wait_min']:>8.1f}"
              f"{m['p95_wait_min']:>8.1f}{m['port_utilisation']*100:>6.1f}%{m['energy_kwh']:>9.1f}")
