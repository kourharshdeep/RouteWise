import React, { useState } from 'react';
import { useNavigate, useLocation, Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import {
  Lock,
  Mail,
  User,
  Eye,
  EyeOff,
  AlertCircle,
  ArrowRight,
  ArrowLeft,
  Sun,
  Moon,
  Shield,
  Car,
} from 'lucide-react';

export default function SignUpView({ theme, setTheme }) {
  const navigate = useNavigate();
  const location = useLocation();
  const { register, authError, setAuthError } = useAuth();

  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [role, setRole] = useState('commuter');
  const [preferredVehicle, setPreferredVehicle] = useState('Car');

  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [fieldErrors, setFieldErrors] = useState({});
  const [isSubmitting, setIsSubmitting] = useState(false);

  const destination = location.state?.from || '/overview';

  const validate = () => {
    const errors = {};
    if (!name.trim()) {
      errors.name = 'Full name is required.';
    }

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

    if (password !== confirmPassword) {
      errors.confirmPassword = 'Passwords do not match.';
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
      await register({
        email: email.trim(),
        password,
        name: name.trim(),
        role,
        preferred_vehicle: preferredVehicle,
      });
      navigate(destination, { replace: true });
    } catch (err) {
      // Auth error is captured in context
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
              <h2>Create RouteWise Account</h2>
              <p>Join the NH-44 Predictive Intelligence Platform</p>
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
              <label htmlFor="signup-name">Full Name</label>
              <div className="input-with-icon">
                <User size={16} className="field-icon" />
                <input
                  id="signup-name"
                  type="text"
                  placeholder="e.g. Dr. Kabir Sharma"
                  value={name}
                  onChange={(e) => {
                    setName(e.target.value);
                    if (fieldErrors.name) setFieldErrors({ ...fieldErrors, name: null });
                  }}
                  disabled={isSubmitting}
                  className={fieldErrors.name ? 'input-error' : ''}
                  required
                />
              </div>
              {fieldErrors.name && <span className="field-error-text">{fieldErrors.name}</span>}
            </div>

            <div className="form-group">
              <label htmlFor="signup-email">Email Address</label>
              <div className="input-with-icon">
                <Mail size={16} className="field-icon" />
                <input
                  id="signup-email"
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
                  required
                />
              </div>
              {fieldErrors.email && <span className="field-error-text">{fieldErrors.email}</span>}
            </div>

            <div className="form-row-2">
              <div className="form-group">
                <label htmlFor="signup-password">Password</label>
                <div className="input-with-icon">
                  <Lock size={16} className="field-icon" />
                  <input
                    id="signup-password"
                    type={showPassword ? 'text' : 'password'}
                    placeholder="Min 6 chars"
                    value={password}
                    onChange={(e) => {
                      setPassword(e.target.value);
                      if (fieldErrors.password) setFieldErrors({ ...fieldErrors, password: null });
                    }}
                    autoComplete="new-password"
                    disabled={isSubmitting}
                    className={fieldErrors.password ? 'input-error' : ''}
                    required
                  />
                  <button
                    type="button"
                    className="toggle-password"
                    onClick={() => setShowPassword(!showPassword)}
                    aria-label={showPassword ? 'Hide password' : 'Show password'}
                  >
                    {showPassword ? <EyeOff size={15} /> : <Eye size={15} />}
                  </button>
                </div>
                {fieldErrors.password && <span className="field-error-text">{fieldErrors.password}</span>}
              </div>

              <div className="form-group">
                <label htmlFor="signup-confirm-password">Confirm Password</label>
                <div className="input-with-icon">
                  <Lock size={16} className="field-icon" />
                  <input
                    id="signup-confirm-password"
                    type={showConfirmPassword ? 'text' : 'password'}
                    placeholder="Repeat password"
                    value={confirmPassword}
                    onChange={(e) => {
                      setConfirmPassword(e.target.value);
                      if (fieldErrors.confirmPassword) setFieldErrors({ ...fieldErrors, confirmPassword: null });
                    }}
                    autoComplete="new-password"
                    disabled={isSubmitting}
                    className={fieldErrors.confirmPassword ? 'input-error' : ''}
                    required
                  />
                  <button
                    type="button"
                    className="toggle-password"
                    onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                    aria-label={showConfirmPassword ? 'Hide confirm password' : 'Show confirm password'}
                  >
                    {showConfirmPassword ? <EyeOff size={15} /> : <Eye size={15} />}
                  </button>
                </div>
                {fieldErrors.confirmPassword && (
                  <span className="field-error-text">{fieldErrors.confirmPassword}</span>
                )}
              </div>
            </div>

            <div className="form-row-2">
              <div className="form-group">
                <label htmlFor="signup-role">Operational Role</label>
                <select
                  id="signup-role"
                  value={role}
                  onChange={(e) => setRole(e.target.value)}
                  className="custom-select"
                >
                  <option value="commuter">Public Commuter</option>
                  <option value="logistics_operator">Logistics / Freight Operator</option>
                  <option value="patrol_officer">Highway Patrol Officer</option>
                  <option value="emergency_responder">Emergency Responder</option>
                </select>
              </div>

              <div className="form-group">
                <label htmlFor="signup-vehicle">Default Vehicle</label>
                <select
                  id="signup-vehicle"
                  value={preferredVehicle}
                  onChange={(e) => setPreferredVehicle(e.target.value)}
                  className="custom-select"
                >
                  <option value="Car">Car / SUV</option>
                  <option value="Motorcycle">Motorcycle</option>
                  <option value="Bus">Bus</option>
                  <option value="Truck">Truck / Heavy Freight</option>
                  <option value="Other">Other / Emergency</option>
                </select>
              </div>
            </div>

            <button
              type="submit"
              className="auth-submit-btn"
              disabled={isSubmitting}
              id="btn-submit-signup"
            >
              {isSubmitting ? (
                'Creating Account...'
              ) : (
                <>
                  <span>Create Account</span>
                  <ArrowRight size={16} style={{ marginLeft: 6 }} />
                </>
              )}
            </button>
          </form>

          <div className="auth-switch-row">
            <span>Already have an account?</span>
            <Link to="/auth/signin" state={{ from: destination }} className="auth-link">
              Sign In
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
