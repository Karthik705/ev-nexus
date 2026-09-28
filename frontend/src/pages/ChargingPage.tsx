import { useEffect, useState } from 'react';
import { api } from '../api';
import type { StationStatus } from '../api';
import { BatteryCharging, AlertCircle } from 'lucide-react';

interface PortInfo { id: number; speed_kw: number; speed_name: string; is_occupied: boolean; ev: any; }

export default function ChargingPage() {
  const [station, setStation] = useState<StationStatus | null>(null);
  const [error, setError]   = useState<string | null>(null);

  useEffect(() => {
    const tick = async () => {
      try { setStation(await api.getStationStatus()); }
      catch { setError('Cannot reach backend.'); }
    };
    tick();
    const id = setInterval(tick, 1500);
    return () => clearInterval(id);
  }, []);

  const ports  = (station?.ports ?? []) as PortInfo[];
  const active = ports.filter(p => p.is_occupied);
  const avail  = ports.filter(p => !p.is_occupied);

  return (
    <div style={{ padding: '24px', display: 'flex', flexDirection: 'column', gap: '20px' }}>
      <div>
        <h1 style={{ fontSize: '18px', fontWeight: 600, color: '#f1f5f9', margin: 0 }}>Charging Monitor</h1>
        <p style={{ fontSize: '12px', color: '#475569', marginTop: '3px' }}>Live station activity · auto-refreshes every 1.5 s</p>
      </div>

      {error && (
        <div style={{ background: '#1a0a0a', border: '1px solid #7f1d1d', borderRadius: '6px', padding: '10px 16px', display: 'flex', alignItems: 'center', gap: '10px', color: '#f87171', fontSize: '13px' }}>
          <AlertCircle size={16} /> {error}
        </div>
      )}

      {/* Active sessions table */}
      <div style={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: '6px', overflow: 'hidden' }}>
        <div style={{ padding: '12px 16px', borderBottom: '1px solid #1e293b', display: 'flex', alignItems: 'center', gap: '8px' }}>
          <BatteryCharging size={14} color="#22d3ee" />
          <span style={{ fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', color: '#475569' }}>Active Sessions</span>
          <span className="badge badge-cyan" style={{ marginLeft: 'auto' }}>{active.length} active</span>
        </div>

        {active.length === 0 ? (
          <div style={{ padding: '40px', textAlign: 'center', color: '#334155', fontSize: '13px' }}>
            <BatteryCharging size={32} color="#1e293b" style={{ marginBottom: '8px' }} />
            <div>No active charging sessions</div>
            <div style={{ fontSize: '11px', marginTop: '4px', color: '#1e293b' }}>Station ports are available</div>
          </div>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>EV</th><th>Port</th><th>Power</th>
                <th>State of Charge</th><th>Target</th><th>Status</th>
              </tr>
            </thead>
            <tbody>
              {active.map(p => (
                <tr key={p.id}>
                  <td style={{ fontFamily: 'monospace', color: '#e2e8f0' }}>EV-{String(p.ev.id).padStart(2, '0')}</td>
                  <td>PORT 0{p.id + 1}</td>
                  <td>{p.speed_kw} kW</td>
                  <td style={{ width: '200px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <div className="progress-track" style={{ flex: 1, height: '6px' }}>
                        <div className="progress-fill" style={{ width: `${p.ev.soc}%` }} />
                      </div>
                      <span style={{ fontFamily: 'monospace', fontSize: '12px', color: '#94a3b8', minWidth: '38px' }}>{p.ev.soc.toFixed(1)}%</span>
                    </div>
                  </td>
                  <td style={{ fontFamily: 'monospace', fontSize: '12px', color: '#475569' }}>{p.ev.target_soc?.toFixed(0) ?? '80'}%</td>
                  <td><span className="badge badge-cyan">Charging</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Available ports */}
      <div style={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: '6px', overflow: 'hidden' }}>
        <div style={{ padding: '12px 16px', borderBottom: '1px solid #1e293b' }}>
          <span style={{ fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', color: '#475569' }}>Available Ports</span>
        </div>
        {avail.length === 0 ? (
          <div style={{ padding: '20px 16px', fontSize: '13px', color: '#334155' }}>All ports are currently occupied.</div>
        ) : (
          <table className="data-table">
            <thead><tr><th>Port</th><th>Speed Rating</th><th>Status</th></tr></thead>
            <tbody>
              {avail.map(p => (
                <tr key={p.id}>
                  <td>PORT 0{p.id + 1}</td>
                  <td>{p.speed_kw} kW · {p.speed_name}</td>
                  <td><span className="badge badge-green">Available</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Queue */}
      {(station?.queue.length ?? 0) > 0 && (
        <div style={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: '6px', overflow: 'hidden' }}>
          <div style={{ padding: '12px 16px', borderBottom: '1px solid #1e293b' }}>
            <span style={{ fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', color: '#475569' }}>Priority Queue</span>
          </div>
          <table className="data-table">
            <thead><tr><th>Position</th><th>EV</th><th>Priority Score</th></tr></thead>
            <tbody>
              {(station!.queue as any[]).map((ev, i) => (
                <tr key={ev.id}>
                  <td style={{ color: '#475569' }}>#{i + 1}</td>
                  <td style={{ fontFamily: 'monospace' }}>EV-{String(ev.id).padStart(2, '0')}</td>
                  <td style={{ fontFamily: 'monospace', color: '#94a3b8' }}>{(ev.priority_score ?? 0).toFixed(3)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
