import json
with open('phase5_results.json') as f:
    d = json.load(f)
for scenario in ['LOW','MEDIUM','HIGH']:
    print(f'\n=== {scenario} ===')
    comp = d['scenarios'][scenario]['comparison']
    for c in comp:
        policy = c['policy']
        wait = c['avg_wait']
        crit = c['avg_crit_wait']
        sat = c['avg_satisfaction']
        rev = c['avg_revenue']
        evs = c['avg_completed']
        print(f'  {policy:<14} wait={wait:.4f}h  crit={crit:.4f}h  sat={sat:.4f}  rev=${rev:.0f}  evs={evs:.1f}')
