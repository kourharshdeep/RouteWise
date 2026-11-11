/**
 * incidentHelper.js
 *
 * RouteWise 2.0 - Incident De-duplication and Routing Wording Decision Helpers (Task 4)
 * Pure, isolated helper module for:
 * 1. Incident de-duplication matching rules.
 * 2. Report count and timestamp formatting.
 * 3. Accurate route reason explanation formatting (never mentioning 0 as a cause).
 * 4. Live date substitution UI notice helpers.
 */

export const DEDUP_WINDOW_HOURS = 24.0;

/**
 * Normalizes category or hazard type to backend-standardized hazard_type.
 * Aligns with backend VALID_PRESETS fallback:
 * 'other', 'snow_or_ice', and 'single_lane_or_obstruction' fall back to 'road_damage'.
 */
export function normalizeHazardType(rawType) {
  const norm = String(rawType || '').toLowerCase().replace(/[- ]/g, '_');
  if (!norm) return '';
  if (norm === 'other' || norm === 'snow_or_ice' || norm === 'single_lane_or_obstruction') {
    return 'road_damage';
  }
  return norm;
}

/**
 * Evaluates whether a new field report or hazard candidate is a duplicate of an existing active event.
 *
 * Conservative matching criteria:
 * - Exactly identical corridor segment_id
 * - Standardized hazard_type matches (with fallback normalization)
 * - Simulation mode matches strictly (real never merges with simulated)
 * - Status is active and validity has not expired
 * - Deduplication time window: checks both created_at and last_reported_at (within 24h)
 *
 * When any criterion fails or timestamps are invalid, returns false (do not merge).
 */
export function isDuplicateHazardCandidate(
  existingEvent,
  candidate,
  now = new Date(),
  windowHours = DEDUP_WINDOW_HOURS
) {
  if (!existingEvent || !candidate) return false;
  if (existingEvent.status !== 'active') return false;

  // Strict segment identity match
  if (!existingEvent.segment_id || !candidate.segment_id) return false;
  if (existingEvent.segment_id !== candidate.segment_id) return false;

  // Strict hazard type match with normalization
  const exType = normalizeHazardType(existingEvent.hazard_type || existingEvent.category || '');
  const candType = normalizeHazardType(candidate.hazard_type || candidate.category || '');
  if (!exType || !candType || exType !== candType) return false;

  // Strict simulation isolation (real never merges with simulated)
  const exSim = Boolean(existingEvent.is_simulated);
  const candSim = Boolean(candidate.is_simulated);
  if (exSim !== candSim) return false;

  // Timestamp validation base
  const nowMs = now instanceof Date ? now.getTime() : new Date(now).getTime();
  if (isNaN(nowMs)) return false;

  // Expiration check (conservative: invalid expires_at fails)
  if (existingEvent.expires_at) {
    const expTime = new Date(existingEvent.expires_at).getTime();
    if (isNaN(expTime) || nowMs >= expTime) return false;
  }

  // Disallow future timestamps (conservative clock/telemetry validation)
  if (existingEvent.created_at) {
    const createdMs = new Date(existingEvent.created_at).getTime();
    if (!isNaN(createdMs) && createdMs > nowMs) return false;
  }
  if (existingEvent.last_reported_at) {
    const lrMs = new Date(existingEvent.last_reported_at).getTime();
    if (!isNaN(lrMs) && lrMs > nowMs) return false;
  }
  if (candidate.created_at) {
    const candCreatedMs = new Date(candidate.created_at).getTime();
    if (!isNaN(candCreatedMs) && candCreatedMs > nowMs) return false;
  }
  if (candidate.client_created_at) {
    const candClientMs = new Date(candidate.client_created_at).getTime();
    if (!isNaN(candClientMs) && candClientMs > nowMs) return false;
  }

  // Deduplication window check (matching backend created_at >= dedup_limit OR last_reported_at >= dedup_limit)
  const windowMs = (Number(windowHours) || DEDUP_WINDOW_HOURS) * 3600 * 1000;

  let createdWithinWindow = false;
  if (existingEvent.created_at) {
    const createdMs = new Date(existingEvent.created_at).getTime();
    if (!isNaN(createdMs) && createdMs <= nowMs && (nowMs - createdMs <= windowMs)) {
      createdWithinWindow = true;
    }
  }

  let lastReportedWithinWindow = false;
  if (existingEvent.last_reported_at) {
    const lrMs = new Date(existingEvent.last_reported_at).getTime();
    if (!isNaN(lrMs) && lrMs <= nowMs && (nowMs - lrMs <= windowMs)) {
      lastReportedWithinWindow = true;
    }
  }

  // Conservative handling: if neither timestamp is present/valid within window, reject duplicate candidate
  if (!createdWithinWindow && !lastReportedWithinWindow) {
    return false;
  }

  return true;
}

/**
 * Computes updated report count and reporter independence.
 * Same reporter repeat does not inflate count.
 */
export function calculateReportCount(currentCount, existingReporterIds, incomingReporterId) {
  const base = Math.max(1, Number(currentCount) || 1);
  if (!incomingReporterId) {
    return { reportCount: base, isIndependent: false };
  }
  const idSet = new Set(existingReporterIds || []);
  if (idSet.has(incomingReporterId)) {
    return { reportCount: base, isIndependent: false };
  }
  return { reportCount: base + 1, isIndependent: true };
}

/**
 * Returns a human-readable display string for report count.
 */
export function formatReportCount(count) {
  const n = Math.max(1, Number(count) || 1);
  return n === 1 ? '1 report' : `${n} reports`;
}

/**
 * Builds accurate routing reason strings without mentioning 0 as a cause.
 * Distinguishes: closed segments, stale telemetry, unmonitored segments, high risk, and clear.
 */
export function buildRoutingReason({
  blockingSegments = [],
  unknownCount = 0,
  isLiveStale = false,
  highCount = 0,
  medCount = 0,
  maxScore = null,
}) {
  if (blockingSegments && blockingSegments.length > 0) {
    const countStr = `${blockingSegments.length} closed segment${blockingSegments.length > 1 ? 's' : ''} (${blockingSegments.slice(0, 3).join(', ')})`;
    return {
      recommendation: 'HOLD',
      reason: `Corridor is blocked by ${countStr} due to active hazard. NH-44 is a single physical mountain road with no bypass; hold at nearest staging yard.`,
    };
  }

  if (unknownCount > 0 || isLiveStale) {
    const lead = unknownCount > 0
      ? `Route includes ${unknownCount} unmonitored segment${unknownCount > 1 ? 's' : ''} with missing data.`
      : 'Live telemetry for corridor segments is stale (>24h).';
    return {
      recommendation: 'NO_DATA',
      reason: `${lead} Conditions cannot be certified safe; proceed only under official traffic authority instructions.`,
    };
  }

  if (highCount > 0 || (maxScore !== null && maxScore >= 0.35)) {
    const lead = highCount > 0
      ? `High disruption hazard tier (>=0.35) detected on ${highCount} segment${highCount > 1 ? 's' : ''};`
      : `Peak segment hazard score (${maxScore.toFixed(2)}) reaches high disruption threshold (>=0.35);`;
    return {
      recommendation: 'DELAY',
      reason: `${lead} delay transit or hold departure until mountain weather conditions improve.`,
    };
  }

  if (medCount > 0 || (maxScore !== null && maxScore >= 0.10)) {
    const lead = medCount > 0
      ? `Elevated disruption risk tier (0.10-0.35) on ${medCount} segment${medCount > 1 ? 's' : ''};`
      : `Elevated peak segment hazard score (${maxScore.toFixed(2)} >= 0.10);`;
    return {
      recommendation: 'PROCEED_WITH_CAUTION',
      reason: `${lead} proceed with heightened caution, avoid night travel, and observe local marshaling.`,
    };
  }

  return {
    recommendation: 'PROCEED',
    reason: 'Corridor baseline clear (<0.10); proceed under standard mountain driving precautions.',
  };
}

/**
 * Returns date substitution helper metadata if requested date was substituted.
 */
export function getSubstitutionNotice(planResult) {
  if (!planResult || !planResult.date_substituted) {
    return null;
  }
  return {
    requestedDate: planResult.requested_date,
    actualDate: planResult.actual_date,
    isSubstituted: true,
  };
}
