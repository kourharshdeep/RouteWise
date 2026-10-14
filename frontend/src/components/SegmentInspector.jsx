import React, { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Layers,
  MapPin,
  AlertCircle,
  Compass,
  Mountain,
  CloudRain,
  Shield,
  Clock,
  ExternalLink,
} from 'lucide-react';
import { fetchSegmentFeatures } from '../services/api';

export default function SegmentInspector({
  selectedSegment,
  riskData,
  selectedDate,
  geojson,
}) {
  const { t } = useTranslation();
  const [features, setFeatures] = useState(null);
  const [loadingFeatures, setLoadingFeatures] = useState(false);

  // Normalize selectedSegment (whether passed as string id or full GeoJSON feature)
  let segmentId = null;
  let properties = null;

  if (selectedSegment) {
    if (typeof selectedSegment === 'string') {
      segmentId = selectedSegment;
      const feat = geojson?.features?.find((f) => f.id === segmentId);
      properties = feat?.properties || {};
    } else {
      segmentId = selectedSegment.id || selectedSegment.segment_id;
      properties = selectedSegment.properties || {};
    }
  }

  // Fetch real contributing environmental factors (ERA5 weather + terrain)
  useEffect(() => {
    let isMounted = true;
    async function loadData() {
      if (!segmentId) {
        setFeatures(null);
        return;
      }
      try {
        setLoadingFeatures(true);
        const data = await fetchSegmentFeatures(segmentId, selectedDate || '2023-07-09');
        if (isMounted) setFeatures(data);
      } catch (err) {
        if (isMounted) setFeatures(null);
      } finally {
        if (isMounted) setLoadingFeatures(false);
      }
    }
    loadData();
    return () => {
      isMounted = false;
    };
  }, [segmentId, selectedDate]);

  if (!segmentId) {
    return (
      <div className="card">
        <div className="card-title">
          <span>{t('inspector.title')}</span>
          <Layers size={16} />
        </div>
        <div className="inspector-empty">
          <Compass size={32} style={{ margin: '0 auto 8px auto', display: 'block', color: 'var(--text-dim)' }} />
          {t('inspector.empty')}
        </div>
      </div>
    );
  }

  // Match with ST-GNN risk output
  const riskItem = riskData?.segments?.find((s) => s.segment_id === segmentId);
  const tier = riskItem?.risk_tier || 'Low';

  const getTierColor = (t) => {
    switch (t) {
      case 'High':
        return 'var(--risk-high)';
      case 'Medium':
        return 'var(--risk-medium)';
      case 'Low':
        return 'var(--risk-low)';
      default:
        return 'var(--risk-unknown)';
    }
  };

  return (
    <div className="card" role="region" aria-label="Highway Segment Inspector">
      <div className="card-title">
        <span>{t('inspector.title')}</span>
        <MapPin size={16} style={{ color: 'var(--accent-secondary)' }} />
      </div>

      <div className="inspector-list">
        {/* Segment Identity & Tier */}
        <div className="inspector-row">
          <span className="inspector-label">{t('inspector.segment_id')}</span>
          <span className="inspector-value" style={{ fontSize: 12, fontFamily: 'monospace' }}>
            {segmentId}
          </span>
        </div>

        <div className="inspector-row">
          <span className="inspector-label">{t('inspector.risk_tier')}</span>
          <span
            className="inspector-value"
            style={{
              color: getTierColor(tier),
              fontWeight: 700,
            }}
          >
            {t(`risk.${tier.toLowerCase()}`, tier)}
          </span>
        </div>

        <div className="inspector-row">
          <span className="inspector-label">{t('inspector.risk_score')}</span>
          <span className="inspector-value" style={{ fontWeight: 700 }}>
            {riskItem?.risk_score !== null && riskItem?.risk_score !== undefined
              ? `${(riskItem.risk_score * 100).toFixed(1)}% (${riskItem.risk_score.toFixed(4)})`
              : 'N/A (Missing)'}
          </span>
        </div>

        <div className="inspector-row">
          <span className="inspector-label">{t('inspector.data_status')}</span>
          <span
            className="inspector-value"
            style={{ color: riskItem?.status === 'OK' ? 'var(--success)' : 'var(--warning)' }}
          >
            {riskItem ? riskItem.status : 'OK'}
          </span>
        </div>

        {/* Contributing Factors Section 1: Physical Highway Terrain */}
        <div className="inspector-section-divider">
          <Mountain size={13} />
          <span>Physical Terrain (SRTM DEM)</span>
        </div>

        <div className="inspector-row">
          <span className="inspector-label">{t('inspector.length')}</span>
          <span className="inspector-value">
            {properties?.length_m
              ? `${properties.length_m} m (${(properties.length_m / 1000).toFixed(2)} km)`
              : features?.length_m
              ? `${features.length_m} m`
              : 'N/A'}
          </span>
        </div>

        <div className="inspector-row">
          <span className="inspector-label">{t('inspector.slope')}</span>
          <span className="inspector-value">
            {properties?.slope !== undefined
              ? `${(properties.slope * 100).toFixed(1)}%`
              : features?.slope_pct !== undefined
              ? `${features.slope_pct}% (${features.slope_deg}°)`
              : 'N/A'}
          </span>
        </div>

        <div className="inspector-row">
          <span className="inspector-label">{t('inspector.elevation')}</span>
          <span className="inspector-value">
            {properties?.elevation_m
              ? `${Math.round(properties.elevation_m)} m ASL`
              : features?.elevation_m
              ? `${Math.round(features.elevation_m)} m ASL`
              : 'N/A'}
          </span>
        </div>

        <div className="inspector-row">
          <span className="inspector-label">{t('inspector.highway')}</span>
          <span className="inspector-value" style={{ textTransform: 'uppercase' }}>
            {properties?.ref || 'NH44'} ({properties?.highway || 'trunk'})
          </span>
        </div>

        {/* Contributing Factors Section 2: Meteorological Reanalysis Inputs */}
        <div className="inspector-section-divider">
          <CloudRain size={13} />
          <span>{t('inspector.environmental_factors')}</span>
        </div>

        {features?.weather ? (
          <>
            <div className="inspector-row">
              <span className="inspector-label">{t('inspector.daily_precip')}</span>
              <span className="inspector-value" style={{ fontWeight: 600 }}>
                {features.weather.precip_mm} mm
              </span>
            </div>
            <div className="inspector-row">
              <span className="inspector-label">{t('inspector.precip_7d')}</span>
              <span className="inspector-value" style={{ fontWeight: 600 }}>
                {features.weather.precip_7d_mm} mm
              </span>
            </div>
            <div className="inspector-row">
              <span className="inspector-label">{t('inspector.temperature')}</span>
              <span className="inspector-value">
                {features.weather.temp_mean_c} °C
              </span>
            </div>
            <div className="inspector-row">
              <span className="inspector-label">{t('inspector.snow_depth')}</span>
              <span className="inspector-value">
                {features.weather.snow_depth_m > 0 ? `${features.weather.snow_depth_m} m` : '0.0 mm'}
              </span>
            </div>
          </>
        ) : (
          <div className="inspector-note-dim">
            ERA5-Land reanalysis inputs active for date: {selectedDate || '2023-07-09'}
          </div>
        )}

        {/* Linked Incident Reports */}
        <div className="inspector-section-divider">
          <Shield size={13} />
          <span>{t('inspector.linked_reports')}</span>
        </div>

        {features?.reports && features.reports.length > 0 ? (
          <div className="inspector-reports-mini-list">
            {features.reports.map((rep) => {
              const isVerified = rep.status === 'verified' || rep.status === 'assigned';
              return (
                <div key={rep.id} className="inspector-report-mini-item">
                  <div className="report-mini-badges">
                    <span className={`badge ${isVerified ? 'badge-verified' : 'badge-unverified'}`}>
                      {isVerified ? t('inspector.verified_badge') : t('inspector.unverified_badge')}
                    </span>
                    <span className="badge badge-category">
                      {t(`categories.${rep.category}`, rep.category)}
                    </span>
                  </div>
                  {rep.description && (
                    <p className="report-mini-desc">{rep.description}</p>
                  )}
                  <span className="report-mini-date">
                    {new Date(rep.created_at).toLocaleDateString()}
                  </span>
                </div>
              );
            })}
          </div>
        ) : (
          <div className="inspector-note-dim">
            {t('inspector.no_reports')}
          </div>
        )}
      </div>

      {/* Retrospective Science Disclaimer */}
      <div className="inspector-retrospective-banner">
        <AlertCircle size={13} style={{ flexShrink: 0, marginTop: 1 }} />
        <div>
          <strong>{t('app.retrospective_badge')}:</strong> {t('map.retrospective_disclaimer')}
        </div>
      </div>
    </div>
  );
}
