import React, { useRef, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import sortedSegmentIds from '../data/corridorSegmentsSorted.json';
import { getSegmentAccessibilityCue } from '../services/liveModeHelper.js';

const LANDMARKS = [
  { index: 0, name: 'Chanderkot', chainage: 'Km 0' },
  { index: 26, name: 'Cafeteria Morh', chainage: 'Km 5.4' },
  { index: 44, name: 'Ramban', chainage: 'Km 10.2' },
  { index: 51, name: 'Digdol', chainage: 'Km 21.5' },
  { index: 79, name: 'Ramsu', chainage: 'Km 31.4' },
  { index: 140, name: 'Banihal', chainage: 'Km 36.0' },
];

export default function CorridorStrip({
  riskData,
  selectedSegmentId,
  onSelectSegment,
  selectedDate,
  mode = 'historical',
  isLiveUpdated = false,
}) {
  const { t } = useTranslation();
  const stripRef = useRef(null);
  const isLive = mode === 'live';

  // Monotonically ordered segments from South (Chanderkot/Ramban) to North (Banihal)
  const segments = useMemo(() => {
    const raw = riskData?.segments || [];
    const lookup = {};
    raw.forEach((s) => {
      lookup[s.segment_id] = s;
    });
    return sortedSegmentIds.map((id) => lookup[id] || { segment_id: id, risk_score: null, risk_tier: 'UNKNOWN' });
  }, [riskData]);

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
          {isLive ? (
            <>
              <span className="badge badge-subtle">{selectedDate}</span>
              <span className="badge badge-subtle">{t('live.live_mode')}</span>
              <span className="badge badge-warning" style={{ fontSize: 10 }}>
                {t('live.experimental_badge')}
              </span>
            </>
          ) : (
            <>
              <span className="badge badge-subtle">{selectedDate}</span>
              <span className="badge badge-retrospective">{t('app.retrospective_badge')}</span>
            </>
          )}
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
          <span className="legend-chip chip-unknown">
            <span style={{ fontSize: 9 }}>?</span> {t('risk.unknown')}
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

      {/* Horizontal Segment Track with subtle live update flash */}
      <div
        className={`corridor-strip-container ${isLiveUpdated ? 'live-update-flash' : ''}`}
        ref={stripRef}
        tabIndex={0}
        aria-label="Corridor Segments list"
      >
        <div className="corridor-strip-track">
          {segments.length === 0 ? (
            <div className="strip-empty-placeholder">Loading 151 corridor segments...</div>
          ) : (
            segments.map((seg, idx) => {
              const score = seg.risk_score;
              const tier = seg.risk_tier || 'UNKNOWN';
              const isSelected = selectedSegmentId === seg.segment_id;
              const opStatus = seg.operational_status;
              const hasEvents = seg.active_events && seg.active_events.length > 0;

              const cue = getSegmentAccessibilityCue(tier, seg.status, seg.is_stale, t);
              const accessibilityIcon = cue.symbol;
              const tierClass = isLive && (seg.is_stale || seg.status === 'STALE_DATA')
                ? 'seg-unknown chip-stale'
                : tier === 'High'
                ? 'seg-high'
                : tier === 'Medium'
                ? 'seg-medium'
                : tier === 'Low'
                ? 'seg-low'
                : 'seg-unknown';

              const scoreLabel = score !== null && score !== undefined ? score.toFixed(3) : 'N/A';
              const opLabel = opStatus ? `\nStatus: ${opStatus}` : '';
              const evLabel = hasEvents ? `\nEvents: ${seg.active_events.map((e) => e.hazard_type).join(', ')}` : '';

              return (
                <button
                  key={seg.segment_id}
                  type="button"
                  id={`corridor-seg-${idx}`}
                  className={`corridor-seg-bar ${tierClass} ${isSelected ? 'selected' : ''}`}
                  onClick={() => onSelectSegment(seg.segment_id)}
                  onKeyDown={(e) => handleKeyDown(e, idx)}
                  aria-label={`Segment ${idx + 1}: ${cue.ariaLabel}, score ${scoreLabel}${opStatus ? `, status ${opStatus}` : ''}`}
                  title={`Segment ${idx + 1} (${seg.segment_id})\nRisk: ${tier} (${scoreLabel})${opLabel}${evLabel}\nClick to inspect features`}
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
          Use <strong>← / →</strong> keyboard arrows or click any segment bar to view real slope, rainfall features, and incident reports in the Risk Drawer.
        </span>
      </div>
    </div>
  );
}
