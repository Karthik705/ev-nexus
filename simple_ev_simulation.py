import numpy as np
import random
from collections import deque
from dataclasses import dataclass
from enum import Enum
from typing import Optional
import time
import sys
import torch

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding='utf-8')

# --- IMPORT YOUR AI BRAIN ---
try:
    from llm_negotiator import GeminiNegotiator
    AI_ENABLED = True 
except ImportError:
    AI_ENABLED = False
    print("⚠️ llm_negotiator.py not found. Running in Dummy Mode.")

class ChargingSpeed(Enum):
    SLOW = 7.0    
    FAST = 50.0   
    ULTRA = 150.0 

class UrgencyLevel(Enum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4

@dataclass
class ChargingPort:
    port_id: int
    speed: ChargingSpeed
    is_occupied: bool = False
    current_ev_id: Optional[int] = None
    
    def start_charging(self, ev_id: int):
        self.is_occupied = True
        self.current_ev_id = ev_id

    def stop_charging(self):
        self.is_occupied = False
        self.current_ev_id = None

class EVAgent:
    def __init__(self, ev_id, max_battery, current_battery, max_charging_speed, arrival_time, target_battery=80, budget=50.0, hidden_deadline=None, driver_message=None):
        self.id = ev_id
        self.max_battery = max_battery
        self.current_battery = current_battery
        self.max_charging_speed = max_charging_speed
        self.arrival_time = arrival_time
        self.target_battery = target_battery
        self.budget = budget
        
        self.battery_needed = max(0, target_battery - current_battery)
        self.wait_time = 0.0
        self.patience = random.uniform(1.0, 4.0) 
        self.urgency_level = random.choice(list(UrgencyLevel))
        self.is_completed = False
        
        # New for Phase 4C
        if hidden_deadline is not None:
            self.hidden_deadline = hidden_deadline
        else:
            self.hidden_deadline = random.randint(15, 120) if self.urgency_level in [UrgencyLevel.HIGH, UrgencyLevel.CRITICAL] else None
            
        if driver_message is not None:
            self.driver_message = driver_message
        else:
            self.driver_message = self._generate_simulated_message()
            
        self.validated_request: Optional["ValidatedChargingRequest"] = None  # Filled by negotiator
        
    def _generate_simulated_message(self) -> str:
        soc = (self.current_battery / self.max_battery) * 100
        lies = random.random() < 0.1 # 10% chance to lie about SOC
        stated_soc = max(0, soc - 20) if lies else soc
        
        if self.urgency_level == UrgencyLevel.CRITICAL:
            return f"Emergency! I only have {stated_soc:.0f}% and I must leave in {self.hidden_deadline} minutes!"
        elif self.urgency_level == UrgencyLevel.HIGH:
            return f"I'm running late, need to charge my {stated_soc:.0f}% battery in {self.hidden_deadline} mins."
        elif self.urgency_level == UrgencyLevel.MEDIUM:
            return f"Just a regular charge, I have {stated_soc:.0f}%, can wait a bit."
        else:
            return f"No rush at all, I'm at {stated_soc:.0f}%, just need the cheapest charge."

    @property
    def battery_percent(self):
        return (self.current_battery / self.max_battery) * 100

    @property
    def battery_needed_val(self):
        return max(0, self.target_battery - self.current_battery)

    def get_urgency_level(self):
        return self.urgency_level

    def calculate_priority_score(self):
        return (self.get_urgency_level().value * 25 + 
                (100 - self.battery_percent) + 
                (self.wait_time * 10))

    def update_wait_time(self, time_step):
        if not self.is_completed:
            self.wait_time += time_step

class ChargingStation:
    def __init__(self, num_slow=2, num_fast=2, num_ultra=1):
        self.ports = []
        p_id = 0
        for _ in range(num_slow): self.ports.append(ChargingPort(p_id, ChargingSpeed.SLOW)); p_id+=1
        for _ in range(num_fast): self.ports.append(ChargingPort(p_id, ChargingSpeed.FAST)); p_id+=1
        for _ in range(num_ultra): self.ports.append(ChargingPort(p_id, ChargingSpeed.ULTRA)); p_id+=1

    def get_available_ports(self):
        return [p for p in self.ports if not p.is_occupied]

    def assign_ev(self, ev, port):
        port.start_charging(ev.id)
        return True

    def step(self, active_evs, time_step):
        completed_ev_ids = []
        for port in self.ports:
            if port.is_occupied:
                ev = next((e for e in active_evs if e.id == port.current_ev_id), None)
                if ev:
                    actual_speed = min(port.speed.value, ev.max_charging_speed)
                    if ev.battery_percent > 80:
                        slow_factor = max(0.1, (100 - ev.battery_percent) / 20.0)
                        actual_speed *= slow_factor
                    
                    ev.current_battery += actual_speed * time_step
                    if ev.current_battery >= ev.target_battery:
                        port.stop_charging()
                        ev.is_completed = True
                        completed_ev_ids.append(ev.id)
        return completed_ev_ids

class Scheduler:
    def __init__(self, policy='FIFO'):
        self.policy = policy
        self.queue = deque()

    def add_ev(self, ev):
        self.queue.append(ev)

    def get_next_ev(self):
        if not self.queue:
            return None
            
        if self.policy == 'FIFO':
            return self.queue.popleft()
        elif self.policy == 'PRIORITY':
            priorities = [(ev, ev.calculate_priority_score()) for ev in self.queue]
            priorities.sort(key=lambda x: x[1], reverse=True)
            selected = priorities[0][0]
            self.queue.remove(selected)
            return selected
        elif self.policy == 'SJF':
            jobs = [(ev, ev.battery_needed_val) for ev in self.queue]
            jobs.sort(key=lambda x: x[1])
            selected = jobs[0][0]
            self.queue.remove(selected)
            return selected
        elif self.policy in ['LLM_DETERMINISTIC', 'DETERMINISTIC_TELEMETRY_ONLY', 'LLM_UNVALIDATED']:
            priorities = []
            for ev in self.queue:
                if ev.validated_request:
                    # In LLM_UNVALIDATED, the validated_request contains the UNVALIDATED LLM urgency directly
                    score = ev.validated_request.calculate_priority_score(ev.wait_time)
                    priorities.append((ev, score))
            if not priorities:
                return self.queue.popleft() 
                
            priorities.sort(key=lambda x: x[1], reverse=True)
            selected = priorities[0][0]
            self.queue.remove(selected)
            return selected
        else:
            return self.queue.popleft()

class EVChargingSimulation:
    def __init__(self, simulation_hours=24.0, arrival_rate=2.5, auto_dispatch=False, num_ports=5, policy='FIFO'):
        self.station = ChargingStation()
        self.scheduler = Scheduler(policy=policy)
        self.simulation_hours = simulation_hours
        self.base_arrival_rate = arrival_rate
        self.time_step = 0.1 
        self.current_time = 0.0
        self.ev_counter = 0
        self.active_evs = [] 
        self.completed_evs = []
        self.auto_dispatch = auto_dispatch
        self.policy = policy
        
        self.all_evs = {}
        self.wait_times = []
        self.satisfaction_scores = []
        self.total_revenue = 0.0
        
        self.dqn_agent = None
        self.negotiator = None
        
        if policy == 'DQN':
            try:
                from dqn_agent import DQNAgent
                self.dqn_agent = DQNAgent(42, 26)
                self.dqn_agent.model.load_state_dict(torch.load("ev_dqn_model_v5.pth", map_location="cpu", weights_only=True))
                self.dqn_agent.model.eval()
            except Exception as e:
                print(f"Failed to load DQN model: {e}")
                
        if policy == 'LLM_DETERMINISTIC':
            from llm_negotiator import GeminiNegotiator
            self.negotiator = GeminiNegotiator()

    def valid_actions_mask(self):
        mask = np.zeros(26, dtype=bool)
        mask[0] = True 
        queue_len = len(self.scheduler.queue)
        for i in range(25):
            q_idx = i // 5
            p_idx = i % 5
            if q_idx < 5 and q_idx < queue_len:
                if p_idx < len(self.station.ports) and not self.station.ports[p_idx].is_occupied:
                    mask[i+1] = True
        return mask

    def _get_dqn_state(self):
        port_states = []
        for port in self.station.ports:
            port_states.extend([1.0 if port.is_occupied else 0.0, port.speed.value / 150.0])
        while len(port_states) < 10: port_states.extend([0.0, 0.0])
        queue_states = []
        queue_list = list(self.scheduler.queue)
        for i in range(5):
            if i < len(queue_list):
                ev = queue_list[i]
                queue_states.extend([ev.battery_percent / 100.0, min(ev.battery_needed_val / 100.0, 1.0), ev.max_charging_speed / 150.0, ev.get_urgency_level().value / 4.0, min(ev.wait_time / 5.0, 1.0), min(ev.budget / 60.0, 1.0)])
            else:
                queue_states.extend([0.0] * 6)
        global_stats = [min(self.current_time / 24.0, 1.0), min(len(queue_list) / 20.0, 1.0)]
        return np.array(port_states + queue_states + global_stats, dtype=np.float32)

    def generate_random_ev(self):
        max_battery = random.choice([40, 60, 75, 100])
        current_battery = max_battery * (random.uniform(0.05, 0.5))
        max_speed = random.choice([50.0, 150.0])
        # Target 70-100% of THIS vehicle's own capacity. Previously this was an
        # absolute kWh value (70-100) independent of max_battery, so any EV with
        # max_battery in {40, 60, 75} got a target exceeding its own capacity
        # (SOC readings above 100% while charging).
        target_battery = max_battery * random.uniform(0.70, 1.00)
        budget = random.uniform(20.0, 100.0)
        new_ev = EVAgent(self.ev_counter, max_battery, current_battery, max_speed, self.current_time, target_battery, budget)
        self.ev_counter += 1
            
        from constraint_validator import ConstraintValidator
        if self.policy == 'LLM_DETERMINISTIC' and self.negotiator:
            llm_req, lat, succ = self.negotiator.negotiate(new_ev.driver_message)
            new_ev.validated_request = ConstraintValidator.validate_request(llm_req, (new_ev.current_battery / new_ev.max_battery) * 100, new_ev.max_battery, new_ev.max_charging_speed, new_ev.budget, self.station.ports, lat, succ)
        elif self.policy in ['LLM_DETERMINISTIC', 'DETERMINISTIC_TELEMETRY_ONLY']:
            new_ev.validated_request = ConstraintValidator.validate_request(None, (new_ev.current_battery / new_ev.max_battery) * 100, new_ev.max_battery, new_ev.max_charging_speed, new_ev.budget, self.station.ports, 0.0, False)
            
        self.all_evs[new_ev.id] = new_ev
        self.scheduler.add_ev(new_ev)
        return new_ev

    def calculate_price(self, ev):
        base_price = 0.30
        urgency_mult = {
            UrgencyLevel.LOW: 1.0,
            UrgencyLevel.MEDIUM: 1.2,
            UrgencyLevel.HIGH: 1.5,
            UrgencyLevel.CRITICAL: 2.0
        }
        
        if ev.max_charging_speed <= 7.0: speed_mult = 1.0
        elif ev.max_charging_speed <= 50.0: speed_mult = 1.3
        else: speed_mult = 1.6
        
        cost = (ev.battery_needed * base_price * 
                urgency_mult.get(ev.get_urgency_level(), 1.0) *
                speed_mult *
                (1 + len(self.scheduler.queue) * 0.05))
        return round(cost, 2)

    def step(self):
        if random.random() < (self.base_arrival_rate * self.time_step):
            self.generate_random_ev()

        completed_ids = self.station.step(self.active_evs, self.time_step)
        for ev_id in completed_ids:
            ev = next(e for e in self.active_evs if e.id == ev_id)
            self.active_evs.remove(ev)
            self.completed_evs.append(ev)
            
            satisfaction = max(0.0, 1.0 - (ev.wait_time / ev.patience))
            self.satisfaction_scores.append(satisfaction)
            self.wait_times.append(ev.wait_time)
            
        if self.auto_dispatch:
            if self.policy == 'DQN' and self.dqn_agent:
                while self.scheduler.queue:
                    state = self._get_dqn_state()
                    mask = self.valid_actions_mask()
                    
                    with torch.no_grad():
                        state_t = torch.FloatTensor(state).unsqueeze(0).to("cpu")
                        q_values = self.dqn_agent.model(state_t).numpy()[0]
                        q_values[~mask] = -np.inf
                        action = np.argmax(q_values)
                        
                    if action == 0:
                        break 
                    
                    idx = action - 1
                    q_idx = idx // 5
                    p_idx = idx % 5
                    
                    if q_idx >= len(self.scheduler.queue) or p_idx >= len(self.station.ports):
                        break
                        
                    ev = self.scheduler.queue[q_idx]
                    port = self.station.ports[p_idx]
                    
                    if port.is_occupied:
                        break
                        
                    price = self.calculate_price(ev)
                    if price > ev.budget:
                        self.scheduler.queue.remove(ev)
                    else:
                        self.station.assign_ev(ev, port)
                        self.scheduler.queue.remove(ev)
                        self.active_evs.append(ev)
                        self.total_revenue += price
            else:
                available_ports = self.station.get_available_ports()
                while available_ports and self.scheduler.queue:
                    ev = self.scheduler.get_next_ev()
                    if not ev: break
                    
                    # Find feasible port
                    feasible_ports = []
                    if self.policy in ['LLM_DETERMINISTIC', 'DETERMINISTIC_TELEMETRY_ONLY', 'LLM_UNVALIDATED'] and ev.validated_request:
                        for p_idx in ev.validated_request.feasible_ports:
                            p = self.station.ports[p_idx]
                            if not p.is_occupied:
                                feasible_ports.append(p)
                    
                    if not feasible_ports:
                        feasible_ports = [p for p in available_ports if p.speed.value <= ev.max_charging_speed * 1.5]
                        if not feasible_ports: feasible_ports = available_ports
                        
                    best_port = min(feasible_ports, key=lambda x: abs(x.speed.value - ev.max_charging_speed))
                    
                    price = self.calculate_price(ev)
                    # Ignore budget constraints for heuristics so they don't break
                    if self.policy in ['LLM_DETERMINISTIC', 'DETERMINISTIC_TELEMETRY_ONLY', 'LLM_UNVALIDATED'] and price > ev.budget:
                        # Budget failure, drop EV
                        pass
                    else:
                        self.station.assign_ev(ev, best_port)
                        self.active_evs.append(ev)
                        available_ports.remove(best_port)
                        self.total_revenue += price

        # Wait Times
        for ev in self.scheduler.queue:
            ev.update_wait_time(self.time_step)
            
        self.current_time += self.time_step

    def run(self):
        steps = int(self.simulation_hours / self.time_step)
        for _ in range(steps):
            self.step()

    def get_results(self):
        completed = len(self.completed_evs)
        total_evs = len(self.all_evs)
        rejected = total_evs - completed - len(self.active_evs) - len(self.scheduler.queue)
        
        avg_wait = np.mean(self.wait_times) if self.wait_times else 0.0
        max_wait = np.max(self.wait_times) if self.wait_times else 0.0
        
        critical_waits = [ev.wait_time for ev in self.all_evs.values() if ev.get_urgency_level() in (UrgencyLevel.CRITICAL, UrgencyLevel.HIGH)]
        avg_critical_wait = np.mean(critical_waits) if critical_waits else 0.0
        
        avg_satisfaction = np.mean(self.satisfaction_scores) if self.satisfaction_scores else 0.0
        
        return {
            'completed': completed,
            'rejected': rejected,
            'total_evs': total_evs,
            'revenue': self.total_revenue,
            'avg_wait_time': avg_wait,
            'max_wait_time': max_wait,
            'avg_critical_wait': avg_critical_wait,
            'avg_satisfaction': avg_satisfaction
        }

if __name__ == "__main__":
    sim = EVChargingSimulation(simulation_hours=12.0, auto_dispatch=True, policy='FIFO')
    sim.run()
    print(sim.get_results())