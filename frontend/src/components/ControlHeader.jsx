import React from 'react';
import { AlertTriangle, CheckCircle, XCircle, Database, Calendar } from 'lucide-react';

export default function ControlHeader({
  health,
  selectedDate,
  onDateChange,
  availableDates,
  isLoading,
}) {
  const isHealthy = health && health.status === 'ok';

  return (
    <div className="header-card">
      <div className="header-top">
        <div className="brand-section">
          <div className="brand-icon">RW</div>
          <div className="brand-title">
            <h1>RouteWise Dashboard</h1>
            <p>Predictive Disruption Risk Platform (NH-44 Ramban–Banihal Pilot Corridor)</p>
          </div>
        </div>

        <div className="system-badges">
          {isHealthy ? (
            <span className="badge badge-connected" title="FastAPI backend connected">
              <CheckCircle size={14} /> Backend Connected
            </span>
          ) : (
            <span className="badge badge-disconnected" title="Backend unreachable">
              <XCircle size={14} /> Backend Offline
            </span>
          )}

          <span className="badge badge-pill">
            <Database size={13} /> Model v{health?.model_version ? health.model_version.slice(0, 8) : '68b04504'}
          </span>

          <span className="badge badge-pill">
            151 Segments | 24h Horizon
          </span>
        </div>
      </div>

      {/* Retrospective Notice Banner */}
      <div className="retrospective-banner">
        <AlertTriangle size={18} style={{ flexShrink: 0, marginTop: 2 }} />
        <div>
          <strong>Retrospective Historical Reanalysis Notice:</strong> The road segment risk scores
          displayed below are evaluated from historical ERA5-Land reanalysis observations (2021–2025).
          These are <em>advisory relative risk ranking estimates</em> for situational awareness and
          route prioritization. They do <strong>not</strong> represent live forecasts or definitive
          road clearance guarantees.
        </div>
      </div>

      {/* Date Control Bar */}
      <div className="control-bar" style={{ padding: '8px 12px', background: '#0f172a' }}>
        <div className="date-controls">
          <div className="date-input-group">
            <Calendar size={15} color="#94a3b8" />
            <label htmlFor="obs-date">Observation Date:</label>
            <input
              id="obs-date"
              type="date"
              className="date-input"
              value={selectedDate}
              min={availableDates?.start_date || '2021-01-06'}
              max={availableDates?.end_date || '2025-12-31'}
              onChange={(e) => onDateChange(e.target.value)}
              disabled={isLoading}
            />
          </div>

          <div className="sample-buttons">
            <span style={{ fontSize: 12, color: '#64748b' }}>Benchmark Dates:</span>
            {['2023-07-09', '2024-03-15', '2022-01-20', '2025-08-10'].map((d) => (
              <button
                key={d}
                type="button"
                className={`sample-btn ${selectedDate === d ? 'active' : ''}`}
                onClick={() => onDateChange(d)}
                disabled={isLoading}
              >
                {d}
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
