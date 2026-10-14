import React, { useState } from 'react';
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

export default function JourneyPlanner({ onNavigateToMap }) {
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
    isPlanning,
    planError,
    executePlan,
  } = useJourney();

  const [showItinerary, setShowItinerary] = useState(false);

  const benchmarkDates = [
    { date: '2023-07-09', label: 'Monsoon Cloudburst (Benchmark)' },
    { date: '2024-03-15', label: 'Spring Thaw Event' },
    { date: '2022-01-20', label: 'Winter Snowstorm' },
    { date: '2025-08-10', label: 'Summer Moderate' },
  ];

  const handlePlanSubmit = async (e) => {
    e.preventDefault();
    try {
      await executePlan();
    } catch (err) {
      // handled
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
        <div className="retrospective-banner">
          <AlertTriangle size={16} style={{ flexShrink: 0, marginTop: 2 }} />
          <div>
            <strong>Single-Path Corridor Topology & Retrospective Analysis Notice:</strong> The NH-44 Ramban–Banihal section is a 
            <strong> single continuous linear mountain highway</strong>; topological alternative paths (such as parallel bypasses) 
            do <em>not</em> exist within this corridor road graph. Consequently, fastest and safest routes follow the identical physical sequence of segments.
            <div style={{ marginTop: 6, fontSize: 12, opacity: 0.9 }}>
              • <strong>Vehicle type:</strong> Configures speed thresholds and hazard vulnerability advisories, but does not alter physical highway geometry.
              <br />
              • <strong>Departure time:</strong> Calibrates estimated arrival times, but daily retrospective ST-GNN risk predictions do not change by hour.
            </div>
          </div>
        </div>
      </div>

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
          <label className="section-label">Travel Schedule & Benchmark Timing</label>
          <div className="timings-grid">
            <div className="form-group">
              <label>
                <Calendar size={14} style={{ display: 'inline', marginRight: 4, color: 'var(--text-muted)' }} />
                Journey Evaluation Date:
              </label>
              <input
                type="date"
                value={journeyDate}
                min="2021-01-06"
                max="2025-12-31"
                onChange={(e) => setJourneyDate(e.target.value)}
                className="date-input"
                required
              />
            </div>

            <div className="form-group">
              <label>
                <Clock size={14} style={{ display: 'inline', marginRight: 4, color: 'var(--text-muted)' }} />
                Preferred Departure Time:
              </label>
              <input
                type="time"
                value={departureTime}
                onChange={(e) => setDepartureTime(e.target.value)}
                className="date-input"
                required
              />
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
          <div className="benchmark-chips-row">
            <span style={{ fontSize: 12, color: 'var(--text-muted)', fontWeight: 600 }}>Historical Benchmark Spells:</span>
            {benchmarkDates.map((b) => (
              <button
                key={b.date}
                type="button"
                className={`sample-btn ${journeyDate === b.date ? 'active' : ''}`}
                onClick={() => setJourneyDate(b.date)}
              >
                {b.date} • {b.label}
              </button>
            ))}
          </div>
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
            </div>
            <div>{getRiskBadge(planResult.overall_route_risk)}</div>
          </div>

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
              <span className="metric-sub">
                Depart: {planResult.departure_time} → Est. Arrive: {planResult.estimated_arrival_time}
              </span>
            </div>

            <div className="metric-box">
              <span className="metric-label">Max Risk Score</span>
              <span
                className="metric-value"
                style={{
                  color:
                    planResult.max_risk_score >= 0.35
                      ? 'var(--risk-high)'
                      : planResult.max_risk_score >= 0.1
                      ? 'var(--risk-medium)'
                      : 'var(--risk-low)',
                }}
              >
                {(planResult.max_risk_score * 100).toFixed(1)}%
              </span>
              <span className="metric-sub">Avg Route Risk: {(planResult.average_risk_score * 100).toFixed(1)}%</span>
            </div>

            <div className="metric-box">
              <span className="metric-label">Segment Breakdown</span>
              <div className="mini-breakdown">
                <span style={{ color: 'var(--risk-high)' }}>{planResult.high_risk_segments_count} High</span> •{' '}
                <span style={{ color: 'var(--risk-medium)' }}>{planResult.medium_risk_segments_count} Med</span> •{' '}
                <span style={{ color: 'var(--risk-low)' }}>{planResult.low_risk_segments_count} Low</span>
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
                          : 'var(--risk-low)';
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
