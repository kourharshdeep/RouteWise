import React, { useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useAuth } from '../context/AuthContext';
import { useJourney } from '../context/JourneyContext';
import { changeLanguage } from '../i18n';
import {
  LayoutDashboard,
  Navigation as NavIcon,
  Map,
  Bot,
  History,
  Settings,
  LogOut,
  LogIn,
  Sun,
  Moon,
  X,
  Shield,
  Car,
  Sparkles,
  UserPlus,
  AlertTriangle,
  Globe,
} from 'lucide-react';

export default function Navigation({ theme, setTheme, health }) {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const location = useLocation();
  const { user, isAuthenticated, isGuest, logout } = useAuth();
  const { vehicleType, resetJourney } = useJourney();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  const isHealthy = health && health.status === 'ok';
  const isPatrol = user?.role === 'patrol' || user?.role === 'admin';

  // Base navigation items for commuters and general users
  const navItems = [
    { id: 'overview', path: '/overview', label: t('nav.overview'), icon: <LayoutDashboard size={18} /> },
    { id: 'journey', path: '/journey', label: t('nav.journey'), icon: <NavIcon size={18} /> },
    { id: 'map', path: '/map', label: t('nav.map'), icon: <Map size={18} /> },
    { id: 'report', path: '/reports', label: t('nav.report'), icon: <AlertTriangle size={18} /> },
  ];

  // Restricted Patrol Operations tab: strictly visible only to patrol and admin
  if (isPatrol) {
    navItems.push({
      id: 'patrol',
      path: '/patrol',
      label: t('nav.patrol'),
      icon: <Shield size={18} style={{ color: 'var(--accent-primary)' }} />,
    });
  }

  navItems.push(
    { id: 'chat', path: '/chat', label: t('nav.chat'), icon: <Bot size={18} /> },
    { id: 'history', path: '/history', label: t('nav.history'), icon: <History size={18} /> },
    { id: 'settings', path: '/settings', label: t('nav.settings'), icon: <Settings size={18} /> }
  );

  const handleNavClick = (path) => {
    navigate(path);
    setMobileMenuOpen(false);
  };

  const handleLogout = () => {
    logout();
    if (resetJourney) resetJourney();
    navigate('/', { replace: true });
  };

  const toggleLanguage = () => {
    const nextLang = i18n.language === 'hi' ? 'en' : 'hi';
    changeLanguage(nextLang);
  };

  const currentPath = location.pathname;

  return (
    <aside className={`app-sidebar ${mobileMenuOpen ? 'mobile-open' : ''}`}>
      {/* Sidebar Header & Brand */}
      <div className="sidebar-brand">
        <div className="brand-icon">RW</div>
        <div className="brand-text">
          <h1>RouteWise</h1>
          <span>NH-44 Corridor AI</span>
        </div>

        <button
          type="button"
          className="mobile-close-btn"
          onClick={() => setMobileMenuOpen(false)}
          aria-label="Close navigation"
        >
          <X size={20} />
        </button>
      </div>

      {/* Backend Status indicator */}
      <div className="sidebar-status-box">
        <div
          className="status-indicator-dot"
          style={{ background: isHealthy ? 'var(--success)' : 'var(--danger)' }}
        />
        <span>{isHealthy ? 'Backend Connected' : 'Backend Offline'}</span>
        <span className="badge badge-pill" style={{ marginLeft: 'auto', fontSize: 10 }}>
          v1.0
        </span>
      </div>

      {/* Guest Mode Indicator Callout */}
      {isGuest && (
        <div className="guest-mode-callout">
          <div className="guest-mode-info">
            <Sparkles size={14} className="guest-mode-sparkle" />
            <span>{t('app.guest_mode')}</span>
          </div>
          <button
            type="button"
            className="guest-upgrade-btn"
            onClick={() => navigate('/auth/signup')}
            title="Create an account to submit field reports and configure vehicle preferences"
          >
            <UserPlus size={13} />
            <span>{t('nav.signup')}</span>
          </button>
        </div>
      )}

      {/* Main Nav Links */}
      <nav className="sidebar-nav">
        {navItems.map((item) => {
          const isActive =
            currentPath === item.path ||
            (item.id === 'overview' && (currentPath === '/' || currentPath === ''));
          return (
            <button
              key={item.id}
              type="button"
              className={`nav-item ${isActive ? 'active' : ''}`}
              onClick={() => handleNavClick(item.path)}
            >
              <span className="nav-item-icon">{item.icon}</span>
              <span className="nav-item-label">{item.label}</span>
              {isActive && <span className="nav-active-pill" />}
            </button>
          );
        })}
      </nav>

      {/* Active Vehicle Badge */}
      <div
        className="sidebar-vehicle-pill"
        onClick={() => handleNavClick('/journey')}
        title="Click to view vehicle advisory"
      >
        <Car size={14} style={{ color: 'var(--accent-secondary)' }} />
        <span style={{ fontSize: 12 }}>
          Vehicle: <strong>{vehicleType}</strong>
        </span>
      </div>

      {/* Sidebar Footer: User / Language / Theme Toggle */}
      <div className="sidebar-footer">
        <div className="sidebar-actions-row">
          {/* Polished English / हिन्दी Segmented Toggle */}
          <div className="lang-segmented-control" role="group" aria-label="Language selection">
            <button
              type="button"
              className={`lang-segment-btn ${i18n.language !== 'hi' ? 'active' : ''}`}
              onClick={() => changeLanguage('en')}
              aria-pressed={i18n.language !== 'hi'}
              title="Switch to English"
            >
              English
            </button>
            <button
              type="button"
              className={`lang-segment-btn ${i18n.language === 'hi' ? 'active' : ''}`}
              onClick={() => changeLanguage('hi')}
              aria-pressed={i18n.language === 'hi'}
              title="हिन्दी में बदलें"
            >
              हिन्दी
            </button>
          </div>

          {/* Theme Switcher */}
          <label className="theme-switch" title="Toggle light/dark mode">
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

        {isAuthenticated ? (
          <div className="sidebar-user-card">
            <div className="user-avatar-circle">
              {isGuest ? 'G' : user?.name ? user.name.charAt(0).toUpperCase() : 'U'}
            </div>
            <div className="user-info">
              <span className="user-name">
                {isGuest ? 'Guest Observer' : user?.name}
              </span>
              <span className="user-role">
                {isGuest ? 'Guest (Read-Only)' : user?.role?.toUpperCase() || 'USER'}
              </span>
            </div>
            <button
              type="button"
              className="user-logout-btn"
              onClick={handleLogout}
              title={isGuest ? 'Exit Guest Session' : t('nav.signout')}
              aria-label={t('nav.signout')}
            >
              <LogOut size={16} />
            </button>
          </div>
        ) : (
          <button
            type="button"
            className="sidebar-login-btn"
            onClick={() => navigate('/auth/signin')}
          >
            <LogIn size={15} style={{ marginRight: 6 }} />
            <span>{t('nav.signin')}</span>
          </button>
        )}
      </div>
    </aside>
  );
}
