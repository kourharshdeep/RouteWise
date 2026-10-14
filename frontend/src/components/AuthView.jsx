import React, { useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { Shield, Lock, Mail, User, Eye, EyeOff, AlertCircle, ArrowRight, CheckCircle2, Truck, Car, Navigation } from 'lucide-react';

export default function AuthView({ onClose }) {
  const { login, register, authError, setAuthError } = useAuth();
  const [isRegister, setIsRegister] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Form states
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [name, setName] = useState('');
  const [role, setRole] = useState('commuter');
  const [preferredVehicle, setPreferredVehicle] = useState('Car');

  const demoAccounts = [
    {
      label: 'Public Commuter',
      email: 'demo@routewise.ai',
      password: 'routewise2026',
      desc: 'Dr. Kabir Sharma • Personal Car Travel',
      icon: <Car size={16} />,
    },
    {
      label: 'Freight Logistics',
      email: 'logistics@routewise.ai',
      password: 'routewise2026',
      desc: 'Tariq Ahmad • Kashmir Freight Heavy Truck',
      icon: <Truck size={16} />,
    },
    {
      label: 'Highway Patrol',
      email: 'patrol@routewise.ai',
      password: 'routewise2026',
      desc: 'Inspector Amit Rathore • NH-44 Sector Unit',
      icon: <Shield size={16} />,
    },
  ];

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!email || !password) {
      setAuthError('Email and password are required.');
      return;
    }
    if (isRegister && !name) {
      setAuthError('Full name is required to create an account.');
      return;
    }

    try {
      setIsSubmitting(true);
      if (isRegister) {
        await register({
          email,
          password,
          name,
          role,
          preferred_vehicle: preferredVehicle,
        });
      } else {
        await login(email, password);
      }
      if (onClose) onClose();
    } catch (err) {
      // Error is set in AuthContext
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleDemoClick = async (account) => {
    setEmail(account.email);
    setPassword(account.password);
    try {
      setIsSubmitting(true);
      await login(account.email, account.password);
      if (onClose) onClose();
    } catch (err) {
      // handled
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="auth-overlay">
      <div className="auth-modal">
        {/* Header */}
        <div className="auth-header">
          <div className="auth-brand">
            <div className="brand-icon">RW</div>
            <div>
              <h2>RouteWise Portal</h2>
              <p>NH-44 Corridor Predictive Intelligence System</p>
            </div>
          </div>
        </div>

        {/* Tab Switcher */}
        <div className="auth-tabs">
          <button
            type="button"
            className={`auth-tab ${!isRegister ? 'active' : ''}`}
            onClick={() => {
              setIsRegister(false);
              setAuthError(null);
            }}
          >
            Sign In
          </button>
          <button
            type="button"
            className={`auth-tab ${isRegister ? 'active' : ''}`}
            onClick={() => {
              setIsRegister(true);
              setAuthError(null);
            }}
          >
            Create Account
          </button>
        </div>

        {/* Error message */}
        {authError && (
          <div className="auth-error-banner">
            <AlertCircle size={16} style={{ flexShrink: 0 }} />
            <span>{authError}</span>
          </div>
        )}

        {/* Form */}
        <form onSubmit={handleSubmit} className="auth-form">
          {isRegister && (
            <div className="form-group">
              <label>Full Name</label>
              <div className="input-with-icon">
                <User size={16} className="field-icon" />
                <input
                  type="text"
                  placeholder="e.g. Dr. Kabir Sharma"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  required={isRegister}
                />
              </div>
            </div>
          )}

          <div className="form-group">
            <label>Email Address</label>
            <div className="input-with-icon">
              <Mail size={16} className="field-icon" />
              <input
                type="email"
                placeholder="name@agency.gov.in or email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
            </div>
          </div>

          <div className="form-group">
            <label>Password</label>
            <div className="input-with-icon">
              <Lock size={16} className="field-icon" />
              <input
                type={showPassword ? 'text' : 'password'}
                placeholder="Enter your password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                minLength={6}
              />
              <button
                type="button"
                className="toggle-password"
                onClick={() => setShowPassword(!showPassword)}
                title={showPassword ? 'Hide password' : 'Show password'}
              >
                {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </div>
          </div>

          {isRegister && (
            <div className="form-row-2">
              <div className="form-group">
                <label>Operational Role</label>
                <select value={role} onChange={(e) => setRole(e.target.value)}>
                  <option value="commuter">Public Commuter</option>
                  <option value="logistics_operator">Logistics / Freight Operator</option>
                  <option value="patrol_officer">Highway Patrol Officer</option>
                  <option value="emergency_responder">Emergency Responder</option>
                </select>
              </div>

              <div className="form-group">
                <label>Default Vehicle</label>
                <select
                  value={preferredVehicle}
                  onChange={(e) => setPreferredVehicle(e.target.value)}
                >
                  <option value="Car">Car / SUV</option>
                  <option value="Motorcycle">Motorcycle</option>
                  <option value="Bus">Bus</option>
                  <option value="Truck">Truck / Heavy Freight</option>
                  <option value="Other">Other / Emergency</option>
                </select>
              </div>
            </div>
          )}

          <button type="submit" className="auth-submit-btn" disabled={isSubmitting}>
            {isSubmitting ? (
              'Authenticating...'
            ) : (
              <>
                {isRegister ? 'Register & Access System' : 'Sign In to RouteWise'}
                <ArrowRight size={16} style={{ marginLeft: 6 }} />
              </>
            )}
          </button>
        </form>

        {/* Quick Demo Logins */}
        <div className="demo-accounts-section">
          <div className="demo-divider">
            <span>Or Quick Login with Project Demo Accounts</span>
          </div>
          <div className="demo-grid">
            {demoAccounts.map((acct) => (
              <button
                key={acct.email}
                type="button"
                className="demo-card-btn"
                onClick={() => handleDemoClick(acct)}
                disabled={isSubmitting}
              >
                <div className="demo-card-header">
                  <span className="demo-icon-wrap">{acct.icon}</span>
                  <strong>{acct.label}</strong>
                </div>
                <span className="demo-desc">{acct.desc}</span>
              </button>
            ))}
          </div>
        </div>

        {/* Security & Project Disclaimer */}
        <div className="auth-footer-notice">
          <Shield size={13} style={{ display: 'inline', marginRight: 4 }} />
          Encrypted authentication backed by SQLite database with PBKDF2 password hashing & HMAC-SHA256 bearer tokens.
        </div>
      </div>
    </div>
  );
}
