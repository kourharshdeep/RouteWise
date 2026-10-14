import React, { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { useAuth } from '../context/AuthContext';
import {
  Shield,
  Filter,
  CheckCircle,
  AlertTriangle,
  UserCheck,
  CheckSquare,
  XCircle,
  RotateCcw,
  Search,
  RefreshCw,
  Eye,
  Camera,
  MapPin,
  Clock,
  Send,
  Lock,
} from 'lucide-react';
import {
  fetchPatrolReports,
  fetchReportSummary,
  updateReportStatus,
  assignReportToPatrol,
} from '../services/api';

export default function PatrolDashboard() {
  const { t } = useTranslation();
  const { user, isPatrol } = useAuth();

  const [summary, setSummary] = useState(null);
  const [reports, setReports] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Filters
  const [statusFilter, setStatusFilter] = useState('all');
  const [categoryFilter, setCategoryFilter] = useState('all');
  const [segmentSearch, setSegmentSearch] = useState('');

  // Selected Report Modal
  const [selectedReport, setSelectedReport] = useState(null);
  const [actionNote, setActionNote] = useState('');
  const [assigneeId, setAssigneeId] = useState(user?.id || 1);
  const [actionError, setActionError] = useState(null);
  const [isSubmittingAction, setIsSubmittingAction] = useState(false);

  useEffect(() => {
    if (isPatrol) {
      loadData();
    }
  }, [isPatrol, statusFilter, categoryFilter, segmentSearch]);

  const loadData = async () => {
    try {
      setLoading(true);
      setError(null);
      const [sumRes, repRes] = await Promise.all([
        fetchReportSummary(),
        fetchPatrolReports({
          status: statusFilter,
          category: categoryFilter,
          segment_id: segmentSearch.trim() || undefined,
        }),
      ]);
      setSummary(sumRes);
      setReports(repRes.items);
      setTotal(repRes.total);
    } catch (err) {
      setError(err.message || 'Failed to load patrol operations data.');
    } finally {
      setLoading(false);
    }
  };

  const handleAction = async (newStatus) => {
    if (!selectedReport) return;
    setActionError(null);

    // Require note for rejection or reopening
    if (newStatus === 'rejected' && !actionNote.trim()) {
      setActionError('A note explaining the rejection reason is required.');
      return;
    }
    if (selectedReport.status === 'resolved' && newStatus === 'verified' && !actionNote.trim()) {
      setActionError('A note is required when reopening a resolved report.');
      return;
    }

    try {
      setIsSubmittingAction(true);
      const updated = await updateReportStatus(selectedReport.id, newStatus, actionNote.trim());
      setSelectedReport(updated);
      setActionNote('');
      await loadData();
    } catch (err) {
      setActionError(err.message || 'Failed to execute status update.');
    } finally {
      setIsSubmittingAction(false);
    }
  };

  const handleAssign = async () => {
    if (!selectedReport) return;
    setActionError(null);
    try {
      setIsSubmittingAction(true);
      const updated = await assignReportToPatrol(selectedReport.id, assigneeId, actionNote.trim());
      setSelectedReport(updated);
      setActionNote('');
      await loadData();
    } catch (err) {
      setActionError(err.message || 'Failed to assign report.');
    } finally {
      setIsSubmittingAction(false);
    }
  };

  if (!isPatrol) {
    return (
      <div className="state-box state-error" style={{ margin: '60px auto', maxWidth: 500 }}>
        <Lock size={32} />
        <div>
          <h3>Access Restricted to Highway Patrol</h3>
          <p>
            You are currently signed in as <strong>{user?.role || 'Guest'}</strong>.
            The Patrol Operations Center requires verified Highway Patrol Officer credentials.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="patrol-dashboard-container">
      {/* Dashboard Top Header */}
      <div className="patrol-header">
        <div className="patrol-header-title">
          <div className="patrol-badge-icon">
            <Shield size={24} />
          </div>
          <div>
            <h2>{t('patrol.dashboard_title')}</h2>
            <span>{t('patrol.dashboard_subtitle')}</span>
          </div>
        </div>
        <button
          type="button"
          className="btn btn-secondary"
          onClick={loadData}
          disabled={loading}
        >
          <RefreshCw size={14} className={loading ? 'spin-icon' : ''} />
          <span>Refresh Queue</span>
        </button>
      </div>

      {/* Summary Metrics Strip */}
      <div className="patrol-summary-strip">
        <div
          className={`summary-pill ${statusFilter === 'all' ? 'active' : ''}`}
          onClick={() => setStatusFilter('all')}
        >
          <span className="summary-pill-label">Total Reports</span>
          <strong className="summary-pill-val">{summary?.total ?? '—'}</strong>
        </div>
        <div
          className={`summary-pill status-submitted ${statusFilter === 'submitted' ? 'active' : ''}`}
          onClick={() => setStatusFilter('submitted')}
        >
          <span className="summary-pill-label">Submitted</span>
          <strong className="summary-pill-val">{summary?.submitted ?? '—'}</strong>
        </div>
        <div
          className={`summary-pill status-verified ${statusFilter === 'verified' ? 'active' : ''}`}
          onClick={() => setStatusFilter('verified')}
        >
          <span className="summary-pill-label">Verified</span>
          <strong className="summary-pill-val">{summary?.verified ?? '—'}</strong>
        </div>
        <div
          className={`summary-pill status-assigned ${statusFilter === 'assigned' ? 'active' : ''}`}
          onClick={() => setStatusFilter('assigned')}
        >
          <span className="summary-pill-label">Assigned</span>
          <strong className="summary-pill-val">{summary?.assigned ?? '—'}</strong>
        </div>
        <div
          className={`summary-pill status-resolved ${statusFilter === 'resolved' ? 'active' : ''}`}
          onClick={() => setStatusFilter('resolved')}
        >
          <span className="summary-pill-label">Resolved</span>
          <strong className="summary-pill-val">{summary?.resolved ?? '—'}</strong>
        </div>
        <div
          className={`summary-pill status-rejected ${statusFilter === 'rejected' ? 'active' : ''}`}
          onClick={() => setStatusFilter('rejected')}
        >
          <span className="summary-pill-label">Rejected</span>
          <strong className="summary-pill-val">{summary?.rejected ?? '—'}</strong>
        </div>
      </div>

      {/* Filter and Search Bar */}
      <div className="patrol-filter-bar">
        <div className="filter-item">
          <Filter size={15} />
          <select
            className="filter-select"
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
          >
            <option value="all">All Statuses</option>
            <option value="submitted">Submitted</option>
            <option value="verified">Verified</option>
            <option value="assigned">Assigned</option>
            <option value="resolved">Resolved</option>
            <option value="rejected">Rejected</option>
          </select>
        </div>

        <div className="filter-item">
          <select
            className="filter-select"
            value={categoryFilter}
            onChange={(e) => setCategoryFilter(e.target.value)}
          >
            <option value="all">All Hazard Categories</option>
            <option value="landslide">Landslide</option>
            <option value="shooting_stones">Shooting Stones</option>
            <option value="flooding">Waterlogging / Flooding</option>
            <option value="road_damage">Road Damage</option>
            <option value="single_lane_or_obstruction">Single Lane / Obstruction</option>
            <option value="snow_or_ice">Snow / Ice</option>
            <option value="other">Other</option>
          </select>
        </div>

        <div className="filter-search-wrapper">
          <Search size={15} />
          <input
            type="text"
            className="filter-search-input"
            placeholder="Filter by segment ID..."
            value={segmentSearch}
            onChange={(e) => setSegmentSearch(e.target.value)}
          />
        </div>
      </div>

      {/* Reports Queue Table */}
      <div className="patrol-table-card">
        {loading ? (
          <div className="state-box state-loading" style={{ margin: '40px auto' }}>
            <span>Retrieving operational report queue...</span>
          </div>
        ) : error ? (
          <div className="state-box state-error" style={{ margin: '20px auto' }}>
            <span>{error}</span>
          </div>
        ) : reports.length === 0 ? (
          <div className="state-box state-neutral" style={{ margin: '40px auto' }}>
            <CheckCircle size={30} style={{ color: 'var(--success)' }} />
            <div>
              <strong>No incidents matching active filters</strong>
              <p style={{ margin: 0, fontSize: 13, color: 'var(--text-muted)' }}>
                All corridor incident reports in this view have been processed.
              </p>
            </div>
          </div>
        ) : (
          <div className="table-responsive">
            <table className="patrol-table">
              <thead>
                <tr>
                  <th>Status</th>
                  <th>Category</th>
                  <th>Corridor Segment</th>
                  <th>Age / Timestamp</th>
                  <th>Reporter</th>
                  <th>Assignee</th>
                  <th>Demo Badge</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {reports.map((rep) => (
                  <tr key={rep.id} className="patrol-table-row">
                    <td>
                      <span className={`badge badge-status-${rep.status}`}>
                        {t(`status.${rep.status}`)}
                      </span>
                    </td>
                    <td>
                      <span className="badge badge-category">
                        {t(`categories.${rep.category}`)}
                      </span>
                    </td>
                    <td>
                      <strong>{rep.nearest_segment_id || 'Off-corridor'}</strong>
                      {rep.nearest_segment_distance_m && (
                        <span className="table-sub-detail">
                          {rep.nearest_segment_distance_m}m
                        </span>
                      )}
                    </td>
                    <td>
                      <span className="table-main-text">
                        {new Date(rep.created_at).toLocaleTimeString()}
                      </span>
                      <span className="table-sub-detail">
                        {new Date(rep.created_at).toLocaleDateString()}
                      </span>
                    </td>
                    <td>{rep.reporter_name || 'Public Commuter'}</td>
                    <td>{rep.assigned_to_name || '—'}</td>
                    <td>
                      {rep.is_simulated ? (
                        <span className="badge badge-simulated">{t('app.simulated_badge')}</span>
                      ) : (
                        <span className="badge badge-subtle">Live Capture</span>
                      )}
                    </td>
                    <td>
                      <button
                        type="button"
                        className="btn btn-sm btn-primary"
                        onClick={() => {
                          setSelectedReport(rep);
                          setActionError(null);
                          setActionNote('');
                        }}
                      >
                        <Eye size={13} />
                        <span>Manage</span>
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Incident Detail & State Machine Action Modal */}
      {selectedReport && (
        <div className="modal-backdrop" onClick={() => setSelectedReport(null)}>
          <div className="modal-dialog" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <div className="modal-title-group">
                <h3>Manage Incident: {t(`categories.${selectedReport.category}`)}</h3>
                <span className={`badge badge-status-${selectedReport.status}`}>
                  {t(`status.${selectedReport.status}`)}
                </span>
                {selectedReport.is_simulated && (
                  <span className="badge badge-simulated">{t('app.simulated_badge')}</span>
                )}
              </div>
              <button
                type="button"
                className="modal-close-btn"
                onClick={() => setSelectedReport(null)}
              >
                ✕
              </button>
            </div>

            <div className="modal-body">
              {actionError && (
                <div className="state-box state-error" style={{ marginBottom: 16 }}>
                  <span>{actionError}</span>
                </div>
              )}

              {/* Details Summary */}
              <div className="incident-meta-grid">
                <div>
                  <span className="meta-label">Location</span>
                  <strong>{selectedReport.latitude}°N, {selectedReport.longitude}°E</strong>
                  {selectedReport.nearest_segment_id && (
                    <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                      Snapped to: {selectedReport.nearest_segment_id}
                    </div>
                  )}
                </div>
                <div>
                  <span className="meta-label">Reporter</span>
                  <strong>{selectedReport.reporter_name || 'Anonymous User'}</strong>
                </div>
                <div>
                  <span className="meta-label">Current Assignee</span>
                  <strong>{selectedReport.assigned_to_name || 'Unassigned'}</strong>
                </div>
                <div>
                  <span className="meta-label">Capture Timestamp</span>
                  <strong>{new Date(selectedReport.created_at).toLocaleString()}</strong>
                </div>
              </div>

              {selectedReport.description && (
                <div className="incident-desc-box">
                  <span className="meta-label">Field Description:</span>
                  <p>{selectedReport.description}</p>
                </div>
              )}

              {/* Photo Evidence */}
              {selectedReport.has_photo && selectedReport.photo_url && (
                <div className="incident-photo-section">
                  <span className="meta-label">
                    <Camera size={14} style={{ display: 'inline', marginRight: 4 }} />
                    Attached Photo Evidence:
                  </span>
                  <div className="modal-photo-wrapper">
                    <img
                      src={selectedReport.photo_url}
                      alt="Incident evidence"
                      className="modal-photo-img"
                    />
                  </div>
                </div>
              )}

              {/* Audit Timeline */}
              <div className="incident-audit-section">
                <h4>Audit Trail History ({selectedReport.history?.length || 0})</h4>
                <div className="timeline-steps">
                  {selectedReport.history?.map((h, i) => (
                    <div key={h.id || i} className="timeline-step">
                      <div className="timeline-dot" />
                      <div className="timeline-content">
                        <div>
                          <strong>{h.to_status.toUpperCase()}</strong> by {h.actor_name} ({h.actor_role})
                        </div>
                        {h.note && <div className="timeline-note">{h.note}</div>}
                        <div className="timeline-time">{new Date(h.timestamp).toLocaleString()}</div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* State Machine Transition Actions */}
              <div className="state-machine-actions-box">
                <h4>Dispatch & State Transition Actions</h4>

                <div className="form-group" style={{ marginBottom: 12 }}>
                  <label className="form-label">
                    Action / Rejection Note (Mandatory for rejection or reopening)
                  </label>
                  <input
                    type="text"
                    className="form-input"
                    placeholder={t('patrol.note_placeholder')}
                    value={actionNote}
                    onChange={(e) => setActionNote(e.target.value)}
                  />
                </div>

                <div className="action-buttons-group">
                  {/* Status: SUBMITTED -> Verified OR Rejected */}
                  {selectedReport.status === 'submitted' && (
                    <>
                      <button
                        type="button"
                        className="btn btn-success"
                        onClick={() => handleAction('verified')}
                        disabled={isSubmittingAction}
                      >
                        <CheckCircle size={15} />
                        <span>{t('patrol.verify_action')}</span>
                      </button>
                      <button
                        type="button"
                        className="btn btn-danger"
                        onClick={() => handleAction('rejected')}
                        disabled={isSubmittingAction}
                      >
                        <XCircle size={15} />
                        <span>{t('patrol.reject_action')}</span>
                      </button>
                    </>
                  )}

                  {/* Status: VERIFIED -> Assigned OR Rejected */}
                  {selectedReport.status === 'verified' && (
                    <>
                      <button
                        type="button"
                        className="btn btn-primary"
                        onClick={handleAssign}
                        disabled={isSubmittingAction}
                      >
                        <UserCheck size={15} />
                        <span>{t('patrol.assign_action')}</span>
                      </button>
                      <button
                        type="button"
                        className="btn btn-danger"
                        onClick={() => handleAction('rejected')}
                        disabled={isSubmittingAction}
                      >
                        <XCircle size={15} />
                        <span>{t('patrol.reject_action')}</span>
                      </button>
                    </>
                  )}

                  {/* Status: ASSIGNED -> Resolved OR Rejected */}
                  {selectedReport.status === 'assigned' && (
                    <>
                      <button
                        type="button"
                        className="btn btn-success"
                        onClick={() => handleAction('resolved')}
                        disabled={isSubmittingAction}
                      >
                        <CheckSquare size={15} />
                        <span>{t('patrol.resolve_action')}</span>
                      </button>
                      <button
                        type="button"
                        className="btn btn-danger"
                        onClick={() => handleAction('rejected')}
                        disabled={isSubmittingAction}
                      >
                        <XCircle size={15} />
                        <span>{t('patrol.reject_action')}</span>
                      </button>
                    </>
                  )}

                  {/* Status: RESOLVED -> Reopen to Verified */}
                  {selectedReport.status === 'resolved' && (
                    <button
                      type="button"
                      className="btn btn-secondary"
                      onClick={() => handleAction('verified')}
                      disabled={isSubmittingAction}
                    >
                      <RotateCcw size={15} />
                      <span>{t('patrol.reopen_action')}</span>
                    </button>
                  )}

                  {selectedReport.status === 'rejected' && (
                    <span className="terminal-note">
                      Report is in terminal rejected state. No further transitions permitted.
                    </span>
                  )}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
