import os
import io
import json
import logging
import uuid
from fastapi import FastAPI, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict
from collections import deque
import sys

# Ensure utf-8 output to prevent windows console issues
# Cast to TextIOWrapper (the concrete type that has reconfigure) so type-checkers
# recognise the attribute; the hasattr guard already guarantees it exists at runtime.
import typing
if hasattr(sys.stdout, "reconfigure"):
    typing.cast(io.TextIOWrapper, sys.stdout).reconfigure(encoding="utf-8")

# Load API key from .env if not already in environment
try:
    with open(".env", "r") as f:
        for line in f:
            if line.startswith("GEMINI_API_KEY="):
                os.environ.setdefault("GEMINI_API_KEY", line.strip().split("=", 1)[1])
except Exception:
    pass

from simple_ev_simulation import EVChargingSimulation, EVAgent, ChargingSpeed, ChargingPort
from constraint_validator import ConstraintValidator
from llm_negotiator import GeminiNegotiator
from negotiation_types import LLMParsedRequest

# v2 scheduling engine — backs the live policy comparison. The same engine
# produces benchmark_v2_results.json, so the website and the benchmark report
# the identical computation rather than two separate implementations.
from scenario_library import SCENARIOS, EVSpec, generate_arrival_stream
from schedule_engine import run_all_policies, POLICIES, DEFAULT_STATION

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="EV Charging Negotiator API")

# ---------------------------------------------------------------------------
# CORS — configured via ALLOWED_ORIGINS environment variable.
# Comma-separated list of allowed origins.
# Example: ALLOWED_ORIGINS=https://myapp.example.com,https://staging.example.com
# Defaults to localhost dev server for local development only.
# DO NOT rely on the default in production.
# ---------------------------------------------------------------------------
_raw_origins = os.environ.get("ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
ALLOWED_ORIGINS: list[str] = [o.strip() for o in _raw_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Per-session simulation state.
# Each session gets its own EVChargingSimulation instance so concurrent
# users cannot corrupt each other's state.
# The "default" session exists for backward-compatibility with the frontend.
# ---------------------------------------------------------------------------
_SESSIONS: Dict[str, EVChargingSimulation] = {}


def _new_sim() -> EVChargingSimulation:
    """Create a fresh simulation instance wired for the interactive UI."""
    sim = EVChargingSimulation(
        simulation_hours=24.0,
        arrival_rate=0.0,
        auto_dispatch=True,
        policy='LLM_DETERMINISTIC',
    )
    sim.station.ports = [
        ChargingPort(0, ChargingSpeed.SLOW),
        ChargingPort(1, ChargingSpeed.FAST),
        ChargingPort(2, ChargingSpeed.ULTRA),
    ]
    sim.scheduler.queue = deque()
    return sim


def _get_sim(session_id: str) -> EVChargingSimulation:
    """Return (or lazily create) the simulation for the given session."""
    if session_id not in _SESSIONS:
        _SESSIONS[session_id] = _new_sim()
    return _SESSIONS[session_id]


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class NegotiateRequest(BaseModel):
    driver_message: str = Field(..., min_length=1, max_length=500,
                                description="Natural-language driver request (1–500 chars)")
    soc: float = Field(..., ge=0.0, le=100.0, description="State of charge (%)")
    battery_capacity: float = Field(..., gt=0.0, description="Battery capacity (kWh)")
    max_charging_rate: float = Field(..., gt=0.0, description="Max charging rate (kW)")
    budget: float = Field(..., ge=0.0, description="Budget ($)")
    force_fallback: Optional[bool] = False
    session_id: Optional[str] = Field(default="default",
                                      description="Session identifier. Use a UUID per browser tab.")

    @validator("driver_message")
    def message_not_blank(cls, v):
        if not v.strip():
            raise ValueError("driver_message must not be blank")
        return v.strip()


class SessionRequest(BaseModel):
    session_id: Optional[str] = Field(default="default")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/api/health")
def health_check():
    """Liveness probe for the frontend's connection-status indicator and for
    deployment platforms' health checks. Deliberately does not touch Gemini
    or any per-session state — it only confirms the API process is up."""
    return {"status": "ok"}


@app.post("/api/negotiate")
def negotiate(req: NegotiateRequest):
    sim = _get_sim(req.session_id or "default")
    try:
        current_battery = (req.soc / 100.0) * req.battery_capacity

        negotiator = GeminiNegotiator()
        if req.force_fallback:
            negotiator.client = None

        llm_req: Optional[LLMParsedRequest] = None
        lat: float = 0.0
        succ: bool = False
        try:
            llm_req, lat, succ = negotiator.negotiate(req.driver_message)
        except Exception as llm_exc:
            # Distinguish auth/key errors from transient failures
            error_type = GeminiNegotiator._classify_error(llm_exc)
            if error_type == "AUTH_ERROR":
                logger.warning(f"LLM auth failure — using telemetry fallback: {llm_exc}")
                raise HTTPException(
                    status_code=503,
                    detail={
                        "error": "LLM backend unavailable (invalid API key)",
                        "fallback": "telemetry_only",
                        "message": "The Gemini API key is present but invalid. "
                                   "Serving request using deterministic telemetry fallback.",
                    }
                )
            logger.error(f"Unexpected LLM error: {llm_exc}")
            llm_req, lat, succ = None, 0.0, False

        # Validate constraints (lie detector + feasibility)
        val_req = ConstraintValidator.validate_request(
            llm_req,
            req.soc,
            req.battery_capacity,
            req.max_charging_rate,
            req.budget,
            sim.station.ports,
            lat,
            succ,
        )

        # Create EV agent
        new_ev = EVAgent(
            ev_id=sim.ev_counter,
            max_battery=req.battery_capacity,
            current_battery=current_battery,
            max_charging_speed=req.max_charging_rate,
            arrival_time=sim.current_time,
            # Target 80% of THIS vehicle's own capacity, not a fixed absolute kWh
            # value — a fixed 80 kWh target exceeds max_battery (and therefore
            # 100% SOC) for any smaller battery, e.g. a 40 kWh car.
            target_battery=0.8 * req.battery_capacity,
            budget=req.budget,
        )
        sim.ev_counter += 1
        new_ev.validated_request = val_req

        # Add to simulation and dispatch
        sim.all_evs[new_ev.id] = new_ev
        sim.scheduler.add_ev(new_ev)
        sim.step()

        # Find assigned port
        assigned_port = None
        for p in sim.station.ports:
            if p.current_ev_id == new_ev.id:
                assigned_port = p.port_id
                break

        # Distinguish "genuinely queued" from "silently dropped": the
        # deterministic dispatcher (simple_ev_simulation.py) removes an EV
        # from the queue without ever assigning it a port if its estimated
        # charging cost exceeds its budget. Previously this looked identical
        # to a normal queued EV ("status": "WAITING") from the API's point of
        # view, which misrepresented a rejection as "waiting for a port."
        if assigned_port is not None:
            status = "CHARGING"
        elif new_ev in sim.scheduler.queue:
            status = "WAITING"
        else:
            status = "REJECTED_BUDGET"

        return {
            "ev_id":             new_ev.id,
            "llm_result":        llm_req.__dict__ if llm_req else None,
            "validation_result": val_req.__dict__,
            "assigned_port":     assigned_port,
            "status":            status,
            "fallback_used":     not succ or req.force_fallback,
            "priority_score":    val_req.validated_urgency_score,
            "session_id":        req.session_id or "default",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in negotiate: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/station")
def get_station_status(session_id: str = "default"):
    sim = _get_sim(session_id)
    ports = []
    for p in sim.station.ports:
        port_info = {
            "id":           p.port_id,
            "speed_name":   p.speed.name,
            "speed_kw":     p.speed.value,
            "is_occupied":  p.is_occupied,
            "current_ev_id": p.current_ev_id,
        }
        if p.is_occupied and p.current_ev_id is not None:
            ev = next((e for e in sim.active_evs if e.id == p.current_ev_id), None)
            if ev:
                port_info["ev"] = {
                    "id":               ev.id,
                    "soc":              ev.battery_percent,
                    "target_soc":       (ev.target_battery / ev.max_battery) * 100 if ev.max_battery else 100,
                    "energy_delivered": ev.current_battery - (ev.battery_percent / 100 * ev.max_battery) if ev.max_battery else 0,
                    "wait_time":        ev.wait_time,
                }
        ports.append(port_info)

    queue = []
    for ev in sim.scheduler.queue:
        queue.append({
            "id":       ev.id,
            "soc":      ev.battery_percent,
            "priority": ev.validated_request.validated_urgency_score if ev.validated_request else 0,
        })

    return {
        "ports":   ports,
        "queue":   queue,
        "metrics": {
            "completed": len(sim.completed_evs),
            "revenue":   round(sim.total_revenue, 2),
        },
        "session_id": session_id,
    }


@app.post("/api/step")
def step_simulation(body: SessionRequest = Body(default=SessionRequest())):
    session_id = body.session_id or "default"
    sim = _get_sim(session_id)

    # Advance time without adding new EVs
    sim.base_arrival_rate = 0.0

    for _ in range(5):
        completed_ids = sim.station.step(sim.active_evs, sim.time_step)
        for ev_id in completed_ids:
            ev = next((e for e in sim.active_evs if e.id == ev_id), None)
            if ev:
                sim.active_evs.remove(ev)
                sim.completed_evs.append(ev)
                satisfaction = max(0.0, 1.0 - (ev.wait_time / ev.patience))
                sim.satisfaction_scores.append(satisfaction)
                sim.wait_times.append(ev.wait_time)
        sim.current_time += sim.time_step

    sim.step()
    return get_station_status(session_id=session_id)


# ---------------------------------------------------------------------------
# /api/benchmarks — explicit allowlist only.
# Only the two result files intended for public exposure are served.
# Glob over *.json was removed: it exposed ALL JSON files in the working
# directory with no filtering or auth.
# ---------------------------------------------------------------------------
_BENCHMARK_ALLOWLIST = [
    "phase4c5_results.json",
    "phase5_results.json",
    "benchmark_v2_results.json",
]


@app.get("/api/benchmarks")
def get_benchmarks():
    results = {}
    for fname in _BENCHMARK_ALLOWLIST:
        if os.path.isfile(fname):
            try:
                with open(fname, "r") as f:
                    results[fname] = json.load(f)
            except Exception as e:
                logger.warning(f"Could not load benchmark file {fname}: {e}")
        else:
            results[fname] = None  # Signal to frontend that file not yet generated
    return results


@app.post("/api/reset")
def reset_simulation(body: SessionRequest = Body(default=SessionRequest())):
    session_id = body.session_id or "default"
    _SESSIONS[session_id] = _new_sim()
    return {"status": "ok", "session_id": session_id}


# ---------------------------------------------------------------------------
# Live policy comparison (v2 engine)
#
# These endpoints run the SAME deterministic engine that produces
# benchmark_v2_results.json. The website therefore demonstrates the real
# computation rather than replaying a stored number, and anyone can change the
# inputs and watch the schedule change.
# ---------------------------------------------------------------------------

MAX_COMPARE_EVS = 60
MAX_COMPARE_HORIZON_MIN = 1440.0


class CompareEV(BaseModel):
    scenario_key: str = Field(..., description="Key from GET /api/scenarios")
    soc: float = Field(..., ge=0.0, le=100.0)
    battery_capacity: float = Field(..., gt=0.0, le=250.0)
    max_charging_rate: float = Field(..., gt=0.0, le=400.0)
    budget: float = Field(..., ge=0.0, le=1000.0)
    arrival_min: float = Field(0.0, ge=0.0, le=MAX_COMPARE_HORIZON_MIN)

    @validator("scenario_key")
    def known_scenario(cls, v):
        if v not in SCENARIOS:
            raise ValueError(f"unknown scenario_key {v!r}")
        return v


class CompareRequest(BaseModel):
    """Either supply an explicit batch of EVs, or ask for a generated stream."""
    evs: Optional[List[CompareEV]] = None
    seed: Optional[int] = Field(None, ge=0, le=10_000_000)
    arrivals_per_hour: Optional[float] = Field(None, gt=0.0, le=20.0)
    horizon_min: float = Field(240.0, gt=0.0, le=MAX_COMPARE_HORIZON_MIN)
    station: Optional[List[float]] = None
    policies: Optional[List[str]] = None
    # Average the metrics over this many consecutive arrival patterns. A single
    # sample of a few dozen cars is noisy enough that an ablation can beat the
    # full agent by chance; averaging makes the displayed comparison trustworthy.
    # The returned schedule is always the FIRST seed, so the chart still matches
    # a real, specific run.
    repeats: int = Field(1, ge=1, le=15)

    @validator("station")
    def valid_station(cls, v):
        if v is None:
            return v
        if not (1 <= len(v) <= 8):
            raise ValueError("station must have between 1 and 8 ports")
        for kw in v:
            if not (1.0 <= kw <= 400.0):
                raise ValueError("port power must be between 1 and 400 kW")
        return v

    @validator("policies")
    def valid_policies(cls, v):
        if v is None:
            return v
        unknown = [p for p in v if p not in POLICIES]
        if unknown:
            raise ValueError(f"unknown policies: {unknown}")
        return v


@app.get("/api/scenarios")
def list_scenarios():
    """The canonical driver messages, with what the model extracted from each.

    `true_deadline_min` is included so the UI can show the answer key alongside
    the decision — but note it is grading data: no scheduling policy reads it.
    """
    from scenario_library import load_extractions, extraction_quality_report
    extractions = load_extractions()

    out = []
    for key, sc in SCENARIOS.items():
        ex = extractions.get(key)
        out.append({
            "key": key,
            "message": sc.message,
            "true_deadline_min": sc.true_deadline_min,
            "true_urgency": sc.true_urgency,
            "required_kwh": sc.required_kwh,
            "wants_full_charge": sc.wants_full_charge,
            "is_unverified_claim": sc.is_unverified_claim,
            "notes": sc.notes,
            "extracted": None if ex is None else {
                "urgency_level": ex.urgency_level,
                "deadline_minutes": ex.deadline_minutes,
                "reason_category": ex.reason_category,
                "claimed_constraints": ex.claimed_constraints,
                "confidence": ex.confidence,
                "explanation": ex.explanation,
            },
        })

    return {
        "scenarios": out,
        "policies": POLICIES,
        "default_station": DEFAULT_STATION,
        "extraction_quality": extraction_quality_report(extractions),
    }


@app.post("/api/compare")
def compare_policies(req: CompareRequest):
    """Schedule one identical set of arrivals under every policy."""
    try:
        if req.evs:
            if len(req.evs) > MAX_COMPARE_EVS:
                raise HTTPException(
                    status_code=422,
                    detail=f"too many EVs: {len(req.evs)} (max {MAX_COMPARE_EVS})",
                )
            specs = [
                EVSpec(
                    ev_id=i,
                    arrival_min=e.arrival_min,
                    battery_kwh=e.battery_capacity,
                    soc_pct=e.soc,
                    max_rate_kw=e.max_charging_rate,
                    budget=e.budget,
                    scenario_key=e.scenario_key,
                )
                for i, e in enumerate(sorted(req.evs, key=lambda x: x.arrival_min))
            ]
        else:
            # Generated stream. Deterministic in `seed`, so a shared link
            # reproduces exactly the same schedule for anyone who opens it.
            specs = generate_arrival_stream(
                seed=req.seed if req.seed is not None else 42,
                horizon_min=req.horizon_min,
                arrivals_per_hour=req.arrivals_per_hour or 5.0,
            )
            if len(specs) > MAX_COMPARE_EVS:
                specs = specs[:MAX_COMPARE_EVS]

        if not specs:
            raise HTTPException(
                status_code=422,
                detail="no EVs to schedule — raise arrivals_per_hour or horizon_min",
            )

        station = req.station or DEFAULT_STATION
        # Allow the queue to drain so deadline outcomes are not truncated by the
        # window; the Gantt is clipped to the display horizon on the client.
        sim_horizon = max(req.horizon_min, max(s.arrival_min for s in specs) + 480.0)

        results = run_all_policies(
            specs, station=station, horizon_min=sim_horizon,
            policies=req.policies, collect_timeline=True,
        )

        # Optionally average the metrics across additional arrival patterns.
        # Only meaningful for generated streams; an explicit EV list is a single
        # fixed scenario with nothing to average over.
        repeats_used = 1
        if req.repeats > 1 and not req.evs:
            base_seed = req.seed if req.seed is not None else 42
            accum: Dict[str, Dict[str, List[float]]] = {
                name: {k: [float(v)] for k, v in res.metrics.items()
                       if isinstance(v, (int, float)) and not isinstance(v, bool)}
                for name, res in results.items()
            }
            for r in range(1, req.repeats):
                extra = generate_arrival_stream(
                    seed=base_seed + r * 1013,
                    horizon_min=req.horizon_min,
                    arrivals_per_hour=req.arrivals_per_hour or 5.0,
                )
                if len(extra) > MAX_COMPARE_EVS:
                    extra = extra[:MAX_COMPARE_EVS]
                if not extra:
                    continue
                extra_horizon = max(
                    req.horizon_min, max(s.arrival_min for s in extra) + 480.0)
                more = run_all_policies(
                    extra, station=station, horizon_min=extra_horizon,
                    policies=req.policies, collect_timeline=False,
                )
                for name, res in more.items():
                    for k, v in res.metrics.items():
                        if isinstance(v, (int, float)) and not isinstance(v, bool):
                            accum.setdefault(name, {}).setdefault(k, []).append(float(v))
                repeats_used += 1

            for name, metric_lists in accum.items():
                averaged = dict(results[name].metrics)
                for k, vals in metric_lists.items():
                    averaged[k] = round(sum(vals) / len(vals), 4)
                results[name].metrics = averaged

        payload = {
            "config": {
                "station_kw": station,
                "num_ports": len(station),
                "horizon_min": req.horizon_min,
                "sim_horizon_min": sim_horizon,
                "num_evs": len(specs),
                "seed": req.seed,
                "arrivals_per_hour": req.arrivals_per_hour,
                "engine": "v2",
                "repeats": repeats_used,
                "metrics_note": (
                    f"metrics averaged over {repeats_used} arrival patterns; "
                    "the schedule shown is the first one"
                ) if repeats_used > 1 else "single arrival pattern",
            },
            "inputs": [
                {
                    "ev_id": s.ev_id,
                    "arrival_min": s.arrival_min,
                    "scenario_key": s.scenario_key,
                    "message": s.message,
                    "soc": s.soc_pct,
                    "battery_kwh": s.battery_kwh,
                    "max_rate_kw": s.max_rate_kw,
                    "budget": s.budget,
                    "true_deadline_min": SCENARIOS[s.scenario_key].true_deadline_min,
                    "true_urgency": SCENARIOS[s.scenario_key].true_urgency,
                    "is_unverified_claim": SCENARIOS[s.scenario_key].is_unverified_claim,
                }
                for s in specs
            ],
            "policies": {
                name: {
                    "label": POLICIES[name]["label"],
                    "family": POLICIES[name]["family"],
                    "metrics": res.metrics,
                    "timeline": res.timeline,
                    "unserved": res.unserved,
                }
                for name, res in results.items()
            },
        }

        # Headline deltas, computed server-side so the UI cannot drift from the
        # benchmark's definition of "improvement".
        if "agent" in results:
            agent_m = results["agent"].metrics
            deltas = {}
            for name, res in results.items():
                if name == "agent":
                    continue
                b = res.metrics
                deltas[name] = {
                    "label": POLICIES[name]["label"],
                    "on_time_rate_pp": round(
                        (agent_m["on_time_rate"] - b["on_time_rate"]) * 100, 2),
                    "critical_on_time_pp": round(
                        (agent_m["critical_on_time_rate"] - b["critical_on_time_rate"]) * 100, 2),
                    "avg_wait_min": round(agent_m["avg_wait_min"] - b["avg_wait_min"], 2),
                    "p95_wait_min": round(agent_m["p95_wait_min"] - b["p95_wait_min"], 2),
                    "served": agent_m["served"] - b["served"],
                }
            payload["agent_vs"] = deltas

        return payload

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in compare: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/new-session")
def create_session():
    """Create a new isolated session. Returns a UUID for use in subsequent calls."""
    session_id = str(uuid.uuid4())
    _SESSIONS[session_id] = _new_sim()
    return {"session_id": session_id}
