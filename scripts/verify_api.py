import requests, json

r = requests.get('http://127.0.0.1:8000/api/benchmarks')
d = r.json()

print("HTTP status:", r.status_code)
print("Response keys:", list(d.keys()))

p5 = d.get('phase5_results.json')
print("phase5_results.json present:", p5 is not None)

if p5:
    sc = p5.get('scenarios', {})
    print("Scenario keys:", list(sc.keys()))
    for sname, sdata in sc.items():
        comp = sdata.get('comparison', [])
        print(f"  {sname}: {len(comp)} policies")
        for row in comp:
            print(f"    {row['policy']:<18} sat={row['avg_satisfaction']:.4f}  wait={row['avg_wait']:.4f}h  crit={row['avg_crit_wait']:.4f}h  evs={row['avg_completed']:.1f}")

# Spot-check LOW LLM vs TELEMETRY
low = sc.get('LOW', {}).get('comparison', [])
llm = next((r for r in low if r['policy'] == 'LLM_NEGOTIATOR'), None)
tel = next((r for r in low if r['policy'] == 'TELEMETRY_ONLY'), None)
if llm and tel:
    gap = (llm['avg_satisfaction'] - tel['avg_satisfaction']) / tel['avg_satisfaction'] * 100
    print(f"\nLOW gap (LLM vs TELEM): {gap:+.1f}%")

# Also check negotiate + station endpoints
print("\n--- /api/station (default session) ---")
sr = requests.get('http://127.0.0.1:8000/api/station')
print("status:", sr.status_code, "keys:", list(sr.json().keys()))

print("\n--- /api/new-session ---")
ns = requests.post('http://127.0.0.1:8000/api/new-session')
print("status:", ns.status_code, "response:", ns.json())
