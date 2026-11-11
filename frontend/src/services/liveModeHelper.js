/**
 * RouteWise Operational Mode & Live Telemetry Decision Helper.
 *
 * Implements strict separation between:
 * 1. Historical Analysis: Static ERA5-Land reanalysis dataset (e.g. 2023-07-09). Date picker active.
 * 2. Current / Live Risk: Dynamic atmospheric observations from Open-Meteo. Current date advisory (T+1)
 *    derived from the last complete observation day (T = yesterday UTC). Date picker disabled.
 * 3. Replay Scenario: Demonstration simulation (July 2024). Date picker disabled. Labeled REPLAY.
 * 4. Off Mode: ROUTEWISE_LIVE_MODE is 'off'. Live features disabled with clear advisory notice.
 */

export function resolveEffectiveMode(userMode, backendMode) {
  if (userMode === 'historical') {
    return 'historical';
  }
  // User selected live mode
  const normalizedBackend = (backendMode || 'live').toLowerCase();
  if (normalizedBackend === 'off') {
    return 'off';
  }
  if (normalizedBackend === 'replay') {
    return 'replay';
  }
  return 'live';
}

export function getEffectiveDate({ userMode, backendMode, selectedHistoricalDate, liveRiskData, liveStatus, nowIso } = {}) {
  const mode = resolveEffectiveMode(userMode, backendMode);
  if (mode === 'historical') {
    return selectedHistoricalDate || '2023-07-09';
  }
  if (mode === 'off') {
    return null;
  }
  if (mode === 'replay') {
    return liveRiskData?.as_of || liveStatus?.latest_risk_as_of || '2024-07-15';
  }
  // Live mode: prefer live risk advisory date (as_of), else status date, else current UTC date
  if (liveRiskData?.as_of) {
    return liveRiskData.as_of;
  }
  if (liveStatus?.latest_risk_as_of) {
    return liveStatus.latest_risk_as_of;
  }
  const refDate = nowIso ? new Date(nowIso) : new Date();
  return refDate.toISOString().slice(0, 10);
}

export function getModeDisplayInfo({ effectiveMode, t } = {}) {
  const safeT = t || ((k) => k);
  switch (effectiveMode) {
    case 'historical':
      return {
        mode: 'historical',
        label: safeT('live.historical_mode'),
        isDatePickerAllowed: true,
        isExperimental: false,
        isReplay: false,
        isOff: false,
        source: 'ERA5-Land (Historical)',
        badgeClass: 'badge-retrospective',
      };
    case 'replay':
      return {
        mode: 'replay',
        label: safeT('live.replay_mode'),
        isDatePickerAllowed: false,
        isExperimental: true,
        isReplay: true,
        isOff: false,
        source: 'Replay Simulation',
        badgeClass: 'badge-warning',
      };
    case 'off':
      return {
        mode: 'off',
        label: safeT('live.mode_off_notice'),
        isDatePickerAllowed: false,
        isExperimental: false,
        isReplay: false,
        isOff: true,
        source: 'None (Live Ingestion Disabled)',
        badgeClass: 'badge-neutral',
      };
    case 'live':
    default:
      return {
        mode: 'live',
        label: safeT('live.live_mode'),
        isDatePickerAllowed: false,
        isExperimental: true,
        isReplay: false,
        isOff: false,
        source: 'Open-Meteo',
        badgeClass: 'badge-warning',
      };
  }
}

export function getSegmentAccessibilityCue(tier, status, isStale, t) {
  const safeT = t || ((k, fallback) => fallback || k);
  if (isStale || status === 'STALE_DATA') {
    return {
      symbol: '⧗',
      pattern: 'dashed',
      ariaLabel: safeT('live.aria_stale_telemetry', 'Stale Telemetry (>24h)'),
      className: 'chip-stale',
    };
  }
  if (tier === 'UNKNOWN' || status === 'MISSING_DATA' || status === 'NEIGHBOUR_DATA_MISSING') {
    return {
      symbol: '?',
      pattern: 'dotted',
      ariaLabel: safeT('live.aria_unknown_telemetry', 'Unknown / Missing Telemetry'),
      className: 'chip-unknown',
    };
  }
  if (tier === 'High') {
    return {
      symbol: '▲',
      pattern: 'cross',
      ariaLabel: safeT('live.aria_high_hazard', 'High Hazard (≥0.35)'),
      className: 'chip-high',
    };
  }
  if (tier === 'Medium') {
    return {
      symbol: '▰',
      pattern: 'stripe',
      ariaLabel: safeT('live.aria_elevated_hazard', 'Elevated Hazard (0.10–0.35)'),
      className: 'chip-med',
    };
  }
  return {
    symbol: '○',
    pattern: 'circle',
    ariaLabel: safeT('live.aria_baseline_hazard', 'Baseline Hazard (<0.10)'),
    className: 'chip-low',
  };
}

