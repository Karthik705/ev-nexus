import gymnasium as gym
from gymnasium import spaces
import numpy as np
from simple_ev_simulation import EVChargingSimulation, ChargingSpeed, UrgencyLevel
import sys

# Force UTF-8 output on Windows to prevent UnicodeEncodeError for emojis
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding='utf-8')

class EVChargingEnv(gym.Env):
    metadata = {'render_modes': ['human']}

    def __init__(self):
        super(EVChargingEnv, self).__init__()
        
        # 1. Setup the NEW Simulation (24 Hours)
        self.sim = EVChargingSimulation(simulation_hours=24.0, arrival_rate=2.5)
        
        # 2. Action Space: 26 Actions (0=Wait, 1-25=Queue(0-4) to Port(0-4))
        self.max_queue_visible = 5  
        self.max_ports = 5
        self.action_space = spaces.Discrete(1 + self.max_queue_visible * self.max_ports)
        
        # 3. Observation Space: 42 numbers
        # [5 Ports * 2] + [5 Cars * 6] + [2 Global]
        self.observation_space = spaces.Box(
            low=0, high=1, shape=(42,), dtype=np.float32
        )

    def valid_actions_mask(self):
        mask = np.zeros(self.action_space.n, dtype=bool)
        mask[0] = True # Wait is always valid
        
        queue_len = len(self.sim.scheduler.queue)
        for i in range(25):
            q_idx = i // self.max_ports
            p_idx = i % self.max_ports
            if q_idx < self.max_queue_visible and q_idx < queue_len:
                if p_idx < len(self.sim.station.ports) and not self.sim.station.ports[p_idx].is_occupied:
                    mask[i+1] = True
        return mask

    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        # Restart the simulation
        self.sim = EVChargingSimulation(simulation_hours=24.0, arrival_rate=2.5)
        return self._get_observation(), {}

    def step(self, action):
        reward = 0
        terminated = False
        truncated = False
        
        # A. HANDLE ACTIONS
        if action == 0:
            # WAIT & ADVANCE TIME
            self.sim.step()
            # Reward active charging to incentivize keeping ports busy
            charging_reward = len(self.sim.active_evs) * 0.5
            # Penalize waiting cars heavily to make queue hoarding a liability
            queue_penalty = sum([0.5 * ev.get_urgency_level().value for ev in self.sim.scheduler.queue])
            
            reward += charging_reward
            reward -= queue_penalty 
        else:
            idx = action - 1
            q_idx = idx // self.max_ports
            p_idx = idx % self.max_ports
            
            if q_idx >= len(self.sim.scheduler.queue) or p_idx >= len(self.sim.station.ports) or self.sim.station.ports[p_idx].is_occupied:
                # Should be caught by mask, but just in case
                reward -= 100
                self.sim.step()
            else:
                ev_to_assign = self.sim.scheduler.queue[q_idx]
                target_port = self.sim.station.ports[p_idx]
                
                price = self.sim.calculate_price(ev_to_assign)
                if price > ev_to_assign.budget:
                    self.sim.scheduler.queue.remove(ev_to_assign)
                    reward -= 1
                else:
                    self.sim.station.assign_ev(ev_to_assign, target_port)
                    self.sim.scheduler.queue.remove(ev_to_assign)
                    self.sim.active_evs[ev_to_assign.ev_id] = ev_to_assign
                    ev_to_assign.is_charging = True
                    
                    # Remove base assignment reward to fix value-hoarding exploit
                    reward += 0 
                    
                    if ev_to_assign.max_charging_speed >= target_port.speed.value:
                        reward += 2 # Good match
                    else:
                        reward -= 2 # Wasting port

        # Check termination
        if self.sim.current_time >= self.sim.simulation_hours:
            terminated = True

        return self._get_observation(), reward, terminated, truncated, {}

    def _get_observation(self):
        # 1. Port States (10 numbers: Occupied, Speed)
        port_states = []
        for port in self.sim.station.ports:
            port_states.extend([1.0 if port.is_occupied else 0.0, port.speed.value / 150.0])
        while len(port_states) < 10: port_states.extend([0.0, 0.0])
        port_states = port_states[:10]

        # 2. Queue States (30 numbers: 5 cars * 6 data points)
        queue_states = []
        queue_list = list(self.sim.scheduler.queue)
        
        for i in range(self.max_queue_visible):
            if i < len(queue_list):
                ev = queue_list[i]
                norm_soc = ev.current_battery / max(1, ev.battery_capacity)
                norm_energy = min(ev.battery_needed / 100.0, 1.0)
                norm_speed = ev.max_charging_speed / 150.0
                norm_urgency = ev.get_urgency_level().value / 4.0
                norm_wait = min(ev.wait_time / 5.0, 1.0)
                norm_budget = min(ev.budget / 60.0, 1.0)
                queue_states.extend([norm_soc, norm_energy, norm_speed, norm_urgency, norm_wait, norm_budget])
            else:
                queue_states.extend([0.0] * 6)

        # 3. Global Stats (2 numbers)
        global_stats = [
            min(self.sim.current_time / 24.0, 1.0),
            min(len(queue_list) / 20.0, 1.0)
        ]

        return np.array(port_states + queue_states + global_stats, dtype=np.float32)

if __name__ == "__main__":
    # QUICK TEST
    env = EVChargingEnv()
    obs, _ = env.reset()
    print("✅ Environment Updated Successfully!")
    print(f"Observation Shape: {obs.shape}")
    print("Try running dqn_agent.py now!")