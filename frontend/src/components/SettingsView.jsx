import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { useJourney } from '../context/JourneyContext';
import { updateUserProfile } from '../services/api';
import {
  User,
  Shield,
  Car,
  Settings,
  LogOut,
  CheckCircle,
  Database,
  Moon,
  Sun,
  AlertCircle,
  Save,
  Cpu,
  UserPlus,
  LogIn,
} from 'lucide-react';

export default function SettingsView({ theme, setTheme }) {
  const navigate = useNavigate();
  const { user, isAuthenticated, isGuest, logout, updateLocalUser } = useAuth();
  const { vehicleType, setVehicleType, resetJourney } = useJourney();

  const [name, setName] = useState(user?.name || '');
  const [preferredVehicle, setPreferredVehicle] = useState(
    user?.preferred_vehicle || vehicleType || 'Car'
  );
  const [isSaving, setIsSaving] = useState(false);
  const [statusMsg, setStatusMsg] = useState(null);

  const handleSave = async (e) => {
    e.preventDefault();
    if (isGuest) {
      setStatusMsg({
        type: 'error',
        text: 'Guest accounts cannot modify persistent profiles. Sign in or register to save preferences.',
      });
      return;
    }

    try {
      setIsSaving(true);
      setStatusMsg(null);
      const updated = await updateUserProfile({
        name,
        preferred_vehicle: preferredVehicle,
      });
      updateLocalUser(updated);
      setVehicleType(preferredVehicle);
      setStatusMsg({ type: 'success', text: 'Profile preferences saved successfully.' });
    } catch (err) {
      setStatusMsg({ type: 'error', text: err.message || 'Failed to update preferences' });
    } finally {
      setIsSaving(false);
    }
  };

  const handleLogout = () => {
    logout();
    if (resetJourney) resetJourney();
    navigate('/', { replace: true });
  };

  return (
    <div className="settings-container">
      {/* Header */}
      <div className="card">
        <div className="card-title">
          <span>System Settings & Operational Profile</span>
          <Settings size={18} style={{ color: 'var(--accent-secondary)' }} />
        </div>
        <p style={{ fontSize: 13, color: 'var(--text-muted)' }}>
          Configure user credentials, vehicle defaults, display themes, and review RouteWise model specifications.
        </p>
      </div>

      <div className="settings-grid">
        {/* Profile Card */}
        <div className="card">
          <div className="card-title">
            <span>User Account & Vehicle Preference</span>
            <User size={16} style={{ color: 'var(--accent-secondary)' }} />
          </div>

          {isGuest ? (
            <div className="guest-settings-prompt" style={{ padding: '8px 0' }}>
              <div
                className="auth-error-banner"
                style={{
                  background: 'var(--warning-bg)',
                  borderColor: 'var(--warning-border)',
                  color: 'var(--warning-text)',
                  marginBottom: 16,
                }}
              >
                <AlertCircle size={16} style={{ flexShrink: 0 }} />
                <span>
                  <strong>Guest Mode Active:</strong> You are currently exploring RouteWise in guest mode. Profile editing and saved alerts require a verified account.
                </span>
              </div>

              <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginTop: 12 }}>
                <button
                  type="button"
                  className="welcome-btn welcome-btn-primary"
                  onClick={() => navigate('/auth/signup')}
                  style={{ padding: '8px 16px', fontSize: 13 }}
                >
                  <UserPlus size={14} />
                  <span>Create Free Account</span>
                </button>
                <button
                  type="button"
                  className="welcome-btn welcome-btn-secondary"
                  onClick={() => navigate('/auth/signin')}
                  style={{ padding: '8px 16px', fontSize: 13 }}
                >
                  <LogIn size={14} />
                  <span>Sign In</span>
                </button>
              </div>
            </div>
          ) : isAuthenticated ? (
            <form onSubmit={handleSave} className="settings-form">
              <div className="form-group">
                <label>Registered Email Address</label>
                <input
                  type="email"
                  value={user?.email || ''}
                  disabled
                  className="date-input"
                  style={{ opacity: 0.7, cursor: 'not-allowed' }}
                />
              </div>

              <div className="form-group">
                <label>User Full Name</label>
                <input
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="date-input"
                  required
                />
              </div>

              <div className="form-group">
                <label>Operational Role</label>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span className="badge badge-pill" style={{ textTransform: 'capitalize' }}>
                    <Shield size={12} /> {user?.role?.replace('_', ' ') || 'Commuter'}
                  </span>
                </div>
              </div>

              <div className="form-group">
                <label>Default Transit Vehicle</label>
                <select
                  value={preferredVehicle}
                  onChange={(e) => setPreferredVehicle(e.target.value)}
                  className="custom-select"
                >
                  <option value="Car">Car / SUV</option>
                  <option value="Motorcycle">Motorcycle / 2-Wheeler</option>
                  <option value="Bus">Passenger Bus / Transit</option>
                  <option value="Truck">Heavy Commercial Freight Truck</option>
                  <option value="Other">Other / Emergency Convoy</option>
                </select>
              </div>

              {statusMsg && (
                <div
                  className="auth-error-banner"
                  style={{
                    background: statusMsg.type === 'success' ? 'var(--success-bg)' : 'var(--danger-bg)',
                    color: statusMsg.type === 'success' ? 'var(--success)' : 'var(--danger)',
                    borderColor: statusMsg.type === 'success' ? 'var(--success-border)' : 'var(--danger-border)',
                  }}
                >
                  {statusMsg.type === 'success' ? <CheckCircle size={16} /> : <AlertCircle size={16} />}
                  <span>{statusMsg.text}</span>
                </div>
              )}

              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 12 }}>
                <button type="submit" className="plan-submit-btn" disabled={isSaving} style={{ padding: '8px 18px' }}>
                  <Save size={14} style={{ marginRight: 6 }} />
                  {isSaving ? 'Saving...' : 'Save Preferences'}
                </button>

                <button
                  type="button"
                  className="sample-btn"
                  onClick={handleLogout}
                  style={{ color: 'var(--danger)', borderColor: 'var(--danger-border)' }}
                >
                  <LogOut size={13} style={{ display: 'inline', marginRight: 4 }} />
                  Sign Out
                </button>
              </div>
            </form>
          ) : (
            <div className="guest-settings-prompt">
              <p style={{ fontSize: 13, color: 'var(--text-muted)', marginBottom: 12 }}>
                You are currently accessing RouteWise as a guest. Sign in or create an account to save vehicle preferences.
              </p>
              <button
                type="button"
                className="plan-submit-btn"
                onClick={() => navigate('/auth/signin')}
                style={{ padding: '8px 18px' }}
              >
                Sign In / Switch Account
              </button>
            </div>
          )}
        </div>

        {/* Display and Theme Preferences */}
        <div className="card">
          <div className="card-title">
            <span>Interface & Display Settings</span>
            <Moon size={16} style={{ color: 'var(--accent-secondary)' }} />
          </div>

          <div className="settings-row">
            <div>
              <strong>Visual Theme Mode</strong>
              <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                Toggle between high-contrast dark mode and clean daylight light theme.
              </div>
            </div>

            <button
              type="button"
              className="theme-toggle"
              onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
              aria-label="Toggle visual theme"
            >
              {theme === 'dark' ? (
                <>
                  <Sun size={15} style={{ color: 'var(--warning)' }} />
                  <span>Switch to Light Theme</span>
                </>
              ) : (
                <>
                  <Moon size={15} style={{ color: 'var(--accent-secondary)' }} />
                  <span>Switch to Dark Theme</span>
                </>
              )}
            </button>
          </div>

          <div className="form-divider" />

          {/* Model Calibration Guide */}
          <div className="card-title" style={{ marginTop: 14 }}>
            <span>Operational Decision Thresholds</span>
            <Cpu size={16} style={{ color: 'var(--success)' }} />
          </div>

          <div className="legend-box">
            <div className="legend-row">
              <span>
                <span className="legend-bullet" style={{ background: 'var(--risk-high)' }}></span>
                High Hazard Tier (Score ≥ 0.35)
              </span>
              <span>Hold / Administrative Delay</span>
            </div>
            <div className="legend-row">
              <span>
                <span className="legend-bullet" style={{ background: 'var(--risk-medium)' }}></span>
                Elevated Hazard Tier (0.10 ≤ Score &lt; 0.35)
              </span>
              <span>Caution / Single-Lane</span>
            </div>
            <div className="legend-row">
              <span>
                <span className="legend-bullet" style={{ background: 'var(--risk-low)' }}></span>
                Baseline Low Risk (Score &lt; 0.10)
              </span>
              <span>Normal Mountain Highway</span>
            </div>
          </div>

          <div style={{ marginTop: 14, fontSize: 11, color: 'var(--text-dim)', lineHeight: 1.5 }}>
            <Database size={12} style={{ display: 'inline', marginRight: 4 }} />
            Decision boundaries were frozen on the 2023 evaluation split to guarantee maximum recall on confirmed
            disruptions while preserving high operational throughput on the highway.
          </div>
        </div>
      </div>
    </div>
  );
}
