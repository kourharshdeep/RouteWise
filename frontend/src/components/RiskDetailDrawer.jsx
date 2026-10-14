import React, { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  X,
  AlertTriangle,
  CloudRain,
  Mountain,
  Compass,
  FileText,
  Thermometer,
  ShieldAlert,
  Info,
  Calendar,
  Layers,
} from 'lucide-react';
import { fetchSegmentFeatures } from '../services/api';

export default function RiskDetailDrawer({
  segmentId,
  selectedDate,
  riskItem,
  onClose,
}) {
  const { t } = useTranslation();
  const [featureData, setFeatureData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let isMounted = true;
    async function loadFeatures() {
      if (!segmentId || !selectedDate) return;
      try {
        setLoading(true);
        setError(null);
        const data = await fetchSegmentFeatures(segmentId, selectedDate);
        if (isMounted) setFeatureData(data);
      } catch (err) {
        if (isMounted) setError(err.message || 'Failed to fetch segment features');
      } finally {
        if (isMounted) setLoading(false);
      }
    }
    loadFeatures();
    return () => {
      isMounted = false;
    };
  }, [segmentId, selectedDate]);

  // Handle ESC key to close drawer
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  if (!segmentId) return null;

  const score = riskItem?.risk_score ?? null;
  const tier = riskItem?.risk_tier || 'Low';

  let tierClass = 'badge-low';
  if (tier === 'High') tierClass = 'badge-high';
  else if (tier === 'Medium') tierClass = 'badge-medium';

  return (
    <div className="risk-drawer-backdrop" onClick={onClose} role="presentation">
      <div
        className="risk-drawer-panel"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-labelledby="drawer-segment-title"
      >
        {/* Drawer Header */}
        <div className="drawer-header">
          <div className="drawer-title-group">
            <div className="drawer-icon-box">
              <Layers size={18} />
            </div>
            <div>
              <h2 id="drawer-segment-title" className="drawer-title">
                Segment {segmentId}
              </h2>
              <span className="drawer-subtitle">
                NH-44 Ramban–Banihal Corridor Segment Analysis
              </span>
            </div>
          </div>
          <button
            type="button"
            className="drawer-close-btn"
            onClick={onClose}
            aria-label="Close drawer"
          >
            <X size={20} />
          </button>
        </div>

        {/* Retrospective Badge & Date Notice */}
        <div className="drawer-meta-bar">
          <span className="badge badge-subtle">
            <Calendar size={13} style={{ display: 'inline', marginRight: 4 }} />
            {selectedDate}
          </span>
          <span className="badge badge-retrospective">
            {t('app.retrospective_badge')}
          </span>
          <span className={`badge ${tierClass}`}>
            {tier} Risk ({score !== null ? score.toFixed(3) : 'N/A'})
          </span>
        </div>

        {/* Drawer Body */}
        <div className="drawer-content">
          {loading ? (
            <div className="state-box state-loading" style={{ margin: '30px auto' }}>
              <span>Loading genuine segment input features...</span>
            </div>
          ) : error ? (
            <div className="state-box state-error" style={{ margin: '20px auto' }}>
              <Info size={18} />
              <span>{error}</span>
            </div>
          ) : (
            <>
              {/* Section 1: Physical Terrain Attributes */}
              <div className="drawer-section">
                <h3 className="section-title">
                  <Mountain size={16} /> Physical Terrain Metrics
                </h3>
                <div className="metrics-grid-2">
                  <div className="metric-box">
                    <span className="metric-label">Segment Length</span>
                    <strong className="metric-value">
                      {featureData?.length_m ? `${featureData.length_m} m` : '—'}
                    </strong>
                  </div>
                  <div className="metric-box">
                    <span className="metric-label">Mean Elevation</span>
                    <strong className="metric-value">
                      {featureData?.elevation_m ? `${Math.round(featureData.elevation_m)} m ASL` : '—'}
                    </strong>
                  </div>
                  <div className="metric-box">
                    <span className="metric-label">Mean Gradient</span>
                    <strong className="metric-value">
                      {featureData?.slope_pct ? `${featureData.slope_pct}% (${featureData.slope_deg}°)` : '—'}
                    </strong>
                  </div>
                  <div className="metric-box">
                    <span className="metric-label">Highway Classification</span>
                    <strong className="metric-value" style={{ textTransform: 'uppercase' }}>
                      {featureData?.highway || 'Trunk (NH-44)'}
                    </strong>
                  </div>
                </div>
              </div>

              {/* Section 2: Input Features (Meteorological inputs from ERA5-Land) */}
              <div className="drawer-section">
                <h3 className="section-title">
                  <CloudRain size={16} /> {t('drawer.input_features')}
                </h3>
                <p className="drawer-disclaimer-note">
                  {featureData?.disclaimer}
                </p>

                {featureData?.weather ? (
                  <div className="metrics-grid-2" style={{ marginTop: 10 }}>
                    <div className="metric-box">
                      <span className="metric-label">Daily Precipitation</span>
                      <strong className="metric-value">
                        {featureData.weather.precip_mm} mm
                      </strong>
                    </div>
                    <div className="metric-box">
                      <span className="metric-label">7-Day Cumulative Rain</span>
                      <strong className="metric-value">
                        {featureData.weather.precip_7d_mm} mm
                      </strong>
                    </div>
                    <div className="metric-box">
                      <span className="metric-label">Mean Air Temperature</span>
                      <strong className="metric-value">
                        {featureData.weather.temp_mean_c} °C
                      </strong>
                    </div>
                    <div className="metric-box">
                      <span className="metric-label">Snow Depth / Equiv.</span>
                      <strong className="metric-value">
                        {featureData.weather.snow_depth_m > 0
                          ? `${featureData.weather.snow_depth_m} m`
                          : '0.0 mm'}
                      </strong>
                    </div>
                  </div>
                ) : (
                  <div className="state-box state-neutral">
                    <span>No stored meteorological observations for this date.</span>
                  </div>
                )}
              </div>

              {/* Section 3: Linked Field Incident Reports */}
              <div className="drawer-section">
                <h3 className="section-title">
                  <FileText size={16} /> Linked Field Reports ({featureData?.reports?.length || 0})
                </h3>
                {!featureData?.reports || featureData.reports.length === 0 ? (
                  <p className="empty-subtext">
                    {t('drawer.no_reports')}
                  </p>
                ) : (
                  <div className="drawer-reports-list">
                    {featureData.reports.map((rep) => (
                      <div key={rep.id} className="drawer-report-card">
                        <div className="report-card-top">
                          <span className="badge badge-category">
                            {t(`categories.${rep.category}`, rep.category)}
                          </span>
                          <span className={`badge badge-status-${rep.status}`}>
                            {t(`status.${rep.status}`, rep.status)}
                          </span>
                          {rep.is_simulated && (
                            <span className="badge badge-simulated">
                              {t('app.simulated_badge')}
                            </span>
                          )}
                        </div>
                        {rep.description && (
                          <p className="report-card-desc">{rep.description}</p>
                        )}
                        <span className="report-card-date">
                          Reported: {new Date(rep.created_at).toLocaleDateString()}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
