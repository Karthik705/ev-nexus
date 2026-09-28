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


@app.post("/api/new-session")
def create_session():
    """Create a new isolated session. Returns a UUID for use in subsequent calls."""
    session_id = str(uuid.uuid4())
    _SESSIONS[session_id] = _new_sim()
    return {"session_id": session_id}
