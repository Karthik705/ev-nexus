"""
Guards against documentation drift.

Every number published in README.md and docs/EXPERIMENTS.md is parsed back out
of those documents and checked against benchmark_v2_results.json. This exists
because it caught a real error: after the benchmark was regenerated following
an engine fix, the LOW-congestion row in both documents was left quoting the
previous run's values.

If you regenerate the benchmark, these tests tell you exactly which published
figures went stale.
"""

import json
import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOL = 0.1  # percentage points


@pytest.fixture(scope="module")
def bench():
    path = os.path.join(ROOT, "benchmark_v2_results.json")
    if not os.path.exists(path):
        pytest.skip("benchmark_v2_results.json not generated; run benchmark_v2.py")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def readme():
    with open(os.path.join(ROOT, "README.md"), encoding="utf-8") as f:
        return f.read()


def on_time(bench, level, policy):
    return bench["scenarios"][level]["policies"][policy]["metrics"]["on_time_rate"]["mean"] * 100


ROW_TO_POLICY = {
    "FIFO": "fifo",
    "Lowest-SOC-first": "soc",
    "Shortest-Job-First": "sjf",
    "EV NEXUS agent": "agent",
    "ablation: no deadlines": "agent_no_deadline",
}


def test_readme_congestion_table_matches_benchmark(bench, readme):
    """Parse the published table and check every cell against the data."""
    table = re.search(
        r"\| \| LOW \(3/hr\) \| MEDIUM \(5/hr\) \| HIGH \(6\.5/hr\) \|\n\|[-| ]+\|\n((?:\|.*\|\n)+)",
        readme,
    )
    assert table, "README congestion table not found — was it reformatted?"

    checked = 0
    for line in table.group(1).strip().splitlines():
        cells = [c.strip().strip("*").strip() for c in line.strip("|").split("|")]
        label = cells[0]
        assert label in ROW_TO_POLICY, f"unrecognised README row {label!r}"
        policy = ROW_TO_POLICY[label]
        for level, cell in zip(("LOW", "MEDIUM", "HIGH"), cells[1:4]):
            claimed = float(cell.strip("*%"))
            actual = on_time(bench, level, policy)
            assert abs(actual - claimed) < TOL, (
                f"README says {level}/{policy} = {claimed}% but the benchmark "
                f"says {actual:.1f}% — regenerate the README table"
            )
            checked += 1
    assert checked == 15, f"expected 15 cells, checked {checked}"


def test_readme_headline_table_matches_benchmark(bench, readme):
    """The HIGH-congestion headline table at the top of the README."""
    hi = bench["scenarios"]["HIGH"]["policies"]
    for label, policy in [("FIFO", "fifo"), ("Lowest-SOC-first", "soc"),
                          ("Shortest-Job-First", "sjf")]:
        row = re.search(
            rf"^\| {re.escape(label)} \| ([\d.]+)% \| ([\d.]+)% \| (\d+) min \| (\d+) min \| ([\d.]+)% \|$",
            readme, re.M)
        assert row, f"headline row for {label} not found"
        m = hi[policy]["metrics"]
        assert abs(float(row.group(1)) - m["on_time_rate"]["mean"] * 100) < TOL
        assert abs(float(row.group(2)) - m["critical_on_time_rate"]["mean"] * 100) < TOL
        assert abs(float(row.group(3)) - m["avg_wait_min"]["mean"]) < 1.0
        assert abs(float(row.group(4)) - m["p95_wait_min"]["mean"]) < 1.0
        assert abs(float(row.group(5)) - m["served_rate"]["mean"] * 100) < TOL


def test_readme_paired_deltas_match(bench, readme):
    """+32.0 pp / +13.7 pp / +22.2 pp and their seed counts."""
    cmp_hi = bench["scenarios"]["HIGH"]["paired_vs_agent"]
    for base, pattern in [
        ("fifo", r"\+([\d.]+) pp over FIFO\*\* \(won (\d+)/30"),
        ("sjf", r"\+([\d.]+) pp over Shortest-Job-First\*\*\s*\n?\((\d+)/30"),
        ("soc", r"\+([\d.]+) pp over Lowest-SOC-first\*\*\s*\n?\((\d+)/30"),
    ]:
        m = re.search(pattern, readme)
        assert m, f"paired delta claim for {base} not found in README"
        d = cmp_hi[base]["on_time_rate"]
        assert abs(float(m.group(1)) - d["paired_delta"]["mean"] * 100) < TOL + 0.05
        assert int(m.group(2)) == d["seeds_agent_better"]


def test_experiments_doc_table_matches_benchmark(bench):
    with open(os.path.join(ROOT, "docs", "EXPERIMENTS.md"), encoding="utf-8") as f:
        doc = f.read()

    rows = {
        "FIFO": "fifo",
        "Lowest-SOC-first": "soc",
        "Shortest-Job-First": "sjf",
        "Agent, no validator": "agent_no_validation",
    }
    for label, policy in rows.items():
        m = re.search(rf"^\| {re.escape(label)} \| ([\d.]+)% \| ([\d.]+)% \| ([\d.]+)% \|$",
                      doc, re.M)
        assert m, f"EXPERIMENTS.md row for {label} not found"
        for i, level in enumerate(("LOW", "MEDIUM", "HIGH"), start=1):
            claimed, actual = float(m.group(i)), on_time(bench, level, policy)
            assert abs(actual - claimed) < TOL, (
                f"EXPERIMENTS.md {level}/{policy}: doc={claimed}% data={actual:.1f}%"
            )


def test_extraction_quality_claims(bench, readme):
    q = bench["agent_input_quality"]
    assert f"{q['deadlines_recovered']} of {q['scenarios_with_true_deadline']}" in readme
    assert f"{q['deadline_recall'] * 100:.1f}% recall" in readme


def test_claims_that_must_hold_directionally(bench):
    """The qualitative claims the README makes, as assertions."""
    for level in ("LOW", "MEDIUM", "HIGH"):
        agent = on_time(bench, level, "agent")
        for base in ("fifo", "sjf", "soc"):
            assert agent > on_time(bench, level, base), (
                f"README claims the agent wins at every congestion level, but at "
                f"{level} it loses to {base}"
            )
        assert on_time(bench, level, "agent_no_deadline") < agent, (
            f"the no-deadline ablation must be worse than the full agent at {level}; "
            f"otherwise the central claim (the gain comes from language) is false"
        )

    # "gap widens with congestion"
    gaps = []
    for level in ("LOW", "MEDIUM", "HIGH"):
        best = max(on_time(bench, level, p) for p in ("fifo", "sjf", "soc"))
        gaps.append(on_time(bench, level, "agent") - best)
    assert gaps[0] < gaps[1] < gaps[2], f"gap does not widen with congestion: {gaps}"

    # "does not buy deadlines with throughput"
    hi = bench["scenarios"]["HIGH"]["policies"]
    ag = hi["agent"]["metrics"]
    for base in ("fifo", "sjf", "soc"):
        bm = hi[base]["metrics"]
        assert ag["served_rate"]["mean"] >= bm["served_rate"]["mean"]
        assert ag["port_utilisation"]["mean"] < bm["port_utilisation"]["mean"]
        assert ag["avg_wait_min"]["mean"] < bm["avg_wait_min"]["mean"]


def test_validator_claim_is_not_overstated(bench, readme):
    """README must not claim the validator helps when it does not."""
    sweep = {r["adversarial_fraction"]: r for r in bench["adversarial"]["sweep"]}
    zero = sweep[0.0]["paired_delta"]
    significant_at_zero = zero["lo"] > 0 or zero["hi"] < 0
    assert not significant_at_zero, (
        "the validator now shows a significant effect at 0% gaming; the README "
        "says it buys nothing there and must be updated"
    )
    heavy = sweep[0.5]["paired_delta"]
    assert heavy["lo"] > 0, "README claims a significant validator effect at 50% gaming"
    assert "nothing when nobody games the system" in readme


def test_phase5_numbers_are_not_restated(readme):
    """Superseded results must stay superseded."""
    for stale in ("0.612", "1.72h", "$1,033", "+62% HIGH", "0.558"):
        assert stale not in readme, (
            f"README restates superseded Phase 5 figure {stale!r}"
        )
