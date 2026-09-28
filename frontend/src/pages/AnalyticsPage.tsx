import React, { useEffect, useState } from 'react';
import { api } from '../api';
import type { StationStatus } from '../api';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { AlertCircle } from 'lucide-react';

const TOOLTIP_STYLE = { backgroundColor: '#020617', border: '1px solid #1e293b', borderRadius: '4px', fontSize: '12px', color: '#e2e8f0' };
const AXIS_TICK     = { fill: '#475569', fontSize: 11 };
const GRID_STROKE   = '#1e293b';

export default function AnalyticsPage() {
  const [station, setStation] = useState<StationStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.getStationStatus().then(setStation).catch(() => setError('Cannot reach backend.'));
  }, []);

  const metrics  = station?.metrics;
  const ports    = (station?.ports ?? []) as any[];
  const active   = ports.filter(p => p.is_occupied).length;
  const q        = station?.queue.length ?? 0;
  const util     = ports.length ? Math.round((active / ports.length) * 100) : 0;

  const utilizationData = [
    { label: 'Active',    value: active },
    { label: 'Available', value: ports.length - active },
    { label: 'Queued',    value: q },
  ];

  return (
    <div style={{ padding: '24px', display: 'flex', flexDirection: 'column', gap: '20px' }}>
      <div>
        <h1 style={{ fontSize: '18px', fontWeight: 600, color: '#f1f5f9', margin: 0 }}>Analytics</h1>
        <p style={{ fontSize: '12px', color: '#475569', marginTop: '3px' }}>Session-level metrics from the active simulation</p>
      </div>

      {error && (
        <div style={{ background: '#1a0a0a', border: '1px solid #7f1d1d', borderRadius: '6px', padding: '10px 16px', display: 'flex', alignItems: 'center', gap: '10px', color: '#f87171', fontSize: '13px' }}>
          <AlertCircle size={16} /> {error}
        </div>
      )}

      {/* Metric row */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '12px' }}>
        {[
          { label: 'EVs Served',    value: metrics?.completed ?? 0,       color: '#22d3ee' },
          { label: 'Total Revenue', value: `$${(metrics?.revenue ?? 0).toFixed(2)}`, color: '#4ade80' },
          { label: 'Active Ports',  value: `${active} / ${ports.length}`, color: '#94a3b8' },
          { label: 'Utilization',   value: `${util}%`,                    color: util > 70 ? '#4ade80' : '#fb923c' },
        ].map(m => (
          <div key={m.label} className="metric-card">
            <div className="mc-label">{m.label}</div>
            <div className="mc-value" style={{ color: m.color }}>{m.value}</div>
          </div>
        ))}
      </div>

      {/* Charts */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
        <ChartPanel title="Port Utilization" subtitle="Current distribution across station ports">
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={utilizationData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={GRID_STROKE} vertical={false} />
              <XAxis dataKey="label" tick={AXIS_TICK} axisLine={false} tickLine={false} />
              <YAxis tick={AXIS_TICK} axisLine={false} tickLine={false} allowDecimals={false} />
              <Tooltip contentStyle={TOOLTIP_STYLE} cursor={{ fill: '#1e293b' }} />
              <Bar dataKey="value" fill="#0e7490" radius={[3, 3, 0, 0]} maxBarSize={60} name="Count" />
            </BarChart>
          </ResponsiveContainer>
        </ChartPanel>

        <div style={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: '6px', padding: '16px', display: 'flex', flexDirection: 'column', gap: '12px' }}>
          <div>
            <div style={{ fontSize: '12px', fontWeight: 600, color: '#94a3b8', marginBottom: '2px' }}>Session Totals</div>
            <div style={{ fontSize: '11px', color: '#334155' }}>Cumulative counts for the current run</div>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {[
              { label: 'Completed Sessions', value: metrics?.completed ?? 0 },
              { label: 'Revenue Collected',  value: `$${(metrics?.revenue ?? 0).toFixed(2)}` },
              { label: 'Queue Depth',        value: q },
              { label: 'Total Ports',        value: ports.length },
            ].map(r => (
              <div key={r.label} style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px', borderBottom: '1px solid #0f172a', paddingBottom: '6px', color: '#94a3b8' }}>
                <span style={{ color: '#475569' }}>{r.label}</span>
                <span style={{ fontFamily: 'monospace' }}>{r.value}</span>
              </div>
            ))}
          </div>
          <div style={{ fontSize: '11px', color: '#1e293b', marginTop: 'auto' }}>
            Note: Time-series and historical analytics require a persistent logging backend.
          </div>
        </div>
      </div>
    </div>
  );
}

function ChartPanel({ title, subtitle, children }: { title: string; subtitle: string; children: React.ReactNode }) {
  return (
    <div style={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: '6px', padding: '16px' }}>
      <div style={{ marginBottom: '16px' }}>
        <div style={{ fontSize: '12px', fontWeight: 600, color: '#94a3b8' }}>{title}</div>
        <div style={{ fontSize: '11px', color: '#334155', marginTop: '2px' }}>{subtitle}</div>
      </div>
      {children}
    </div>
  );
}
