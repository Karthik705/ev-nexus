import numpy as np
import random
from collections import deque
from dataclasses import dataclass
from enum import Enum
from typing import List, Dict, Optional
import os
import time
import sys

# Force UTF-8 output on Windows to prevent UnicodeEncodeError for emojis
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding='utf-8')

from simple_ev_simulation import EVChargingSimulation, UrgencyLevel

class Dashboard:
    
    @staticmethod
    def clear_screen():
        os.system('cls' if os.name == 'nt' else 'clear')
    
    @staticmethod
    def draw_station(station, all_evs):
        print("\n" + "╔" + "═"*68 + "╗")
        print("║" + " "*20 + "⚡ CHARGING STATION ⚡" + " "*27 + "║")
        print("╚" + "═"*68 + "╝")
        for port in station.ports:
            speed_label = f"{port.speed.value:>3}kW"
            if port.is_occupied:
                ev = all_evs.get(port.current_ev_id)
                if ev:
                    urgency_emoji = {
                        'CRITICAL': '🔴',
                        'HIGH': '🟠',
                        'MEDIUM': '🟡',
                        'LOW': '🟢'
                    }
                    emoji = urgency_emoji.get(ev.get_urgency_level().name, '⚪')
                    total_time = ev.battery_needed / min(port.speed.value, ev.max_charging_speed)
                    time_remaining = (ev.target_battery - ev.current_battery) / min(port.speed.value, ev.max_charging_speed)
                    progress = ev.current_battery / ev.target_battery if ev.target_battery > 0 else 0
                    bar_length = 20
                    filled = int(bar_length * progress)
                    bar = "█" * filled + "░" * (bar_length - filled)
                    status = (f"{emoji} EV{port.current_ev_id:2d} [{bar}] "
                            f"{max(0, time_remaining):.1f}h left")
                else:
                    status = "🚗 Charging..."
            else:
                status = "⚪ Available"
            print(f"  Port {port.port_id} ({speed_label}): {status}")
        print()
    
    @staticmethod
    def draw_queue(queue_list, max_show=8):
        print("╔" + "═"*68 + "╗")
        print("║" + " "*25 + "⏳ WAITING QUEUE" + " "*28 + "║")
        print("╚" + "═"*68 + "╝")
        
        if not queue_list:
            print("  (empty - no EVs waiting)")
        else:
            for i, ev in enumerate(queue_list[:max_show]):
                urgency_emoji = {
                    'CRITICAL': '🔴',
                    'HIGH': '🟠',
                    'MEDIUM': '🟡',
                    'LOW': '🟢'
                }
                emoji = urgency_emoji.get(ev.get_urgency_level().name, '⚪')
                pct = int(ev.battery_percent)
                bar_length = 20
                filled = int(bar_length * pct / 100)
                battery_bar = "█" * filled + "░" * (bar_length - filled)
                
                priority = int(ev.calculate_priority_score())
                
                print(f"  {i+1:2d}. {emoji} EV{ev.ev_id:2d} [{battery_bar}] "
                      f"{pct:3d}% | Wait: {ev.wait_time:.1f}h | Priority: {priority:3d}")
            
            if len(queue_list) > max_show:
                print(f"  ... and {len(queue_list) - max_show} more EVs waiting")
        
        print()
    
    @staticmethod
    def draw_stats(sim_time, total_evs, completed, charging, waiting, revenue, avg_satisfaction):
        print("╔" + "═"*68 + "╗")
        print("║" + " "*26 + "📊 STATISTICS" + " "*29 + "║")
        print("╚" + "═"*68 + "╝")
        
        print(f"  ⏰ Simulation Time:     {sim_time:6.1f} hours")
        print(f"  🚗 Total EVs Arrived:   {total_evs:6d}")
        print(f"  ✅ Completed:           {completed:6d}")
        print(f"  ⚡ Currently Charging:  {charging:6d}")
        print(f"  ⏳ Waiting in Queue:    {waiting:6d}")
        print(f"  💰 Revenue:            ${revenue:7.2f}")
        print(f"  😊 Avg Satisfaction:    {avg_satisfaction:6.2f}")
        print()


class VisualEVChargingSimulation(EVChargingSimulation):
    def __init__(self, simulation_hours=8.0, arrival_rate=2.0, visual_mode=True):
        super().__init__(simulation_hours=simulation_hours, arrival_rate=arrival_rate, auto_dispatch=True)
        self.visual_mode = visual_mode

    def run(self):
        print("="*70)
        print("🔌 EV CHARGING SIMULATION - VISUAL MODE")
        print("="*70)
        print("Starting simulation...")
        time.sleep(2)
        steps = int(self.simulation_hours / self.time_step)
        update_interval = int(0.5 / self.time_step)  
        for i in range(steps):
            self.step()           
            if self.visual_mode and i % update_interval == 0:
                Dashboard.clear_screen()
                avg_sat = (sum(self.satisfaction_scores) / len(self.satisfaction_scores)
                          if self.satisfaction_scores else 0)
                Dashboard.draw_stats(
                    self.current_time,
                    len(self.all_evs),
                    len(self.completed_evs),
                    len(self.active_evs),
                    len(self.scheduler.queue),
                    self.total_revenue,
                    avg_sat
                )
                Dashboard.draw_station(self.station, self.active_evs)
                Dashboard.draw_queue(list(self.scheduler.queue))   
                time.sleep(0.3)  
        self.print_final_summary()
        
    def print_final_summary(self):
        avg_satisfaction = (sum(self.satisfaction_scores) / len(self.satisfaction_scores)
                           if self.satisfaction_scores else 0)
        avg_wait = (self.scheduler.total_wait_time / self.scheduler.total_served
                   if self.scheduler.total_served > 0 else 0)
        print("\n" + "="*70)
        print("📊 FINAL RESULTS")
        print("="*70)
        print(f"Total EVs arrived:      {len(self.all_evs)}")
        print(f"EVs completed:          {len(self.completed_evs)}")
        print(f"EVs still waiting:      {len(self.scheduler.queue)}")
        print(f"Total revenue:         ${self.total_revenue:.2f}")
        print(f"Average wait time:      {avg_wait:.2f} hours")
        print(f"Average satisfaction:   {avg_satisfaction:.2f}")
        print("="*70)

if __name__ == "__main__":
    random.seed(42)
    np.random.seed(42)
    sim = VisualEVChargingSimulation(
        simulation_hours=6.0,
        arrival_rate=3.0,
        visual_mode=True  
    )
    sim.run()