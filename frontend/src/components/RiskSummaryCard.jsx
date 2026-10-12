import React from 'react';
import { ShieldAlert, Info } from 'lucide-react';

export default function RiskSummaryCard({ summary, metadata }) {
  if (!summary) return null;

  return (
    <div className="card">
      <div className="card-title">
        <span>Corridor Risk Breakdown</span>
        <ShieldAlert size={16} />
      </div>

      <div className="summary-grid">
        <div className="summary-pill pill-high">
          <span className="pill-count">{summary.high_risk_count}</span>
          <span className="pill-label">High Risk (≥0.35)</span>
        </div>

        <div className="summary-pill pill-med">
          <span className="pill-count">{summary.medium_risk_count}</span>
          <span className="pill-label">Medium Risk (0.10–0.35)</span>
        </div>

        <div className="summary-pill pill-low">
          <span className="pill-count">{summary.low_risk_count}</span>
          <span className="pill-label">Low Risk (&lt;0.10)</span>
        </div>

        <div className="summary-pill pill-unknown">
          <span className="pill-count">{summary.unknown_count}</span>
          <span className="pill-label">Unknown / Stale</span>
        </div>
      </div>

      {/* Threshold Legend */}
      <div className="legend-box">
        <div style={{ fontWeight: 600, color: '#94a3b8', marginBottom: 2 }}>
          Operational Threshold Legend
        </div>
        <div className="legend-row">
          <span>
            <span className="legend-bullet" style={{ background: '#ef4444' }}></span>
            High Hazard Risk (Score ≥ 0.35)
          </span>
          <span style={{ color: '#94a3b8' }}>Advisory: Hold / Delay</span>
        </div>
        <div className="legend-row">
          <span>
            <span className="legend-bullet" style={{ background: '#f59e0b' }}></span>
            Elevated Hazard Risk (0.10 ≤ Score &lt; 0.35)
          </span>
          <span style={{ color: '#94a3b8' }}>Proceed with Caution</span>
        </div>
        <div className="legend-row">
          <span>
            <span className="legend-bullet" style={{ background: '#10b981' }}></span>
            Baseline / Low Risk (Score &lt; 0.10)
          </span>
          <span style={{ color: '#94a3b8' }}>Standard Highway Flow</span>
        </div>
      </div>

      <div style={{ marginTop: 12, fontSize: 11, color: '#64748b', lineHeight: 1.4 }}>
        <Info size={12} style={{ display: 'inline', marginRight: 4, verticalAlign: 'middle' }} />
        Thresholds were calibrated and frozen on the 2023 validation set ($\tau=0.10, 0.35$)
        bounding false negatives while maintaining high negative predictive value.
      </div>
    </div>
  );
}
