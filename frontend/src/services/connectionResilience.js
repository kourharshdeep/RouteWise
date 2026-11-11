/**
 * RouteWise Connection Resilience & Reconciliation Service.
 *
 * Provides:
 * 1. Exponential backoff with jitter calculation for SSE and polling fallbacks.
 * 2. Deterministic ConnectionStateMachine: connected | reconnecting | polling | offline.
 * 3. State reconciliation helpers for alerts and hazard events (zero duplicates).
 * 4. Journey Planner auto-refresh qualification predicates.
 */

export const RESILIENCE_CONFIG = {
  BASE_RECONNECT_MS: 1000,      // 1 second base
  BACKOFF_FACTOR: 2,           // 2x exponential multiplier
  MAX_RECONNECT_MS: 30000,     // 30 seconds cap
  HEALTHY_THRESHOLD_MS: 5000,  // 5 seconds uninterrupted connection resets backoff
  SSE_FAILURES_BEFORE_POLL: 3, // N=3 consecutive SSE failures triggers polling fallback
  BASE_POLL_MS: 15000,         // 15 seconds base poll interval
  MAX_POLL_MS: 60000,          // 60 seconds maximum poll interval
  DEBOUNCE_REFRESH_MS: 500,    // 500ms planner refresh debounce
};

/**
 * Calculates exponential backoff with full jitter.
 * delay = random() * min(maxMs, baseMs * (factor ^ attempt))
 */
export function calculateBackoffDelay({
  attempt = 0,
  baseMs = RESILIENCE_CONFIG.BASE_RECONNECT_MS,
  factor = RESILIENCE_CONFIG.BACKOFF_FACTOR,
  maxMs = RESILIENCE_CONFIG.MAX_RECONNECT_MS,
  randomFn = Math.random,
} = {}) {
  const safeAttempt = Math.max(0, attempt);
  const ceiling = Math.min(maxMs, baseMs * Math.pow(factor, safeAttempt));
  // Upper-half jitter: delay is never below 50% of the computed capped delay
  const minDelay = 0.5 * ceiling;
  const jittered = Math.round(minDelay + (0.5 * ceiling * randomFn()));
  return Math.max(0, jittered);
}

/**
 * Connection State Machine for the Live Dashboard.
 * Permitted States: 'connected' | 'reconnecting' | 'polling' | 'offline'
 */
export class ConnectionStateMachine {
  constructor({
    config = RESILIENCE_CONFIG,
    randomFn = Math.random,
    onStateChange = null,
  } = {}) {
    this.config = config;
    this.randomFn = randomFn;
    this.onStateChange = onStateChange;

    this.state = 'connected';
    this.sseFailures = 0;
    this.pollFailures = 0;
    this.healthyTimer = null;
    this.lastSuccessfulUpdate = null;
  }

  _setState(newState) {
    if (this.state !== newState) {
      const oldState = this.state;
      this.state = newState;
      if (this.onStateChange) {
        this.onStateChange(newState, oldState);
      }
    }
  }

  getState() {
    return this.state;
  }

  getLastSuccessfulUpdate() {
    return this.lastSuccessfulUpdate;
  }

  isStaleRiskIndicated() {
    return this.state !== 'connected';
  }

  getConsecutiveFailures() {
    return this.sseFailures;
  }

  resetConsecutiveFailures() {
    this.sseFailures = 0;
  }

  handleSseOpen() {
    this.handleSuccess();
  }

  /**
   * Called when an SSE frame or REST polling response successfully arrives.
   */
  handleSuccess(timestamp = new Date().toISOString()) {
    this.lastSuccessfulUpdate = timestamp;
    this.pollFailures = 0;

    if (this.state === 'polling' || this.state === 'reconnecting' || this.state === 'offline') {
      // Reconnected
      this._setState('connected');
    }

    // Schedule reset of exponential backoff after connection stays healthy
    if (!this.healthyTimer) {
      this.healthyTimer = setTimeout(() => {
        this.sseFailures = 0;
        this.healthyTimer = null;
      }, this.config.HEALTHY_THRESHOLD_MS);
    }
  }

  /**
   * Called when SSE encounters an error, close, or transport disconnect.
   */
  handleSseError({ isOnline = true } = {}) {
    if (this.healthyTimer) {
      clearTimeout(this.healthyTimer);
      this.healthyTimer = null;
    }

    if (!isOnline) {
      this._setState('offline');
      return {
        nextState: 'offline',
        delayMs: 0,
        shouldPoll: false,
      };
    }

    this.sseFailures += 1;

    if (this.sseFailures >= this.config.SSE_FAILURES_BEFORE_POLL) {
      this._setState('polling');
      const delayMs = calculateBackoffDelay({
        attempt: this.pollFailures,
        baseMs: this.config.BASE_POLL_MS,
        factor: 1.5,
        maxMs: this.config.MAX_POLL_MS,
        randomFn: this.randomFn,
      });
      return {
        nextState: 'polling',
        delayMs,
        shouldPoll: true,
      };
    }

    this._setState('reconnecting');
    const delayMs = calculateBackoffDelay({
      attempt: this.sseFailures - 1,
      baseMs: this.config.BASE_RECONNECT_MS,
      factor: this.config.BACKOFF_FACTOR,
      maxMs: this.config.MAX_RECONNECT_MS,
      randomFn: this.randomFn,
    });

    return {
      nextState: 'reconnecting',
      delayMs,
      shouldPoll: false,
    };
  }

  /**
   * Called when a REST poll attempt fails while in polling mode.
   */
  handlePollError({ isOnline = true } = {}) {
    if (!isOnline) {
      this._setState('offline');
      return { nextState: 'offline', delayMs: 0 };
    }

    this.pollFailures += 1;
    this._setState('polling');

    const delayMs = calculateBackoffDelay({
      attempt: this.pollFailures,
      baseMs: this.config.BASE_POLL_MS,
      factor: 1.5,
      maxMs: this.config.MAX_POLL_MS,
      randomFn: this.randomFn,
    });

    return { nextState: 'polling', delayMs };
  }

  /**
   * Called when browser goes online or tab becomes visible again.
   */
  handleOnlineResume() {
    if (this.state === 'offline') {
      this._setState('reconnecting');
    }
  }

  destroy() {
    if (this.healthyTimer) {
      clearTimeout(this.healthyTimer);
      this.healthyTimer = null;
    }
  }
}

/**
 * Reconciles incoming alerts with current alerts without duplicating IDs.
 * Preserves local acknowledged / cleared flags for existing active alerts.
 */
export function reconcileAlerts(currentAlerts = [], incomingAlerts = []) {
  if (!Array.isArray(incomingAlerts)) return currentAlerts || [];
  if (!Array.isArray(currentAlerts)) currentAlerts = [];

  const currentMap = new Map();
  for (const a of currentAlerts) {
    if (a && a.id) {
      currentMap.set(String(a.id), a);
    }
  }

  const seenIds = new Set();
  const reconciled = [];

  for (const inc of incomingAlerts) {
    if (!inc || !inc.id) continue;
    const idStr = String(inc.id);
    if (seenIds.has(idStr)) continue;
    seenIds.add(idStr);

    const existing = currentMap.get(idStr);
    // Server status ALWAYS wins: do not preserve local acknowledged/cleared over server value
    const visualLocalState = existing ? {
      _clientUiExpanded: existing._clientUiExpanded,
      _clientUiSelected: existing._clientUiSelected,
    } : {};

    reconciled.push({
      ...inc,
      ...visualLocalState,
      status: inc.status,
      acknowledged: Boolean(inc.acknowledged || inc.status === 'acknowledged'),
      is_stale_context: Boolean(inc.is_stale_context),
    });
  }

  return reconciled;
}

/**
 * Reconciles incoming hazard events with current hazard events.
 * Guarantees zero duplicate event IDs and deterministic ordering.
 */
export function reconcileHazardEvents(currentEvents = [], incomingEvents = []) {
  if (!Array.isArray(incomingEvents)) return currentEvents || [];
  const seenIds = new Set();
  const reconciled = [];

  for (const ev of incomingEvents) {
    if (!ev || !ev.id) continue;
    const idStr = String(ev.id);
    if (seenIds.has(idStr)) continue;
    seenIds.add(idStr);
    reconciled.push({ ...ev });
  }

  return reconciled;
}

/**
 * Predicate to decide whether the Journey Planner should auto-refresh.
 * Rules:
 * - Refresh only when mode is 'live'
 * - Never refresh in 'historical' mode
 * - Never refresh if already planning (prevents request storms)
 * - Must have an existing visible plan result to re-evaluate
 */
export function shouldRefreshPlanner({
  mode = 'live',
  hasActivePlan = false,
  isPlanning = false,
  isTabVisible = true,
  changeDetected = true,
} = {}) {
  if (mode !== 'live') return false;
  if (!hasActivePlan) return false;
  if (isPlanning) return false;
  if (!isTabVisible) return false;
  return Boolean(changeDetected);
}

/**
 * Checks if journey planner recommendation changed between evaluations.
 */
export function hasRecommendationChanged(oldRec, newRec) {
  if (!oldRec || !newRec) return false;
  return String(oldRec).trim().toUpperCase() !== String(newRec).trim().toUpperCase();
}
