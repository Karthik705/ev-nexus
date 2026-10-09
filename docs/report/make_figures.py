"""Generate the figures used in docs/PROJECT_REPORT.md from benchmark_v2_results.json.

Run from the repository root:  python docs/report/make_figures.py
No network or API key needed; it only reads the committed benchmark output.
"""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "figures"
OUT.mkdir(exist_ok=True)
data = json.loads((ROOT / "benchmark_v2_results.json").read_text())

# Palette: the agent is the one series that matters, so it alone carries colour.
AGENT = "#2a78d6"
ABLATION = "#eb6834"
BASE = ["#6f6e69", "#9b9a95", "#c3c2b7"]
INK, MUTED, GRID = "#0b0b0b", "#52514e", "#e6e5e0"

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 10, "axes.edgecolor": GRID,
    "axes.labelcolor": MUTED, "xtick.color": MUTED, "ytick.color": MUTED,
    "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True,
    "grid.color": GRID, "grid.linewidth": 0.8, "axes.axisbelow": True,
    "savefig.dpi": 200, "savefig.bbox": "tight", "figure.facecolor": "white",
})

levels = ["LOW", "MEDIUM", "HIGH"]
rates = [data["experiment_config"]["congestion_levels"][l] for l in levels]
xlabels = [f"{l.title()}\n{r:g} cars/hr" for l, r in zip(levels, rates)]


def on_time(policy, level):
    return data["scenarios"][level]["policies"][policy]["metrics"]["on_time_rate"]["mean"] * 100


# --- Figure 1: deadline adherence vs congestion -------------------------------
series = [
    ("fifo", "FIFO", BASE[2], "-"),
    ("soc", "Lowest-SOC-first", BASE[1], "-"),
    ("sjf", "Shortest-Job-First", BASE[0], "-"),
    ("agent_no_deadline", "Agent, deadlines withheld (ablation)", ABLATION, "--"),
    ("agent", "EV NEXUS agent", AGENT, "-"),
]
fig, ax = plt.subplots(figsize=(7.2, 4.0))
x = range(len(levels))
for key, label, color, ls in series:
    ys = [on_time(key, l) for l in levels]
    lw = 2.6 if key == "agent" else 2.0
    ax.plot(x, ys, ls, color=color, lw=lw, marker="o", ms=6,
            markeredgecolor="white", markeredgewidth=1.5, label=label, zorder=3)
    ax.annotate(f"{ys[-1]:.1f}%", (2, ys[-1]), xytext=(8, 0), textcoords="offset points",
                va="center", fontsize=9, color=INK if key == "agent" else MUTED,
                fontweight="bold" if key == "agent" else "normal")
ax.set_xticks(list(x), xlabels)
ax.set_xlim(-0.15, 2.45)
ax.set_ylim(20, 85)
ax.set_ylabel("Drivers whose deadline was met (%)")
ax.legend(frameon=False, fontsize=8.5, loc="lower left")
ax.set_title("Deadline adherence by station congestion (30 paired seeds per level)",
             loc="left", fontsize=11, color=INK, pad=10)
fig.savefig(OUT / "fig1_deadline_adherence.png")
plt.close(fig)

# --- Figure 2: paired deltas with 95% CIs at HIGH congestion --------------------
paired = data["scenarios"]["HIGH"]["paired_vs_agent"]
names = {"fifo": "vs FIFO", "soc": "vs Lowest-SOC-first", "sjf": "vs Shortest-Job-First",
         "agent_no_deadline": "vs agent with deadlines withheld",
         "agent_no_validation": "vs agent without validator"}
rows = []
for key in ["fifo", "soc", "sjf", "agent_no_deadline", "agent_no_validation"]:
    if key not in paired:
        continue
    d = paired[key]["on_time_rate"]
    pd_ = d["paired_delta"]
    rows.append((names[key], pd_["mean"] * 100, pd_["lo"] * 100, pd_["hi"] * 100,
                 d["seeds_agent_better"], d["seeds_total"]))
fig, ax = plt.subplots(figsize=(7.2, 3.2))
for i, (name, m, lo, hi, won, tot) in enumerate(rows):
    y = len(rows) - 1 - i
    color = AGENT if lo > 0 else MUTED
    ax.plot([lo, hi], [y, y], color=color, lw=2.2, solid_capstyle="round")
    ax.plot(m, y, "o", color=color, ms=8, markeredgecolor="white", markeredgewidth=1.5)
    ax.annotate(f"{m:+.1f} pp  [{lo:+.1f}, {hi:+.1f}]   won {won}/{tot}", (hi, y),
                xytext=(8, 0), textcoords="offset points", va="center", fontsize=8.5, color=INK)
ax.axvline(0, color=MUTED, lw=1)
ax.set_yticks(range(len(rows)), [r[0] for r in reversed(rows)])
ax.set_xlim(-5, 52)
ax.grid(axis="y", visible=False)
ax.set_xlabel("Agent minus comparison, on-time rate (percentage points, 95% bootstrap CI)")
ax.set_title("Paired improvement at HIGH congestion (6.5 cars/hr)", loc="left",
             fontsize=11, color=INK, pad=10)
fig.savefig(OUT / "fig2_paired_deltas.png")
plt.close(fig)

# --- Figure 3: adversarial sweep -----------------------------------------------
sweep = data["adversarial"]["sweep"]
fx = [s["adversarial_fraction"] * 100 for s in sweep]
fig, ax = plt.subplots(figsize=(7.2, 3.6))
ax.plot(fx, [s["agent_on_time"] * 100 for s in sweep], "-o", color=AGENT, lw=2.4, ms=6,
        markeredgecolor="white", markeredgewidth=1.5, label="With validator")
ax.plot(fx, [s["no_validator_on_time"] * 100 for s in sweep], "--o", color=BASE[0], lw=2,
        ms=6, markeredgecolor="white", markeredgewidth=1.5, label="Without validator")
last = sweep[-1]
ax.annotate(f"+{(last['agent_on_time'] - last['no_validator_on_time']) * 100:.1f} pp",
            (fx[-1], (last["agent_on_time"] + last["no_validator_on_time"]) * 50),
            xytext=(10, 0), textcoords="offset points", va="center", fontsize=9, color=INK,
            fontweight="bold")
ax.set_xlabel("Share of drivers falsely claiming an emergency (%)")
ax.set_ylabel("Deadlines met (%)")
ax.set_xlim(-3, 60)
ax.set_ylim(45, 65)
ax.legend(frameon=False, fontsize=9, loc="lower left")
ax.set_title("The validator matters only when people try to game the queue", loc="left",
             fontsize=11, color=INK, pad=10)
fig.savefig(OUT / "fig3_adversarial.png")
plt.close(fig)

print("wrote", sorted(p.name for p in OUT.glob("*.png")))
