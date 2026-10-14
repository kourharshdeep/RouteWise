import React, { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { useAuth } from '../context/AuthContext';
import {
  AlertTriangle,
  Camera,
  MapPin,
  Clock,
  Send,
  RefreshCw,
  Trash2,
  CheckCircle,
  FileText,
  AlertCircle,
  Shield,
  Layers,
  ChevronRight,
  Info,
  Save,
  RotateCcw,
} from 'lucide-react';
import {
  enqueueReport,
  getPendingReports,
  syncPendingQueue,
  removeReportFromQueue,
} from '../services/reportQueue';
import { fetchMyReports } from '../services/api';

const CATEGORIES = [
  { id: 'landslide', icon: '⛰️' },
  { id: 'shooting_stones', icon: '🪨' },
  { id: 'flooding', icon: '🌊' },
  { id: 'road_damage', icon: '🚧' },
  { id: 'single_lane_or_obstruction', icon: '⚠️' },
  { id: 'snow_or_ice', icon: '❄️' },
  { id: 'other', icon: '📍' },
];

const CORRIDOR_SHORTCUTS = [
  { name: 'Chanderkot', lat: '33.2080', lon: '75.2950' },
  { name: 'Cafeteria Morh', lat: '33.2370', lon: '75.2420' },
  { name: 'Ramban Town', lat: '33.2530', lon: '75.2070' },
  { name: 'Maroog', lat: '33.2620', lon: '75.1860' },
  { name: 'Digdol', lat: '33.3030', lon: '75.1820' },
  { name: 'Ramsu', lat: '33.3440', lon: '75.2000' },
  { name: 'Banihal', lat: '33.4380', lon: '75.1910' },
];

export default function IncidentReporter({ onNavigateToSignIn }) {
  const { t } = useTranslation();
  const { token, isAuthenticated, isGuest } = useAuth();

  const [activeTab, setActiveTab] = useState('new'); // 'new', 'pending', 'mine'

  // Form State
  const [category, setCategory] = useState('shooting_stones');
  const [description, setDescription] = useState('');
  const [latitude, setLatitude] = useState('33.2435');
  const [longitude, setLongitude] = useState('75.2415');
  const [locationSource, setLocationSource] = useState('Default (Ramban Gateway)');
  const [gpsAccuracy, setGpsAccuracy] = useState(null);
  const [isCapturingGps, setIsCapturingGps] = useState(false);
  const [photoBlob, setPhotoBlob] = useState(null);
  const [photoPreview, setPhotoPreview] = useState(null);
  const [photoName, setPhotoName] = useState(null);
  const [formStep, setFormStep] = useState(1); // 1 = Details, 2 = Review & Confirm
  const [formError, setFormError] = useState(null);
  const [submitSuccess, setSubmitSuccess] = useState(false);
  const [draftRestored, setDraftRestored] = useState(false);

  // Queue & My Reports State
  const [pendingItems, setPendingItems] = useState([]);
  const [isSyncing, setIsSyncing] = useState(false);
  const [myReports, setMyReports] = useState([]);
  const [loadingReports, setLoadingReports] = useState(false);

  // 1. Restore draft from localStorage on initial load
  useEffect(() => {
    try {
      const savedDraft = localStorage.getItem('routewise_incident_draft');
      if (savedDraft) {
        const parsed = JSON.parse(savedDraft);
        if (parsed.category) setCategory(parsed.category);
        if (parsed.description) setDescription(parsed.description);
        if (parsed.latitude) setLatitude(parsed.latitude);
        if (parsed.longitude) setLongitude(parsed.longitude);
        if (parsed.locationSource) setLocationSource(parsed.locationSource);
        setDraftRestored(true);
      }
    } catch (_) {}
  }, []);

  // 2. Auto-save draft on changes
  useEffect(() => {
    if (description || category !== 'shooting_stones' || latitude !== '33.2435') {
      try {
        localStorage.setItem(
          'routewise_incident_draft',
          JSON.stringify({
            category,
            description,
            latitude,
            longitude,
            locationSource,
          })
        );
      } catch (_) {}
    }
  }, [category, description, latitude, longitude, locationSource]);

  const handleClearDraft = () => {
    try {
      localStorage.removeItem('routewise_incident_draft');
    } catch (_) {}
    setCategory('shooting_stones');
    setDescription('');
    setLatitude('33.2435');
    setLongitude('75.2415');
    setLocationSource('Default (Ramban Gateway)');
    setGpsAccuracy(null);
    setPhotoBlob(null);
    setPhotoPreview(null);
    setPhotoName(null);
    setDraftRestored(false);
  };

  // Refresh pending queue
  const refreshQueue = async () => {
    try {
      const items = await getPendingReports();
      setPendingItems(items);
    } catch (err) {
      console.warn('Error reading indexedDB queue:', err);
    }
  };

  useEffect(() => {
    refreshQueue();
    const interval = setInterval(refreshQueue, 4000);
    return () => clearInterval(interval);
  }, []);

  // Listen to online events
  useEffect(() => {
    const handleOnline = () => {
      triggerSync();
    };
    window.addEventListener('online', handleOnline);
    return () => window.removeEventListener('online', handleOnline);
  }, [token]);

  // Load user reports when tab changes
  useEffect(() => {
    if (activeTab === 'mine' && isAuthenticated && !isGuest) {
      loadMyReports();
    }
  }, [activeTab, isAuthenticated, isGuest]);

  const loadMyReports = async () => {
    try {
      setLoadingReports(true);
      const data = await fetchMyReports();
      setMyReports(data);
    } catch (err) {
      console.error('Failed to load my reports:', err);
    } finally {
      setLoadingReports(false);
    }
  };

  const handleCaptureGps = () => {
    if (!navigator.geolocation) {
      setFormError('Geolocation is not supported by your browser.');
      return;
    }
    setIsCapturingGps(true);
    setFormError(null);
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setIsCapturingGps(false);
        const lat = pos.coords.latitude.toFixed(6);
        const lon = pos.coords.longitude.toFixed(6);
        setLatitude(lat);
        setLongitude(lon);
        const acc = Math.round(pos.coords.accuracy);
        setGpsAccuracy(acc);
        setLocationSource(`Live GPS (±${acc}m)`);
      },
      (err) => {
        setIsCapturingGps(false);
        setFormError(t('reporter.gps_denied'));
      },
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 }
    );
  };

  const handleSelectShortcut = (sc) => {
    setLatitude(sc.lat);
    setLongitude(sc.lon);
    setLocationSource(`Landmark: ${sc.name}`);
    setGpsAccuracy(null);
    setFormError(null);
  };

  const handlePhotoSelect = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;

    if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) {
      setFormError(t('validation.photo_format'));
      return;
    }
    if (file.size > 5 * 1024 * 1024) {
      setFormError(t('validation.photo_size'));
      return;
    }

    setPhotoBlob(file);
    setPhotoName(file.name);
    setFormError(null);

    const reader = new FileReader();
    reader.onload = () => {
      setPhotoPreview(reader.result);
    };
    reader.readAsDataURL(file);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (isGuest) {
      setFormError(t('app.guest_prompt'));
      return;
    }

    const latNum = parseFloat(latitude);
    const lonNum = parseFloat(longitude);
    if (isNaN(latNum) || isNaN(lonNum)) {
      setFormError(t('validation.lat_lon_required'));
      return;
    }

    // Generate unique client UUID
    const clientUuid = `rep-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`;

    const reportPayload = {
      client_uuid: clientUuid,
      category,
      description: description.trim(),
      latitude: latNum,
      longitude: lonNum,
      client_created_at: new Date().toISOString(),
      photo_blob: photoBlob,
      photo_name: photoName,
    };

    try {
      // 1. Enqueue in persistent IndexedDB
      await enqueueReport(reportPayload);
      setSubmitSuccess(true);
      setFormStep(1);

      // Clear draft after enqueuing
      handleClearDraft();
      await refreshQueue();

      // 2. Immediate sync attempt if online
      triggerSync();

      setTimeout(() => setSubmitSuccess(false), 5000);
    } catch (err) {
      setFormError(`Failed to enqueue report: ${err.message}`);
    }
  };

  const triggerSync = async () => {
    if (isSyncing) return;
    try {
      setIsSyncing(true);
      await syncPendingQueue({
        token,
        onStatusChange: refreshQueue,
        onAuthRequired: () => {
          if (onNavigateToSignIn) onNavigateToSignIn();
        },
      });
      await refreshQueue();
      if (activeTab === 'mine') loadMyReports();
    } finally {
      setIsSyncing(false);
    }
  };

  const handleDiscard = async (clientUuid) => {
    await removeReportFromQueue(clientUuid);
    await refreshQueue();
  };

  return (
    <div className="incident-reporter-container" role="region" aria-label="Incident Reporter">
      {/* Tab Header Navigation */}
      <div className="reporter-tabs">
        <button
          type="button"
          className={`reporter-tab-btn ${activeTab === 'new' ? 'active' : ''}`}
          onClick={() => setActiveTab('new')}
        >
          <AlertTriangle size={16} />
          <span>{t('reporter.new_report')}</span>
        </button>

        <button
          type="button"
          className={`reporter-tab-btn ${activeTab === 'pending' ? 'active' : ''}`}
          onClick={() => setActiveTab('pending')}
        >
          <Clock size={16} />
          <span>{t('reporter.pending_queue')}</span>
          {pendingItems.length > 0 && (
            <span className="queue-pill-count">{pendingItems.length}</span>
          )}
        </button>

        <button
          type="button"
          className={`reporter-tab-btn ${activeTab === 'mine' ? 'active' : ''}`}
          onClick={() => setActiveTab('mine')}
        >
          <FileText size={16} />
          <span>{t('reporter.my_reports')}</span>
        </button>
      </div>

      {/* Guest Mode Alert Notice */}
      {isGuest && (
        <div className="state-box state-warning" style={{ margin: '16px 0' }}>
          <Shield size={20} />
          <div>
            <strong>{t('app.guest_mode')}:</strong> {t('app.guest_prompt')}
          </div>
        </div>
      )}

      {/* Draft Restored Banner */}
      {activeTab === 'new' && draftRestored && (
        <div className="draft-notice-banner">
          <div className="draft-notice-text">
            <Save size={14} style={{ color: 'var(--accent-secondary)' }} />
            <span>{t('reporter.draft_restored')}</span>
          </div>
          <button
            type="button"
            className="draft-clear-btn"
            onClick={handleClearDraft}
            title={t('reporter.clear_draft')}
          >
            <RotateCcw size={13} />
            <span>{t('reporter.clear_draft')}</span>
          </button>
        </div>
      )}

      {/* TAB 1: New Report Submission Form */}
      {activeTab === 'new' && (
        <div className="reporter-card">
          {submitSuccess && (
            <div className="state-box state-success" style={{ marginBottom: 16 }}>
              <CheckCircle size={20} />
              <div>
                <strong>{t('reporter.enqueued_success')}</strong>
              </div>
            </div>
          )}

          {formError && (
            <div className="state-box state-error" style={{ marginBottom: 16 }}>
              <AlertCircle size={20} />
              <span>{formError}</span>
            </div>
          )}

          <form onSubmit={handleSubmit}>
            {formStep === 1 ? (
              <>
                {/* 1. Category Selector */}
                <div className="form-group">
                  <label className="form-label">{t('reporter.category_select')}</label>
                  <div className="category-chips-grid">
                    {CATEGORIES.map((cat) => (
                      <button
                        key={cat.id}
                        type="button"
                        className={`cat-chip ${category === cat.id ? 'active' : ''}`}
                        onClick={() => setCategory(cat.id)}
                      >
                        <span className="cat-chip-icon">{cat.icon}</span>
                        <span className="cat-chip-label">{t(`categories.${cat.id}`)}</span>
                      </button>
                    ))}
                  </div>
                </div>

                {/* 2. GPS Location Capture & Shortcuts */}
                <div className="form-group">
                  <div className="label-with-action">
                    <label className="form-label">{t('reporter.coordinates_label')}</label>
                    <button
                      type="button"
                      className="inline-action-btn"
                      onClick={handleCaptureGps}
                      disabled={isCapturingGps}
                    >
                      <MapPin size={14} />
                      <span>{isCapturingGps ? t('reporter.acquiring_gps') : t('reporter.acquire_gps')}</span>
                    </button>
                  </div>

                  <div className="coords-inputs-row">
                    <div className="coord-input-wrapper">
                      <span className="coord-prefix">Lat:</span>
                      <input
                        type="number"
                        step="any"
                        className="form-input"
                        value={latitude}
                        onChange={(e) => {
                          setLatitude(e.target.value);
                          setLocationSource('Manual Coordinate Entry');
                        }}
                        required
                      />
                    </div>
                    <div className="coord-input-wrapper">
                      <span className="coord-prefix">Lon:</span>
                      <input
                        type="number"
                        step="any"
                        className="form-input"
                        value={longitude}
                        onChange={(e) => {
                          setLongitude(e.target.value);
                          setLocationSource('Manual Coordinate Entry');
                        }}
                        required
                      />
                    </div>
                  </div>
                  <span className="input-hint-text">
                    Source: {locationSource} {gpsAccuracy && `(${t('reporter.gps_accuracy', { meters: gpsAccuracy })})`}
                  </span>

                  {/* Quick Landmark Shortcuts */}
                  <div className="landmark-shortcuts-row">
                    <span className="shortcuts-title">{t('reporter.landmark_shortcuts')}:</span>
                    <div className="shortcuts-pills">
                      {CORRIDOR_SHORTCUTS.map((sc) => (
                        <button
                          key={sc.name}
                          type="button"
                          className="shortcut-pill-btn"
                          onClick={() => handleSelectShortcut(sc)}
                        >
                          {sc.name}
                        </button>
                      ))}
                    </div>
                  </div>
                </div>

                {/* 3. Description Notes */}
                <div className="form-group">
                  <label className="form-label">
                    {t('reporter.description_label')}
                    <span className="char-count">{description.length}/1000</span>
                  </label>
                  <textarea
                    className="form-textarea"
                    rows={3}
                    maxLength={1000}
                    placeholder={t('reporter.description_placeholder')}
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                  />
                </div>

                {/* 4. Photo Evidence Capture */}
                <div className="form-group">
                  <label className="form-label">{t('reporter.photo_label')}</label>
                  <div className="photo-upload-box">
                    <input
                      type="file"
                      id="photo-input"
                      accept="image/jpeg,image/png,image/webp"
                      className="hidden-file-input"
                      onChange={handlePhotoSelect}
                    />
                    <label htmlFor="photo-input" className="photo-upload-label">
                      <Camera size={22} />
                      <span>{photoName ? photoName : 'Tap to take photo or choose file'}</span>
                      <span className="exif-notice">
                        {t('reporter.photo_notice')}
                      </span>
                    </label>

                    {photoPreview && (
                      <div className="photo-preview-wrapper">
                        <img src={photoPreview} alt="Incident preview" className="photo-thumbnail" />
                        <button
                          type="button"
                          className="photo-remove-btn"
                          onClick={() => {
                            setPhotoBlob(null);
                            setPhotoPreview(null);
                            setPhotoName(null);
                          }}
                        >
                          <Trash2 size={14} /> Remove
                        </button>
                      </div>
                    )}
                  </div>
                </div>

                <div className="form-actions">
                  <button
                    type="button"
                    className="btn btn-primary"
                    onClick={() => {
                      const latNum = parseFloat(latitude);
                      const lonNum = parseFloat(longitude);
                      if (isNaN(latNum) || isNaN(lonNum)) {
                        setFormError(t('validation.lat_lon_required'));
                        return;
                      }
                      setFormError(null);
                      setFormStep(2);
                    }}
                  >
                    <span>{t('reporter.step_review')}</span>
                    <ChevronRight size={16} />
                  </button>
                </div>
              </>
            ) : (
              /* Step 2: Review & Confirm Submission */
              <div className="review-step-box">
                <h3 className="review-title">Confirm Report Details Before Enqueuing</h3>
                <div className="review-table">
                  <div className="review-row">
                    <span className="review-label">Hazard Category:</span>
                    <strong className="review-val">{t(`categories.${category}`)}</strong>
                  </div>
                  <div className="review-row">
                    <span className="review-label">Coordinates:</span>
                    <strong className="review-val">{latitude}°N, {longitude}°E</strong>
                  </div>
                  <div className="review-row">
                    <span className="review-label">Location Source:</span>
                    <span className="review-val">{locationSource}</span>
                  </div>
                  <div className="review-row">
                    <span className="review-label">Observations:</span>
                    <span className="review-val">{description || 'None provided'}</span>
                  </div>
                  <div className="review-row">
                    <span className="review-label">Evidence Photo:</span>
                    <span className="review-val">{photoName || 'None attached'}</span>
                  </div>
                </div>

                <div className="review-actions">
                  <button
                    type="button"
                    className="btn btn-secondary"
                    onClick={() => setFormStep(1)}
                  >
                    {t('reporter.back_to_edit')}
                  </button>
                  <button
                    type="submit"
                    className="btn btn-primary"
                    disabled={isGuest}
                  >
                    <Send size={16} />
                    <span>{t('reporter.confirm_submit')}</span>
                  </button>
                </div>
              </div>
            )}
          </form>
        </div>
      )}

      {/* TAB 2: Pending-Sync Queue */}
      {activeTab === 'pending' && (
        <div className="reporter-card">
          <div className="queue-header-row">
            <div>
              <h3>Persistent Offline Sync Queue</h3>
              <p className="empty-subtext">
                Reports are stored safely in browser IndexedDB and automatically retried upon connection restore.
              </p>
            </div>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={triggerSync}
              disabled={isSyncing || pendingItems.length === 0}
            >
              <RefreshCw size={14} className={isSyncing ? 'spin-icon' : ''} />
              <span>{isSyncing ? t('reporter.syncing') : t('reporter.sync_now')}</span>
            </button>
          </div>

          {pendingItems.length === 0 ? (
            <div className="state-box state-neutral" style={{ margin: '30px auto' }}>
              <CheckCircle size={28} style={{ color: 'var(--success)' }} />
              <div>
                <strong>Queue is Empty</strong>
                <p style={{ margin: 0, fontSize: 13, color: 'var(--text-muted)' }}>
                  All captured reports have been synced with the RouteWise patrol backend.
                </p>
              </div>
            </div>
          ) : (
            <div className="queue-items-list">
              {pendingItems.map((item) => (
                <div key={item.client_uuid} className="queue-item-card">
                  <div className="queue-item-left">
                    <div className="queue-item-title">
                      <span className="badge badge-category">
                        {t(`categories.${item.category}`)}
                      </span>
                      <span className={`badge badge-queue-${item.status}`}>
                        {item.status.toUpperCase()}
                      </span>
                      {item.photo_blob && (
                        <span className="badge badge-subtle">Photo Attached</span>
                      )}
                    </div>
                    <div className="queue-item-coords">
                      GPS: {item.latitude.toFixed(4)}°N, {item.longitude.toFixed(4)}°E • Capture Time: {new Date(item.created_at).toLocaleTimeString()}
                    </div>
                    {item.last_error && (
                      <div className="queue-error-msg">{item.last_error}</div>
                    )}
                  </div>

                  <div className="queue-item-actions">
                    <button
                      type="button"
                      className="btn-icon"
                      onClick={() => triggerSync()}
                      title={t('reporter.retry')}
                    >
                      <RefreshCw size={15} />
                    </button>
                    <button
                      type="button"
                      className="btn-icon danger"
                      onClick={() => handleDiscard(item.client_uuid)}
                      title={t('reporter.discard')}
                    >
                      <Trash2 size={15} />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* TAB 3: My Reports & Timeline */}
      {activeTab === 'mine' && (
        <div className="reporter-card">
          <div className="queue-header-row">
            <div>
              <h3>My Submitted Reports & Status Timeline</h3>
              <p className="empty-subtext">
                Live audit trail of reports submitted from your authenticated account.
              </p>
            </div>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={loadMyReports}
              disabled={loadingReports}
            >
              <RefreshCw size={14} className={loadingReports ? 'spin-icon' : ''} />
              <span>Refresh</span>
            </button>
          </div>

          {loadingReports ? (
            <div className="state-box state-loading" style={{ margin: '30px auto' }}>
              <span>Loading report history...</span>
            </div>
          ) : myReports.length === 0 ? (
            <div className="state-box state-neutral" style={{ margin: '30px auto' }}>
              <FileText size={24} />
              <span>No reports submitted from this account yet.</span>
            </div>
          ) : (
            <div className="my-reports-list">
              {myReports.map((rep) => (
                <div key={rep.id} className="my-report-card">
                  <div className="my-report-top">
                    <div className="my-report-info">
                      <span className="badge badge-category">
                        {t(`categories.${rep.category}`)}
                      </span>
                      <span className={`badge badge-status-${rep.status}`}>
                        {t(`status.${rep.status}`)}
                      </span>
                      {rep.is_simulated && (
                        <span className="badge badge-simulated">{t('app.simulated_badge')}</span>
                      )}
                      <span className="report-id-subtle">ID: {rep.id.substring(0, 8)}...</span>
                    </div>
                    <span className="report-date-text">
                      {new Date(rep.created_at).toLocaleString()}
                    </span>
                  </div>

                  {rep.description && (
                    <p className="my-report-desc">{rep.description}</p>
                  )}

                  {rep.nearest_segment_id && (
                    <div className="my-report-segment">
                      Snapped Corridor Segment: <strong>{rep.nearest_segment_id}</strong>
                      {rep.nearest_segment_distance_m && ` (${rep.nearest_segment_distance_m}m from highway)`}
                    </div>
                  )}

                  {/* Audit Timeline */}
                  <div className="my-report-timeline">
                    <h4>Audit Progress Timeline</h4>
                    <div className="timeline-steps">
                      {rep.history?.map((h, i) => (
                        <div key={h.id || i} className="timeline-step">
                          <div className="timeline-dot" />
                          <div className="timeline-content">
                            <div className="timeline-action">
                              <strong>{h.to_status.toUpperCase()}</strong> by {h.actor_name} ({h.actor_role})
                            </div>
                            {h.note && <div className="timeline-note">{h.note}</div>}
                            <div className="timeline-time">
                              {new Date(h.timestamp).toLocaleTimeString()} • {new Date(h.timestamp).toLocaleDateString()}
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
