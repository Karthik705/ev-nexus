from llm_negotiator import GeminiNegotiator
from negotiation_types import LLMParsedRequest
from constraint_validator import ConstraintValidator
from simple_ev_simulation import ChargingPort, ChargingSpeed
import os

print("--- MOCK TESTS FOR VALIDATION LOGIC ---")

# Setup dummy ports
ports = [
    ChargingPort(0, ChargingSpeed.SLOW, False),
    ChargingPort(1, ChargingSpeed.FAST, False),
    ChargingPort(2, ChargingSpeed.ULTRA, False)
]

def print_result(name, req):
    print(f"\n[{name}]")
    print(f"Fallback Used: {req.fallback_used}")
    print(f"Urgency Score: {req.validated_urgency_score}")
    print(f"Feasible Ports: {req.feasible_ports}")
    print(f"Contradiction: {req.contradiction_found}")

# Test 1: Normal Request (High Urgency)
mock_llm_1 = LLMParsedRequest("HIGH", 20, "LATE", [], None, 0.9, "Driver is late")
val_1 = ConstraintValidator.validate_request(mock_llm_1, 30.0, 100.0, 150.0, 50.0, ports, 0.1)
print_result("Test 1: Normal High Urgency", val_1)

# Test 2: Contradictory Claim (Claims Emergency but has 80% SOC)
mock_llm_2 = LLMParsedRequest("CRITICAL", 10, "EMERGENCY", [], None, 0.9, "Driver says critical")
val_2 = ConstraintValidator.validate_request(mock_llm_2, 85.0, 100.0, 150.0, 50.0, ports, 0.1)
print_result("Test 2: Contradiction (Lie Detector)", val_2)

# Test 3: Fallback (LLM Failed)
val_3 = ConstraintValidator.validate_request(None, 15.0, 100.0, 150.0, 50.0, ports, 0.0, False)
print_result("Test 3: Fallback used (15% SOC)", val_3)

print("\n--- REAL GEMINI TEST ---")
api_key = os.environ.get("GEMINI_API_KEY")
if api_key:
    negotiator = GeminiNegotiator()
    msg = "I'm literally on 2% battery and my wife is in labor! I need the fastest charger you have right now!"
    print(f"Driver says: {msg}")
    llm_req, lat, succ = negotiator.negotiate(msg)
    if succ:
        print(f"LLM Parsed (Latency: {lat:.2f}s): {llm_req}")
        
        val_real = ConstraintValidator.validate_request(
            llm_req, 2.0, 75.0, 150.0, 100.0, ports, lat, succ
        )
        print_result("Real Gemini Validated", val_real)
    else:
        print("API call failed.")
else:
    print("No GEMINI_API_KEY found, skipping real test.")
