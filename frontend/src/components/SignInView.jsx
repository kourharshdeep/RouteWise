import React, { useState } from 'react';
import { useNavigate, useLocation, Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import {
  Lock,
  Mail,
  Eye,
  EyeOff,
  AlertCircle,
  ArrowRight,
  ArrowLeft,
  Shield,
  Sun,
  Moon,
  Car,
  Truck,
} from 'lucide-react';

export default function SignInView({ theme, setTheme }) {
  const navigate = useNavigate();
  const location = useLocation();
  const { login, authError, setAuthError } = useAuth();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [fieldErrors, setFieldErrors] = useState({});
  const [isSubmitting, setIsSubmitting] = useState(false);

  const destination = location.state?.from || '/overview';

  const validate = () => {
    const errors = {};
    if (!email.trim()) {
      errors.email = 'Email address is required.';
    } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) {
      errors.email = 'Please enter a valid email address.';
    }

    if (!password) {
      errors.password = 'Password is required.';
    } else if (password.length < 6) {
      errors.password = 'Password must be at least 6 characters.';
    }
    setFieldErrors(errors);
    return Object.keys(errors).length === 0;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!validate() || isSubmitting) return;

    try {
      setIsSubmitting(true);
      setAuthError(null);
      await login(email.trim(), password);
      navigate(destination, { replace: true });
    } catch (err) {
      // Auth error is captured in context
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleDemoFill = async (demoEmail, demoPwd) => {
    setEmail(demoEmail);
    setPassword(demoPwd);
    setFieldErrors({});
    try {
      setIsSubmitting(true);
      setAuthError(null);
      await login(demoEmail, demoPwd);
      navigate(destination, { replace: true });
    } catch (err) {
      // Handled
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="auth-page-wrapper">
      {/* Top Header */}
      <div className="auth-page-topbar">
        <Link to="/" className="back-link">
          <ArrowLeft size={16} />
          <span>Back to Welcome</span>
        </Link>

        <label className="theme-switch" title="Toggle theme">
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

      <div className="auth-card-wrapper">
        <div className="auth-card">
          <div className="auth-brand-header">
            <div className="brand-icon">RW</div>
            <div>
              <h2>Sign In to RouteWise</h2>
              <p>Predictive Highway Disruption Platform</p>
            </div>
          </div>

          {authError && (
            <div className="auth-error-banner" role="alert">
              <AlertCircle size={16} style={{ flexShrink: 0 }} />
              <span>{authError}</span>
            </div>
          )}

          <form onSubmit={handleSubmit} className="auth-form" noValidate>
            <div className="form-group">
              <label htmlFor="signin-email">Email Address</label>
              <div className="input-with-icon">
                <Mail size={16} className="field-icon" />
                <input
                  id="signin-email"
                  type="email"
                  placeholder="name@agency.gov.in"
                  value={email}
                  onChange={(e) => {
                    setEmail(e.target.value);
                    if (fieldErrors.email) setFieldErrors({ ...fieldErrors, email: null });
                  }}
                  autoComplete="email"
                  disabled={isSubmitting}
                  className={fieldErrors.email ? 'input-error' : ''}
                />
              </div>
              {fieldErrors.email && <span className="field-error-text">{fieldErrors.email}</span>}
            </div>

            <div className="form-group">
              <label htmlFor="signin-password">Password</label>
              <div className="input-with-icon">
                <Lock size={16} className="field-icon" />
                <input
                  id="signin-password"
                  type={showPassword ? 'text' : 'password'}
                  placeholder="Enter your password"
                  value={password}
                  onChange={(e) => {
                    setPassword(e.target.value);
                    if (fieldErrors.password) setFieldErrors({ ...fieldErrors, password: null });
                  }}
                  autoComplete="current-password"
                  disabled={isSubmitting}
                  className={fieldErrors.password ? 'input-error' : ''}
                />
                <button
                  type="button"
                  className="toggle-password"
                  onClick={() => setShowPassword(!showPassword)}
                  aria-label={showPassword ? 'Hide password' : 'Show password'}
                  tabIndex={0}
                >
                  {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
              {fieldErrors.password && <span className="field-error-text">{fieldErrors.password}</span>}
            </div>

            <button
              type="submit"
              className="auth-submit-btn"
              disabled={isSubmitting}
              id="btn-submit-signin"
            >
              {isSubmitting ? (
                'Verifying Credentials...'
              ) : (
                <>
                  <span>Sign In</span>
                  <ArrowRight size={16} style={{ marginLeft: 6 }} />
                </>
              )}
            </button>
          </form>

          {/* Quick Demo Logins */}
          <div className="demo-accounts-section">
            <div className="demo-divider">
              <span>Or One-Click Demo Access</span>
            </div>
            <div className="demo-grid">
              <button
                type="button"
                className="demo-card-btn"
                onClick={() => handleDemoFill('demo@routewise.ai', 'routewise2026')}
                disabled={isSubmitting}
              >
                <div className="demo-card-header">
                  <span className="demo-icon-wrap"><Car size={15} /></span>
                  <strong>Dr. Kabir Sharma</strong>
                </div>
                <span className="demo-desc">Commuter (Personal Car)</span>
              </button>

              <button
                type="button"
                className="demo-card-btn"
                onClick={() => handleDemoFill('logistics@routewise.ai', 'routewise2026')}
                disabled={isSubmitting}
              >
                <div className="demo-card-header">
                  <span className="demo-icon-wrap"><Truck size={15} /></span>
                  <strong>Tariq Ahmad</strong>
                </div>
                <span className="demo-desc">Kashmir Freight (Heavy Truck)</span>
              </button>
            </div>
          </div>

          <div className="auth-switch-row">
            <span>Don't have an account yet?</span>
            <Link to="/auth/signup" state={{ from: destination }} className="auth-link">
              Create an Account
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
