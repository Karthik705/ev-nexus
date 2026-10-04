import { useEffect, useState } from 'react';
import { BrowserRouter, Routes, Route, Navigate, NavLink } from 'react-router-dom';
import {
  Zap, LayoutGrid, BatteryCharging, BarChart3, Activity, GitBranch, CalendarClock,
} from 'lucide-react';

import { api } from './api';
import SchedulerPage from './pages/SchedulerPage';
import OverviewPage from './pages/OverviewPage';
import ChargingPage from './pages/ChargingPage';
import AnalyticsPage from './pages/AnalyticsPage';
import BenchmarksPage from './pages/BenchmarksPage';
import ArchitecturePage from './pages/ArchitecturePage';

const NAV = [
  { to: '/scheduler',     Icon: CalendarClock,   label: 'Scheduler'     },
  { to: '/overview',      Icon: LayoutGrid,      label: 'Negotiate'     },
  { to: '/charging',      Icon: BatteryCharging, label: 'Charging'      },
  { to: '/analytics',     Icon: BarChart3,        label: 'Analytics'     },
  { to: '/benchmarks',    Icon: Activity,         label: 'Benchmarks'    },
  { to: '/architecture',  Icon: GitBranch,        label: 'Architecture'  },
];

export default function App() {
  // Real liveness check against the backend — not a hardcoded "always online"
  // indicator. Polled independently of whatever page is currently mounted.
  const [online, setOnline] = useState<boolean | null>(null);
  useEffect(() => {
    let cancelled = false;
    const check = async () => {
      const ok = await api.checkHealth();
      if (!cancelled) setOnline(ok);
    };
    check();
    const id = setInterval(check, 5000);
    return () => { cancelled = true; clearInterval(id); };
  }, []);

  return (
    <BrowserRouter>
      <div style={{ display: 'flex', height: '100vh', background: '#020617', overflow: 'hidden' }}>

        {/* ── Sidebar ─────────────────────────────────────────── */}
        <aside style={{
          width: '200px', flexShrink: 0,
          background: '#0a0f1e',
          borderRight: '1px solid #1e293b',
          display: 'flex', flexDirection: 'column',
        }}>
          {/* Logo */}
          <div style={{
            height: '48px', display: 'flex', alignItems: 'center',
            gap: '8px', padding: '0 16px',
            borderBottom: '1px solid #1e293b',
          }}>
            <div style={{
              width: '24px', height: '24px', borderRadius: '4px',
              background: 'linear-gradient(135deg,#0e7490,#22d3ee)',
              display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
            }}>
              <Zap size={13} color="#fff" />
            </div>
            <div>
              <div style={{ fontSize: '12px', fontWeight: 700, letterSpacing: '0.12em', color: '#f1f5f9' }}>EV NEXUS</div>
              <div style={{ fontSize: '9px', color: '#475569', letterSpacing: '0.06em', textTransform: 'uppercase' }}>Operations</div>
            </div>
          </div>

          {/* Nav items */}
          <nav style={{ flex: 1, padding: '12px 8px', display: 'flex', flexDirection: 'column', gap: '2px' }}>
            {NAV.map(({ to, Icon, label }) => (
              <NavLink key={to} to={to} style={({ isActive }) => ({
                display: 'flex', alignItems: 'center', gap: '10px',
                padding: '8px 10px', borderRadius: '5px',
                fontSize: '13px', fontWeight: 500,
                textDecoration: 'none',
                transition: 'all 0.15s',
                background: isActive ? '#0e2a38' : 'transparent',
                color: isActive ? '#22d3ee' : '#64748b',
                borderLeft: isActive ? '2px solid #0891b2' : '2px solid transparent',
              })}>
                <Icon size={15} />
                <span>{label}</span>
              </NavLink>
            ))}
          </nav>

          {/* System status — reflects a real /api/health poll, not a static indicator */}
          <div style={{
            padding: '12px 16px', borderTop: '1px solid #1e293b',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '2px' }}>
              <div style={{
                width: '6px', height: '6px', borderRadius: '50%',
                background: online ? '#4ade80' : '#f87171',
                boxShadow: online ? '0 0 6px #4ade80' : '0 0 6px #f87171',
              }} />
              <span style={{ fontSize: '10px', fontWeight: 700, color: online ? '#4ade80' : '#f87171', letterSpacing: '0.08em', textTransform: 'uppercase' }}>
                {online === null ? 'Checking…' : online ? 'System Online' : 'Backend Unreachable'}
              </span>
            </div>
            <div style={{ fontSize: '10px', color: '#334155', letterSpacing: '0.04em' }}>
              {online ? 'API Connected' : 'No response from /api/health'}
            </div>
          </div>
        </aside>

        {/* ── Main area ────────────────────────────────────────── */}
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0, overflow: 'hidden' }}>

          {/* Top bar */}
          <TopBar online={online} />

          {/* Page content */}
          <main style={{ flex: 1, overflow: 'auto', background: '#020617' }}>
            <Routes>
              <Route path="/"             element={<Navigate to="/scheduler" replace />} />
              <Route path="/scheduler"    element={<SchedulerPage />} />
              <Route path="/overview"     element={<OverviewPage />} />
              <Route path="/charging"     element={<ChargingPage />} />
              <Route path="/analytics"    element={<AnalyticsPage />} />
              <Route path="/benchmarks"   element={<BenchmarksPage />} />
              <Route path="/architecture" element={<ArchitecturePage />} />
              <Route path="*"             element={<Navigate to="/scheduler" replace />} />
            </Routes>
          </main>
        </div>
      </div>
    </BrowserRouter>
  );
}

function TopBar({ online }: { online: boolean | null }) {
  return (
    <div style={{
      height: '48px', flexShrink: 0,
      background: '#0a0f1e',
      borderBottom: '1px solid #1e293b',
      display: 'flex', alignItems: 'center',
      padding: '0 24px',
      gap: '24px',
    }}>
      <div style={{ flex: 1 }}>
        <span style={{ fontSize: '12px', fontWeight: 700, letterSpacing: '0.1em', color: '#94a3b8', textTransform: 'uppercase' }}>
          EV Charging Negotiator
        </span>
      </div>
      <div style={{ fontSize: '12px', color: '#475569' }}>
        Deadline-aware EV charging scheduler
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
        <div style={{ width: '6px', height: '6px', borderRadius: '50%', background: online ? '#4ade80' : '#f87171', boxShadow: online ? '0 0 5px #4ade80' : '0 0 5px #f87171' }} />
        <span style={{ fontSize: '11px', fontWeight: 600, color: online ? '#4ade80' : '#f87171', letterSpacing: '0.06em' }}>
          {online === null ? 'CHECKING…' : online ? 'OPERATIONAL' : 'UNREACHABLE'}
        </span>
      </div>
    </div>
  );
}
