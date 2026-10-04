import { useEffect, useMemo, useState, useCallback } from 'react';
import { api } from '../api';
import type { CompareResponse, ScenarioCatalogue, TimelineRow } from '../api';
import {
  Play, RefreshCw, AlertCircle, Clock, Gauge, ShieldCheck,
  ShieldAlert, Zap, ChevronRight, Dices,
} from 'lucide-react';
import ScheduleGantt, { GanttLegend } from '../components/ScheduleGantt';

/* Demand levels chosen so the station is actually contended. With plenty of
   spare capacity every policy serves everyone immediately and scheduling is
   irrelevant — which is true, and visible here if you pick "Quiet". */
const PRESETS = [
  { key: 'quiet',  label: 'Quiet',      rate: 2.0, horizon: 300 },
  { key: 'steady', label: 'Steady',     rate: 4.0, horizon: 360 },
  { key: 'busy',   label: 'Busy',       rate: 6.5, horizon: 240 },
  { key: 'peak',   label: 'Overloaded', rate: 8.0, horizon: 300 },
];

const STATIONS = [
  { key: 'small',  label: '3 ports',  kw: [7, 50, 150] },
  { key: 'fast',   label: '4 ports · all DC', kw: [50, 50, 150, 150] },
  { key: 'mixed',  label: '5 ports · mixed',  kw: [7, 50, 50, 150, 150] },
];

const BASELINES = ['sjf', 'fifo', 'soc', 'agent_no_deadline'] as const;

export default function SchedulerPage() {
  const [cat, setCat] = useState<ScenarioCatalogue | null>(null);
  const [data, setData] = useState<CompareResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [preset, setPreset] = useState('busy');
  const [station, setStation] = useState('small');
  const [seed, setSeed] = useState(7);
  const [repeats, setRepeats] = useState(10);
  const [baseline, setBaseline] = useState<string>('sjf');
  const [mode, setMode] = useState<'requests' | 'station'>('requests');
  const [selEv, setSelEv] = useState<number | null>(null);

  useEffect(() => {
    api.getScenarios().then(setCat).catch(() => {/* catalogue is optional */});
  }, []);

  const run = useCallback(async () => {
    const p = PRESETS.find(x => x.key === preset)!;
    const st = STATIONS.find(x => x.key === station)!;
    setBusy(true); setError(null);
    try {
      const res = await api.compare({
        seed,
        arrivals_per_hour: p.rate,
        horizon_min: p.horizon,
        station: st.kw,
        repeats,
      });
      setData(res);
      setSelEv(null);
    } catch (e: any) {
      setError(
        e?.response?.data?.detail ??
        e?.message ??
        'Could not reach the scheduling API.'
      );
    } finally {
      setBusy(false);
    }
  }, [preset, station, seed, repeats]);

  useEffect(() => { run(); }, [run]);

  const agent = data?.policies['agent'];
  const base = data?.policies[baseline];
  const delta = data?.agent_vs?.[baseline];

  const selected: TimelineRow | undefined = useMemo(() => {
    if (selEv === null || !agent) return undefined;
    return agent.timeline.find(r => r.ev_id === selEv);
  }, [selEv, agent]);

  const selectedBase: TimelineRow | undefined = useMemo(() => {
    if (selEv === null || !base) return undefined;
    return base.timeline.find(r => r.ev_id === selEv);
  }, [selEv, base]);

  const selInput = useMemo(
    () => data?.inputs.find(i => i.ev_id === selEv),
    [selEv, data]
  );

  const selScenario = useMemo(
    () => cat?.scenarios.find(s => s.key === selInput?.scenario_key),
    [cat, selInput]
  );

  /* Draw the chart out to the end of the longest session actually scheduled,
     so sessions running past the arrival window are fully visible instead of
     piling up as slivers against the right edge. */
  const ganttHorizon = useMemo(() => {
    if (!data) return 240;
    const ends: number[] = [];
    for (const key of ['agent', baseline]) {
      const p = data.policies[key];
      if (!p) continue;
      for (const r of p.timeline) {
        if (r.end_min !== null) ends.push(r.end_min);
        if (r.true_deadline_abs !== null) ends.push(r.true_deadline_abs);
      }
    }
    const maxEnd = ends.length ? Math.max(...ends) : data.config.horizon_min;
    return Math.max(data.config.horizon_min, Math.ceil(maxEnd / 30) * 30);
  }, [data, baseline]);

  return (
    <div style={{ padding: 24, display: 'flex', flexDirection: 'column', gap: 18 }}>

      {/* ── Title ───────────────────────────────────────────────── */}
      <div>
        <h1 style={{ fontSize: 19, fontWeight: 600, color: '#f1f5f9', margin: 0,
                     letterSpacing: '-0.01em' }}>
          Live Scheduling Comparison
        </h1>
        <p style={{ fontSize: 12.5, color: '#64748b', marginTop: 5, maxWidth: 780,
                    lineHeight: 1.6 }}>
          One identical set of drivers is scheduled by the agent and by conventional
          policies. Drivers state their deadline in plain language — so only the
          agent can see it. Everything below is computed live by the same engine
          that produces the benchmark.
        </p>
      </div>

      {/* ── INPUT ───────────────────────────────────────────────── */}
      <div className="panel" style={{ padding: 18 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14 }}>
          <span style={{ fontSize: 10, fontWeight: 700, letterSpacing: '0.12em',
                         color: '#22d3ee', textTransform: 'uppercase' }}>Input</span>
          <span style={{ height: 1, flex: 1, background: '#1e293b' }} />
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(190px, 1fr))',
                      gap: 18, alignItems: 'end' }}>
          <div>
            <div className="field-label"><span>Demand</span></div>
            <div className="seg" style={{ flexWrap: 'wrap' }}>
              {PRESETS.map(p => (
                <button key={p.key} className={preset === p.key ? 'on' : ''}
                        disabled={busy} onClick={() => setPreset(p.key)}>
                  {p.label}
                </button>
              ))}
            </div>
          </div>

          <div>
            <div className="field-label"><span>Station</span></div>
            <div className="seg" style={{ flexWrap: 'wrap' }}>
              {STATIONS.map(s => (
                <button key={s.key} className={station === s.key ? 'on' : ''}
                        disabled={busy} onClick={() => setStation(s.key)}>
                  {s.label}
                </button>
              ))}
            </div>
          </div>

          <div>
            <div className="field-label">
              <span>Arrival pattern</span><b>seed {seed}</b>
            </div>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <input className="range" type="range" min={1} max={60} value={seed}
                     disabled={busy}
                     onChange={e => setSeed(Number(e.target.value))} />
              <button className="scenario-btn" disabled={busy}
                      title="Random arrival pattern"
                      onClick={() => setSeed(1 + Math.floor(Math.random() * 60))}>
                <Dices size={11} style={{ verticalAlign: '-1px' }} />
              </button>
            </div>
          </div>

          <div>
            <div className="field-label">
              <span>Average over</span>
              <b>{repeats === 1 ? '1 pattern' : `${repeats} patterns`}</b>
            </div>
            <input className="range" type="range" min={1} max={15} value={repeats}
                   disabled={busy}
                   onChange={e => setRepeats(Number(e.target.value))} />
          </div>

          <div style={{ display: 'flex', gap: 8 }}>
            <button className="btn-primary" onClick={run} disabled={busy}
                    style={{ display: 'inline-flex', alignItems: 'center', gap: 7 }}>
              {busy ? <RefreshCw size={13} className="spin" /> : <Play size={13} />}
              {busy ? 'SCHEDULING…' : 'RUN COMPARISON'}
            </button>
          </div>
        </div>

        {error && (
          <div style={{ marginTop: 14, background: '#1a0a0a', border: '1px solid #7f1d1d',
                        borderRadius: 6, padding: '10px 14px', color: '#f87171',
                        fontSize: 12.5, display: 'flex', gap: 9, alignItems: 'center' }}>
            <AlertCircle size={15} /> {error}
          </div>
        )}

        {/* The actual requests — this IS the input, shown verbatim */}
        {data && (
          <div style={{ marginTop: 16 }}>
            <div className="field-label">
              <span>{data.inputs.length} driver requests</span>
              <b>
                {data.config.station_kw.length} ports · {data.config.horizon_min} min
                {agent && ` · ${(agent.metrics.port_utilisation * 100).toFixed(0)}% port load`}
              </b>
            </div>
            <div style={{ maxHeight: 186, overflowY: 'auto', border: '1px solid #141f33',
                          borderRadius: 6, padding: 4 }}>
              {data.inputs.map(inp => {
                const row = agent?.timeline.find(r => r.ev_id === inp.ev_id);
                return (
                  <div key={inp.ev_id}
                       className={`req-row ${selEv === inp.ev_id ? 'on' : ''}`}
                       onClick={() => setSelEv(selEv === inp.ev_id ? null : inp.ev_id)}>
                    <span className="rq-id">
                      EV-{String(inp.ev_id).padStart(2, '0')}
                      <span style={{ color: '#334155' }}> ·{Math.round(inp.arrival_min)}m</span>
                    </span>
                    <span className="rq-msg">“{inp.message}”</span>
                    <span style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                      {inp.is_unverified_claim && (
                        <span className="badge badge-amber" title="Unverifiable urgency claim">
                          claim
                        </span>
                      )}
                      <span style={{ fontSize: 10.5, color: '#475569',
                                     fontFamily: 'ui-monospace, monospace' }}>
                        {inp.soc.toFixed(0)}% · {inp.max_rate_kw}kW
                      </span>
                      {inp.true_deadline_min !== null ? (
                        <span className="badge badge-gray"
                              style={{ color: '#fbbf24', borderColor: '#78350f' }}>
                          {inp.true_deadline_min}m
                        </span>
                      ) : (
                        <span className="badge badge-gray">flexible</span>
                      )}
                      {row && row.met_deadline !== null && (
                        <span className={`badge ${row.met_deadline ? 'badge-green' : 'badge-red'}`}>
                          {row.met_deadline ? 'met' : 'miss'}
                        </span>
                      )}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>

      {/* ── OUTPUT ──────────────────────────────────────────────── */}
      {agent && base && (
        <>
          <div className="panel" style={{ padding: 18 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12,
                          marginBottom: 15, flexWrap: 'wrap' }}>
              <span style={{ fontSize: 10, fontWeight: 700, letterSpacing: '0.12em',
                             color: '#22d3ee', textTransform: 'uppercase' }}>Output</span>
              <span style={{ fontSize: 11, color: '#475569' }}>compare against</span>
              <div className="seg">
                {BASELINES.map(b => (
                  <button key={b} className={baseline === b ? 'on' : ''}
                          onClick={() => setBaseline(b)}>
                    {data!.policies[b]?.label ?? b}
                  </button>
                ))}
              </div>
              <span style={{ height: 1, flex: 1, background: '#1e293b', minWidth: 20 }} />
              <span style={{ fontSize: 10.5, color: '#475569' }}>
                {data!.config.repeats > 1
                  ? `averaged over ${data!.config.repeats} arrival patterns`
                  : 'single arrival pattern'}
              </span>
            </div>

            {data!.config.repeats === 1 && (
              <div className="callout warn" style={{ marginBottom: 14 }}>
                A single sample of a few dozen cars is noisy — an ablation can beat
                the full agent by chance. Raise “average over” for a comparison you
                can rely on, or see the Benchmarks page for the 30-seed result.
              </div>
            )}

            {delta && (
              <div style={{ display: 'grid',
                            gridTemplateColumns: 'repeat(auto-fit, minmax(178px, 1fr))',
                            gap: 12 }}>
                <DeltaCard
                  label="Deadlines met"
                  deltaText={`${delta.on_time_rate_pp >= 0 ? '+' : ''}${delta.on_time_rate_pp.toFixed(1)} pp`}
                  good={delta.on_time_rate_pp > 0}
                  flat={Math.abs(delta.on_time_rate_pp) < 0.05}
                  agentVal={`${(agent.metrics.on_time_rate * 100).toFixed(1)}%`}
                  baseVal={`${(base.metrics.on_time_rate * 100).toFixed(1)}%`}
                  baseLabel={base.label}
                  icon={<Clock size={13} />}
                />
                <DeltaCard
                  label="Urgent deadlines met"
                  deltaText={`${delta.critical_on_time_pp >= 0 ? '+' : ''}${delta.critical_on_time_pp.toFixed(1)} pp`}
                  good={delta.critical_on_time_pp > 0}
                  flat={Math.abs(delta.critical_on_time_pp) < 0.05}
                  agentVal={`${(agent.metrics.critical_on_time_rate * 100).toFixed(1)}%`}
                  baseVal={`${(base.metrics.critical_on_time_rate * 100).toFixed(1)}%`}
                  baseLabel={base.label}
                  icon={<ShieldCheck size={13} />}
                />
                <DeltaCard
                  label="Average wait"
                  deltaText={`${delta.avg_wait_min >= 0 ? '+' : ''}${delta.avg_wait_min.toFixed(0)} min`}
                  good={delta.avg_wait_min < 0}
                  flat={Math.abs(delta.avg_wait_min) < 0.5}
                  agentVal={`${agent.metrics.avg_wait_min.toFixed(0)}m`}
                  baseVal={`${base.metrics.avg_wait_min.toFixed(0)}m`}
                  baseLabel={base.label}
                  icon={<Gauge size={13} />}
                />
                <DeltaCard
                  label="Worst-case wait (p95)"
                  deltaText={`${delta.p95_wait_min >= 0 ? '+' : ''}${delta.p95_wait_min.toFixed(0)} min`}
                  good={delta.p95_wait_min < 0}
                  flat={Math.abs(delta.p95_wait_min) < 0.5}
                  agentVal={`${agent.metrics.p95_wait_min.toFixed(0)}m`}
                  baseVal={`${base.metrics.p95_wait_min.toFixed(0)}m`}
                  baseLabel={base.label}
                  icon={<Zap size={13} />}
                />
              </div>
            )}

            {agent.metrics.deadline_evs === 0 && (
              <div className="callout warn" style={{ marginTop: 14 }}>
                No driver in this sample stated a deadline, so there is nothing to
                compare on deadline adherence. Try a different arrival pattern.
              </div>
            )}
          </div>

          {/* ── SCHEDULE ──────────────────────────────────────── */}
          <div className="panel" style={{ padding: 18 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12,
                          marginBottom: 14, flexWrap: 'wrap' }}>
              <span style={{ fontSize: 10, fontWeight: 700, letterSpacing: '0.12em',
                             color: '#22d3ee', textTransform: 'uppercase' }}>
                The schedule
              </span>
              <div className="seg">
                <button className={mode === 'requests' ? 'on' : ''}
                        onClick={() => setMode('requests')}>Per request</button>
                <button className={mode === 'station' ? 'on' : ''}
                        onClick={() => setMode('station')}>Per port</button>
              </div>
              <span style={{ height: 1, flex: 1, background: '#1e293b', minWidth: 20 }} />
              <span style={{ fontSize: 11, color: '#475569' }}>
                click any bar for the decision behind it
              </span>
            </div>

            <GanttBlock
              title="EV NEXUS Agent"
              accent="#22d3ee"
              metrics={`${(agent.metrics.on_time_rate * 100).toFixed(1)}% on time · ${agent.metrics.avg_wait_min.toFixed(0)}m avg wait`}
              data={data!} policy="agent" mode={mode} horizon={ganttHorizon}
              selEv={selEv} setSelEv={setSelEv}
            />

            <div style={{ height: 14 }} />

            <GanttBlock
              title={base.label}
              accent="#64748b"
              metrics={`${(base.metrics.on_time_rate * 100).toFixed(1)}% on time · ${base.metrics.avg_wait_min.toFixed(0)}m avg wait`}
              data={data!} policy={baseline} mode={mode} horizon={ganttHorizon}
              selEv={selEv} setSelEv={setSelEv}
            />

            <div style={{ marginTop: 16, paddingTop: 14, borderTop: '1px solid #141f33' }}>
              <GanttLegend />
            </div>
          </div>

          {/* ── DECISION DETAIL ───────────────────────────────── */}
          {selected && selInput && (
            <div className="panel fade-in" style={{ padding: 18 }}>
              <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: '0.12em',
                            color: '#22d3ee', textTransform: 'uppercase',
                            marginBottom: 13 }}>
                Decision · EV-{String(selInput.ev_id).padStart(2, '0')}
              </div>

              <div style={{ fontSize: 14.5, color: '#e2e8f0', fontStyle: 'italic',
                            marginBottom: 16, lineHeight: 1.5 }}>
                “{selInput.message}”
              </div>

              <div style={{ display: 'grid',
                            gridTemplateColumns: 'repeat(auto-fit, minmax(230px, 1fr))',
                            gap: 14 }}>
                {/* Step 1 — what language gave us */}
                <DetailCard title="1 · Extracted from language">
                  {selScenario?.extracted ? (
                    <>
                      <KV k="Urgency claimed" v={selScenario.extracted.urgency_level} />
                      <KV k="Deadline found"
                          v={selScenario.extracted.deadline_minutes !== null
                            ? `${selScenario.extracted.deadline_minutes} min`
                            : 'none stated'} />
                      <KV k="Reason" v={selScenario.extracted.reason_category} />
                      <KV k="Confidence"
                          v={`${(selScenario.extracted.confidence * 100).toFixed(0)}%`} />
                    </>
                  ) : <KV k="Extraction" v="unavailable" />}
                </DetailCard>

                {/* Step 2 — validation against telemetry */}
                <DetailCard title="2 · Checked against telemetry">
                  <KV k="Actual charge" v={`${selInput.soc.toFixed(0)}%`} />
                  <KV k="Accepts" v={`${selInput.max_rate_kw} kW`} />
                  <KV k="Urgency used" v={selected.believed_urgency}
                      highlight={selected.contradiction_flagged ? '#fb923c' : undefined} />
                  {selected.contradiction_flagged ? (
                    <div style={{ display: 'flex', gap: 7, marginTop: 8, fontSize: 11.5,
                                  color: '#fb923c', lineHeight: 1.5 }}>
                      <ShieldAlert size={14} style={{ flexShrink: 0, marginTop: 1 }} />
                      Claim contradicted by a {selInput.soc.toFixed(0)}% battery —
                      downgraded, so it cannot jump the queue.
                    </div>
                  ) : (
                    <div style={{ display: 'flex', gap: 7, marginTop: 8, fontSize: 11.5,
                                  color: '#34d399', lineHeight: 1.5 }}>
                      <ShieldCheck size={14} style={{ flexShrink: 0, marginTop: 1 }} />
                      Claim consistent with telemetry.
                    </div>
                  )}
                </DetailCard>

                {/* Step 3 — the outcome, both policies */}
                <DetailCard title="3 · Scheduled result">
                  <KV k="Agent"
                      v={selected.start_min !== null
                        ? `port ${(selected.port_id ?? 0) + 1} at ${Math.round(selected.start_min)}m`
                        : 'not served'} />
                  <KV k="Agent waited" v={`${Math.round(selected.wait_min)} min`} />
                  <KV k={base.label}
                      v={selectedBase && selectedBase.start_min !== null
                        ? `port ${(selectedBase.port_id ?? 0) + 1} at ${Math.round(selectedBase.start_min)}m`
                        : 'not served'} />
                  <KV k={`${base.label} waited`}
                      v={selectedBase ? `${Math.round(selectedBase.wait_min)} min` : '—'} />

                  {selInput.true_deadline_min !== null && (
                    <div style={{ marginTop: 10, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                      <span className={`badge ${selected.met_deadline ? 'badge-green' : 'badge-red'}`}>
                        agent {selected.met_deadline ? 'met' : 'missed'}
                      </span>
                      {selectedBase && (
                        <span className={`badge ${selectedBase.met_deadline ? 'badge-green' : 'badge-red'}`}>
                          {base.label} {selectedBase.met_deadline ? 'met' : 'missed'}
                        </span>
                      )}
                    </div>
                  )}
                </DetailCard>
              </div>

              {selInput.true_deadline_min !== null && (
                <div className="callout" style={{ marginTop: 14 }}>
                  <strong style={{ color: '#cbd5e1' }}>Ground truth:</strong> this driver
                  really needed to leave in {selInput.true_deadline_min} minutes.
                  That figure appears nowhere in the telemetry — it exists only in the
                  sentence above, which is why FIFO, Shortest-Job-First and
                  Lowest-SOC-First cannot act on it. It is used here only to mark the
                  answer; no scheduler reads it.
                </div>
              )}
            </div>
          )}

          {/* ── ALL POLICIES ──────────────────────────────────── */}
          <div className="panel" style={{ padding: 18, overflowX: 'auto' }}>
            <div className="section-title">Every policy on this same input</div>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Policy</th><th>Deadlines met</th><th>Urgent met</th>
                  <th>Served</th><th>Avg wait</th><th>p95 wait</th><th>Port time</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(data!.policies)
                  .sort((a, b) => b[1].metrics.on_time_rate - a[1].metrics.on_time_rate)
                  .map(([key, p]) => (
                    <tr key={key}
                        style={key === 'agent'
                          ? { background: '#0b1b2b' } : undefined}>
                      <td>
                        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 7 }}>
                          {key === 'agent' && <ChevronRight size={12} color="#22d3ee" />}
                          <span style={{ color: key === 'agent' ? '#22d3ee' : '#cbd5e1',
                                         fontWeight: key === 'agent' ? 600 : 400 }}>
                            {p.label}
                          </span>
                          {p.family === 'ablation' && (
                            <span className="badge badge-gray">ablation</span>
                          )}
                        </span>
                      </td>
                      <Num v={`${(p.metrics.on_time_rate * 100).toFixed(1)}%`} hi={key === 'agent'} />
                      <Num v={`${(p.metrics.critical_on_time_rate * 100).toFixed(1)}%`} hi={key === 'agent'} />
                      <Num v={`${p.metrics.served}/${p.metrics.arrived}`} />
                      <Num v={`${p.metrics.avg_wait_min.toFixed(0)}m`} />
                      <Num v={`${p.metrics.p95_wait_min.toFixed(0)}m`} />
                      <Num v={`${(p.metrics.port_utilisation * 100).toFixed(0)}%`} />
                    </tr>
                  ))}
              </tbody>
            </table>
            <div className="callout" style={{ marginTop: 14 }}>
              <strong style={{ color: '#cbd5e1' }}>Ablations are the control.</strong>{' '}
              “Agent (no deadlines)” is the full agent with the language-derived
              deadline removed. It falls back toward the conventional policies — which
              is the evidence that the improvement comes from reading the driver's
              language, not from tuning the scheduler.
            </div>
          </div>
        </>
      )}
    </div>
  );
}

/* ─── small presentational helpers ──────────────────────────────── */

function GanttBlock({ title, accent, metrics, data, policy, mode, horizon, selEv, setSelEv }: {
  title: string; accent: string; metrics: string;
  data: CompareResponse; policy: string;
  mode: 'requests' | 'station'; horizon: number;
  selEv: number | null; setSelEv: (n: number | null) => void;
}) {
  const p = data.policies[policy];
  if (!p) return null;
  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, marginBottom: 6,
                    flexWrap: 'wrap' }}>
        <span style={{ width: 3, height: 13, background: accent, borderRadius: 2,
                       display: 'inline-block' }} />
        <span style={{ fontSize: 12.5, fontWeight: 600, color: accent }}>{title}</span>
        <span style={{ fontSize: 11, color: '#475569',
                       fontVariantNumeric: 'tabular-nums' }}>{metrics}</span>
      </div>
      <ScheduleGantt
        timeline={p.timeline}
        inputs={data.inputs}
        numPorts={data.config.num_ports}
        stationKw={data.config.station_kw}
        horizonMin={horizon}
        mode={mode}
        selectedEv={selEv}
        onSelectEv={setSelEv}
        compact={mode === 'requests' && data.inputs.length > 18}
      />
    </div>
  );
}

function DeltaCard({ label, deltaText, good, flat, agentVal, baseVal, baseLabel, icon }: {
  label: string; deltaText: string; good: boolean; flat: boolean;
  agentVal: string; baseVal: string; baseLabel: string; icon: React.ReactNode;
}) {
  return (
    <div className="delta-card">
      <div className="dc-label" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        <span style={{ color: '#475569' }}>{icon}</span>{label}
      </div>
      <div className={`dc-delta ${flat ? 'flat' : good ? 'good' : 'bad'}`}>{deltaText}</div>
      <div className="dc-pair">
        <span className="dc-agent">{agentVal}</span>
        <span style={{ color: '#334155' }}>vs</span>
        <span className="dc-base">{baseVal}</span>
      </div>
      <div style={{ fontSize: 10, color: '#334155' }}>agent vs {baseLabel}</div>
    </div>
  );
}

function DetailCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ background: '#0a1222', border: '1px solid #141f33',
                  borderRadius: 7, padding: 14 }}>
      <div style={{ fontSize: 9.5, fontWeight: 700, letterSpacing: '0.1em',
                    color: '#475569', textTransform: 'uppercase', marginBottom: 11 }}>
        {title}
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>{children}</div>
    </div>
  );
}

function KV({ k, v, highlight }: { k: string; v: string; highlight?: string }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10,
                  fontSize: 12, alignItems: 'baseline' }}>
      <span style={{ color: '#475569' }}>{k}</span>
      <span style={{ color: highlight ?? '#cbd5e1', fontWeight: highlight ? 600 : 400,
                     textAlign: 'right' }}>{v}</span>
    </div>
  );
}

function Num({ v, hi }: { v: string; hi?: boolean }) {
  return (
    <td style={{ fontFamily: 'ui-monospace, monospace', fontSize: 12,
                 color: hi ? '#22d3ee' : '#94a3b8',
                 fontWeight: hi ? 600 : 400 }}>{v}</td>
  );
}
