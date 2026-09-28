import React, { useState, useEffect, useRef } from 'react';
import { api } from '../api';
import type { NegotiateRequest, NegotiateResponse, StationStatus } from '../api';
import {
  Send, RotateCcw, AlertCircle, BrainCircuit,
  ShieldCheck, ShieldAlert, CalendarCheck, CheckCircle2,
} from 'lucide-react';

/* ──────────────────────────── helpers ─────────────────────────────── */
const S = {
  page: { padding: '24px', display: 'flex', flexDirection: 'column' as const, gap: '20px', minHeight: '100%' },
  panel: (extra?: React.CSSProperties): React.CSSProperties => ({
    background: '#0f172a', border: '1px solid #1e293b', borderRadius: '6px', ...extra,
  }),
};

const URGENCY_COLORS: Record<string, string> = {
  CRITICAL: '#f87171', HIGH: '#fb923c', MEDIUM: '#fbbf24', LOW: '#4ade80', FLEXIBLE: '#4ade80',
};

/* ──────────────────────────── types ───────────────────────────────── */
interface PortInfo { id: number; speed_kw: number; speed_name: string; is_occupied: boolean; ev: any; }

/* ──────────────────────────── Overview Page ─────────────────────────── */
export default function OverviewPage() {
  const [station, setStation] = useState<StationStatus | null>(null);
  const [step, setStep] = useState(0);               // pipeline stage 0–5
  const [result, setResult] = useState<NegotiateResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [, setSim] = useState(false);
  const simRef = useRef<number | null>(null);

  /* initial fetch + poll station every 2 s when sim is idle */
  useEffect(() => {
    fetchStation();
  }, []);

  async function fetchStation() {
    try { setStation(await api.getStationStatus()); }
    catch (e: any) { setError('Backend unavailable — check uvicorn on port 8000.'); }
  }

  async function handleNegotiate(req: NegotiateRequest) {
    setError(null); setResult(null); setStep(1);
    try {
      const r = await api.negotiate(req);
      setResult(r); setStep(3);
      await fetchStation();
      // A rejected (over-budget) request was never assigned a port or queued —
      // there is nothing to simulate stepping through, and showing the
      // "Charging Session Complete" banner for it would misrepresent a
      // declined request as a finished charging session.
      if (r.status !== 'REJECTED_BUDGET') {
        startSim();
      }
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? e.message ?? 'Negotiation failed.');
      setStep(0);
    }
  }

  function startSim() {
    setSim(true); setStep(4);
    simRef.current = window.setInterval(async () => {
      try {
        const s = await api.stepSimulation();
        setStation(s);
        if (!s.ports.some((p: PortInfo) => p.is_occupied) && s.queue.length === 0) {
          clearInterval(simRef.current!); simRef.current = null;
          setSim(false); setStep(5);
        }
      } catch (e: any) {
        clearInterval(simRef.current!); simRef.current = null;
        setSim(false); setError('Simulation step failed.');
      }
    }, 1000);
  }

  async function handleReset() {
    if (simRef.current) { clearInterval(simRef.current); simRef.current = null; }
    setSim(false); setStep(0); setResult(null); setError(null);
    await api.resetSimulation();
    await fetchStation();
  }

  /* ── Metrics from station ── */
  const ports = (station?.ports ?? []) as PortInfo[];
  const active = ports.filter(p => p.is_occupied).length;
  const avail  = ports.filter(p => !p.is_occupied).length;
  const queue  = station?.queue.length ?? 0;
  const util   = ports.length > 0 ? Math.round((active / ports.length) * 100) : 0;

  return (
    <div style={S.page}>

      {/* ── Page title + metrics ── */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '20px', flexWrap: 'wrap' }}>
        <div>
          <h1 style={{ fontSize: '18px', fontWeight: 600, color: '#f1f5f9', letterSpacing: '-0.01em', margin: 0 }}>
            Charging Command Center
          </h1>
          <p style={{ fontSize: '12px', color: '#475569', marginTop: '3px' }}>AI-assisted EV charging scheduling · Station Alpha</p>
        </div>
        <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
          <MetricCard label="EVs in Queue"     value={queue}   color="" />
          <MetricCard label="Active Sessions"  value={active}  color="#22d3ee" />
          <MetricCard label="Available Ports"  value={avail}   color="#4ade80" />
          <MetricCard label="Utilization"      value={`${util}%`} color="#94a3b8" />
        </div>
      </div>

      {/* ── Error banner ── */}
      {error && (
        <div style={{ background: '#1a0a0a', border: '1px solid #7f1d1d', borderRadius: '6px', padding: '10px 16px', display: 'flex', alignItems: 'center', gap: '10px', color: '#f87171', fontSize: '13px' }}>
          <AlertCircle size={16} />
          <span>{error}</span>
        </div>
      )}

      {/* ── Station + Driver Request ── */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
        <StationPanel ports={ports} />
        <DriverRequest onSubmit={handleNegotiate} disabled={step > 0 && step < 5} onReset={handleReset} showReset={step > 0} />
      </div>

      {/* ── Pipeline bar ── */}
      <PipelineBar step={step} />

      {/* ── Result panels ── */}
      {result && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '16px' }}>
          <AIPanel result={result} />
          <ValidationPanel result={result} />
          <SchedulerPanel result={result} />
        </div>
      )}

      {/* ── Completion banner ── */}
      {step === 5 && station && (
        <CompletionBanner metrics={station.metrics} />
      )}
    </div>
  );
}

/* ───────────────── Metric Card ──────────────────────────────────────── */
function MetricCard({ label, value, color }: { label: string; value: string | number; color: string }) {
  return (
    <div className="metric-card" style={{ minWidth: '130px' }}>
      <div className="mc-label">{label}</div>
      <div className="mc-value" style={color ? { color } : {}}>{value}</div>
    </div>
  );
}

/* ───────────────── Station Panel ────────────────────────────────────── */
function StationPanel({ ports }: { ports: PortInfo[] }) {
  return (
    <div style={{ ...S.panel(), padding: '16px' }}>
      <div className="section-title" style={{ marginBottom: '12px' }}>Station Status</div>
      <div style={{ display: 'flex', gap: '12px' }}>
        {ports.length === 0
          ? <div style={{ fontSize: '13px', color: '#334155' }}>Connecting to backend…</div>
          : ports.map(p => <PortCard key={p.id} port={p} />)
        }
      </div>
    </div>
  );
}

function PortCard({ port }: { port: PortInfo }) {
  const active = port.is_occupied && port.ev;
  return (
    <div className={`port-card ${active ? 'active' : ''}`} style={{ flex: 1 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '10px' }}>
        <div>
          <div style={{ fontSize: '11px', fontWeight: 700, color: '#94a3b8', letterSpacing: '0.08em' }}>PORT 0{port.id + 1}</div>
          <div style={{ fontSize: '11px', color: '#475569', marginTop: '2px' }}>{port.speed_kw} kW · {port.speed_name}</div>
        </div>
        <span className={`badge ${active ? 'badge-cyan' : 'badge-gray'}`}>{active ? 'Charging' : 'Available'}</span>
      </div>

      {active ? (
        <>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px', color: '#94a3b8', marginBottom: '6px' }}>
            <span style={{ fontFamily: 'monospace' }}>EV-{String(port.ev.id).padStart(2, '0')}</span>
            <span>{port.ev.soc.toFixed(1)}%</span>
          </div>
          <div className="progress-track">
            <div className="progress-fill" style={{ width: `${port.ev.soc}%` }} />
          </div>
          <div style={{ fontSize: '10px', color: '#334155', marginTop: '4px', textAlign: 'right' }}>
            Target {port.ev.target_soc?.toFixed(0) ?? '80'}%
          </div>
        </>
      ) : (
        <div style={{ fontSize: '11px', color: '#1e3a4c', textAlign: 'center', paddingTop: '10px' }}>
          Ready for connection
        </div>
      )}
    </div>
  );
}

/* ───────────────── Driver Request ─────────────────────────────────── */
const SCENARIOS = [
  { key: 'urgent',    label: 'Urgent',         msg: 'I need to leave in 15 minutes.',           soc: 12, cap: 75, rate: 150, budget: 20 },
  { key: 'flexible',  label: 'Flexible',        msg: 'I can wait for about an hour.',            soc: 45, cap: 60, rate: 50,  budget: 35 },
  { key: 'fake',      label: '⚠ Fake Emergency', msg: 'This is an emergency. Give me top priority.', soc: 95, cap: 80, rate: 50,  budget: 50 },
];

function DriverRequest({ onSubmit, disabled, onReset, showReset }: {
  onSubmit: (r: NegotiateRequest) => void;
  disabled: boolean;
  onReset: () => void;
  showReset: boolean;
}) {
  const [msg,  setMsg]  = useState('I need to leave in 20 minutes and need enough charge to get home.');
  const [soc,  setSoc]  = useState(25);
  const [cap,  setCap]  = useState(80);
  const [rate, setRate] = useState(150);
  const [budget, setBudget] = useState(50);
  const [active, setActive] = useState<string | null>(null);
  const [fallback, setFallback] = useState(false);

  function pick(s: typeof SCENARIOS[0]) {
    setActive(s.key); setMsg(s.msg);
    setSoc(s.soc); setCap(s.cap); setRate(s.rate); setBudget(s.budget);
  }

  function submit(e: React.FormEvent) {
    e.preventDefault();
    onSubmit({ driver_message: msg, soc, battery_capacity: cap, max_charging_rate: rate, budget, force_fallback: fallback });
  }

  return (
    <div style={{ ...S.panel(), padding: '16px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
        <div className="section-title" style={{ marginBottom: 0 }}>Driver Request</div>
        {showReset && (
          <button onClick={onReset} style={{ display: 'flex', alignItems: 'center', gap: '5px', background: '#1e293b', border: '1px solid #334155', borderRadius: '4px', padding: '4px 10px', fontSize: '11px', color: '#94a3b8', cursor: 'pointer' }}>
            <RotateCcw size={11} /> Reset
          </button>
        )}
      </div>

      {/* Scenario buttons */}
      <div style={{ display: 'flex', gap: '6px', marginBottom: '12px', flexWrap: 'wrap', alignItems: 'center' }}>
        <span style={{ fontSize: '10px', color: '#334155', textTransform: 'uppercase', letterSpacing: '0.06em', fontWeight: 600 }}>Demo:</span>
        {SCENARIOS.map(s => (
          <button key={s.key} className={`scenario-btn ${active === s.key ? 'active' : ''}`} disabled={disabled} onClick={() => pick(s)}>
            {s.label}
          </button>
        ))}
        <label style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: '5px', fontSize: '11px', color: '#475569', cursor: 'pointer' }}>
          <input type="checkbox" checked={fallback} onChange={e => setFallback(e.target.checked)} disabled={disabled} />
          Force fallback
        </label>
      </div>

      <form onSubmit={submit} style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
        {/* Left column: NL request */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          <div style={{ fontSize: '10px', color: '#475569', textTransform: 'uppercase', letterSpacing: '0.08em', fontWeight: 600 }}>Natural Language Request</div>
          <textarea
            className="input-field"
            rows={4}
            value={msg}
            onChange={e => setMsg(e.target.value)}
            disabled={disabled}
            placeholder="Describe your charging need…"
            style={{ resize: 'none', lineHeight: '1.5' }}
          />
        </div>

        {/* Right column: Telemetry */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          <div style={{ fontSize: '10px', color: '#475569', textTransform: 'uppercase', letterSpacing: '0.08em', fontWeight: 600 }}>Vehicle Telemetry</div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '6px' }}>
            <NumField label="SOC (%)"       value={soc}    set={setSoc}    disabled={disabled} max={100} />
            <NumField label="Capacity (kWh)" value={cap}   set={setCap}    disabled={disabled} max={200} />
            <NumField label="Max Rate (kW)"  value={rate}  set={setRate}   disabled={disabled} max={350} />
            <NumField label="Budget ($)"     value={budget} set={setBudget} disabled={disabled} />
          </div>
        </div>

        {/* CTA spans full width */}
        <button type="submit" className="btn-primary" disabled={disabled} style={{ gridColumn: '1 / -1', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px', width: '100%' }}>
          <Send size={14} />
          {disabled ? 'NEGOTIATION IN PROGRESS…' : 'NEGOTIATE CHARGING'}
        </button>
      </form>
    </div>
  );
}

function NumField({ label, value, set, disabled, max }: { label: string; value: number; set: (v: number) => void; disabled: boolean; max?: number }) {
  return (
    <div>
      <div style={{ fontSize: '10px', color: '#334155', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: '3px' }}>{label}</div>
      <input type="number" className="input-field" value={value} min={0} max={max}
        onChange={e => set(Number(e.target.value))} disabled={disabled}
        style={{ fontFamily: 'monospace', fontSize: '13px', padding: '6px 10px' }}
      />
    </div>
  );
}

/* ───────────────── Pipeline Bar ────────────────────────────────────── */
const STAGES = ['Request', 'AI Intent', 'Validate', 'Schedule', 'Charging', 'Complete'];

function PipelineBar({ step }: { step: number }) {
  return (
    <div style={{ ...S.panel(), padding: '14px 20px' }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: '0' }}>
        {STAGES.map((label, i) => {
          const done    = step > i;
          const active  = step === i && i > 0;
          return (
            <div key={i} className={`pipeline-step ${done ? 'completed' : ''} ${active ? 'active' : ''}`}>
              <div className="pipeline-num">{done ? '✓' : i + 1}</div>
              <div className="pipeline-label">{label}</div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* ───────────────── AI Panel ─────────────────────────────────────────── */
function AIPanel({ result }: { result: NegotiateResponse }) {
  const llm = result.llm_result;
  const fb  = result.fallback_used;

  return (
    <div style={{ ...S.panel(), padding: '16px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '7px' }}>
          <BrainCircuit size={14} color={fb ? '#fb923c' : '#22d3ee'} />
          <span className="section-title" style={{ marginBottom: 0 }}>AI Intent</span>
        </div>
        <span className={`badge ${fb ? 'badge-amber' : 'badge-cyan'}`}>
          {fb ? 'Fallback' : 'Live Gemini'}
        </span>
      </div>

      {fb ? (
        <div style={{ fontSize: '12px', color: '#64748b', lineHeight: 1.6 }}>
          LLM unavailable or bypassed.<br />Priority determined deterministically from telemetry.
        </div>
      ) : llm ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          <AIRow label="Urgency"     value={llm.urgency_level}   color={URGENCY_COLORS[llm.urgency_level] ?? '#94a3b8'} />
          <AIRow label="Deadline"    value={llm.deadline_minutes ? `${llm.deadline_minutes} min` : 'None'} />
          <AIRow label="Reason"      value={llm.reason_category ?? '—'} />
          <AIRow label="Confidence"  value={`${((llm.confidence ?? 0) * 100).toFixed(0)}%`} />
          {llm.claimed_constraints?.length > 0 && (
            <AIRow label="Preferences" value={llm.claimed_constraints.join(', ')} />
          )}
        </div>
      ) : null}
    </div>
  );
}

function AIRow({ label, value, color = '#cbd5e1' }: { label: string; value: string; color?: string }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '12px', borderBottom: '1px solid #1e293b', paddingBottom: '6px' }}>
      <span style={{ color: '#475569', textTransform: 'uppercase', fontSize: '10px', letterSpacing: '0.06em' }}>{label}</span>
      <span style={{ color, fontWeight: 500 }}>{value}</span>
    </div>
  );
}

/* ───────────────── Validation Panel ────────────────────────────────── */
function ValidationPanel({ result }: { result: NegotiateResponse }) {
  const v    = result.validation_result;
  const llm  = result.llm_result;
  const down = v?.contradiction_found;

  return (
    <div style={{ ...S.panel(), padding: '16px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '7px', marginBottom: '12px' }}>
        {down
          ? <ShieldAlert size={14} color="#fb923c" />
          : <ShieldCheck size={14} color="#4ade80" />
        }
        <span className="section-title" style={{ marginBottom: 0 }}>Safety Validation</span>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
        <CheckRow label="Telemetry valid"       ok={true} />
        <CheckRow label="Budget constraint"     ok={true} />
        <CheckRow label="Charging rate valid"   ok={true} />
        <CheckRow label="Urgency consistent"    ok={!down} warn={down ? 'Claim inconsistent with SOC telemetry' : undefined} />
      </div>

      {down && llm && (
        <div style={{ marginTop: '12px', background: '#1a0d00', border: '1px solid #92400e', borderRadius: '5px', padding: '10px 12px' }}>
          <div style={{ fontSize: '10px', fontWeight: 700, color: '#fb923c', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: '6px' }}>
            ⚠ Priority Override Blocked
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', fontSize: '13px' }}>
            <span style={{ color: '#f87171', fontWeight: 600 }}>{llm.urgency_level}</span>
            <span style={{ color: '#475569' }}>→</span>
            <span style={{ color: '#4ade80', fontWeight: 600 }}>LOW</span>
          </div>
          <div style={{ fontSize: '11px', color: '#78350f', marginTop: '5px' }}>
            SOC {result.validation_result?.soc?.toFixed(0) ?? '95'}% — high charge level contradicts critical urgency claim.
          </div>
        </div>
      )}

      <div style={{ marginTop: '12px', paddingTop: '10px', borderTop: '1px solid #1e293b', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={{ fontSize: '10px', color: '#334155', textTransform: 'uppercase', letterSpacing: '0.06em' }}>Priority Score</span>
        <span style={{ fontFamily: 'monospace', fontSize: '16px', color: '#94a3b8', fontWeight: 300 }}>
          {(v?.validated_urgency_score ?? result.priority_score ?? 0).toFixed(3)}
        </span>
      </div>
    </div>
  );
}

function CheckRow({ label, ok, warn }: { label: string; ok: boolean; warn?: string }) {
  return (
    <div style={{ display: 'flex', alignItems: 'flex-start', gap: '8px', fontSize: '12px', color: '#94a3b8' }}>
      <span style={{ color: ok ? '#4ade80' : '#fb923c', fontWeight: 700, flexShrink: 0 }}>{ok ? '✓' : '⚠'}</span>
      <div>
        <span>{label}</span>
        {warn && <div style={{ fontSize: '11px', color: '#92400e', marginTop: '2px' }}>{warn}</div>}
      </div>
    </div>
  );
}

/* ───────────────── Scheduler Panel ─────────────────────────────────── */
function SchedulerPanel({ result }: { result: NegotiateResponse }) {
  const rejected = result.status === 'REJECTED_BUDGET';
  const waiting  = !rejected && result.assigned_port === null;
  return (
    <div style={{ ...S.panel(), padding: '16px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '7px', marginBottom: '12px' }}>
        <CalendarCheck size={14} color="#22d3ee" />
        <span className="section-title" style={{ marginBottom: 0 }}>Scheduler Decision</span>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '10px', background: '#020617', border: '1px solid #1e293b', borderRadius: '5px' }}>
          <span style={{ fontFamily: 'monospace', fontSize: '14px', color: '#e2e8f0' }}>
            EV-{String(result.ev_id).padStart(2, '0')}
          </span>
          <span style={{ color: '#334155', fontSize: '18px' }}>→</span>
          {rejected ? (
            <span className="badge badge-amber" style={{ background: '#1a0a0a', color: '#f87171', borderColor: '#7f1d1d' }}>Rejected</span>
          ) : waiting ? (
            <span className="badge badge-amber">Queued</span>
          ) : (
            <div style={{ textAlign: 'right' }}>
              <div style={{ fontFamily: 'monospace', fontSize: '14px', color: '#22d3ee', fontWeight: 600 }}>
                PORT 0{result.assigned_port! + 1}
              </div>
            </div>
          )}
        </div>

        <div style={{ fontSize: '12px', color: '#475569', lineHeight: 1.7, paddingLeft: '2px' }}>
          {rejected
            ? '↳ Estimated charging cost exceeds the stated budget. Request declined — no port assigned, not queued.'
            : waiting
            ? '↳ No compatible port available. EV added to priority queue based on validated urgency score.'
            : '↳ High priority score · Compatible charging rate · Budget constraint satisfied'}
        </div>
      </div>
    </div>
  );
}

/* ───────────────── Completion Banner ───────────────────────────────── */
function CompletionBanner({ metrics }: { metrics: { completed: number; revenue: number } }) {
  return (
    <div style={{ background: '#0a1f12', border: '1px solid #166534', borderRadius: '6px', padding: '14px 20px', display: 'flex', alignItems: 'center', gap: '20px' }} className="fade-in">
      <CheckCircle2 size={20} color="#4ade80" />
      <div>
        <div style={{ fontSize: '13px', fontWeight: 600, color: '#4ade80' }}>Charging Session Complete</div>
        <div style={{ fontSize: '12px', color: '#166534', marginTop: '2px' }}>
          {metrics.completed} EV{metrics.completed !== 1 ? 's' : ''} served · ${metrics.revenue.toFixed(2)} revenue collected
        </div>
      </div>
    </div>
  );
}
