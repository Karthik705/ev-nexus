import {
  User, MessageSquare, BrainCircuit, ShieldCheck,
  CalendarCheck, BatteryCharging, BarChart3, ArrowRight, ArrowDown,
  AlertTriangle,
} from 'lucide-react';

/* ─── node & edge helpers ─────────────────────────────────── */
function Node({
  icon: Icon, title, desc, accent = '#0e7490', small = false,
}: {
  icon: any; title: string; desc: string;
  accent?: string; small?: boolean;
}) {
  return (
    <div style={{
      background: '#0f172a', border: `1px solid #1e293b`,
      borderRadius: '6px', padding: small ? '10px 14px' : '14px 16px',
      display: 'flex', gap: '12px', alignItems: 'flex-start',
      minWidth: small ? '160px' : '210px', maxWidth: small ? '200px' : '260px',
      flex: small ? '0 0 auto' : '0 0 auto',
    }}>
      <div style={{
        width: small ? '28px' : '32px', height: small ? '28px' : '32px',
        borderRadius: '5px', background: '#020617', border: `1px solid #1e293b`,
        display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
      }}>
        <Icon size={small ? 14 : 16} color={accent} />
      </div>
      <div>
        <div style={{ fontSize: small ? '11px' : '12px', fontWeight: 700, color: '#e2e8f0', lineHeight: 1.3 }}>{title}</div>
        <div style={{ fontSize: '10px', color: '#475569', marginTop: '3px', lineHeight: 1.4 }}>{desc}</div>
      </div>
    </div>
  );
}

function HArrow({ label }: { label?: string }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '0 6px', gap: '2px', flexShrink: 0 }}>
      <ArrowRight size={16} color="#1e293b" />
      {label && <span style={{ fontSize: '9px', color: '#334155', textTransform: 'uppercase', letterSpacing: '0.05em' }}>{label}</span>}
    </div>
  );
}

function VArrow({ label }: { label?: string }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '2px', padding: '4px 0', flexShrink: 0 }}>
      <ArrowDown size={16} color="#1e293b" />
      {label && <span style={{ fontSize: '9px', color: '#334155', textTransform: 'uppercase', letterSpacing: '0.05em' }}>{label}</span>}
    </div>
  );
}

/* ─── main component ──────────────────────────────────────── */
export default function ArchitecturePage() {
  return (
    <div style={{ padding: '24px', display: 'flex', flexDirection: 'column', gap: '20px', minHeight: '100%' }}>
      <div>
        <h1 style={{ fontSize: '18px', fontWeight: 600, color: '#f1f5f9', margin: 0 }}>System Architecture</h1>
        <p style={{ fontSize: '12px', color: '#475569', marginTop: '3px' }}>EV Charging Negotiator · Data-flow & component reference</p>
      </div>

      {/* ── Canvas ── */}
      <div style={{ background: '#0a0f1e', border: '1px solid #1e293b', borderRadius: '6px', padding: '32px 24px', overflow: 'auto' }}>

        {/* Row 1: Driver → NL Request */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0' }}>
          <Node icon={User} title="Driver" desc="Arrives at charging station" accent="#94a3b8" />
          <HArrow />
          <Node icon={MessageSquare} title="Natural Language Request" desc="Free-text description of charging need" accent="#94a3b8" />
        </div>

        {/* Connector down */}
        <div style={{ display: 'flex', justifyContent: 'center' }}>
          <VArrow />
        </div>

        {/* Row 2: AI Intent Engine, with Fallback branching off to the right */}
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'center', gap: '20px' }}>
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '0' }}>
            <Node icon={BrainCircuit} title="AI Intent Engine" desc="Gemini LLM — extracts urgency, deadline, constraints, confidence" accent="#22d3ee" />
          </div>

          {/* Fallback side branch */}
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-start', gap: '0', paddingTop: '14px', borderLeft: '1px dashed #334155', marginLeft: '10px', paddingLeft: '20px' }}>
            <div style={{ fontSize: '10px', color: '#334155', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: '6px', fontWeight: 600 }}>If LLM unavailable</div>
            <Node icon={AlertTriangle} title="Deterministic Fallback" desc="Rule-based intent from raw telemetry" accent="#fb923c" small />
          </div>
        </div>

        {/* Connector down from AI block */}
        <div style={{ display: 'flex', justifyContent: 'center' }}>
          <VArrow />
        </div>

        {/* Row 3: Constraint Validator with Telemetry annotation */}
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'center', gap: '20px' }}>
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
            <Node icon={ShieldCheck} title="Constraint Validator" desc="Cross-checks LLM claims against SOC, budget, and hardware limits" accent="#4ade80" />
          </div>

          {/* Telemetry inbound */}
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-start', gap: '0', paddingTop: '14px', borderLeft: '1px dashed #334155', marginLeft: '10px', paddingLeft: '20px' }}>
            <div style={{ fontSize: '10px', color: '#334155', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: '6px', fontWeight: 600 }}>Telemetry input</div>
            <Node icon={BatteryCharging} title="EV Telemetry" desc="SOC, capacity, max rate, budget" accent="#475569" small />
          </div>
        </div>

        <div style={{ display: 'flex', justifyContent: 'center' }}>
          <VArrow label="Validated intent" />
        </div>

        {/* Row 4: Resource-Aware Scheduler */}
        <div style={{ display: 'flex', justifyContent: 'center' }}>
          <Node icon={CalendarCheck} title="Resource-Aware Scheduler" desc="Maps EVs to ports by priority, rate compatibility, and availability" accent="#22d3ee" />
        </div>

        <div style={{ display: 'flex', justifyContent: 'center' }}>
          <VArrow label="Port assignment" />
        </div>

        {/* Row 5: Charging Simulator */}
        <div style={{ display: 'flex', justifyContent: 'center' }}>
          <Node icon={BatteryCharging} title="Charging Station Simulator" desc="Advances SOC over discrete time-steps; removes EVs on completion" accent="#0d9488" />
        </div>

        <div style={{ display: 'flex', justifyContent: 'center' }}>
          <VArrow label="Session result" />
        </div>

        {/* Row 6: Results */}
        <div style={{ display: 'flex', justifyContent: 'center' }}>
          <Node icon={BarChart3} title="Results & Metrics" desc="Revenue, throughput, wait times, driver satisfaction" accent="#4ade80" />
        </div>
      </div>

      {/* Component table */}
      <div style={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: '6px', overflow: 'hidden' }}>
        <div style={{ padding: '12px 16px', borderBottom: '1px solid #1e293b' }}>
          <span style={{ fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', color: '#475569' }}>
            Component Reference
          </span>
        </div>
        <table className="data-table">
          <thead><tr><th>Component</th><th>Implementation</th><th>Key Responsibility</th></tr></thead>
          <tbody>
            {[
              ['AI Intent Engine',          'llm_negotiator.py · Gemini API',  'NL → structured DriverIntent'],
              ['Deterministic Fallback',     'llm_negotiator.py (fallback branch)', 'SOC / urgency heuristic when LLM unavailable'],
              ['Constraint Validator',       'constraint_validator.py',         'Safety checks · urgency downgrade'],
              ['Resource-Aware Scheduler',   'simple_ev_simulation.py',         'Priority queue · port assignment'],
              ['Charging Station Simulator', 'simple_ev_simulation.py (step())', 'Discrete time-step simulation'],
              ['REST API Bridge',            'app.py · FastAPI',                '/api/negotiate, /step, /station, /benchmarks, /reset, /new-session, /health'],
            ].map(([c, i, r]) => (
              <tr key={c}>
                <td style={{ color: '#e2e8f0', fontWeight: 500 }}>{c}</td>
                <td style={{ fontFamily: 'monospace', fontSize: '12px', color: '#475569' }}>{i}</td>
                <td style={{ color: '#64748b' }}>{r}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
