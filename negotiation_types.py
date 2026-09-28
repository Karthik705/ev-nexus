from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

@dataclass
class LLMParsedRequest:
    urgency_level: str  # "LOW", "MEDIUM", "HIGH", "CRITICAL"
    deadline_minutes: Optional[int]
    reason_category: str
    claimed_constraints: List[str]
    requested_port_type: Optional[str]
    confidence: float
    explanation: str

@dataclass
class ValidatedChargingRequest:
    # Telemetry-derived fields
    actual_soc: float
    battery_capacity: float
    max_charging_speed: float
    budget: float
    
    # LLM-derived fields (Validated)
    validated_urgency_score: float # 0.0 to 1.0 mapping of urgency
    deadline_minutes: Optional[int]
    reason_category: str
    
    # System-derived fields
    feasible_ports: List[int] = field(default_factory=list)
    llm_latency_sec: float = 0.0
    parsing_success: bool = True
    fallback_used: bool = False
    contradiction_found: bool = False
    
    def calculate_priority_score(self, current_wait_time: float) -> float:
        """
        Deterministic scoring function.
        Weights:
        - Urgency: highly weighted.
        - Wait time: prevents starvation.
        - Deadline pressure: inverse to remaining time if deadline exists.
        """
        score = self.validated_urgency_score * 10.0
        score += (current_wait_time * 0.1)
        
        if self.deadline_minutes is not None:
            # If deadline is tight (e.g. less than 30 mins), pressure increases exponentially
            if self.deadline_minutes > 0:
                pressure = 30.0 / max(1.0, float(self.deadline_minutes))
                score += min(15.0, pressure) 
            else:
                score += 20.0 # Missed deadline but still waiting
                
        return score
