/**
 * RouteWise Journey Planner Mode & Scheduling Helper (Task 3c)
 *
 * Enforces mode-aware behavior for JourneyPlanner across:
 * - Live: UTC evaluation date (read-only), weather window end, no benchmark buttons,
 *   no historical date picker, default local departure time, experimental framing.
 * - Replay: Read-only simulated replay date, REPLAY / SIMULATED badge, no benchmark buttons.
 * - Historical / Off: Editable date picker (2021-2025), benchmark quick-select chips.
 */

/**
 * Returns current local time in "HH:MM" format (24-hour).
 * @param {Date} [now]
 * @returns {string}
 */
export function getDefaultDepartureTime(now = new Date()) {
  const hours = String(now.getHours()).padStart(2, '0');
  const minutes = String(now.getMinutes()).padStart(2, '0');
  return `${hours}:${minutes}`;
}

/**
 * Validates whether a time string is a valid 24-hour "HH:MM" format.
 * @param {string} timeStr
 * @returns {boolean}
 */
export function isTimeWithinAdvisoryValidity(timeStr) {
  if (typeof timeStr !== 'string') return false;
  const match = /^([01]\d|2[0-3]):([0-5]\d)$/.exec(timeStr.trim());
  return Boolean(match);
}

/**
 * Builds mode-specific display and form configuration for JourneyPlanner.
 *
 * @param {Object} [params]
 * @param {string} [params.mode] 'live' | 'replay' | 'historical' | 'off'
 * @param {string|null} [params.liveAsOf] Latest live risk as_of date (YYYY-MM-DD)
 * @param {string|null} [params.weatherWindowEnd] ISO timestamp or date of weather window
 * @param {string|null} [params.replayDate] Replay scenario date (YYYY-MM-DD)
 * @param {Date} [params.now] Optional reference date
 * @returns {Object} Mode configuration object
 */
export function getPlannerModeConfig({
  mode = 'historical',
  liveAsOf = null,
  weatherWindowEnd = null,
  replayDate = null,
  now = new Date(),
} = {}) {
  const normalized = (mode || 'historical').toLowerCase();

  if (normalized === 'live') {
    const utcDate = now.toISOString().slice(0, 10);
    const evalDate = liveAsOf || utcDate;
    return {
      mode: 'live',
      isLive: true,
      isReplay: false,
      isHistorical: false,
      isDateEditable: false,
      showBenchmarkButtons: false,
      evaluationDate: evalDate,
      weatherWindowEnd: weatherWindowEnd || null,
      statusBadgeKey: 'planner.live_badge',
      statusBadgeText: 'Live Operational Advisory • Experimental - not validated',
      statusBadgeClass: 'planner-badge-live',
      scheduleTitleKey: 'planner.schedule_title_live',
      scheduleTitleText: 'Travel Schedule (Live Advisory)',
      headerNoticeTitleKey: 'planner.notice_live_title',
      headerNoticeTitleText: 'Single-Path Corridor Topology & Operational Live Advisory Notice:',
      departureTimeNoticeKey: 'planner.departure_time_notice_live',
      departureTimeNoticeText:
        'Calibrates estimated transit times. ST-GNN live advisories reflect daily relative-risk indices from complete weather days (not hourly live changes); experimental telemetry.',
      departureHelpKey: 'planner.departure_help_live',
      departureHelpText:
        'Advisory reflects daily relative risk from complete weather days (not hourly). Departure time calibrates transit times.',
      isExperimental: true,
    };
  }

  if (normalized === 'replay') {
    const evalDate = replayDate || liveAsOf || '2023-07-09';
    return {
      mode: 'replay',
      isLive: false,
      isReplay: true,
      isHistorical: false,
      isDateEditable: false,
      showBenchmarkButtons: false,
      evaluationDate: evalDate,
      weatherWindowEnd: null,
      statusBadgeKey: 'planner.replay_badge',
      statusBadgeText: 'REPLAY / SIMULATED SCENARIO',
      statusBadgeClass: 'planner-badge-replay',
      scheduleTitleKey: 'planner.schedule_title_replay',
      scheduleTitleText: 'Travel Schedule (Simulated Replay)',
      headerNoticeTitleKey: 'planner.notice_replay_title',
      headerNoticeTitleText: 'Corridor Topology & Simulated Replay Scenario Notice:',
      departureTimeNoticeKey: 'planner.departure_time_notice_replay',
      departureTimeNoticeText:
        'Calibrates simulated travel times across historical playback scenarios.',
      departureHelpKey: null,
      departureHelpText: null,
      isExperimental: false,
    };
  }

  // 'historical' or 'off' or fallback
  return {
    mode: normalized === 'off' ? 'off' : 'historical',
    isLive: false,
    isReplay: false,
    isHistorical: true,
    isDateEditable: true,
    showBenchmarkButtons: true,
    evaluationDate: null,
    weatherWindowEnd: null,
    statusBadgeKey: 'planner.historical_badge',
    statusBadgeText: 'Historical Reanalysis',
    statusBadgeClass: 'planner-badge-historical',
    scheduleTitleKey: 'planner.schedule_title_historical',
    scheduleTitleText: 'Travel Schedule & Benchmark Timing',
    headerNoticeTitleKey: 'planner.notice_historical_title',
    headerNoticeTitleText: 'Single-Path Corridor Topology & Retrospective Analysis Notice:',
    departureTimeNoticeKey: 'planner.departure_time_notice_historical',
    departureTimeNoticeText:
      'Calibrates estimated arrival times, but daily retrospective ST-GNN risk predictions do not change by hour.',
    departureHelpKey: null,
    departureHelpText: null,
    isExperimental: false,
  };
}

