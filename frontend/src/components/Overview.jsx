import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Navigation,
  Map,
  Bot,
  History,
  Shield,
  Layers,
  CheckCircle,
  AlertTriangle,
  ArrowRight,
  Cpu,
} from 'lucide-react';
import CorridorStrip from './CorridorStrip';
import RiskDetailDrawer from './RiskDetailDrawer';
import OfficialAdvisoriesCard from './OfficialAdvisoriesCard';
import AlongRouteServicesCard from './AlongRouteServicesCard';

export default function Overview({ health, riskData, onNavigate, selectedDate }) {
  const { t } = useTranslation();
  const isHealthy = health && health.status === 'ok';
  const summary = riskData?.summary;
  const [activeDrawerSegId, setActiveDrawerSegId] = useState(null);

  const selectedRiskItem = riskData?.segments?.find((s) => s.segment_id === activeDrawerSegId);

  return (
    <div className="overview-container">
      {/* Hero Welcome Banner */}
      <div className="overview-hero-card">
        <div className="hero-content">
          <div className="hero-badge">
            <Shield size={14} /> Official Final Year Engineering Capstone Project
          </div>
          <h1>{t('app.name')}: {t('app.subtitle')}</h1>
          <p>
            Edge-resilient GeoAI and Spatial-Temporal Graph Neural Network (ST-GNN) disruption
            forecasting system for the critical <strong>NH-44 Ramban–Banihal mountain corridor</strong>.
          </p>

          <div className="hero-metrics-row">
            <div className="hero-metric">
              <span className="hero-num">151</span>
              <span className="hero-lbl">Highway Segments</span>
            </div>
            <div className="hero-metric">
              <span className="hero-num">~36 km</span>
              <span className="hero-lbl">Corridor Length</span>
            </div>
            <div className="hero-metric">
              <span className="hero-num">700–1750m</span>
              <span className="hero-lbl">Elevation Range</span>
            </div>
            <div className="hero-metric">
              <span className="hero-num">24 Hours</span>
              <span className="hero-lbl">Advisory Horizon</span>
            </div>
          </div>
        </div>

        {/* Retrospective Science Notice */}
        <div className="retrospective-banner" style={{ marginTop: 16 }}>
          <AlertTriangle size={16} style={{ flexShrink: 0, marginTop: 2 }} />
          <div>
            <strong>Retrospective Environmental Reanalysis Notice:</strong> Segment risk scores
            are calculated from historical Copernicus ERA5-Land meteorological reanalysis and SRTM topographic
            DEM slope metrics. They represent <em>advisory relative risk ranking</em> for situational awareness
            and logistics planning; they do not represent live traffic or road safety guarantees.
          </div>
        </div>
      </div>

      {/* Corridor Segment Risk Strip */}
      <CorridorStrip
        riskData={riskData}
        selectedDate={selectedDate}
        selectedSegmentId={activeDrawerSegId}
        onSelectSegment={(segId) => setActiveDrawerSegId(segId)}
      />

      {/* Snapshot Cards Row */}
      <div className="overview-grid-2">
        {/* Active Date Risk Snapshot */}
        <div className="card">
          <div className="card-title">
            <span>Corridor Risk Snapshot ({selectedDate})</span>
            <Layers size={16} style={{ color: 'var(--accent-secondary)' }} />
          </div>

          {summary ? (
            <div className="summary-grid">
              <div className="summary-pill pill-high">
                <span className="pill-count">{summary.high_risk_count}</span>
                <span className="pill-label">High Hazard (≥0.35)</span>
              </div>
              <div className="summary-pill pill-med">
                <span className="pill-count">{summary.medium_risk_count}</span>
                <span className="pill-label">Elevated (0.10–0.35)</span>
              </div>
              <div className="summary-pill pill-low">
                <span className="pill-count">{summary.low_risk_count}</span>
                <span className="pill-label">Baseline (&lt;0.10)</span>
              </div>
              <div className="summary-pill pill-unknown">
                <span className="pill-count">{summary.unknown_count}</span>
                <span className="pill-label">Missing / Stale</span>
              </div>
            </div>
          ) : (
            <div className="inspector-empty">Loading corridor risk breakdown...</div>
          )}

          <div style={{ marginTop: 8, display: 'flex', justifyContent: 'flex-end' }}>
            <button
              type="button"
              className="sample-btn"
              onClick={() => onNavigate('map')}
            >
              Open Interactive Risk Map →
            </button>
          </div>
        </div>

        {/* System & Model Health */}
        <div className="card">
          <div className="card-title">
            <span>System Health & Model Checkpoint</span>
            <Cpu size={16} style={{ color: 'var(--success)' }} />
          </div>

          <div className="inspector-list">
            <div className="inspector-row">
              <span className="inspector-label">FastAPI Backend Status</span>
              <span className="inspector-value" style={{ color: isHealthy ? 'var(--success)' : 'var(--danger)' }}>
                {isHealthy ? '● Connected & Operational' : '○ Offline / Degraded'}
              </span>
            </div>

            <div className="inspector-row">
              <span className="inspector-label">ST-GNN Model Checkpoint</span>
              <span className="inspector-value" style={{ fontFamily: 'monospace' }}>
                {health?.model_version ? health.model_version.slice(0, 12) : '68b04504d6c6'} (PyTorch CPU)
              </span>
            </div>

            <div className="inspector-row">
              <span className="inspector-label">Precomputed Risk Cache</span>
              <span className="inspector-value">
                {health?.available_dates_count ? `${health.available_dates_count} Evaluated Dates` : 'Available (2021–2025)'}
              </span>
            </div>

            <div className="inspector-row">
              <span className="inspector-label">Operational Decision Thresholds</span>
              <span className="inspector-value">τ_med = 0.10, τ_high = 0.35</span>
            </div>
          </div>

          <div style={{ marginTop: 12, fontSize: 11, color: 'var(--text-dim)' }}>
            Evaluated on Copernicus ERA5-Land reanalysis + OpenTopography 30m SRTM DEM.
          </div>
        </div>
      </div>

      {/* Official Traffic Advisories & Emergency Services Cards */}
      <OfficialAdvisoriesCard />
      <AlongRouteServicesCard onSelectLocation={() => onNavigate('map')} />

      {/* Feature Navigation Cards Grid */}
      <div className="overview-features-grid">
        <div className="feature-nav-card" onClick={() => onNavigate('journey')}>
          <div className="feature-nav-icon" style={{ background: 'var(--info-bg)', color: 'var(--accent-secondary)' }}>
            <Navigation size={24} />
          </div>
          <h3>Plan a Corridor Journey</h3>
          <p>
            Select your vehicle class (Car, Motorcycle, Bus, Truck), choose origin & destination along NH-44,
            and receive segment-by-segment hazard profiling with travel duration estimates.
          </p>
          <span className="feature-nav-link">
            Open Journey Planner <ArrowRight size={14} />
          </span>
        </div>

        <div className="feature-nav-card" onClick={() => onNavigate('map')}>
          <div className="feature-nav-icon" style={{ background: 'var(--success-bg)', color: 'var(--success)' }}>
            <Map size={24} />
          </div>
          <h3>Corridor Risk Map</h3>
          <p>
            Explore the full 151-segment interactive highway geometry. Inspect terrain slope, elevation ASL,
            and advisory risk classifications across benchmark and observation dates.
          </p>
          <span className="feature-nav-link">
            Explore Interactive Map <ArrowRight size={14} />
          </span>
        </div>

        <div className="feature-nav-card" onClick={() => onNavigate('reports')}>
          <div className="feature-nav-icon" style={{ background: 'var(--warning-bg)', color: 'var(--warning)' }}>
            <AlertTriangle size={24} />
          </div>
          <h3>Incident Reporter & Sync Queue</h3>
          <p>
            Capture GPS-tagged incident observations with optional photo evidence. Persistent IndexedDB queue
            ensures reports are stored offline and automatically synced when connection is restored.
          </p>
          <span className="feature-nav-link">
            Report Road Hazard <ArrowRight size={14} />
          </span>
        </div>

        <div className="feature-nav-card" onClick={() => onNavigate('chat')}>
          <div className="feature-nav-icon" style={{ background: 'var(--info-bg)', color: 'var(--accent-secondary)' }}>
            <Bot size={24} />
          </div>
          <h3>Conversational AI Advisor</h3>
          <p>
            Interactive AI reasoning assistant that explains corridor risk scores, model calibration,
            vehicle operational vulnerabilities, and historical benchmark disruption spells.
          </p>
          <span className="feature-nav-link">
            Consult AI Advisor <ArrowRight size={14} />
          </span>
        </div>
      </div>

      {/* Segment Risk Detail Drawer Modal */}
      {activeDrawerSegId && (
        <RiskDetailDrawer
          segmentId={activeDrawerSegId}
          selectedDate={selectedDate}
          riskItem={selectedRiskItem}
          onClose={() => setActiveDrawerSegId(null)}
        />
      )}
    </div>
  );
}
