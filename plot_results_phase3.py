import json
import matplotlib.pyplot as plt
import numpy as np
import os
import sys

# Force UTF-8 output on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding='utf-8')

def load_results():
    if not os.path.exists('phase3_results.json'):
        print("Error: phase3_results.json not found.")
        return None
    with open('phase3_results.json', 'r') as f:
        return json.load(f)

def plot_grouped_bar_chart(scenarios_data, metric_key, title, ylabel, filename, policies=['FIFO', 'PRIORITY', 'SJF', 'DQN']):
    scenario_names = list(scenarios_data.keys())
    x = np.arange(len(scenario_names))
    width = 0.2
    
    fig, ax = plt.subplots(figsize=(10, 6))
    
    colors = {'FIFO': 'steelblue', 'PRIORITY': 'firebrick', 'SJF': 'forestgreen', 'DQN': 'goldenrod'}
    
    for i, policy in enumerate(policies):
        values = []
        for s in scenario_names:
            # Find policy data in scenario
            comp = scenarios_data[s]['comparison']
            val = next((c[metric_key] for c in comp if c['policy'] == policy), 0)
            values.append(val)
        
        offset = (i - len(policies)/2 + 0.5) * width
        rects = ax.bar(x + offset, values, width, label=policy, color=colors[policy], alpha=0.8)
        
        # Add labels on bars
        for rect in rects:
            height = rect.get_height()
            ax.annotate(f'{height:.2f}',
                        xy=(rect.get_x() + rect.get_width() / 2, height),
                        xytext=(0, 3),  
                        textcoords="offset points",
                        ha='center', va='bottom', fontsize=8, rotation=90)

    ax.set_ylabel(ylabel, fontsize=12)
    ax.set_title(title, fontsize=14, fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels(scenario_names)
    ax.legend(title="Policy")
    ax.grid(axis='y', linestyle='--', alpha=0.7)
    
    fig.tight_layout()
    plt.savefig(filename, dpi=150)
    print(f"📊 Saved {filename}")
    plt.close()

def main():
    data = load_results()
    if not data:
        return
        
    scenarios_data = data.get('scenarios', {})
    if not scenarios_data:
        print("No scenario data found.")
        return
    
    os.makedirs('plots_phase3', exist_ok=True)
    
    plot_grouped_bar_chart(scenarios_data, 'avg_revenue', "Average Revenue by Policy across Congestion Levels", "Revenue (USD)", "plots_phase3/revenue_comparison.png")
    plot_grouped_bar_chart(scenarios_data, 'avg_wait', "Average Wait Time by Policy across Congestion Levels", "Wait Time (Hours)", "plots_phase3/wait_comparison.png")
    plot_grouped_bar_chart(scenarios_data, 'avg_crit_wait', "Critical Wait Time by Policy across Congestion Levels", "Wait Time (Hours)", "plots_phase3/crit_wait_comparison.png")
    plot_grouped_bar_chart(scenarios_data, 'avg_completed', "Station Throughput across Congestion Levels", "EVs Served", "plots_phase3/throughput_comparison.png")
    plot_grouped_bar_chart(scenarios_data, 'avg_satisfaction', "Average Satisfaction across Congestion Levels", "Satisfaction Score", "plots_phase3/satisfaction_comparison.png")

    print("\n✅ Visualization complete! Check the 'plots_phase3/' directory.")

if __name__ == "__main__":
    main()
