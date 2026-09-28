import json
import matplotlib.pyplot as plt
import numpy as np
import os
import sys

# Force UTF-8 output on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding='utf-8')

def load_results():
    if not os.path.exists('dqn_comparison_results.json'):
        print("Error: dqn_comparison_results.json not found.")
        return None
    with open('dqn_comparison_results.json', 'r') as f:
        return json.load(f)

def plot_bar_chart(policies, values, title, ylabel, filename, color):
    plt.figure(figsize=(8, 5))
    bars = plt.bar(policies, values, color=color, alpha=0.8)
    plt.title(title, fontsize=14, fontweight='bold')
    plt.ylabel(ylabel, fontsize=12)
    plt.grid(axis='y', linestyle='--', alpha=0.7)
    
    # Add values on top of bars
    for bar in bars:
        yval = bar.get_height()
        plt.text(bar.get_x() + bar.get_width()/2, yval, f"{yval:.2f}", ha='center', va='bottom', fontsize=10, fontweight='bold')
        
    plt.tight_layout()
    plt.savefig(filename, dpi=150)
    print(f"📊 Saved {filename}")

def main():
    data = load_results()
    if not data:
        return
        
    comparison = data.get('comparison', [])
    if not comparison:
        print("No comparison data found.")
        return
        
    policies = [c['policy'] for c in comparison]
    avg_wait = [c['avg_wait'] for c in comparison]
    crit_wait = [c['avg_crit_wait'] for c in comparison]
    revenue = [c['avg_revenue'] for c in comparison]
    throughput = [c['avg_completed'] for c in comparison]
    
    # Ensure plots directory exists
    os.makedirs('plots', exist_ok=True)
    
    plot_bar_chart(policies, avg_wait, "Average Waiting Time by Policy (Lower is Better)", "Wait Time (Hours)", "plots/avg_wait.png", "steelblue")
    plot_bar_chart(policies, crit_wait, "Critical EV Waiting Time by Policy (Lower is Better)", "Wait Time (Hours)", "plots/crit_wait.png", "firebrick")
    plot_bar_chart(policies, throughput, "Station Throughput (Higher is Better)", "EVs Served", "plots/throughput.png", "forestgreen")
    plot_bar_chart(policies, revenue, "Average Revenue by Policy (Higher is Better)", "Revenue (USD)", "plots/revenue.png", "goldenrod")
    
    print("\n✅ Visualization complete! Check the 'plots/' directory.")

if __name__ == "__main__":
    main()
