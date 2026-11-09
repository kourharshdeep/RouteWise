import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Bell,
  X,
  AlertTriangle,
  AlertOctagon,
  Info,
  CheckCircle2,
  Shield,
  Clock,
  Check,
  Trash2,
} from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { acknowledgeAlert, clearAlert } from '../services/api';

export default function AlertDrawer({
  isOpen,
  onClose,
  alerts = [],
  onAlertUpdated,
}) {
  const { user } = useAuth();
  const { t } = useTranslation();
  const [processingId, setProcessingId] = useState(null);
  const [actionError, setActionError] = useState(null);

  if (!isOpen) return null;

  const canAcknowledgeOrClear = user && (user.role === 'patrol' || user.role === 'admin');

  const handleAcknowledge = async (alertId) => {
    try {
      setProcessingId(alertId);
      setActionError(null);
      await acknowledgeAlert(alertId);
      if (onAlertUpdated) onAlertUpdated();
    } catch (err) {
      setActionError(err.message || 'Failed to acknowledge alert');
    } finally {
      setProcessingId(null);
    }
  };

  const handleClear = async (alertId) => {
    try {
      setProcessingId(alertId);
      setActionError(null);
      await clearAlert(alertId);
      if (onAlertUpdated) onAlertUpdated();
    } catch (err) {
      setActionError(err.message || 'Failed to clear alert');
    } finally {
      setProcessingId(null);
    }
  };

  const getSeverityIcon = (sev) => {
    switch (sev) {
      case 'critical':
        return <AlertOctagon size={18} style={{ color: 'var(--danger)' }} />;
      case 'warning':
        return <AlertTriangle size={18} style={{ color: 'var(--warning, #f97316)' }} />;
      case 'advisory':
        return <Info size={18} style={{ color: 'var(--accent-primary, #3b82f6)' }} />;
      default:
        return <Info size={18} style={{ color: 'var(--text-muted)' }} />;
    }
  };

  const activeAlerts = alerts.filter((a) => a.status !== 'cleared');

  return (
    <div className="alert-drawer-backdrop" onClick={onClose}>
      <div
        className="alert-drawer-panel"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-label="Active Corridor Alerts Drawer"
      >
        {/* Drawer Header */}
        <div className="alert-drawer-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <Bell size={18} style={{ color: 'var(--accent-primary)' }} />
            <h3 style={{ margin: 0, fontSize: 16 }}>Corridor Active Alerts ({activeAlerts.length})</h3>
          </div>
          <button
            type="button"
            className="icon-btn"
            onClick={onClose}
            aria-label="Close alerts drawer"
          >
            <X size={18} />
          </button>
        </div>

        {/* In-App Delivery Boundary Notice */}
        <div className="alert-boundary-notice">
          <Shield size={14} style={{ flexShrink: 0, marginTop: 1, color: 'var(--accent-secondary)' }} />
          <span>
            <strong>In-App Delivery Boundary:</strong> All alerts are delivered purely inside this web application.
            No SMS, cellular broadcasts, or external push notification daemons are utilized.
          </span>
        </div>

        {actionError && (
          <div className="auth-error-banner" style={{ margin: '8px 16px' }}>
            <AlertOctagon size={14} />
            <span>{actionError}</span>
          </div>
        )}

        {/* Alert Items List */}
        <div className="alert-drawer-body">
          {activeAlerts.length === 0 ? (
            <div className="alert-empty-state">
              <CheckCircle2 size={32} style={{ color: 'var(--success, #22c55e)' }} />
              <p>No active corridor disruption alerts at this time.</p>
              <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>Baseline mountain driving precautions apply.</span>
            </div>
          ) : (
            activeAlerts.map((item) => {
              const isCrit = item.severity === 'critical';
              const isAck = item.status === 'acknowledged';

              return (
                <div
                  key={item.id}
                  className={`alert-card ${isCrit ? 'alert-critical' : 'alert-warning'} ${isAck ? 'alert-ack' : ''}`}
                >
                  <div className="alert-card-header">
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                      {getSeverityIcon(item.severity)}
                      <strong style={{ fontSize: 13 }}>{item.title_en}</strong>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                      {item.is_stale_context && (
                        <span
                          className="badge badge-stale-context"
                          data-testid="badge-stale-context"
                          style={{ fontSize: 10, borderColor: '#eab308', color: '#eab308' }}
                        >
                          {t('alerts.lastKnownDataStale')}
                        </span>
                      )}
                      {item.is_simulated && (
                        <span className="badge badge-pill" style={{ fontSize: 10, borderColor: '#f97316', color: '#f97316' }}>
                          SIMULATED
                        </span>
                      )}
                      <span className={`badge ${isAck ? 'badge-connected' : 'badge-disconnected'}`} style={{ fontSize: 10 }}>
                        {item.status.toUpperCase()}
                      </span>
                    </div>
                  </div>

                  <div className="alert-card-bilingual">
                    <p className="alert-msg-en">{item.message_en}</p>
                    <p className="alert-msg-hi" style={{ fontSize: 12, opacity: 0.85, margin: '4px 0 0 0' }}>
                      {item.message_hi}
                    </p>
                  </div>

                  <div className="alert-card-meta">
                    <span style={{ fontFamily: 'monospace', fontSize: 11, color: 'var(--text-muted)' }}>
                      Seg: {item.segment_id}
                    </span>
                    <span style={{ fontSize: 11, color: 'var(--text-dim)' }}>
                      <Clock size={11} style={{ display: 'inline', marginRight: 3 }} />
                      {new Date(item.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                    </span>
                  </div>

                  {/* Patrol / Admin Action Controls */}
                  {canAcknowledgeOrClear && (
                    <div className="alert-card-actions">
                      {!isAck && (
                        <button
                          type="button"
                          className="sample-btn"
                          style={{ padding: '3px 8px', fontSize: 11 }}
                          disabled={processingId === item.id}
                          onClick={() => handleAcknowledge(item.id)}
                        >
                          <Check size={12} style={{ marginRight: 4 }} />
                          Acknowledge
                        </button>
                      )}
                      <button
                        type="button"
                        className="sample-btn"
                        style={{ padding: '3px 8px', fontSize: 11, color: 'var(--danger)' }}
                        disabled={processingId === item.id}
                        onClick={() => handleClear(item.id)}
                      >
                        <Trash2 size={12} style={{ marginRight: 4 }} />
                        Clear Alert
                      </button>
                    </div>
                  )}
                </div>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
}
