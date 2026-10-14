import React from 'react';
import { Layers, MapPin, AlertCircle, Compass } from 'lucide-react';

export default function SegmentInspector({ selectedSegment, riskData }) {
  if (!selectedSegment) {
    return (
      <div className="card">
        <div className="card-title">
          <span>Segment Inspector</span>
          <Layers size={16} />
        </div>
        <div className="inspector-empty">
          <Compass size={32} style={{ margin: '0 auto 8px auto', display: 'block', color: 'var(--text-dim)' }} />
          Click any road segment on the corridor map to inspect terrain characteristics and advisory risk output.
        </div>
      </div>
    );
  }

  const { id, properties } = selectedSegment;
  // Match with risk data item if available
  const riskItem = riskData?.segments?.find((s) => s.segment_id === id);

  const getTierColor = (tier) => {
    switch (tier) {
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
    <div className="card">
      <div className="card-title">
        <span>Segment Inspector</span>
        <MapPin size={16} style={{ color: 'var(--accent-secondary)' }} />
      </div>

      <div className="inspector-list">
        <div className="inspector-row">
          <span className="inspector-label">Segment ID</span>
          <span className="inspector-value" style={{ fontSize: 12 }}>{id}</span>
        </div>

        <div className="inspector-row">
          <span className="inspector-label">Risk Tier</span>
          <span
            className="inspector-value"
            style={{
              color: getTierColor(riskItem?.risk_tier),
              fontWeight: 700,
            }}
          >
            {riskItem ? riskItem.risk_tier : 'Unknown'}
          </span>
        </div>

        <div className="inspector-row">
          <span className="inspector-label">Advisory Risk Score</span>
          <span className="inspector-value">
            {riskItem?.risk_score !== null && riskItem?.risk_score !== undefined
              ? `${(riskItem.risk_score * 100).toFixed(1)}% (${riskItem.risk_score.toFixed(4)})`
              : 'N/A (Missing/Stale)'}
          </span>
        </div>

        <div className="inspector-row">
          <span className="inspector-label">Data Status</span>
          <span className="inspector-value" style={{ color: riskItem?.status === 'OK' ? 'var(--success)' : 'var(--warning)' }}>
            {riskItem ? riskItem.status : 'N/A'}
          </span>
        </div>

        <div className="inspector-row">
          <span className="inspector-label">Segment Length</span>
          <span className="inspector-value">
            {properties?.length_m ? `${properties.length_m} m (${(properties.length_m / 1000).toFixed(2)} km)` : 'N/A'}
          </span>
        </div>

        <div className="inspector-row">
          <span className="inspector-label">Terrain Slope</span>
          <span className="inspector-value">
            {properties?.slope !== undefined ? `${(properties.slope * 100).toFixed(1)}%` : 'N/A'}
          </span>
        </div>

        <div className="inspector-row">
          <span className="inspector-label">Elevation</span>
          <span className="inspector-value">
            {properties?.elevation_m ? `${properties.elevation_m} m ASL` : 'N/A'}
          </span>
        </div>

        <div className="inspector-row">
          <span className="inspector-label">Highway / Ref</span>
          <span className="inspector-value">
            {properties?.ref || 'NH44'} ({properties?.highway || 'trunk'})
          </span>
        </div>
      </div>

      <div
        style={{
          marginTop: 14,
          padding: '8px 10px',
          background: 'var(--info-bg)',
          borderRadius: 6,
          fontSize: 11,
          color: 'var(--info-text)',
          lineHeight: 1.4,
        }}
      >
        <AlertCircle size={13} style={{ display: 'inline', marginRight: 4, verticalAlign: 'middle' }} />
        Predictions are conditioned on 7-day preceding ERA5-Land environmental windows.
      </div>
    </div>
  );
}
