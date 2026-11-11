import React from 'react';
import { AlertOctagon, RotateCcw } from 'lucide-react';
import i18n from '../i18n';

export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    console.error("ErrorBoundary caught render crash:", error, errorInfo);
  }

  handleReload = () => {
    if (typeof window !== 'undefined') {
      window.location.reload();
    }
  };

  render() {
    if (this.state.hasError) {
      const title = i18n.t('error_boundary.title', { defaultValue: 'Something went wrong' });
      const message = i18n.t('error_boundary.message', {
        defaultValue: 'An unexpected error occurred while rendering the dashboard.',
      });
      const reloadText = i18n.t('error_boundary.reload', { defaultValue: 'Reload Application' });

      return (
        <div
          className="error-boundary-card"
          role="alert"
          style={{
            padding: '40px 24px',
            maxWidth: '540px',
            margin: '60px auto',
            textAlign: 'center',
            background: 'var(--bg-card, #1e293b)',
            border: '1px solid var(--border-color, #334155)',
            borderRadius: '12px',
            boxShadow: '0 8px 24px rgba(0, 0, 0, 0.25)',
            color: 'var(--text-primary, #f8fafc)',
          }}
        >
          <div
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              width: '56px',
              height: '56px',
              borderRadius: '50%',
              background: 'rgba(239, 68, 68, 0.15)',
              color: 'var(--danger, #ef4444)',
              marginBottom: '16px',
            }}
          >
            <AlertOctagon size={32} aria-hidden="true" />
          </div>
          <h2 style={{ fontSize: '20px', fontWeight: 700, marginBottom: '8px' }}>
            {title}
          </h2>
          <p
            style={{
              fontSize: '14px',
              color: 'var(--text-muted, #94a3b8)',
              marginBottom: '24px',
              lineHeight: 1.5,
            }}
          >
            {message}
          </p>
          <button
            type="button"
            className="sample-btn active"
            onClick={this.handleReload}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '8px',
              padding: '10px 20px',
              fontSize: '14px',
              fontWeight: 600,
              cursor: 'pointer',
            }}
          >
            <RotateCcw size={16} aria-hidden="true" />
            {reloadText}
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}

