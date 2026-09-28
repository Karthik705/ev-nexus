import os
import torch
import numpy as np
from simple_ev_simulation import EVChargingSimulation, EVAgent, ChargingSpeed, UrgencyLevel, ChargingPort
from ev_gym_env import EVChargingEnv
from dqn_agent import DQNAgent

def create_deterministic_sim():
    sim = EVChargingSimulation(simulation_hours=24.0, arrival_rate=0.0)
    # Clear auto-generated ports and make a specific setup
    sim.station.ports = [
        ChargingPort(0, ChargingSpeed.SLOW),
        ChargingPort(1, ChargingSpeed.SLOW),
        ChargingPort(2, ChargingSpeed.FAST),
        ChargingPort(3, ChargingSpeed.FAST),
        ChargingPort(4, ChargingSpeed.ULTRA)
    ]
    sim.scheduler.queue = []
    sim.active_evs = {}
    return sim

def load_dqn(sim, model_path="ev_dqn_model_v4.pth"):
    agent = DQNAgent(42, 26)
    if os.path.exists(model_path):
        agent.model.load_state_dict(torch.load(model_path, map_location="cpu", weights_only=True))
        agent.model.eval()
    return agent

def run_scenario(name, evs, use_dqn=True):
    print(f"\n{'='*50}\nSCENARIO: {name} (Policy: {'DQN' if use_dqn else 'FIFO'})\n{'='*50}")
    env = EVChargingEnv()
    env.reset()
    env.sim = create_deterministic_sim()
    
    # Add EVs to queue
    for ev in evs:
        env.sim.scheduler.queue.append(ev)
        
    agent = load_dqn(env.sim)
    
    total_reward = 0
    # Run a few steps to empty the queue
    for _ in range(10):
        if not env.sim.scheduler.queue:
            break
            
        if use_dqn:
            state = env._get_observation()
            mask = env.valid_actions_mask()
            action = agent.act_greedy(state, mask)
        else:
            # FIFO: Find first EV that fits in any available port
            action = 0
            for i, ev in enumerate(env.sim.scheduler.queue):
                for p_idx, p in enumerate(env.sim.station.ports):
                    if not p.is_occupied:
                        action = 1 + (i * 5) + p_idx
                        break
                if action != 0:
                    break
        
        if action == 0:
            print("Action: WAIT")
            env.step(action)
        else:
            idx = action - 1
            q_idx = idx // 5
            p_idx = idx % 5
            ev_id = env.sim.scheduler.queue[q_idx].id
            port_speed = env.sim.station.ports[p_idx].speed.name
            print(f"Action: Assigned EV {ev_id} to Port {p_idx} ({port_speed})")
            _, r, _, _, _ = env.step(action)
            total_reward += r
            print(f"   Reward: {r:.2f}")

if __name__ == "__main__":
    # Scenario 1: 7kW EV + 150kW-capable EV
    # Setup: 2 EVs in queue.
    ev1 = EVAgent("SlowEV", 40, 10, 7.0, 0, 80)
    ev2 = EVAgent("FastEV", 80, 20, 150.0, 0, 80)
    
    # Let's add multiple scenarios to satisfy the user request:
    
    # SCENARIO 1: 7-kW EV + 150-kW-capable EV
    run_scenario("1. 7kW + 150kW EVs", [ev1, ev2], use_dqn=False)
    run_scenario("1. 7kW + 150kW EVs", [ev1, ev2], use_dqn=True)
    
    # SCENARIO 2: Critical 150-kW EV behind a low-urgency EV
    ev_crit = EVAgent("CritFast", 80, 5, 150.0, 0, 80)
    run_scenario("2. Critical Fast Behind Slow", [ev1, ev_crit], use_dqn=False)
    run_scenario("2. Critical Fast Behind Slow", [ev1, ev_crit], use_dqn=True)
    
    # SCENARIO 3: Multiple EVs competing for a single ultra-fast port.
    ev_fast2 = EVAgent("FastEV2", 80, 20, 150.0, 0, 80)
    run_scenario("3. Multiple Fast Competing", [ev2, ev_fast2, ev_crit], use_dqn=False)
    run_scenario("3. Multiple Fast Competing", [ev2, ev_fast2, ev_crit], use_dqn=True)
