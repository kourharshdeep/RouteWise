import React, { useRef, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { AlertTriangle, CheckCircle, Info, ShieldAlert } from 'lucide-react';

const LANDMARKS = [
  { index: 0, name: 'Dewal', chainage: 'Km 0' },
  { index: 22, name: 'Cafeteria Morh', chainage: 'Km 5.4' },
  { index: 41, name: 'Ramban', chainage: 'Km 10.2' },
  { index: 65, name: 'Seri', chainage: 'Km 16.0' },
  { index: 88, name: 'Maroog', chainage: 'Km 21.5' },
  { index: 110, name: 'Digdol', chainage: 'Km 26.8' },
  { index: 132, name: 'Ramsu', chainage: 'Km 31.4' },
  { index: 150, name: 'Banihal', chainage: 'Km 36.0' },
];

export default function CorridorStrip({
  riskData,
  selectedSegmentId,
  onSelectSegment,
  selectedDate,
}) {
  const { t } = useTranslation();
  const stripRef = useRef(null);

  const segments = riskData?.segments || [];
  const riskLookup = {};
  segments.forEach((s) => {
    riskLookup[s.segment_id] = s;
  });

  const handleKeyDown = (e, idx) => {
    if (e.key === 'ArrowRight' && idx < segments.length - 1) {
      e.preventDefault();
      onSelectSegment(segments[idx + 1].segment_id);
    } else if (e.key === 'ArrowLeft' && idx > 0) {
      e.preventDefault();
      onSelectSegment(segments[idx - 1].segment_id);
    } else if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      onSelectSegment(segments[idx].segment_id);
    }
  };

  return (
    <div className="corridor-strip-card" role="region" aria-label="Corridor Segment Risk Strip">
      <div className="corridor-strip-header">
        <div className="corridor-strip-title">
          <span className="strip-dot" />
          <strong>NH-44 Ramban–Banihal Continuous Corridor Strip</strong>
          <span className="badge badge-subtle">{selectedDate}</span>
          <span className="badge badge-retrospective">{t('app.retrospective_badge')}</span>
        </div>
        <div className="corridor-strip-legend" aria-hidden="true">
          <span className="legend-chip chip-low">
            <span className="pattern-circle" /> {t('risk.low')} (&lt;0.10)
          </span>
          <span className="legend-chip chip-med">
            <span className="pattern-stripe" /> {t('risk.medium')} (0.10–0.35)
          </span>
          <span className="legend-chip chip-high">
            <span className="pattern-cross" /> {t('risk.high')} (≥0.35)
          </span>
        </div>
      </div>

      {/* Chainage Landmarks Header */}
      <div className="corridor-landmarks-track">
        {LANDMARKS.map((lm) => {
          const pct = (lm.index / 150) * 100;
          return (
            <div
              key={lm.name}
              className="landmark-marker"
              style={{ left: `${pct}%` }}
              title={`${lm.name} (${lm.chainage})`}
            >
              <div className="landmark-tick" />
              <span className="landmark-label">{lm.name}</span>
            </div>
          );
        })}
      </div>

      {/* Horizontal Segment Track */}
      <div className="corridor-strip-container" ref={stripRef} tabIndex={0} aria-label="Corridor Segments list">
        <div className="corridor-strip-track">
          {segments.length === 0 ? (
            <div className="strip-empty-placeholder">Loading 151 corridor segments...</div>
          ) : (
            segments.map((seg, idx) => {
              const score = seg.risk_score ?? 0;
              const tier = seg.risk_tier || 'Low';
              const isSelected = selectedSegmentId === seg.segment_id;

              let tierClass = 'seg-low';
              let accessibilityIcon = '●';
              if (tier === 'High') {
                tierClass = 'seg-high';
                accessibilityIcon = '▲';
              } else if (tier === 'Medium') {
                tierClass = 'seg-medium';
                accessibilityIcon = '■';
              }

              return (
                <button
                  key={seg.segment_id}
                  type="button"
                  id={`corridor-seg-${idx}`}
                  className={`corridor-seg-bar ${tierClass} ${isSelected ? 'selected' : ''}`}
                  onClick={() => onSelectSegment(seg.segment_id)}
                  onKeyDown={(e) => handleKeyDown(e, idx)}
                  aria-label={`Segment ${idx + 1}: ${tier} risk, score ${score.toFixed(3)}`}
                  title={`Segment ${idx + 1} (${seg.segment_id})\nRisk: ${tier} (${score.toFixed(3)})\nClick to inspect input features`}
                >
                  <span className="seg-cues" aria-hidden="true">
                    {accessibilityIcon}
                  </span>
                </button>
              );
            })
          )}
        </div>
      </div>

      <div className="corridor-strip-footer">
        <span className="strip-help-text">
          Use <strong>← / →</strong> keyboard arrows or click any segment bar to view real slope, rainfall features, and field incident reports in the Risk Drawer.
        </span>
      </div>
    </div>
  );
}
