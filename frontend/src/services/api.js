/**
 * RouteWise API Client
 * Connects to FastAPI backend endpoints via configured base URL or Vite proxy.
 */

const API_BASE = import.meta.env.VITE_API_BASE_URL || '';

function getAuthHeaders() {
  const token = localStorage.getItem('routewise_token');
  const headers = { 'Content-Type': 'application/json' };
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  return headers;
}

// 1. Health and Status
export async function fetchHealth() {
  const res = await fetch(`${API_BASE}/api/health`);
  if (!res.ok) {
    throw new Error(`Health check failed with status ${res.status}`);
  }
  return res.json();
}

// 2. Risk Forecasts and Historical Dates
export async function fetchAvailableDates() {
  const res = await fetch(`${API_BASE}/api/v1/risk/dates`);
  if (!res.ok) {
    throw new Error(`Failed to load observation dates: HTTP ${res.status}`);
  }
  return res.json();
}

export async function fetchCorridorSegments() {
  const res = await fetch(`${API_BASE}/api/v1/corridor/segments`);
  if (!res.ok) {
    throw new Error(`Failed to load corridor highway geometry: HTTP ${res.status}`);
  }
  return res.json();
}

export async function fetchCorridorRisk(dateStr) {
  const res = await fetch(`${API_BASE}/api/v1/risk?date=${encodeURIComponent(dateStr)}`);
  if (!res.ok) {
    const errData = await res.json().catch(() => ({}));
    throw new Error(errData.detail || `Failed to fetch risk for ${dateStr} (HTTP ${res.status})`);
  }
  return res.json();
}

// 3. Authentication
export async function loginUser(email, password) {
  const res = await fetch(`${API_BASE}/api/v1/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) {
    const errData = await res.json().catch(() => ({}));
    throw new Error(errData.detail || `Login failed (HTTP ${res.status})`);
  }
  return res.json();
}

export async function loginGuest() {
  const res = await fetch(`${API_BASE}/api/v1/auth/guest`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  });
  if (!res.ok) {
    const errData = await res.json().catch(() => ({}));
    throw new Error(errData.detail || 'Guest login failed');
  }
  return res.json();
}

export async function registerUser(payload) {
  const res = await fetch(`${API_BASE}/api/v1/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const errData = await res.json().catch(() => ({}));
    throw new Error(errData.detail || `Registration failed (HTTP ${res.status})`);
  }
  return res.json();
}

export async function fetchCurrentUser() {
  const res = await fetch(`${API_BASE}/api/v1/auth/me`, {
    headers: getAuthHeaders(),
  });
  if (!res.ok) {
    throw new Error(`Unauthorized (HTTP ${res.status})`);
  }
  return res.json();
}

export async function fetchDemoAccounts() {
  const res = await fetch(`${API_BASE}/api/v1/auth/demo-accounts`);
  if (!res.ok) {
    return [];
  }
  return res.json();
}

export async function updateUserProfile(payload) {
  const res = await fetch(`${API_BASE}/api/v1/auth/profile`, {
    method: 'PUT',
    headers: getAuthHeaders(),
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const errData = await res.json().catch(() => ({}));
    throw new Error(errData.detail || 'Failed to update profile');
  }
  return res.json();
}

// 4. Journey Planning
export async function fetchCorridorPlaces() {
  const res = await fetch(`${API_BASE}/api/v1/journey/places`);
  if (!res.ok) {
    throw new Error(`Failed to load corridor landmarks: HTTP ${res.status}`);
  }
  return res.json();
}

export async function planJourney(payload) {
  const res = await fetch(`${API_BASE}/api/v1/journey/plan`, {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const errData = await res.json().catch(() => ({}));
    throw new Error(errData.detail || `Journey analysis failed (HTTP ${res.status})`);
  }
  return res.json();
}

// 5. Historical Disruptions
export async function fetchDisruptions({ year, disruptionType, closure, query, page = 1, pageSize = 20 } = {}) {
  const params = new URLSearchParams();
  if (year) params.append('year', year);
  if (disruptionType && disruptionType !== 'all') params.append('disruption_type', disruptionType);
  if (closure && closure !== 'all') params.append('closure', closure);
  if (query) params.append('query', query);
  params.append('page', page);
  params.append('page_size', pageSize);

  const res = await fetch(`${API_BASE}/api/v1/disruptions?${params.toString()}`);
  if (!res.ok) {
    throw new Error(`Failed to load historical disruptions (HTTP ${res.status})`);
  }
  return res.json();
}

export async function fetchDisruptionStats() {
  const res = await fetch(`${API_BASE}/api/v1/disruptions/stats`);
  if (!res.ok) {
    throw new Error(`Failed to load disruption statistics (HTTP ${res.status})`);
  }
  return res.json();
}

// 6. Conversational AI Assistant
export async function sendChatQuery(message, history = [], context = {}) {
  const res = await fetch(`${API_BASE}/api/v1/chat/query`, {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify({ message, history, context }),
  });
  if (!res.ok) {
    const errData = await res.json().catch(() => ({}));
    throw new Error(errData.detail || `AI query failed (HTTP ${res.status})`);
  }
  return res.json();
}

// 7. Field Reports & Patrol Operations
export async function submitReport(formData) {
  const token = localStorage.getItem('routewise_token');
  const headers = {};
  if (token) headers['Authorization'] = `Bearer ${token}`;

  const res = await fetch(`${API_BASE}/api/v1/reports`, {
    method: 'POST',
    headers,
    body: formData,
  });
  if (!res.ok) {
    const errData = await res.json().catch(() => ({}));
    throw new Error(errData.detail || `Report submission failed (HTTP ${res.status})`);
  }
  return res.json();
}

export async function fetchMyReports() {
  const res = await fetch(`${API_BASE}/api/v1/reports/mine`, {
    headers: getAuthHeaders(),
  });
  if (!res.ok) {
    const errData = await res.json().catch(() => ({}));
    throw new Error(errData.detail || 'Failed to fetch your reports');
  }
  return res.json();
}

export async function fetchPublicReports() {
  const res = await fetch(`${API_BASE}/api/v1/reports/public`);
  if (!res.ok) {
    return [];
  }
  return res.json();
}

export async function fetchPatrolReports({ status, category, segment_id, limit = 50, offset = 0 } = {}) {
  const params = new URLSearchParams();
  if (status && status !== 'all') params.append('status', status);
  if (category && category !== 'all') params.append('category', category);
  if (segment_id) params.append('segment_id', segment_id);
  params.append('limit', limit);
  params.append('offset', offset);

  const res = await fetch(`${API_BASE}/api/v1/reports?${params.toString()}`, {
    headers: getAuthHeaders(),
  });
  if (!res.ok) {
    const errData = await res.json().catch(() => ({}));
    throw new Error(errData.detail || `Failed to fetch patrol reports (HTTP ${res.status})`);
  }
  return res.json();
}

export async function fetchReportSummary() {
  const res = await fetch(`${API_BASE}/api/v1/reports/summary`, {
    headers: getAuthHeaders(),
  });
  if (!res.ok) {
    return { total: 0, submitted: 0, verified: 0, assigned: 0, resolved: 0, rejected: 0 };
  }
  return res.json();
}

export async function updateReportStatus(reportId, newStatus, note = '') {
  const res = await fetch(`${API_BASE}/api/v1/reports/${encodeURIComponent(reportId)}/status`, {
    method: 'PATCH',
    headers: getAuthHeaders(),
    body: JSON.stringify({ status: newStatus, note }),
  });
  if (!res.ok) {
    const errData = await res.json().catch(() => ({}));
    throw new Error(errData.detail || `Status update failed (HTTP ${res.status})`);
  }
  return res.json();
}

export async function assignReportToPatrol(reportId, assignedToUserId, note = '') {
  const res = await fetch(`${API_BASE}/api/v1/reports/${encodeURIComponent(reportId)}/assign`, {
    method: 'PATCH',
    headers: getAuthHeaders(),
    body: JSON.stringify({ assigned_to: assignedToUserId, note }),
  });
  if (!res.ok) {
    const errData = await res.json().catch(() => ({}));
    throw new Error(errData.detail || `Assignment failed (HTTP ${res.status})`);
  }
  return res.json();
}

// 8. Segment Features Drawer, Along-Route Services, and Official Advisories
export async function fetchSegmentFeatures(segmentId, dateStr) {
  const res = await fetch(
    `${API_BASE}/api/v1/corridor/segments/${encodeURIComponent(segmentId)}/features?date=${encodeURIComponent(dateStr)}`,
    {
      headers: getAuthHeaders(),
    }
  );
  if (!res.ok) {
    const errData = await res.json().catch(() => ({}));
    throw new Error(errData.detail || 'Failed to fetch segment input features');
  }
  return res.json();
}

export async function fetchAlongRouteServices() {
  const res = await fetch(`${API_BASE}/api/v1/corridor/services`);
  if (!res.ok) {
    return [];
  }
  return res.json();
}

export async function fetchOfficialAdvisories() {
  const res = await fetch(`${API_BASE}/api/v1/corridor/advisories`);
  if (!res.ok) {
    throw new Error(`Failed to load advisories config: HTTP ${res.status}`);
  }
  return res.json();
}

export async function fetchCorridorWeather(dateStr) {
  const res = await fetch(`${API_BASE}/api/v1/corridor/weather?date=${encodeURIComponent(dateStr)}`);
  if (!res.ok) {
    return null;
  }
  return res.json();
}

