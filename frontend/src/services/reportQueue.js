/**
 * Persistent Offline Report Sync Queue backed by browser IndexedDB.
 *
 * Stores pending incident reports (with payload and photo Blob) locally.
 * Automatically retries submissions with exponential backoff on 'online' event and page load.
 * Handles 401 (pauses queue and signals re-authentication), 4xx (marks failed without looping),
 * and network/5xx errors (schedules backoff retry).
 */

const DB_NAME = 'routewise_offline_db';
const DB_VERSION = 1;
const STORE_NAME = 'pending_reports';

function openDB() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);
    request.onupgradeneeded = (event) => {
      const db = event.target.result;
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        const store = db.createObjectStore(STORE_NAME, { keyPath: 'client_uuid' });
        store.createIndex('status', 'status', { unique: false });
        store.createIndex('created_at', 'created_at', { unique: false });
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

export async function enqueueReport(reportItem) {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, 'readwrite');
    const store = tx.objectStore(STORE_NAME);

    const record = {
      client_uuid: reportItem.client_uuid,
      category: reportItem.category,
      description: reportItem.description || '',
      latitude: Number(reportItem.latitude),
      longitude: Number(reportItem.longitude),
      client_created_at: reportItem.client_created_at || new Date().toISOString(),
      photo_blob: reportItem.photo_blob || null,
      photo_name: reportItem.photo_name || null,
      status: 'pending', // 'pending', 'syncing', 'sent', 'failed'
      attempt_count: 0,
      last_error: null,
      created_at: Date.now(),
      next_retry_at: Date.now(),
    };

    const req = store.put(record);
    req.onsuccess = () => resolve(record);
    req.onerror = () => reject(req.error);
  });
}

export async function getPendingReports() {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, 'readonly');
    const store = tx.objectStore(STORE_NAME);
    const req = store.getAll();
    req.onsuccess = () => resolve(req.result || []);
    req.onerror = () => reject(req.error);
  });
}

export async function updateReportInQueue(client_uuid, updates) {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, 'readwrite');
    const store = tx.objectStore(STORE_NAME);
    const getReq = store.get(client_uuid);
    getReq.onsuccess = () => {
      const existing = getReq.result;
      if (!existing) {
        resolve(null);
        return;
      }
      const updated = { ...existing, ...updates };
      const putReq = store.put(updated);
      putReq.onsuccess = () => resolve(updated);
      putReq.onerror = () => reject(putReq.error);
    };
    getReq.onerror = () => reject(getReq.error);
  });
}

export async function removeReportFromQueue(client_uuid) {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, 'readwrite');
    const store = tx.objectStore(STORE_NAME);
    const req = store.delete(client_uuid);
    req.onsuccess = () => resolve(true);
    req.onerror = () => reject(req.error);
  });
}

/**
 * Attempts to sync all pending reports to backend.
 * Calls onAuthRequired callback if backend returns 401.
 */
export async function syncPendingQueue({ token, onStatusChange, onAuthRequired }) {
  if (!navigator.onLine) {
    return { synced: 0, failed: 0, offline: true };
  }

  const items = await getPendingReports();
  const eligible = items.filter(
    (item) => (item.status === 'pending' || item.status === 'failed') && Date.now() >= (item.next_retry_at || 0)
  );

  let syncedCount = 0;
  let failedCount = 0;

  for (const item of eligible) {
    try {
      await updateReportInQueue(item.client_uuid, { status: 'syncing' });
      if (onStatusChange) onStatusChange();

      const formData = new FormData();
      formData.append('client_uuid', item.client_uuid);
      formData.append('category', item.category);
      formData.append('latitude', String(item.latitude));
      formData.append('longitude', String(item.longitude));
      if (item.description) formData.append('description', item.description);
      if (item.client_created_at) formData.append('client_created_at', item.client_created_at);
      if (item.photo_blob) {
        const ext = item.photo_blob.type === 'image/png' ? 'png' : (item.photo_blob.type === 'image/webp' ? 'webp' : 'jpg');
        formData.append('photo', item.photo_blob, item.photo_name || `photo.${ext}`);
      }

      const headers = {};
      if (token) {
        headers['Authorization'] = `Bearer ${token}`;
      }

      const response = await fetch('/api/v1/reports', {
        method: 'POST',
        headers,
        body: formData,
      });

      if (response.status === 200 || response.status === 201) {
        // Success: remove from pending queue
        await removeReportFromQueue(item.client_uuid);
        syncedCount++;
      } else if (response.status === 401) {
        // Auth expired: pause queue and notify caller
        await updateReportInQueue(item.client_uuid, {
          status: 'failed',
          last_error: 'Authentication expired. Please sign in to resume sync.',
        });
        if (onAuthRequired) onAuthRequired();
        break; // Stop sync loop until authenticated
      } else if (response.status >= 400 && response.status < 500) {
        // Client validation error: mark failed and do NOT retry endlessly
        let detail = `Validation error (${response.status})`;
        try {
          const errData = await response.json();
          detail = errData.detail || detail;
        } catch (_) {}
        await updateReportInQueue(item.client_uuid, {
          status: 'failed',
          last_error: detail,
        });
        failedCount++;
      } else {
        // 5xx or server glitch: exponential backoff retry
        const attempts = (item.attempt_count || 0) + 1;
        const backoffSeconds = Math.min(300, Math.pow(2, attempts) * 5); // 10s, 20s, 40s... max 5m
        await updateReportInQueue(item.client_uuid, {
          status: 'pending',
          attempt_count: attempts,
          next_retry_at: Date.now() + backoffSeconds * 1000,
          last_error: `Server error (${response.status}). Retrying in ${backoffSeconds}s...`,
        });
        failedCount++;
      }
    } catch (netErr) {
      // Network drop: schedule retry
      const attempts = (item.attempt_count || 0) + 1;
      const backoffSeconds = Math.min(300, Math.pow(2, attempts) * 5);
      await updateReportInQueue(item.client_uuid, {
        status: 'pending',
        attempt_count: attempts,
        next_retry_at: Date.now() + backoffSeconds * 1000,
        last_error: `Network unavailable: ${netErr.message || 'Offline'}. Will retry automatically.`,
      });
      failedCount++;
    }
  }

  if (onStatusChange) onStatusChange();
  return { synced: syncedCount, failed: failedCount };
}
