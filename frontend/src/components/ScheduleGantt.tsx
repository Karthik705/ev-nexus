import { useMemo } from 'react';
import type { TimelineRow, CompareInput } from '../api';

/* Outcome palette. Deadline adherence is the thing being judged, so it drives
   colour: green met, red missed, slate not graded. */
export const OUTCOME = {
  met:     { fill: '#065f46', stroke: '#10b981', text: '#6ee7b7' },
  missed:  { fill: '#4c0519', stroke: '#f43f5e', text: '#fda4af' },
  none:    { fill: '#1e293b', stroke: '#475569', text: '#94a3b8' },
  unserved:{ fill: '#1c1917', stroke: '#78716c', text: '#a8a29e' },
};

function outcomeOf(row: TimelineRow) {
  if (row.status !== 'done') return OUTCOME.unserved;
  if (row.met_deadline === null) return OUTCOME.none;
  return row.met_deadline ? OUTCOME.met : OUTCOME.missed;
}

interface Props {
  timeline: TimelineRow[];
  inputs: CompareInput[];
  numPorts: number;
  stationKw: number[];
  horizonMin: number;
  mode: 'requests' | 'station';
  selectedEv: number | null;
  onSelectEv: (id: number | null) => void;
  compact?: boolean;
}

const LABEL_W = 132;
const ROW_H = 22;
const ROW_GAP = 4;
const PAD_T = 26;
const PAD_R = 16;

export default function ScheduleGantt({
  timeline, inputs, numPorts, stationKw, horizonMin,
  mode, selectedEv, onSelectEv, compact = false,
}: Props) {
  const rowH = compact ? 14 : ROW_H;
  const gap = compact ? 2 : ROW_GAP;

  const byEv = useMemo(() => {
    const m = new Map<number, TimelineRow>();
    timeline.forEach(r => m.set(r.ev_id, r));
    return m;
  }, [timeline]);

  /* Lanes: one per request, or one per physical port. */
  const lanes = useMemo(() => {
    if (mode === 'station') {
      return Array.from({ length: numPorts }, (_, i) => ({
        key: `p${i}`,
        label: `PORT ${i + 1}`,
        sub: `${stationKw[i]} kW`,
        rows: timeline.filter(r => r.port_id === i),
      }));
    }
    return inputs.map(inp => {
      const r = byEv.get(inp.ev_id);
      return {
        key: `ev${inp.ev_id}`,
        label: `EV-${String(inp.ev_id).padStart(2, '0')}`,
        sub: inp.scenario_key.split('_').slice(1).join(' ').toLowerCase() || inp.scenario_key,
        rows: r ? [r] : [],
        input: inp,
      };
    });
  }, [mode, numPorts, stationKw, timeline, inputs, byEv]);

  const height = PAD_T + lanes.length * (rowH + gap) + 18;
  const plotW = 1000 - LABEL_W - PAD_R;
  const x = (min: number) => LABEL_W + Math.max(0, Math.min(1, min / horizonMin)) * plotW;

  /* Time gridlines at a sensible interval. */
  const tickStep = horizonMin <= 120 ? 15 : horizonMin <= 300 ? 30 : horizonMin <= 720 ? 60 : 120;
  const ticks: number[] = [];
  for (let t = 0; t <= horizonMin; t += tickStep) ticks.push(t);

  return (
    <div style={{ width: '100%', overflowX: 'auto' }}>
      <svg
        viewBox={`0 0 1000 ${height}`}
        style={{ width: '100%', minWidth: 680, display: 'block' }}
        role="img"
        aria-label="Charging schedule"
      >
        {/* Time axis */}
        {ticks.map(t => (
          <g key={t}>
            <line x1={x(t)} y1={PAD_T - 8} x2={x(t)} y2={height - 16}
                  stroke="#1e293b" strokeWidth={1} />
            <text x={x(t)} y={PAD_T - 13} fill="#475569" fontSize={9}
                  textAnchor="middle" fontFamily="ui-monospace, monospace">
              {t >= 60 ? `${Math.floor(t / 60)}h${t % 60 ? (t % 60) : ''}` : `${t}m`}
            </text>
          </g>
        ))}

        {lanes.map((lane, i) => {
          const y = PAD_T + i * (rowH + gap);
          const isSel = mode === 'requests' && selectedEv === (lane as any).input?.ev_id;

          return (
            <g key={lane.key}>
              {/* Lane background */}
              <rect
                x={LABEL_W} y={y} width={plotW} height={rowH}
                fill={isSel ? '#0b1b2b' : i % 2 ? '#0a1222' : 'transparent'}
                rx={2}
              />

              {/* Lane label */}
              <text x={8} y={y + rowH / 2 + 3} fill={isSel ? '#22d3ee' : '#94a3b8'}
                    fontSize={compact ? 8 : 10} fontWeight={600}
                    fontFamily="ui-monospace, monospace">
                {lane.label}
              </text>
              {!compact && (
                <text x={78} y={y + rowH / 2 + 3} fill="#475569" fontSize={8}>
                  {String(lane.sub).slice(0, 12)}
                </text>
              )}

              {/* Waiting band (arrival -> start): makes the queue visible */}
              {mode === 'requests' && (lane as any).input && lane.rows.map(r => {
                const startX = x((lane as any).input.arrival_min);
                const endX = r.start_min !== null
                  ? x(r.start_min)
                  : x(horizonMin);
                const w = Math.max(0, endX - startX);
                if (w < 0.5) return null;
                return (
                  <rect key={`w${r.ev_id}`}
                        x={startX} y={y + rowH / 2 - 2} width={w} height={4}
                        fill="#1e293b" rx={2} />
                );
              })}

              {/* Charging sessions */}
              {lane.rows.map(r => {
                if (r.start_min === null) return null;
                const end = r.end_min ?? horizonMin;
                const bx = x(r.start_min);
                const bw = Math.max(2.5, x(end) - bx);
                const c = outcomeOf(r);
                const sel = selectedEv === r.ev_id;
                return (
                  <g key={`s${r.ev_id}`} style={{ cursor: 'pointer' }}
                     onClick={() => onSelectEv(sel ? null : r.ev_id)}>
                    <rect
                      x={bx} y={y + 2} width={bw} height={rowH - 4}
                      fill={c.fill} stroke={sel ? '#22d3ee' : c.stroke}
                      strokeWidth={sel ? 2 : 1} rx={3}
                    />
                    {bw > 34 && !compact && (
                      <text x={bx + 4} y={y + rowH / 2 + 3} fill={c.text}
                            fontSize={9} fontFamily="ui-monospace, monospace">
                        {mode === 'station'
                          ? `EV-${String(r.ev_id).padStart(2, '0')}`
                          : `${r.energy_kwh.toFixed(0)}kWh`}
                      </text>
                    )}
                  </g>
                );
              })}

              {/* True deadline marker */}
              {mode === 'requests' && lane.rows.map(r => {
                if (r.true_deadline_abs === null) return null;
                const dx = x(r.true_deadline_abs);
                if (r.true_deadline_abs > horizonMin) return null;
                return (
                  <g key={`d${r.ev_id}`}>
                    <line x1={dx} y1={y} x2={dx} y2={y + rowH}
                          stroke="#fbbf24" strokeWidth={1.5}
                          strokeDasharray="2 2" />
                    <circle cx={dx} cy={y + 1.5} r={2} fill="#fbbf24" />
                  </g>
                );
              })}
            </g>
          );
        })}
      </svg>
    </div>
  );
}

export function GanttLegend() {
  const items = [
    { c: OUTCOME.met,      t: 'Deadline met' },
    { c: OUTCOME.missed,   t: 'Deadline missed' },
    { c: OUTCOME.none,     t: 'No deadline stated' },
    { c: OUTCOME.unserved, t: 'Never served' },
  ];
  return (
    <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', alignItems: 'center',
                  fontSize: 11, color: '#64748b' }}>
      {items.map(i => (
        <span key={i.t} style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
          <span style={{ width: 11, height: 11, borderRadius: 2, background: i.c.fill,
                         border: `1px solid ${i.c.stroke}` }} />
          {i.t}
        </span>
      ))}
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
        <span style={{ width: 11, height: 4, background: '#1e293b', borderRadius: 2 }} />
        Waiting in queue
      </span>
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
        <span style={{ width: 2, height: 11, background: '#fbbf24' }} />
        Driver's real deadline
      </span>
    </div>
  );
}
