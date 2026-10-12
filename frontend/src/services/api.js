/**
 * RouteWise API Client
 * Connects to FastAPI endpoints via /api proxy.
 */

export async function fetchHealth() {
  const res = await fetch('/api/health');
  if (!res.ok) {
    throw new Error(`Health check failed with status ${res.status}`);
  }
  return res.json();
}

export async function fetchAvailableDates() {
  const res = await fetch('/api/v1/risk/dates');
  if (!res.ok) {
    throw new Error(`Failed to load observation dates: HTTP ${res.status}`);
  }
  return res.json();
}

export async function fetchCorridorSegments() {
  const res = await fetch('/api/v1/corridor/segments');
  if (!res.ok) {
    throw new Error(`Failed to load corridor highway geometry: HTTP ${res.status}`);
  }
  return res.json();
}

export async function fetchCorridorRisk(dateStr) {
  const res = await fetch(`/api/v1/risk?date=${encodeURIComponent(dateStr)}`);
  if (!res.ok) {
    const errData = await res.json().catch(() => ({}));
    throw new Error(errData.detail || `Failed to fetch risk for ${dateStr} (HTTP ${res.status})`);
  }
  return res.json();
}
