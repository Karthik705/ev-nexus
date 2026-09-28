import json
import sys

def load_json(path):
    with open(path, 'r') as f:
        return json.load(f)

old = load_json('phase5_results.json')
new = load_json('phase5_final_results.json')

scenarios = ['LOW', 'MEDIUM', 'HIGH']

print(f"{'Scenario':<8} | {'Policy':<15} | {'Old Sat':<8} | {'New Sat':<8} | {'Delta':<8} | {'Old Wait':<8} | {'New Wait':<8} | {'Delta':<8}")
print("-" * 100)

for s in scenarios:
    old_s = old['scenarios'][s]['comparison']
    new_s = new['scenarios'][s]['comparison']
    
    for policy in ['LLM_NEGOTIATOR', 'TELEMETRY_ONLY']:
        o = next((x for x in old_s if x['policy'] == policy), None)
        n = next((x for x in new_s if x['policy'] == policy), None)
        
        if o and n:
            sat_d = n['avg_satisfaction'] - o['avg_satisfaction']
            wait_d = n['avg_wait'] - o['avg_wait']
            
            print(f"{s:<8} | {policy:<15} | {o['avg_satisfaction']:<8.4f} | {n['avg_satisfaction']:<8.4f} | {sat_d:<+8.4f} | {o['avg_wait']:<8.2f} | {n['avg_wait']:<8.2f} | {wait_d:<+8.2f}")
