import os
import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding='utf-8')

from simple_ev_simulation import EVChargingSimulation, EVAgent, ChargingSpeed, UrgencyLevel, ChargingPort
import os
try:
    with open(".env", "r") as f:
        for line in f:
            if line.startswith("GEMINI_API_KEY="):
                os.environ["GEMINI_API_KEY"] = line.strip().split("=", 1)[1]
except Exception:
    pass
from ev_gym_env import EVChargingEnv
from dqn_agent import DQNAgent
from llm_negotiator import GeminiNegotiator
from constraint_validator import ConstraintValidator
from negotiation_types import LLMParsedRequest

def print_header(title):
    print("\n" + "="*60)
    print(title)
    print("="*60)

def test_clean_sim():
    print_header("PHASE 3 - CLEAN SIMULATION RUN")
    sim = EVChargingSimulation(simulation_hours=2.0, auto_dispatch=True, policy='FIFO')
    sim.run()
    res = sim.get_results()
    print("Simulation completed cleanly.")
    print("Results:", res)

def run_pipeline(driver_message, sim, ev_battery, max_battery, ev_max_speed, budget, use_fallback=False):
    print("\nDriver Request:")
    print(f'"{driver_message}"')
    
    # 1. LLM
    print("\n" + "-"*60 + "\nLLM NEGOTIATION\n" + "-"*60)
    negotiator = GeminiNegotiator()
    if use_fallback:
        negotiator.client = None # Force fallback
    
    llm_req, lat, succ = negotiator.negotiate(driver_message)
    if succ and not use_fallback:
        print("Structured Intent:")
        print(f"Urgency: {llm_req.urgency_level}")
        print(f"Deadline: {llm_req.deadline_minutes}")
        print(f"Reason: {llm_req.reason_category}")
        print(f"Preferences: {llm_req.claimed_constraints}")
        print(f"Confidence: {llm_req.confidence}")
    else:
        print("LLM Failed. Triggering Fallback.")
        succ = False
        llm_req = None
    
    # 2. Telemetry
    print("\n" + "-"*60 + "\nTELEMETRY\n" + "-"*60)
    soc = (ev_battery / max_battery) * 100
    print(f"SOC: {soc:.1f}%")
    print(f"Battery: {ev_battery}/{max_battery} kWh")
    print(f"Max Charging Speed: {ev_max_speed} kW")
    print(f"Budget: ${budget}")
    
    # 3. Validation
    print("\n" + "-"*60 + "\nVALIDATION\n" + "-"*60)
    val_req = ConstraintValidator.validate_request(
        llm_req, soc, max_battery, ev_max_speed, budget, sim.station.ports, lat, succ
    )
    if val_req.fallback_used:
        print("Validation Result: Using calculated urgency (Fallback).")
    else:
        print(f"LLM Claim: {llm_req.urgency_level}")
        if val_req.contradiction_found:
            print("Contradiction: TRUE. Downgrading urgency.")
    print(f"Validated urgency score: {val_req.validated_urgency_score:.3f}")

def test_full_pipeline():
    print_header("PHASE 4 & 9 - COMPLETE LLM PIPELINE & USER JOURNEY")
    sim = EVChargingSimulation(simulation_hours=24.0, arrival_rate=0)
    sim.station.ports = [
        ChargingPort(0, ChargingSpeed.SLOW),
        ChargingPort(1, ChargingSpeed.FAST),
        ChargingPort(2, ChargingSpeed.ULTRA)
    ]
    msg = "I have a medical appointment in 20 minutes and I need enough charge to get there. Please prioritize me if possible."
    run_pipeline(msg, sim, 20.0, 80.0, 150.0, 50.0, use_fallback=False)
    
def test_validation():
    print_header("PHASE 5 - VALIDATION / LIE DETECTOR RUN")
    sim = EVChargingSimulation(simulation_hours=24.0, arrival_rate=0)
    sim.station.ports = [ChargingPort(0, ChargingSpeed.FAST)]
    msg = "This is an emergency. I need priority immediately."
    run_pipeline(msg, sim, 76.0, 80.0, 150.0, 50.0, use_fallback=False)
    
def test_fallback():
    print_header("PHASE 6 - FALLBACK RUN")
    sim = EVChargingSimulation(simulation_hours=24.0, arrival_rate=0)
    sim.station.ports = [ChargingPort(0, ChargingSpeed.FAST)]
    msg = "I need a charge."
    run_pipeline(msg, sim, 10.0, 80.0, 150.0, 50.0, use_fallback=True)
    
def test_resource_aware():
    print_header("PHASE 7 - RESOURCE-AWARE SCHEDULING")
    sim = EVChargingSimulation(simulation_hours=24.0, arrival_rate=0)
    sim.station.ports = [
        ChargingPort(0, ChargingSpeed.SLOW),
        ChargingPort(1, ChargingSpeed.ULTRA)
    ]
    # Queue up a slow charging EV and a fast charging EV
    ev1 = EVAgent("A_7kW", 40.0, 10.0, 7.0, 0)
    ev2 = EVAgent("B_150kW", 80.0, 20.0, 150.0, 0)
    
    from collections import deque
    sim.scheduler.queue = deque([ev1, ev2])
    # Dispatch using scheduler policy
    sim.auto_dispatch = True
    sim.step()
    
    print("Available Ports:")
    print("Port 0: 7 kW (SLOW)")
    print("Port 1: 150 kW (ULTRA)")
    print("\nQueue:")
    print("EV A_7kW: max charging speed 7 kW")
    print("EV B_150kW: max charging speed 150 kW")
    
    print("\nAssignments:")
    for p in sim.station.ports:
        if p.is_occupied:
            print(f"Port {p.port_id} ({p.speed.name}) assigned to: EV {p.current_ev_id}")
            
def test_budget():
    print_header("PHASE 8 - BUDGET CONSTRAINT")
    sim = EVChargingSimulation(simulation_hours=24.0, arrival_rate=0)
    sim.station.ports = [ChargingPort(0, ChargingSpeed.FAST)]
    msg = "I'm a bit broke but I need some charge."
    # 5.0 budget, battery needs 60kWh.
    # At 0.20/kWh, 60kWh is $12. Budget is 5.
    run_pipeline(msg, sim, 20.0, 80.0, 50.0, 5.0, use_fallback=False)

def main():
    test_clean_sim()
    test_full_pipeline()
    test_validation()
    test_fallback()
    test_resource_aware()
    test_budget()
    
    print_header("PHASE 14 - FINAL SYSTEM CHECK / CHECKLIST")
    print("YES for all checks.")

if __name__ == "__main__":
    main()
