import { useEffect, useState } from 'react';
import { api } from '../api';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Cell,
} from 'recharts';
import { FlaskConical, AlertCircle } from 'lucide-react';

/* ─── Styling constants ─────────────────────────────────────────────────── */
const TOOLTIP_STYLE = {
  backgroundColor: '#020617', border: '1px solid #1e293b',
  borderRadius: '4px', fontSize: '12px', color: '#e2e8f0',
};
const AXIS_TICK   = { fill: '#475569', fontSize: 11 };
const GRID_STROKE = '#1e293b';

/* ─── Policy colours — includes ALL 6 policies in phase5_results.json ───── */
const POLICY_COLORS: Record<string, string> = {
  FIFO:           '#0e7490',   // cyan
  PRIORITY:       '#0d9488',   // teal
  SJF:            '#059669',   // emerald
  DQN:            '#b45309',   // amber — experimental RL baseline
  LLM_NEGOTIATOR: '#7c3aed',   // violet — the core research contribution
  TELEMETRY_ONLY: '#475569',   // slate — deterministic SOC fallback
};

/* ─── Metrics — exact field names from the comparison array in phase5 ───── */
const METRICS = [
  { key: 'avg_satisfaction', label: 'Satisfaction (0–1)', invert: false },
  { key: 'avg_wait',         label: 'Avg Wait (hr)',       invert: true  },
  { key: 'avg_crit_wait',    label: 'Critical Wait (hr)',  invert: true  },
  { key: 'avg_completed',    label: 'EVs Served',          invert: false },
  { key: 'avg_revenue',      label: 'Revenue ($)',         invert: false },
];

type Scenario = 'LOW' | 'MEDIUM' | 'HIGH';

/* ─── Phase5 shape (what /api/benchmarks returns) ──────────────────────── */
interface ComparisonRow {
  policy:           string;
  avg_wait:         number;
  avg_crit_wait:    number;
  avg_satisfaction: number;
  avg_revenue:      number;
  avg_completed:    number;
}

interface Phase5Data {
  experiment_config: { methodology: string; num_runs: number };
  scenarios: Record<Scenario, { arrival_rate: number; comparison: ComparisonRow[] }>;
}

/* ─── Component ─────────────────────────────────────────────────────────── */
export default function BenchmarksPage() {
  const [data,     setData]     = useState<any>(null);
  const [error,    setError]    = useState<string | null>(null);
  const [metric,   setMetric]   = useState('avg_satisfaction');
  const [scenario, setScenario] = useState<Scenario>('MEDIUM');

  useEffect(() => {
    api.getBenchmarks()
      .then(d => setData(d))
      .catch(() => setError('Could not load benchmark data from /api/benchmarks.'));
  }, []);

  /* ── Error / loading states ─────────────────────────────────────────── */
  if (error) return (
    <div style={{ padding: '24px', display: 'flex', gap: '10px', color: '#f87171', fontSize: '13px' }}>
      <AlertCircle size={16} style={{ flexShrink: 0, marginTop: 1 }} /> {error}
    </div>
  );

  if (!data) return (
    <div style={{ padding: '24px', color: '#334155', fontSize: '13px' }}>Loading benchmark data…</div>
  );

  /* ── Extract phase5 nested shape ────────────────────────────────────── */
  const phase5Raw: Phase5Data | null = data['phase5_results.json'] ?? null;

  if (!phase5Raw) return (
    <div style={{ padding: '24px', color: '#f87171', fontSize: '13px' }}>
      <AlertCircle size={14} style={{ verticalAlign: 'middle', marginRight: 6 }} />
      <strong>phase5_results.json</strong> not found in the benchmark response.
      Run <code>python experiment_comparison.py</code> to generate it.
    </div>
  );

  const scenarioData = phase5Raw.scenarios[scenario];
  // Sort rows by the currently selected metric so the chart reads naturally
  const rows: ComparisonRow[] = [...scenarioData.comparison].sort((a, b) => {
    const metaDef = METRICS.find(m => m.key === metric);
    const aVal = a[metric as keyof ComparisonRow] as number;
    const bVal = b[metric as keyof ComparisonRow] as number;
    return metaDef?.invert ? aVal - bVal : bVal - aVal; // asc for "lower is better"
  });

  const metaInfo = METRICS.find(m => m.key === metric)!;
  const numRuns  = phase5Raw.experiment_config?.num_runs ?? 30;

  const SCENARIO_RATES: Record<Scenario, string> = {
    LOW:    '2.5 EVs/hr',
    MEDIUM: '5.0 EVs/hr',
    HIGH:   '8.5 EVs/hr',
  };

  return (
    <div style={{ padding: '24px', display: 'flex', flexDirection: 'column', gap: '20px' }}>

      {/* ── Header ── */}
      <div>
        <h1 style={{ fontSize: '18px', fontWeight: 600, color: '#f1f5f9', margin: 0 }}>
          Phase 5 Policy Benchmarks
        </h1>
        <p style={{ fontSize: '12px', color: '#475569', marginTop: '3px' }}>
          Fixture-based LLM replay · {numRuns} runs × 3 congestion levels ·{' '}
          <span style={{ color: '#334155' }}>source: phase5_results.json</span>
        </p>
      </div>

      {/* ── Scenario selector (LOW / MEDIUM / HIGH) ── */}
      <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
        <span style={{ fontSize: '11px', color: '#475569', marginRight: 4 }}>Congestion level:</span>
        {(['LOW', 'MEDIUM', 'HIGH'] as Scenario[]).map(s => (
          <button
            key={s}
            id={`scenario-btn-${s.toLowerCase()}`}
            onClick={() => setScenario(s)}
            style={{
              padding: '5px 14px', borderRadius: '4px', fontSize: '12px',
              fontWeight: 600, cursor: 'pointer', border: '1px solid',
              background:   scenario === s ? '#0e2a38' : '#0f172a',
              color:        scenario === s ? '#22d3ee' : '#475569',
              borderColor:  scenario === s ? '#0891b2' : '#1e293b',
            }}
          >
            {s} <span style={{ fontWeight: 400, fontSize: '10px', opacity: 0.7 }}>
              ({SCENARIO_RATES[s]})
            </span>
          </button>
        ))}
      </div>

      {/* ── Policy legend ── */}
      <div style={{ display: 'flex', gap: '14px', flexWrap: 'wrap', alignItems: 'center' }}>
        {rows.map(r => (
          <div key={r.policy} style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px', color: '#94a3b8' }}>
            <div style={{
              width: '10px', height: '10px', borderRadius: '2px',
              background: POLICY_COLORS[r.policy] ?? '#64748b', flexShrink: 0,
            }} />
            <span>{r.policy}</span>
            {r.policy === 'DQN' && (
              <span style={{ fontSize: '9px', color: '#b45309', background: '#1c0a00', border: '1px solid #92400e', borderRadius: '3px', padding: '1px 5px' }}>
                Exp. RL
              </span>
            )}
            {r.policy === 'LLM_NEGOTIATOR' && (
              <span style={{ fontSize: '9px', color: '#a78bfa', background: '#140b2a', border: '1px solid #5b21b6', borderRadius: '3px', padding: '1px 5px' }}>
                Core finding
              </span>
            )}
          </div>
        ))}
      </div>

      {/* ── Metric selector ── */}
      <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
        {METRICS.map(m => (
          <button
            key={m.key}
            id={`metric-btn-${m.key}`}
            onClick={() => setMetric(m.key)}
            style={{
              padding: '6px 14px', borderRadius: '4px', fontSize: '12px',
              fontWeight: 500, cursor: 'pointer', border: '1px solid',
              background:   metric === m.key ? '#0e2a38' : '#0f172a',
              color:        metric === m.key ? '#22d3ee' : '#475569',
              borderColor:  metric === m.key ? '#0891b2' : '#1e293b',
            }}
          >
            {m.label}
          </button>
        ))}
      </div>

      {/* ── Chart + Raw table ── */}
      <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: '16px' }}>

        {/* Bar chart */}
        <div style={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: '6px', padding: '16px' }}>
          <div style={{ marginBottom: '16px' }}>
            <div style={{ fontSize: '12px', fontWeight: 600, color: '#94a3b8' }}>
              {metaInfo.label} — {scenario} congestion
            </div>
            <div style={{ fontSize: '11px', color: '#334155', marginTop: '2px' }}>
              {metaInfo.invert ? 'Lower values indicate better performance' : 'Higher values indicate better performance'}
            </div>
          </div>
          <ResponsiveContainer width="100%" height={260}>
            <BarChart
              data={rows.map(r => ({ name: r.policy, value: r[metric as keyof ComparisonRow] as number }))}
              margin={{ top: 18, right: 10, left: -20, bottom: 5 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke={GRID_STROKE} vertical={false} />
              <XAxis dataKey="name" tick={AXIS_TICK} axisLine={false} tickLine={false} />
              <YAxis tick={AXIS_TICK} axisLine={false} tickLine={false} />
              <Tooltip contentStyle={TOOLTIP_STYLE} cursor={{ fill: '#1e293b' }} />
              <Bar dataKey="value" radius={[3, 3, 0, 0]} maxBarSize={70} name={metaInfo.label}
                label={({ x, y, width, value }: any) => (
                  <text x={x + width / 2} y={y - 6} textAnchor="middle" fill="#475569" fontSize={10}>
                    {typeof value === 'number' ? value.toFixed(3) : value}
                  </text>
                )}
              >
                {rows.map(r => (
                  <Cell key={r.policy} fill={POLICY_COLORS[r.policy] ?? '#64748b'} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Raw values table */}
        <div style={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: '6px', padding: '16px', overflow: 'auto' }}>
          <div style={{ fontSize: '12px', fontWeight: 600, color: '#94a3b8', marginBottom: '12px' }}>
            All Metrics — {scenario}
          </div>
          <table className="data-table">
            <thead>
              <tr>
                <th>Policy</th>
                <th>Sat.</th>
                <th>Wait</th>
                <th>Crit.</th>
                <th>EVs</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(r => (
                <tr key={r.policy} style={r.policy === 'LLM_NEGOTIATOR' ? { background: '#140b2a' } : {}}>
                  <td>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <div style={{
                        width: '8px', height: '8px', borderRadius: '2px',
                        background: POLICY_COLORS[r.policy] ?? '#64748b', flexShrink: 0,
                      }} />
                      <span style={{ fontSize: '11px' }}>{r.policy}</span>
                    </div>
                  </td>
                  <td style={{ fontFamily: 'monospace', color: '#e2e8f0', fontSize: '11px' }}>
                    {r.avg_satisfaction.toFixed(3)}
                  </td>
                  <td style={{ fontFamily: 'monospace', color: '#94a3b8', fontSize: '11px' }}>
                    {r.avg_wait.toFixed(2)}h
                  </td>
                  <td style={{ fontFamily: 'monospace', color: '#94a3b8', fontSize: '11px' }}>
                    {r.avg_crit_wait.toFixed(2)}h
                  </td>
                  <td style={{ fontFamily: 'monospace', color: '#94a3b8', fontSize: '11px' }}>
                    {r.avg_completed.toFixed(1)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* ── Insight box — accurate phase5 conclusions ── */}
      <div style={{ background: '#0a0f1e', border: '1px solid #1e293b', borderRadius: '6px', padding: '16px', display: 'flex', gap: '14px' }}>
        <FlaskConical size={18} color="#475569" style={{ flexShrink: 0, marginTop: 1 }} />
        <div>
          <div style={{ fontSize: '12px', fontWeight: 600, color: '#94a3b8', marginBottom: '8px' }}>
            Phase 5 Key Findings
          </div>
          <p style={{ fontSize: '12px', color: '#64748b', lineHeight: 1.7, margin: '0 0 8px 0' }}>
            <strong style={{ color: '#a78bfa' }}>LLM_NEGOTIATOR</strong> consistently outperforms{' '}
            <strong style={{ color: '#94a3b8' }}>TELEMETRY_ONLY</strong> on driver satisfaction
            (+11% LOW · +34% MEDIUM · +62% HIGH congestion), using natural-language deadline and
            reason context to prioritise more accurately than SOC alone.
          </p>
          <p style={{ fontSize: '12px', color: '#64748b', lineHeight: 1.7, margin: '0 0 8px 0' }}>
            <strong style={{ color: '#22d3ee' }}>SJF</strong> achieves the highest throughput but
            at a steep fairness cost: critical-EV wait times are{' '}
            <strong style={{ color: '#f87171' }}>76–149% longer than LLM_NEGOTIATOR</strong> under
            MEDIUM and HIGH congestion — it starves emergency and low-battery EVs in favour of
            shorter jobs. Use SJF only for throughput-maximising scenarios where all EVs are
            roughly equivalent.
          </p>
          <p style={{ fontSize: '12px', color: '#475569', lineHeight: 1.7, margin: 0 }}>
            <strong style={{ color: '#b45309' }}>DQN</strong> is an experimental RL baseline only.
            It exhibited reward-hoarding behaviour in the discrete-time formulation and produced
            the lowest satisfaction scores (0.09–0.13) across all scenarios.
          </p>
        </div>
      </div>
    </div>
  );
}
