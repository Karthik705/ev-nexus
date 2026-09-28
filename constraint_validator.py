from typing import List, Optional, Any
from negotiation_types import LLMParsedRequest, ValidatedChargingRequest


class ConstraintValidator:

    @staticmethod
    def validate_request(
        llm_request: Optional[LLMParsedRequest],
        actual_soc: float,
        battery_capacity: float,
        max_charging_speed: float,
        budget: float,
        available_ports: List[Any],  # List of ChargingPort
        llm_latency: float,
        parsing_success: bool = True,
    ) -> ValidatedChargingRequest:

        # If parsing failed or llm_request is None, use fallback
        if not parsing_success or llm_request is None:
            return ConstraintValidator._create_fallback_request(
                actual_soc, battery_capacity, max_charging_speed, budget, available_ports, llm_latency
            )

        contradiction = False

        # Map urgency string to score
        urgency_map = {
            "LOW": 0.2,
            "MEDIUM": 0.5,
            "HIGH": 0.8,
            "CRITICAL": 1.0,
        }
        urgency_score = urgency_map.get(llm_request.urgency_level, 0.5)

        # LIE DETECTOR: Override urgency if SOC contradicts claim
        if urgency_score > 0.5 and actual_soc > 60.0:
            urgency_score = 0.2  # Force to LOW
            contradiction = True

        if llm_request.reason_category == "TIME_CRITICAL" and llm_request.deadline_minutes is None:
            # If they claim time critical but gave no deadline, penalize confidence/urgency
            urgency_score = min(urgency_score, 0.6)

        # Determine Feasible Ports based on physical capabilities
        feasible_ports = []
        for i, port in enumerate(available_ports):
            if not port.is_occupied:
                feasible_ports.append(i)

        return ValidatedChargingRequest(
            actual_soc=actual_soc,
            battery_capacity=battery_capacity,
            max_charging_speed=max_charging_speed,
            budget=budget,
            validated_urgency_score=urgency_score,
            deadline_minutes=llm_request.deadline_minutes,
            reason_category=llm_request.reason_category,
            feasible_ports=feasible_ports,
            llm_latency_sec=llm_latency,
            parsing_success=True,
            fallback_used=False,
            contradiction_found=contradiction,
        )

    @staticmethod
    def _create_fallback_request(
        actual_soc: float,
        battery_capacity: float,
        max_charging_speed: float,
        budget: float,
        available_ports: List[Any],
        llm_latency: float,
    ) -> ValidatedChargingRequest:

        # Heuristic fallback based purely on telemetry
        if actual_soc < 20.0:
            urgency_score = 0.9
            reason = "TELEMETRY_CRITICAL"
        elif actual_soc < 50.0:
            urgency_score = 0.5
            reason = "TELEMETRY_MEDIUM"
        else:
            urgency_score = 0.2
            reason = "TELEMETRY_LOW"

        feasible_ports = [i for i, p in enumerate(available_ports) if not p.is_occupied]

        return ValidatedChargingRequest(
            actual_soc=actual_soc,
            battery_capacity=battery_capacity,
            max_charging_speed=max_charging_speed,
            budget=budget,
            validated_urgency_score=urgency_score,
            deadline_minutes=None,  # Cannot infer deadline without NLP
            reason_category=reason,
            feasible_ports=feasible_ports,
            llm_latency_sec=llm_latency,
            parsing_success=False,
            fallback_used=True,
            contradiction_found=False,
        )
