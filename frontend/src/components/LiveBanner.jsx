import React from 'react';
import { useTranslation } from 'react-i18next';
import {
  AlertTriangle,
  Radio,
  Wifi,
  WifiOff,
  RefreshCw,
  Clock,
  HelpCircle,
  Activity,
  History,
} from 'lucide-react';

export default function LiveBanner({
  mode = 'historical',
  onModeChange,
  liveStatus,
  connectionStatus = 'connected',
  onRefresh,
  isLoading = false,
}) {
  const { t } = useTranslation();
  const isLive = mode === 'live';
  const isStale = liveStatus?.data_age_hours > 24 || liveStatus?.stale_count > 0;
  const unknownCount = liveStatus?.unknown_count ?? 0;

  return (
    <div
      className={`live-experimental-banner ${isLive && isStale ? 'stale' : ''}`}
      role="region"
      aria-label="RouteWise Operating Mode and Telemetry Status"
    >
      <div className="live-banner-left">
        {/* Operating Mode Toggle (Default: Historical) */}
        <div className="live-mode-toggle" role="group" aria-label={t('live.toggle_label')}>
          <button
            type="button"
            className={`live-toggle-btn ${!isLive ? 'active' : ''}`}
            onClick={() => onModeChange && onModeChange('historical')}
            aria-pressed={!isLive}
          >
            <History size={13} aria-hidden="true" />
            <span>{t('live.historical_mode')}</span>
          </button>
          <button
            type="button"
            className={`live-toggle-btn ${isLive ? 'active' : ''}`}
            onClick={() => onModeChange && onModeChange('live')}
            aria-pressed={isLive}
          >
            <Radio size={13} aria-hidden="true" />
            <span>{t('live.live_mode')}</span>
          </button>
        </div>

        {/* In Live Mode: Display Persistent Experimental Badge */}
        {isLive && (
          <span className="live-experimental-badge" title={t('live.experimental_notice')}>
            <Activity size={13} aria-hidden="true" />
            <span>{t('live.experimental_badge')}</span>
          </span>
        )}

        {/* Stale Warning Badge if data age > 24h */}
        {isLive && isStale && (
          <span
            className="badge badge-warning"
            style={{ display: 'inline-flex', alignItems: 'center', gap: 4, fontWeight: 700 }}
          >
            <AlertTriangle size={13} aria-hidden="true" />
            <span>{t('live.data_stale')}</span>
          </span>
        )}
      </div>

      {/* Live Mode Telemetry Metadata & Connection State */}
      {isLive && (
        <div className="live-banner-meta">
          {/* Data Age & Last Updated */}
          {liveStatus?.data_age_hours !== null && liveStatus?.data_age_hours !== undefined && (
            <div className="live-banner-item" title={liveStatus?.latest_fetch || 'Recent'}>
              <Clock size={13} style={{ color: 'var(--text-muted)' }} aria-hidden="true" />
              <span>
                {t('live.data_age')}: <strong>{liveStatus.data_age_hours.toFixed(1)}h</strong>
              </span>
            </div>
          )}

          {/* Unknown Segments Indicator */}
          {unknownCount > 0 && (
            <div
              className="live-banner-item"
              title="Missing or stale telemetry is designated UNKNOWN (never assumed safe)"
            >
              <HelpCircle size={13} style={{ color: 'var(--text-dim)' }} aria-hidden="true" />
              <span style={{ color: 'var(--text-dim)', fontWeight: 600 }}>
                {unknownCount} {t('live.unknown_segments')}
              </span>
            </div>
          )}

          {/* SSE Stream Connection Indicator */}
          <div
            className={`live-connection-indicator ${
              connectionStatus === 'connected' ? 'connected' : 'lost'
            }`}
          >
            {connectionStatus === 'connected' ? (
              <>
                <Wifi size={12} aria-hidden="true" />
                <span>{t('live.connection_connected')}</span>
              </>
            ) : (
              <>
                <WifiOff size={12} aria-hidden="true" />
                <span>{t('live.connection_lost')}</span>
              </>
            )}
          </div>

          {/* Manual Refresh Action */}
          {onRefresh && (
            <button
              type="button"
              className="sample-btn"
              onClick={onRefresh}
              disabled={isLoading}
              title={t('live.refresh_now')}
              style={{ padding: '3px 8px', fontSize: 11 }}
            >
              <RefreshCw
                size={11}
                className={isLoading ? 'spin-icon' : ''}
                style={{ display: 'inline', marginRight: 4 }}
                aria-hidden="true"
              />
              {t('live.refresh_now')}
            </button>
          )}
        </div>
      )}
    </div>
  );
}
