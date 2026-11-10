import React, { useState, useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { RESILIENCE_CONFIG, shouldRefreshPlanner, hasRecommendationChanged } from '../services/connectionResilience';
import { getPlannerModeConfig, getDefaultDepartureTime } from '../services/plannerModeHelper';
import { useJourney } from '../context/JourneyContext';
import VehicleSelector from './VehicleSelector';
import {
  MapPin,
  Calendar,
  Clock,
  Navigation,
  AlertTriangle,
  CheckCircle2,
  AlertOctagon,
  ChevronDown,
  ChevronUp,
  RefreshCw,
  TrendingUp,
  Shield,
  Layers,
  Sparkles,
} from 'lucide-react';

export default function JourneyPlanner({
  onNavigateToMap,
  mode = "historical",
  lastRouteUpdate = null,
  riskData = null,
}) {
  const {
    vehicleType,
    origin,
    setOrigin,
    destination,
    setDestination,
    journeyDate,
    setJourneyDate,
    departureTime,
    setDepartureTime,
    arrivalDeadline,
    setArrivalDeadline,
    places,
    planResult,
    previousPlanResult,
    isPlanning,
    planError,
    executePlan,
  } = useJourney();

  const [showItinerary, setShowItinerary] = useState(false);
  const [showPreviousComparison, setShowPreviousComparison] = useState(false);

  const benchmarkDates = [
    { date: '2023-07-09', label: 'Monsoon Cloudburst (Benchmark)' },
    { date: '2024-03-15', label: 'Spring Thaw Event' },
    { date: '2022-01-20', label: 'Winter Snowstorm' },
    { date: '2025-08-10', label: 'Summer Moderate' },
  ];

  const { t } = useTranslation();
  const config = getPlannerModeConfig({
    mode,
    liveAsOf: riskData?.as_of,
    weatherWindowEnd: riskData?.weather_window_end,
    replayDate: mode === 'replay' ? (riskData?.as_of || '2023-07-09') : null,
  });

  useEffect(() => {
    if (mode === 'live' && departureTime === '08:00') {
      setDepartureTime(getDefaultDepartureTime());
    }
  }, [mode]);

  const [autoRefreshedAt, setAutoRefreshedAt] = useState(null);
  const [recommendationDiffNotice, setRecommendationDiffNotice] = useState(null);
  const autoRefreshTimerRef = useRef(null);
  const isExecutingRef = useRef(false);
  const prevRouteUpdateRef = useRef(lastRouteUpdate);
  const prevRiskUpdateRef = useRef(riskData?.computed_at);

  useEffect(() => {
    isExecutingRef.current = isPlanning;
  }, [isPlanning]);

  useEffect(() => {
    const routeChanged = Boolean(lastRouteUpdate) && lastRouteUpdate !== prevRouteUpdateRef.current;
    const riskChanged = Boolean(riskData?.computed_at) && riskData?.computed_at !== prevRiskUpdateRef.current;
    prevRouteUpdateRef.current = lastRouteUpdate;
    prevRiskUpdateRef.current = riskData?.computed_at;

    if (!routeChanged && !riskChanged) {
      return;
    }

    if (!shouldRefreshPlanner({
      mode,
      hasActivePlan: Boolean(planResult),
      isPlanning: isExecutingRef.current,
      isTabVisible: typeof document !== 'undefined' ? !document.hidden : true,
      changeDetected: true,
    })) {
      return;
    }

    if (autoRefreshTimerRef.current) {
      clearTimeout(autoRefreshTimerRef.current);
    }

    autoRefreshTimerRef.current = setTimeout(async () => {
      if (isExecutingRef.current) return;
      try {
        const prevRec = planResult?.recommendation;
        const newRes = await executePlan({ mode });
        const now = new Date();
        const timeStr = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
        setAutoRefreshedAt(timeStr);
        if (newRes && prevRec && hasRecommendationChanged(prevRec, newRes.recommendation)) {
          setRecommendationDiffNotice({
            oldRec: prevRec,
            newRec: newRes.recommendation,
            time: timeStr,
          });
        }
      } catch (err) {
        console.warn("Planner auto-refresh error:", err);
      }
    }, RESILIENCE_CONFIG.DEBOUNCE_REFRESH_MS);

    return () => {
      if (autoRefreshTimerRef.current) {
        clearTimeout(autoRefreshTimerRef.current);
      }
    };
  }, [lastRouteUpdate, riskData?.computed_at, mode, planResult, executePlan]);

  const handlePlanSubmit = async (e) => {
    e.preventDefault();
    try {
      await executePlan({
        mode,
        date: config.isLive ? (config.evaluationDate || undefined) : undefined,
      });
    } catch (err) {
      // handled
    }
  };

  const renderRecommendation = (rec, reason, blocking) => {
    switch (rec) {
      case 'HOLD':
        return (
          <div className="recommendation-banner hold" data-testid="recommendation-hold">
            <AlertOctagon size={20} style={{ flexShrink: 0, marginTop: 2 }} />
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                <span className="badge badge-disconnected" style={{ fontSize: 13, fontWeight: 700 }}>HOLD — CORRIDOR CLOSED</span>
                {blocking && blocking.length > 0 && (
                  <span style={{ fontSize: 12, opacity: 0.9 }}>Blocked by segment(s): {blocking.join(', ')}</span>
                )}
              </div>
              <p style={{ marginTop: 6, fontSize: 13, lineHeight: 1.4, margin: '6px 0 0 0' }}>{reason}</p>
            </div>
          </div>
        );
      case 'DELAY':
        return (
          <div className="recommendation-banner delay" data-testid="recommendation-delay">
            <AlertTriangle size={20} style={{ flexShrink: 0, marginTop: 2 }} />
            <div>
              <span className="badge badge-pill" style={{ color: '#f97316', borderColor: '#f97316', fontSize: 13, fontWeight: 700 }}>DELAY — HIGH HAZARD</span>
              <p style={{ marginTop: 6, fontSize: 13, lineHeight: 1.4, margin: '6px 0 0 0' }}>{reason}</p>
            </div>
          </div>
        );
      case 'PROCEED_WITH_CAUTION':
        return (
          <div className="recommendation-banner caution" data-testid="recommendation-caution">
            <AlertTriangle size={20} style={{ flexShrink: 0, marginTop: 2 }} />
            <div>
              <span className="badge badge-pill" style={{ color: '#eab308', borderColor: '#eab308', fontSize: 13, fontWeight: 700 }}>PROCEED WITH CAUTION</span>
              <p style={{ marginTop: 6, fontSize: 13, lineHeight: 1.4, margin: '6px 0 0 0' }}>{reason}</p>
            </div>
          </div>
        );
      case 'NO_DATA':
        return (
          <div className="recommendation-banner no_data" data-testid="recommendation-no-data">
            <AlertTriangle size={20} style={{ flexShrink: 0, marginTop: 2 }} />
            <div>
              <span className="badge badge-pill" style={{ color: 'var(--text-muted)', borderColor: 'var(--text-muted)', fontSize: 13, fontWeight: 700 }}>NO DATA — TELEMETRY UNKNOWN/STALE</span>
              <p style={{ marginTop: 6, fontSize: 13, lineHeight: 1.4, margin: '6px 0 0 0' }}>{reason}</p>
            </div>
          </div>
        );
      default:
        return (
          <div className="recommendation-banner proceed" data-testid="recommendation-proceed">
            <CheckCircle2 size={20} style={{ flexShrink: 0, marginTop: 2 }} />
            <div>
              <span className="badge badge-connected" style={{ fontSize: 13, fontWeight: 700 }}>PROCEED — BASELINE CLEAR</span>
              <p style={{ marginTop: 6, fontSize: 13, lineHeight: 1.4, margin: '6px 0 0 0' }}>{reason}</p>
            </div>
          </div>
        );
    }
  };

  const getRiskBadge = (risk) => {
    switch (risk?.toLowerCase()) {
      case 'high':
        return (
          <span className="risk-tag risk-tag-high">
            <AlertOctagon size={14} /> High Hazard Corridor Stretch
          </span>
        );
      case 'medium':
        return (
          <span className="risk-tag risk-tag-med">
            <AlertTriangle size={14} /> Elevated Hazard Advisory
          </span>
        );
      case 'unknown':
        return (
          <span
            className="risk-tag"
            style={{
              background: 'rgba(156, 163, 175, 0.15)',
              color: 'var(--text-muted)',
              border: '1px solid rgba(156, 163, 175, 0.4)',
            }}
          >
            <AlertTriangle size={14} /> Unknown Hazard Level (Incomplete Data)
          </span>
        );
      default:
        return (
          <span className="risk-tag risk-tag-low">
            <CheckCircle2 size={14} /> Baseline / Low Risk Route
          </span>
        );
    }
  };

  const getDeadlineBadge = (status) => {
    if (!status) return null;
    if (status === 'Achievable') {
      return <span className="badge badge-connected">Deadline Achievable</span>;
    } else if (status === 'At Risk') {
      return (
        <span
          className="badge badge-pill"
          style={{ color: 'var(--warning)', borderColor: 'var(--warning-border)' }}
        >
          Deadline At Risk (&lt;20m buffer)
        </span>
      );
    } else {
      return <span className="badge badge-disconnected">Arrival Deadline Exceeded</span>;
    }
  };

  return (
    <div className="planner-container">
      {/* Page Header */}
      <div className="planner-header-card">
        <div className="planner-header-content">
          <div className="brand-section">
            <div className="brand-icon">
              <Navigation size={22} />
            </div>
            <div>
              <h2>Corridor Journey Planning & Route Hazard Analysis</h2>
              <p>NH-44 Ramban–Banihal Mountain Highway • Integrated ST-GNN Risk Profiler</p>
            </div>
          </div>
        </div>

        {/* Retrospective Science Banner & Single-Path Corridor Honesty Notice */}
        <div className={`retrospective-banner ${config.isLive ? 'live-banner-style' : config.isReplay ? 'replay-banner-style' : ''}`}>
          <AlertTriangle size={16} style={{ flexShrink: 0, marginTop: 2 }} />
          <div>
            <strong>{t(config.headerNoticeTitleKey, config.headerNoticeTitleText)}</strong>{' '}
            {t('planner.linear_topology_notice', 'The NH-44 Ramban–Banihal section is a single continuous linear mountain highway; topological alternative paths (such as parallel bypasses) do not exist within this corridor road graph. Consequently, fastest and safest routes follow the identical physical sequence of segments.')}

            <div style={{ marginTop: 6, fontSize: 12, opacity: 0.9 }}>
              • <strong>{t('planner.vehicle_type_label', 'Vehicle type:')}</strong> {t('planner.vehicle_type_notice', 'Configures speed thresholds and hazard vulnerability advisories, but does not alter physical highway geometry.')}
              <br />
              • <strong>{t('planner.departure_time_label', 'Departure time:')}</strong> {t(config.departureTimeNoticeKey, config.departureTimeNoticeText)}
            </div>
          </div>
        </div>
      </div>

      {/* Real-time SSE Route Update Notification */}
      {lastRouteUpdate && planResult && mode === 'live' && (
        <div className="route-update-notification">
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <Clock size={16} style={{ color: 'var(--accent-primary)' }} />
            <span>
              <strong>Route updated at {lastRouteUpdate.time}</strong> — <em>{lastRouteUpdate.reason}</em>
            </span>
          </div>
          <button
            type="button"
            className="sample-btn"
            style={{ padding: '4px 10px', fontSize: 12 }}
            onClick={() => executePlan({ mode })}
          >
            Re-evaluate Route
          </button>
        </div>
      )}

      {/* Main Planning Form */}
      <form onSubmit={handlePlanSubmit} className="planner-form-card">
        {/* Step 1: Vehicle Type */}
        <div className="form-section">
          <VehicleSelector />
        </div>

        <div className="form-divider" />

        {/* Step 2: Route Origin & Destination */}
        <div className="form-section">
          <label className="section-label">Select Corridor Segment Termini</label>
          <div className="route-select-grid">
            <div className="form-group">
              <label>
                <MapPin size={14} style={{ display: 'inline', marginRight: 4, color: 'var(--accent-secondary)' }} />
                Departure Origin Point:
              </label>
              <select
                value={origin}
                onChange={(e) => setOrigin(e.target.value)}
                className="custom-select"
              >
                {places.map((p) => (
                  <option key={p.id} value={p.name}>
                    {p.name} ({p.lat.toFixed(3)}°N, {p.lon.toFixed(3)}°E)
                  </option>
                ))}
              </select>
            </div>

            <div className="form-group">
              <label>
                <MapPin size={14} style={{ display: 'inline', marginRight: 4, color: 'var(--danger)' }} />
                Arrival Destination:
              </label>
              <select
                value={destination}
                onChange={(e) => setDestination(e.target.value)}
                className="custom-select"
              >
                {places.map((p) => (
                  <option key={p.id} value={p.name}>
                    {p.name} ({p.lat.toFixed(3)}°N, {p.lon.toFixed(3)}°E)
                  </option>
                ))}
              </select>
            </div>
          </div>
        </div>

        <div className="form-divider" />

        {/* Step 3: Date & Departure Timings */}
        <div className="form-section">
          <label className="section-label">{t(config.scheduleTitleKey, config.scheduleTitleText)}</label>
          <div className="timings-grid">
            <div className="form-group">
              <label>
                <Calendar size={14} style={{ display: 'inline', marginRight: 4, color: 'var(--text-muted)' }} />
                {t('planner.evaluation_date', 'Journey Evaluation Date:')}
              </label>
              {config.isDateEditable ? (
                <input
                  type="date"
                  value={journeyDate}
                  min="2021-01-06"
                  max="2025-12-31"
                  onChange={(e) => setJourneyDate(e.target.value)}
                  className="date-input"
                  required
                />
              ) : (
                <div className="planner-readonly-date-container">
                  <div className="planner-readonly-date">
                    <span className="planner-date-value">{config.evaluationDate}</span>
                    <span className={`planner-mode-badge ${config.statusBadgeClass}`}>
                      {t(config.statusBadgeKey, config.statusBadgeText)}
                    </span>
                  </div>
                  {config.weatherWindowEnd && (
                    <div className="planner-window-end-text">
                      {t('planner.weather_window_through', 'Weather window through')}: {config.weatherWindowEnd}
                    </div>
                  )}
                  {config.isLive && (
                    <div className="planner-experimental-note">
                      {t('planner.experimental_warning', 'Experimental - not validated for life-safety')}
                    </div>
                  )}
                </div>
              )}
            </div>

            <div className="form-group">
              <label>
                <Clock size={14} style={{ display: 'inline', marginRight: 4, color: 'var(--text-muted)' }} />
                {t('planner.departure_time_label', 'Preferred Departure Time:')}
              </label>
              <input
                type="time"
                value={departureTime}
                onChange={(e) => setDepartureTime(e.target.value)}
                className="date-input"
                required
              />
              {config.departureHelpKey && (
                <div className="departure-daily-help">
                  {t(config.departureHelpKey, config.departureHelpText)}
                </div>
              )}
            </div>

            <div className="form-group">
              <label>
                <Clock size={14} style={{ display: 'inline', marginRight: 4, color: 'var(--text-muted)' }} />
                Target Arrival Deadline (Optional):
              </label>
              <input
                type="time"
                value={arrivalDeadline}
                onChange={(e) => setArrivalDeadline(e.target.value)}
                className="date-input"
                placeholder="Optional HH:MM"
              />
            </div>
          </div>

          {/* Benchmark Date Quick Select Chips */}
          {config.showBenchmarkButtons && (
            <div className="benchmark-chips-row">
              <span style={{ fontSize: 12, color: 'var(--text-muted)', fontWeight: 600 }}>
                {t('planner.historical_benchmarks', 'Historical Benchmark Spells:')}
              </span>
              {benchmarkDates.map((b) => (
                <button
                  key={b.date}
                  type="button"
                  className={`sample-btn ${journeyDate === b.date ? 'active' : ''}`}
                  onClick={() => setJourneyDate(b.date)}
                >
                  {b.date} ? {b.label}
                </button>
              ))}
            </div>
          )}
        </div>

        {planError && (
          <div className="auth-error-banner" style={{ marginTop: 12 }}>
            <AlertOctagon size={16} />
            <span>{planError}</span>
          </div>
        )}

        {/* Action Button */}
        <div className="planner-action-bar">
          <button type="submit" className="plan-submit-btn" disabled={isPlanning}>
            {isPlanning ? (
              <>
                <RefreshCw size={16} className="spin-icon" style={{ marginRight: 8 }} />
                Analyzing Corridor Topology & ST-GNN Scores...
              </>
            ) : (
              <>
                <Sparkles size={16} style={{ marginRight: 8 }} />
                Analyze & Plan Corridor Journey
              </>
            )}
          </button>
        </div>
      </form>

      {/* Plan Results Presentation */}
      {planResult && (
        <div className="plan-results-card">
          <div className="results-top-bar">
            <div className="results-title-group">
              <div className="route-endpoints">
                <span className="endpoint-pill">{planResult.origin}</span>
                <span className="endpoint-arrow">➔</span>
                <span className="endpoint-pill">{planResult.destination}</span>
              </div>
              <span className="journey-date-tag">Date: {planResult.journey_date}</span>
              {autoRefreshedAt && mode === 'live' && (
                <span className="planner-auto-refresh-badge" data-testid="planner-auto-refresh-badge">
                  <RefreshCw size={11} className="spin-slow" aria-hidden="true" />
                  {t('journey.plan_auto_refreshed', { time: autoRefreshedAt })}
                </span>
              )}
            </div>
            <div>{getRiskBadge(planResult.overall_route_risk)}</div>
          </div>

          {/* Visible Notification when Auto-Refresh Alters Recommendation */}
          {recommendationDiffNotice && mode === 'live' && (
            <div
              className="recommendation-change-notice"
              data-testid="recommendation-change-notice"
              role="alert"
              style={{
                background: 'var(--warning-bg)',
                color: 'var(--warning-text, var(--warning))',
                border: '1px solid var(--warning-border)',
                borderRadius: 8,
                padding: '8px 12px',
                margin: '12px 0',
                fontSize: 13,
                fontWeight: 600,
                display: 'flex',
                alignItems: 'center',
                gap: 8,
              }}
            >
              <AlertTriangle size={16} aria-hidden="true" />
              <span>
                {t('journey.recommendation_changed_notice', {
                  oldRec: recommendationDiffNotice.oldRec,
                  newRec: recommendationDiffNotice.newRec,
                })}
              </span>
            </div>
          )}

          {/* Operational Recommendation Banner (Task 4) */}
          {planResult.recommendation && renderRecommendation(
            planResult.recommendation,
            planResult.recommendation_reason,
            planResult.blocking_segments
          )}

          {/* Previous Result Comparison Drawer */}
          {previousPlanResult && (
            <div style={{ margin: '8px 0 12px 0' }}>
              <button
                type="button"
                className="sample-btn"
                style={{ fontSize: 12, padding: '4px 10px' }}
                onClick={() => setShowPreviousComparison(!showPreviousComparison)}
              >
                {showPreviousComparison ? 'Hide Previous Route Comparison' : 'Compare with Previous Calculation'}
              </button>
              {showPreviousComparison && (
                <div style={{ marginTop: 8, padding: 12, background: 'var(--bg-primary)', border: '1px solid var(--border-color)', borderRadius: 6, fontSize: 12 }}>
                  <strong>Previous Evaluation ({previousPlanResult.journey_date}):</strong>
                  <div style={{ marginTop: 4 }}>
                    Recommendation: <strong>{previousPlanResult.recommendation || 'N/A'}</strong> • Est. Transit: <strong>{previousPlanResult.estimated_travel_minutes} min</strong> • Risk: <strong>{previousPlanResult.overall_route_risk}</strong>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Side-by-Side Alternative Routes Presentation (Task 4) */}
          {(planResult.baseline_route || planResult.risk_aware_route) && (
            <div className="routes-comparison-section" style={{ margin: '14px 0' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
                <h3 style={{ fontSize: 14, fontWeight: 600, display: 'flex', alignItems: 'center', gap: 6, margin: 0 }}>
                  <Navigation size={15} /> Side-by-Side Route Alternatives & Trade-Offs
                </h3>
                <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                  Mode: {mode === 'live' ? 'Live Telemetry' : 'Historical Reanalysis'}
                </span>
              </div>

              <div className="routes-comparison-grid">
                {planResult.baseline_route && (
                  <div className="route-alternative-card">
                    <div className="route-alt-header">
                      <strong style={{ fontSize: 13 }}>Distance-Only Baseline</strong>
                      <span className={`badge ${planResult.baseline_route.is_passable ? 'badge-connected' : 'badge-disconnected'}`}>
                        {planResult.baseline_route.is_passable ? 'Passable' : 'Blocked'}
                      </span>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13 }}>
                      <span>Distance: <strong>{planResult.baseline_route.total_distance_km} km</strong></span>
                      <span>Est. Time: <strong>{planResult.baseline_route.estimated_travel_minutes} min</strong></span>
                    </div>
                    <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                      Risk Assessment: <strong>{planResult.baseline_route.overall_risk}</strong>
                      {planResult.baseline_route.max_risk_score !== null && (
                        <span> (Max: {(planResult.baseline_route.max_risk_score * 100).toFixed(1)}%)</span>
                      )}
                    </div>
                    <p style={{ fontSize: 12, fontStyle: 'italic', color: 'var(--text-dim)', margin: 0 }}>
                      {planResult.baseline_route.trade_off_explanation}
                    </p>
                  </div>
                )}

                {planResult.risk_aware_route && (
                  <div className="route-alternative-card highlight">
                    <div className="route-alt-header">
                      <strong style={{ fontSize: 13, color: 'var(--accent-primary)' }}>Risk-Aware Route (ST-GNN)</strong>
                      <span className={`badge ${planResult.risk_aware_route.is_passable ? 'badge-connected' : 'badge-disconnected'}`}>
                        {planResult.risk_aware_route.is_passable ? 'Passable' : 'Hold / Blocked'}
                      </span>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13 }}>
                      <span>Distance: <strong>{planResult.risk_aware_route.total_distance_km} km</strong></span>
                      <span>Est. Time: <strong>{planResult.risk_aware_route.estimated_travel_minutes} min</strong></span>
                    </div>
                    <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                      Risk Assessment: <strong>{planResult.risk_aware_route.overall_risk}</strong>
                      {planResult.risk_aware_route.max_risk_score !== null && (
                        <span> (Max: {(planResult.risk_aware_route.max_risk_score * 100).toFixed(1)}%)</span>
                      )}
                    </div>
                    <p style={{ fontSize: 12, fontStyle: 'italic', color: 'var(--text-dim)', margin: 0 }}>
                      {planResult.risk_aware_route.trade_off_explanation}
                    </p>
                  </div>
                )}
              </div>

              <div style={{ fontSize: 11, color: 'var(--text-muted)', background: 'var(--bg-primary)', padding: '8px 12px', borderRadius: 6, border: '1px solid var(--border-color)', marginTop: 8 }}>
                ℹ <strong>Single Physical Corridor Constraint:</strong> NH-44 Ramban–Banihal is a single linear mountain highway. Both baseline and risk-aware evaluations traverse the identical physical road segments; topological alternatives do not exist in this graph.
              </div>
            </div>
          )}

          {/* Incomplete Data / Unknown Risk Alert Banner */}
          {planResult.is_incomplete_data && (
            <div
              className="retrospective-banner"
              style={{
                background: 'rgba(239, 68, 68, 0.08)',
                borderColor: 'rgba(239, 68, 68, 0.35)',
                margin: '12px 0',
              }}
            >
              <AlertOctagon size={16} style={{ color: 'var(--danger)', flexShrink: 0, marginTop: 2 }} />
              <div>
                <strong style={{ color: 'var(--danger)' }}>Incomplete Hazard Assessment Notice:</strong>{' '}
                {planResult.unknown_segments_count} segment(s) on this route lack precomputed ST-GNN risk evaluations.
                Because missing data is never certified as safe, the overall route risk is designated as <strong>Unknown</strong>.
                Exercise extreme caution when traversing unmonitored segments.
              </div>
            </div>
          )}

          {/* Metrics Row */}
          <div className="results-metrics-grid">
            <div className="metric-box">
              <span className="metric-label">Corridor Distance</span>
              <span className="metric-value">{planResult.total_distance_km} km</span>
              <span className="metric-sub">{planResult.total_route_segments} Graph Edges</span>
            </div>

            <div className="metric-box">
              <span className="metric-label">Est. Transit Time</span>
              <span className="metric-value">
                {Math.floor(planResult.estimated_travel_minutes / 60)}h {planResult.estimated_travel_minutes % 60}m
              </span>
              <span className="metric-sub" title={planResult.travel_time_disclaimer}>
                Depart: {planResult.departure_time} → Est: {planResult.estimated_arrival_time} (Assumed Speed)
              </span>
            </div>

            <div className="metric-box">
              <span className="metric-label">Max Risk Score</span>
              <span
                className="metric-value"
                style={{
                  color:
                    planResult.max_risk_score === null || planResult.max_risk_score === undefined
                      ? 'var(--text-muted)'
                      : planResult.max_risk_score >= 0.35
                      ? 'var(--risk-high)'
                      : planResult.max_risk_score >= 0.1
                      ? 'var(--risk-medium)'
                      : 'var(--risk-low)',
                }}
              >
                {planResult.max_risk_score !== null && planResult.max_risk_score !== undefined
                  ? `${(planResult.max_risk_score * 100).toFixed(1)}%`
                  : 'N/A'}
              </span>
              <span className="metric-sub">
                Avg Route Risk:{' '}
                {planResult.average_risk_score !== null && planResult.average_risk_score !== undefined
                  ? `${(planResult.average_risk_score * 100).toFixed(1)}%`
                  : 'N/A'}
              </span>
            </div>

            <div className="metric-box">
              <span className="metric-label">Segment Breakdown</span>
              <div className="mini-breakdown">
                <span style={{ color: 'var(--risk-high)' }}>{planResult.high_risk_segments_count} High</span> •{' '}
                <span style={{ color: 'var(--risk-medium)' }}>{planResult.medium_risk_segments_count} Med</span> •{' '}
                <span style={{ color: 'var(--risk-low)' }}>{planResult.low_risk_segments_count} Low</span>
                {planResult.unknown_segments_count > 0 && (
                  <>
                    {' '}• <span style={{ color: 'var(--text-muted)' }}>{planResult.unknown_segments_count} Unknown</span>
                  </>
                )}
              </div>
              {planResult.arrival_deadline && (
                <div style={{ marginTop: 4 }}>{getDeadlineBadge(planResult.deadline_status)}</div>
              )}
            </div>
          </div>

          {/* Vehicle Advisory Box */}
          <div className="vehicle-advisory-card">
            <div className="advisory-header">
              <Shield size={16} style={{ color: 'var(--accent-secondary)' }} />
              <strong>Vehicle Operational Advisory: {planResult.vehicle_advisory.vehicle_type}</strong>
              <span className="badge badge-pill">Clearance: {planResult.vehicle_advisory.operational_clearance}</span>
            </div>
            <p className="advisory-body">{planResult.vehicle_advisory.advisory_text}</p>
            <div className="advisory-footer">
              <strong>Technical Note:</strong> {planResult.vehicle_advisory.model_applicability_note}
            </div>
          </div>

          {/* Bottlenecks Warning */}
          {planResult.bottlenecks && planResult.bottlenecks.length > 0 && (
            <div className="bottlenecks-card">
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontWeight: 600, color: 'var(--danger-text)', marginBottom: 6 }}>
                <AlertOctagon size={16} />
                <span>Identified High-Hazard Bottlenecks on Route:</span>
              </div>
              <ul className="bottlenecks-list">
                {planResult.bottlenecks.map((b, idx) => (
                  <li key={idx}>{b}</li>
                ))}
              </ul>
            </div>
          )}

          {/* Toggleable Detailed Itinerary */}
          <div className="itinerary-section">
            <button
              type="button"
              className="toggle-itinerary-btn"
              onClick={() => setShowItinerary(!showItinerary)}
            >
              <Layers size={15} style={{ marginRight: 6 }} />
              <span>{showItinerary ? 'Hide Segment-by-Segment Itinerary' : `View Full Itinerary (${planResult.itinerary.length} Segments)`}</span>
              {showItinerary ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
            </button>

            {showItinerary && (
              <div className="itinerary-table-wrapper">
                <table className="itinerary-table">
                  <thead>
                    <tr>
                      <th>#</th>
                      <th>Segment ID</th>
                      <th>Elevation</th>
                      <th>Length</th>
                      <th>Slope</th>
                      <th>Risk Score</th>
                      <th>Risk Tier</th>
                      <th>Hazard Advisory</th>
                    </tr>
                  </thead>
                  <tbody>
                    {planResult.itinerary.map((item) => {
                      const tierColor =
                        item.risk_tier === 'High'
                          ? 'var(--risk-high)'
                          : item.risk_tier === 'Medium'
                          ? 'var(--risk-medium)'
                          : item.risk_tier === 'Low'
                          ? 'var(--risk-low)'
                          : 'var(--text-muted)';
                      return (
                        <tr key={item.segment_id}>
                          <td>{item.sequence}</td>
                          <td style={{ fontFamily: 'monospace', fontSize: 11 }}>{item.segment_id}</td>
                          <td>{item.elevation_m.toFixed(0)} m ASL</td>
                          <td>{item.length_m.toFixed(0)} m</td>
                          <td>{(item.slope * 100).toFixed(1)}%</td>
                          <td style={{ fontWeight: 600, color: tierColor }}>
                            {item.risk_score !== null ? `${(item.risk_score * 100).toFixed(1)}%` : 'N/A'}
                          </td>
                          <td>
                            <span
                              className="tier-badge"
                              style={{ color: tierColor, borderColor: tierColor }}
                            >
                              {item.risk_tier}
                            </span>
                          </td>
                          <td style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                            {item.hazard_notes || 'Standard clearance'}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {/* Action to Corridor Map */}
          {onNavigateToMap && (
            <div style={{ marginTop: 14, display: 'flex', justifyContent: 'flex-end' }}>
              <button
                type="button"
                className="sample-btn"
                style={{ padding: '8px 16px', background: 'var(--accent-primary)', color: 'var(--text-on-accent)' }}
                onClick={onNavigateToMap}
              >
                Inspect Full Corridor Map for {planResult.journey_date} →
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
