import React from 'react';
import { useTranslation } from 'react-i18next';
import {
  AlertTriangle,
  CheckCircle,
  XCircle,
  Database,
  Calendar,
  Radio,
  Activity,
} from 'lucide-react';
import LiveBanner from './LiveBanner';

export default function ControlHeader({
  health,
  selectedDate,
  onDateChange,
  availableDates,
  isLoading,
  mode = 'historical',
  onModeChange,
  liveStatus,
  connectionStatus = 'connected',
  onRefreshLive,
}) {
  const { t } = useTranslation();
  const isHealthy = health && health.status === 'ok';
  const isLive = mode === 'live';

  return (
    <div className="header-card" role="banner">
      <div className="header-top">
        <div className="brand-section">
          <div className="brand-icon" aria-hidden="true">RW</div>
          <div className="brand-title">
            <h1>RouteWise Dashboard</h1>
            <p>Predictive Disruption Risk Platform (NH-44 Ramban–Banihal Pilot Corridor)</p>
          </div>
        </div>

        <div className="system-badges">
          {isHealthy ? (
            <span className="badge badge-connected" title="FastAPI backend connected">
              <CheckCircle size={14} aria-hidden="true" /> Backend Connected
            </span>
          ) : (
            <span className="badge badge-disconnected" title="Backend unreachable">
              <XCircle size={14} aria-hidden="true" /> Backend Offline
            </span>
          )}

          <span className="badge badge-pill">
            <Database size={13} aria-hidden="true" /> Model v
            {health?.model_version ? health.model_version.slice(0, 8) : '68b04504'}
          </span>

          <span className="badge badge-pill">
            151 Segments | 24h Horizon
          </span>
        </div>
      </div>

      {/* Operating Mode Switcher & Telemetry Bar */}
      <LiveBanner
        mode={mode}
        onModeChange={onModeChange}
        liveStatus={liveStatus}
        connectionStatus={connectionStatus}
        onRefresh={onRefreshLive}
        isLoading={isLoading}
      />

      {/* Mode-Specific Information & Controls */}
      {!isLive ? (
        <>
          {/* Historical Retrospective Notice Banner (Unchanged from Pass 1) */}
          <div className="retrospective-banner">
            <AlertTriangle size={18} style={{ flexShrink: 0, marginTop: 2 }} aria-hidden="true" />
            <div>
              <strong>Retrospective Historical Reanalysis Notice:</strong> The road segment risk scores
              displayed below are evaluated from historical ERA5-Land reanalysis observations (2021–2025).
              These are <em>advisory relative risk ranking estimates</em> for situational awareness and
              route prioritization. They do <strong>not</strong> represent live forecasts or definitive
              road clearance guarantees.
            </div>
          </div>

          {/* Historical Date Control Bar (Unchanged from Pass 1) */}
          <div className="control-bar" style={{ padding: '8px 12px', background: 'var(--bg-input)' }}>
            <div className="date-controls">
              <div className="date-input-group">
                <Calendar size={15} style={{ color: 'var(--text-muted)' }} aria-hidden="true" />
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
                <span style={{ fontSize: 12, color: 'var(--text-dim)' }}>Benchmark Dates:</span>
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
        </>
      ) : (
        /* Live Mode Active Horizon Notice */
        <div
          className="control-bar"
          style={{
            padding: '10px 14px',
            background: 'var(--bg-input)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            flexWrap: 'wrap',
            gap: 10,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13 }}>
            <Radio size={15} style={{ color: 'var(--accent-secondary)' }} aria-hidden="true" />
            <span>
              {liveStatus?.mode === 'off' ? (
                <strong style={{ color: 'var(--text-muted)' }}>{t('live.mode_off_notice')}</strong>
              ) : liveStatus?.mode === 'replay' ? (
                <>
                  <strong>{t('live.replay_mode')}:</strong> 24-hour advisory relative risk evaluated from Replay scenario simulation.
                </>
              ) : (
                <>
                  <strong>Live Telemetry Horizon:</strong> 24-hour advisory relative risk evaluated from Open-Meteo weather ingestion.
                </>
              )}
            </span>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: 16, fontSize: 12, color: 'var(--text-dim)', flexWrap: 'wrap' }}>
            <div>
              {t('live.source_label')}: <strong>{liveStatus?.provider === 'open-meteo' ? 'Open-Meteo' : (liveStatus?.mode === 'replay' ? 'Replay' : 'None')}</strong>
            </div>
            {liveStatus?.latest_weather_date && (
              <div>
                {t('live.weather_window_end')}: <strong>{liveStatus.latest_weather_date}</strong>
              </div>
            )}
            <div>
              Current Advisory: <strong>{selectedDate || 'Today'}</strong>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
