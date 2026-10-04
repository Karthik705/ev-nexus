import { useEffect, useState } from 'react';
import { api } from '../api';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Cell, ErrorBar,
} from 'recharts';
import { FlaskConical, AlertCircle, ShieldAlert, Microscope } from 'lucide-react';

const TOOLTIP_STYLE = {
  backgroundColor: '#020617', border: '1px solid #1e293b',
  borderRadius: '4px', fontSize: '12px', color: '#e2e8f0',
};
const AXIS_TICK = { fill: '#475569', fontSize: 11 };
const GRID = '#1e293b';

const POLICY_COLOR: Record<string, string> = {
  agent: '#22d3ee',
  sjf: '#059669',
  fifo: '#0e7490',
  soc: '#0d9488',
  agent_no_validation: '#b45309',
  agent_no_deadline: '#9333ea',
};

type Scenario = 'LOW' | 'MEDIUM' | 'HIGH';

const METRIC_OPTIONS = [
  { key: 'on_time_rate', label: 'Deadlines met', pct: true, higherBetter: true },
  { key: 'critical_on_time_rate', label: 'Urgent deadlines met', pct: true, higherBetter: true },
  { key: 'avg_wait_min', label: 'Average wait (min)', pct: false, higherBetter: false },
  { key: 'p95_wait_min', label: 'Worst-case wait (min)', pct: false, higherBetter: false },
  { key: 'served_rate', label: 'Cars served', pct: true, higherBetter: true },
];

export default function BenchmarksPage() {
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [scenario, setScenario] = useState<Scenario>('HIGH');
  const [metric, setMetric] = useState('on_time_rate');

  useEffect(() => {
    api.getBenchmarks()
      .then(setData)
      .catch(() => setError('Could not load benchmark data from /api/benchmarks.'));
  }, []);

  if (error) return (
    <div style={{ padding: 24, display: 'flex', gap: 10, color: '#f87171', fontSize: 13 }}>
      <AlertCircle size={16} style={{ flexShrink: 0, marginTop: 1 }} /> {error}
    </div>
  );
  if (!data) return (
    <div style={{ padding: 24, color: '#334155', fontSize: 13 }}>Loading benchmark data…</div>
  );

  const v2 = data['benchmark_v2_results.json'];
  if (!v2) return (
    <div style={{ padding: 24, color: '#f87171', fontSize: 13 }}>
      <AlertCircle size={14} style={{ verticalAlign: 'middle', marginRight: 6 }} />
      <strong>benchmark_v2_results.json</strong> not found. Run{' '}
      <code>python benchmark_v2.py</code> to generate it.
    </div>
  );

  const sc = v2.scenarios[scenario];
  const cfg = v2.experiment_config;
  const quality = v2.agent_input_quality;
  const meta = METRIC_OPTIONS.find(m => m.key === metric)!;

  const order = ['fifo', 'soc', 'sjf', 'agent_no_deadline', 'agent_no_validation', 'agent'];
  const chartData = order
    .filter(p => sc.policies[p])
    .map(p => {
      const m = sc.policies[p].metrics[metric];
      const val = meta.pct ? m.mean * 100 : m.mean;
      const lo = meta.pct ? m.lo * 100 : m.lo;
      const hi = meta.pct ? m.hi * 100 : m.hi;
      return {
        name: sc.policies[p].label,
        key: p,
        value: Number(val.toFixed(2)),
        err: [Number((val - lo).toFixed(2)), Number((hi - val).toFixed(2))],
      };
    });

  const comparisons = sc.paired_vs_agent ?? {};

  return (
    <div style={{ padding: 24, display: 'flex', flexDirection: 'column', gap: 18 }}>

      <div>
        <h1 style={{ fontSize: 19, fontWeight: 600, color: '#f1f5f9', margin: 0 }}>
          Benchmark Evidence
        </h1>
        <p style={{ fontSize: 12.5, color: '#64748b', marginTop: 5, lineHeight: 1.6,
                    maxWidth: 820 }}>
          {cfg.num_seeds} paired runs per congestion level, 24 h each. Every policy
          receives the byte-identical arrival stream, so each seed is a true paired
          comparison. Intervals are {cfg.statistics}.
        </p>
      </div>

      {/* How good the agent's own inputs are — stated up front, not buried */}
      <div className="panel" style={{ padding: 16 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
          <Microscope size={14} color="#64748b" />
          <span className="section-title" style={{ marginBottom: 0 }}>
            The agent is not given an oracle
          </span>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px,1fr))',
                      gap: 12, marginBottom: 12 }}>
          <Stat label="Deadline recall"
                value={`${(quality.deadline_recall * 100).toFixed(1)}%`}
                sub={`${quality.deadlines_recovered}/${quality.scenarios_with_true_deadline} recovered`} />
          <Stat label="Urgency agreement"
                value={`${(quality.urgency_agreement * 100).toFixed(0)}%`}
                sub={`${quality.urgency_judged_scenarios} scenarios`} />
          <Stat label="Deadlines missed"
                value={String(quality.deadlines_missed)}
                sub="by the language model" />
        </div>
        <div className="callout">
          Ground truth is hand-authored from each driver's message and used{' '}
          <strong style={{ color: '#cbd5e1' }}>only for grading</strong> — no policy
          reads it. The model missed {quality.deadlines_missed} deadlines
          ({quality.deadlines_missed_keys?.join(', ')}), so every result below is
          achieved from imperfect extraction rather than perfect knowledge.
        </div>
      </div>

      {/* Controls */}
      <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap', alignItems: 'center' }}>
        <span style={{ fontSize: 11, color: '#475569' }}>Congestion</span>
        <div className="seg">
          {(['LOW', 'MEDIUM', 'HIGH'] as Scenario[]).map(s => (
            <button key={s} className={scenario === s ? 'on' : ''}
                    onClick={() => setScenario(s)}>
              {s} · {v2.scenarios[s].arrivals_per_hour}/hr
            </button>
          ))}
        </div>
        <span style={{ fontSize: 11, color: '#475569', marginLeft: 8 }}>Metric</span>
        <div className="seg" style={{ flexWrap: 'wrap' }}>
          {METRIC_OPTIONS.map(m => (
            <button key={m.key} className={metric === m.key ? 'on' : ''}
                    onClick={() => setMetric(m.key)}>
              {m.label}
            </button>
          ))}
        </div>
      </div>

      {/* Chart */}
      <div className="panel" style={{ padding: 18 }}>
        <div style={{ marginBottom: 14 }}>
          <div style={{ fontSize: 12.5, fontWeight: 600, color: '#94a3b8' }}>
            {meta.label} — {scenario} congestion
            <span style={{ color: '#475569', fontWeight: 400 }}>
              {' '}({sc.mean_arrivals_per_day} cars/day)
            </span>
          </div>
          <div style={{ fontSize: 11, color: '#334155', marginTop: 2 }}>
            {meta.higherBetter ? 'Higher is better' : 'Lower is better'} · bars show
            95% confidence intervals
          </div>
        </div>
        <ResponsiveContainer width="100%" height={270}>
          <BarChart data={chartData} margin={{ top: 16, right: 12, left: -16, bottom: 4 }}>
            <CartesianGrid strokeDasharray="3 3" stroke={GRID} vertical={false} />
            <XAxis dataKey="name" tick={{ ...AXIS_TICK, fontSize: 10 }}
                   axisLine={false} tickLine={false} interval={0} />
            <YAxis tick={AXIS_TICK} axisLine={false} tickLine={false} />
            <Tooltip contentStyle={TOOLTIP_STYLE} cursor={{ fill: '#0f172a' }}
                     formatter={(v: any) => meta.pct ? `${v}%` : `${v} min`} />
            <Bar dataKey="value" radius={[3, 3, 0, 0]} maxBarSize={74} name={meta.label}>
              {chartData.map(d => (
                <Cell key={d.key} fill={POLICY_COLOR[d.key] ?? '#64748b'} />
              ))}
              <ErrorBar dataKey="err" width={5} strokeWidth={1.2} stroke="#64748b" />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Paired deltas */}
      <div className="panel" style={{ padding: 18, overflowX: 'auto' }}>
        <div className="section-title">
          Agent vs each policy — paired difference per seed
        </div>
        <table className="data-table">
          <thead>
            <tr>
              <th>Compared with</th><th>Agent</th><th>Them</th>
              <th>Difference</th><th>95% CI</th><th>Seeds won</th><th>Verdict</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(comparisons).map(([key, c]: [string, any]) => {
              const d = c[metric];
              if (!d) return null;
              const scale = meta.pct ? 100 : 1;
              const unit = meta.pct ? 'pp' : 'min';
              const good = d.favours_agent;
              return (
                <tr key={key}>
                  <td>{sc.policies[key]?.label ?? key}</td>
                  <td style={{ fontFamily: 'ui-monospace, monospace', color: '#22d3ee' }}>
                    {(d.agent_mean * scale).toFixed(meta.pct ? 1 : 0)}{meta.pct ? '%' : 'm'}
                  </td>
                  <td style={{ fontFamily: 'ui-monospace, monospace', color: '#94a3b8' }}>
                    {(d.baseline_mean * scale).toFixed(meta.pct ? 1 : 0)}{meta.pct ? '%' : 'm'}
                  </td>
                  <td style={{ fontFamily: 'ui-monospace, monospace', fontWeight: 600,
                               color: good ? '#34d399' : '#fb7185' }}>
                    {d.paired_delta.mean > 0 ? '+' : ''}
                    {(d.paired_delta.mean * scale).toFixed(1)} {unit}
                  </td>
                  <td style={{ fontFamily: 'ui-monospace, monospace', fontSize: 11,
                               color: '#64748b' }}>
                    [{(d.paired_delta.lo * scale).toFixed(1)}, {(d.paired_delta.hi * scale).toFixed(1)}]
                  </td>
                  <td style={{ fontFamily: 'ui-monospace, monospace', color: '#94a3b8' }}>
                    {d.seeds_agent_better}/{d.seeds_total}
                  </td>
                  <td>
                    <span className={`badge ${d.significant_at_95
                      ? (good ? 'badge-green' : 'badge-red') : 'badge-gray'}`}>
                      {d.significant_at_95 ? (good ? 'significant' : 'worse') : 'inconclusive'}
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>

        <div className="callout" style={{ marginTop: 14 }}>
          <strong style={{ color: '#cbd5e1' }}>Why the ablations matter.</strong>{' '}
          “Agent (no deadlines)” is the identical scheduler with the language-derived
          deadline withheld. It falls back toward the conventional policies, which is
          the evidence that the improvement comes from information recovered from the
          driver's sentence — not from a better-tuned scoring function.
        </div>
      </div>

      {/* Adversarial */}
      {v2.adversarial && (
        <div className="panel" style={{ padding: 18, overflowX: 'auto' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
            <ShieldAlert size={14} color="#b45309" />
            <span className="section-title" style={{ marginBottom: 0 }}>
              What the validator is worth under gaming pressure
            </span>
          </div>
          <table className="data-table">
            <thead>
              <tr>
                <th>Drivers faking urgency</th><th>With validator</th>
                <th>Without</th><th>Difference</th><th>95% CI</th>
              </tr>
            </thead>
            <tbody>
              {v2.adversarial.sweep.map((row: any) => {
                const sig = (row.paired_delta.lo > 0) || (row.paired_delta.hi < 0);
                return (
                  <tr key={row.adversarial_fraction}>
                    <td>{(row.adversarial_fraction * 100).toFixed(0)}%</td>
                    <td style={{ fontFamily: 'ui-monospace, monospace', color: '#22d3ee' }}>
                      {(row.agent_on_time * 100).toFixed(1)}%
                    </td>
                    <td style={{ fontFamily: 'ui-monospace, monospace', color: '#94a3b8' }}>
                      {(row.no_validator_on_time * 100).toFixed(1)}%
                    </td>
                    <td style={{ fontFamily: 'ui-monospace, monospace',
                                 color: sig ? '#34d399' : '#64748b', fontWeight: 600 }}>
                      {row.paired_delta.mean > 0 ? '+' : ''}
                      {(row.paired_delta.mean * 100).toFixed(1)} pp
                    </td>
                    <td style={{ fontFamily: 'ui-monospace, monospace', fontSize: 11,
                                 color: '#64748b' }}>
                      [{(row.paired_delta.lo * 100).toFixed(1)}, {(row.paired_delta.hi * 100).toFixed(1)}]
                      {!sig && <span style={{ marginLeft: 6, color: '#475569' }}>n.s.</span>}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <div className="callout warn" style={{ marginTop: 14 }}>
            {v2.adversarial.note}
          </div>
        </div>
      )}

      {/* Historical */}
      <div className="panel" style={{ padding: 18 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
          <FlaskConical size={14} color="#475569" />
          <span className="section-title" style={{ marginBottom: 0 }}>
            Earlier results, kept for provenance
          </span>
        </div>
        <p style={{ fontSize: 12, color: '#64748b', lineHeight: 1.7, margin: 0 }}>
          An earlier benchmark (<code>phase5_results.json</code>) is retained in the
          repository but is <strong style={{ color: '#94a3b8' }}>superseded</strong>.
          It enforced the budget constraint only for the agent policies while letting
          the heuristics ignore it, its arrival streams silently diverged between
          policies despite a shared seed, and it never measured deadline adherence at
          all. Those numbers are not restated here because the comparison was not
          sound; they are kept only so the project's history can be audited.
        </p>
      </div>
    </div>
  );
}

function Stat({ label, value, sub }: { label: string; value: string; sub: string }) {
  return (
    <div style={{ background: '#0a1222', border: '1px solid #141f33',
                  borderRadius: 7, padding: '12px 14px' }}>
      <div style={{ fontSize: 9.5, fontWeight: 700, letterSpacing: '0.1em',
                    color: '#475569', textTransform: 'uppercase' }}>{label}</div>
      <div style={{ fontSize: 22, fontWeight: 300, color: '#f1f5f9', marginTop: 5 }}>
        {value}
      </div>
      <div style={{ fontSize: 10.5, color: '#334155', marginTop: 2 }}>{sub}</div>
    </div>
  );
}
