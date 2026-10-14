import React, { useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import {
  Shield,
  Navigation,
  Map,
  Bot,
  History,
  LogIn,
  UserPlus,
  ArrowRight,
  Sun,
  Moon,
  AlertTriangle,
  Layers,
  Sparkles,
  Car,
  Truck,
  CheckCircle2,
} from 'lucide-react';

export default function WelcomeView({ theme, setTheme, health }) {
  const navigate = useNavigate();
  const location = useLocation();
  const { loginAsGuest, login } = useAuth();
  const [isGuestLoading, setIsGuestLoading] = useState(false);
  const [guestError, setGuestError] = useState(null);

  const destination = location.state?.from || '/overview';

  const handleGuestEntry = async () => {
    try {
      setIsGuestLoading(true);
      setGuestError(null);
      await loginAsGuest();
      navigate(destination, { replace: true });
    } catch (err) {
      setGuestError(err.message || 'Unable to start guest session.');
    } finally {
      setIsGuestLoading(false);
    }
  };

  const handleDemoLogin = async (email, password) => {
    try {
      setIsGuestLoading(true);
      setGuestError(null);
      await login(email, password);
      navigate(destination, { replace: true });
    } catch (err) {
      setGuestError(err.message || 'Demo login failed.');
    } finally {
      setIsGuestLoading(false);
    }
  };

  const isHealthy = health && health.status === 'ok';

  return (
    <div className="welcome-page-wrapper">
      {/* Top Navbar */}
      <header className="welcome-nav-bar">
        <div className="welcome-brand">
          <div className="brand-icon">RW</div>
          <div>
            <span className="brand-name">RouteWise</span>
            <span className="brand-subtitle">NH-44 Corridor Intelligence</span>
          </div>
        </div>

        <div className="welcome-nav-actions">
          <div className="sidebar-status-box" style={{ padding: '4px 10px' }}>
            <div
              className="status-indicator-dot"
              style={{ background: isHealthy ? 'var(--success)' : 'var(--danger)' }}
            />
            <span style={{ fontSize: 12 }}>{isHealthy ? 'Backend Connected' : 'Backend Offline'}</span>
          </div>

          {/* Theme switch */}
          <label className="theme-switch" title="Toggle light/dark theme">
            <Sun size={15} className="theme-icon" />
            <input
              type="checkbox"
              checked={theme === 'dark'}
              onChange={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
              aria-label="Toggle dark mode"
            />
            <span className="theme-slider">
              <span className="theme-knob" />
            </span>
            <Moon size={15} className="theme-icon" />
          </label>
        </div>
      </header>

      {/* Main Hero Container */}
      <main className="welcome-content-container">
        <div className="welcome-hero-card">
          <div className="hero-badge">
            <Shield size={14} /> Edge-Resilient GeoAI & Predictive Logistics Platform
          </div>

          <h1 className="welcome-hero-title">
            Predictive Disruption & Route Intelligence for NH-44
          </h1>

          <p className="welcome-hero-description">
            A specialized decision-support system forecasting highway segment disruption risks
            along the high-hazard <strong>Ramban–Banihal corridor</strong>. Built with Spatial-Temporal
            Graph Neural Networks (ST-GNN) conditioned on Copernicus ERA5-Land environmental reanalysis
            and high-resolution 30m topographic DEM slope modeling.
          </p>

          {/* Primary Action Buttons */}
          <div className="welcome-cta-group">
            <button
              type="button"
              className="welcome-btn welcome-btn-primary"
              onClick={() => navigate('/auth/signin', { state: { from: destination } })}
              id="btn-welcome-signin"
            >
              <LogIn size={16} />
              <span>Sign In</span>
            </button>

            <button
              type="button"
              className="welcome-btn welcome-btn-secondary"
              onClick={() => navigate('/auth/signup', { state: { from: destination } })}
              id="btn-welcome-signup"
            >
              <UserPlus size={16} />
              <span>Create Account</span>
            </button>

            <button
              type="button"
              className="welcome-btn welcome-btn-guest"
              onClick={handleGuestEntry}
              disabled={isGuestLoading}
              id="btn-welcome-guest"
            >
              <Sparkles size={16} />
              <span>{isGuestLoading ? 'Initializing Guest...' : 'Continue as Guest'}</span>
              <ArrowRight size={14} />
            </button>
          </div>

          {guestError && (
            <div className="auth-error-banner" style={{ marginTop: 14 }}>
              <AlertTriangle size={15} />
              <span>{guestError}</span>
            </div>
          )}

          {/* Retrospective Science Disclaimer */}
          <div className="retrospective-banner" style={{ marginTop: 20 }}>
            <AlertTriangle size={16} style={{ flexShrink: 0, marginTop: 2 }} />
            <div>
              <strong>Retrospective Environmental Modeling Notice:</strong> Disruption probabilities
              represent relative risk rankings computed from 7-day preceding ERA5-Land reanalysis observations
              and terrain slope geometry. They provide advisory situational awareness for departure planning;
              they do <strong>not</strong> represent live CCTV traffic or guaranteed road clearance.
            </div>
          </div>
        </div>

        {/* Feature Highlights Grid */}
        <div className="welcome-features-grid">
          <div className="welcome-feature-card">
            <div className="feature-nav-icon" style={{ background: 'var(--info-bg)', color: 'var(--accent-secondary)' }}>
              <Navigation size={22} />
            </div>
            <h3>Vehicle Journey Planning</h3>
            <p>
              Simulate route transits for Car, Motorcycle, Bus, or Freight Truck with mountain gradient
              speed limits and vehicle-specific hazard vulnerability advisories.
            </p>
          </div>

          <div className="welcome-feature-card">
            <div className="feature-nav-icon" style={{ background: 'var(--success-bg)', color: 'var(--success)' }}>
              <Map size={22} />
            </div>
            <h3>151-Segment Corridor Map</h3>
            <p>
              Interactive Leaflet corridor topology with dynamic light/dark basemaps, slope gradients,
              elevation profiles, and calibrated ST-GNN risk scores.
            </p>
          </div>

          <div className="welcome-feature-card">
            <div className="feature-nav-icon" style={{ background: 'var(--warning-bg)', color: 'var(--warning)' }}>
              <History size={22} />
            </div>
            <h3>Verified Disruption Archive</h3>
            <p>
              Searchable catalog of 99 confirmed landslide, rockfall, and snow closures snapped to
              highway graph segments with corroborated media documentation (2018–2025).
            </p>
          </div>

          <div className="welcome-feature-card">
            <div className="feature-nav-icon" style={{ background: 'var(--info-bg)', color: 'var(--info)' }}>
              <Bot size={22} />
            </div>
            <h3>Conversational AI Advisor</h3>
            <p>
              Natural-language corridor intelligence explaining ST-GNN calibration thresholds (0.10 & 0.35),
              hazard hotspots (Panthyal, Digdol, Cafeteria Morh), and travel timing.
            </p>
          </div>
        </div>

        {/* Evaluation Quick Demo Card */}
        <div className="welcome-demo-drawer">
          <div className="demo-divider">
            <span>Fast Evaluation Profiles (Instant Access)</span>
          </div>
          <div className="demo-grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))' }}>
            <button
              type="button"
              className="demo-card-btn"
              onClick={() => handleDemoLogin('demo@routewise.ai', 'routewise2026')}
              disabled={isGuestLoading}
            >
              <div className="demo-card-header">
                <span className="demo-icon-wrap"><Car size={16} /></span>
                <strong>Dr. Kabir Sharma</strong>
              </div>
              <span className="demo-desc">Public Commuter • Personal Car Travel</span>
            </button>

            <button
              type="button"
              className="demo-card-btn"
              onClick={() => handleDemoLogin('logistics@routewise.ai', 'routewise2026')}
              disabled={isGuestLoading}
            >
              <div className="demo-card-header">
                <span className="demo-icon-wrap"><Truck size={16} /></span>
                <strong>Tariq Ahmad</strong>
              </div>
              <span className="demo-desc">Kashmir Freight • Heavy Multi-Axle Truck</span>
            </button>

            <button
              type="button"
              className="demo-card-btn"
              onClick={() => handleDemoLogin('patrol@routewise.ai', 'routewise2026')}
              disabled={isGuestLoading}
            >
              <div className="demo-card-header">
                <span className="demo-icon-wrap"><Shield size={16} /></span>
                <strong>Inspector Amit Rathore</strong>
              </div>
              <span className="demo-desc">NH-44 Highway Patrol Unit</span>
            </button>
          </div>
        </div>
      </main>

      <footer className="welcome-footer">
        <span>RouteWise System • Final Year Capstone Project • NH-44 Ramban–Banihal Pilot Stretch</span>
      </footer>
    </div>
  );
}
