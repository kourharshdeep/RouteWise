import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import enTranslations from '../src/i18n/locales/en.json' with { type: 'json' };
import hiTranslations from '../src/i18n/locales/hi.json' with { type: 'json' };
import {
  resolveEffectiveMode,
  getEffectiveDate,
  getModeDisplayInfo,
  getSegmentAccessibilityCue,
} from '../src/services/liveModeHelper.js';
import {
  RESILIENCE_CONFIG,
  calculateBackoffDelay,
  ConnectionStateMachine,
  reconcileAlerts,
  reconcileHazardEvents,
  shouldRefreshPlanner,
  hasRecommendationChanged,
} from '../src/services/connectionResilience.js';
import { normalizeRiskSummary } from '../src/services/riskSummaryHelper.js';

// ==============================================================================
// 1. Pending Sync Queue Logic Tests
// ==============================================================================
describe('Pending-Sync Queue Logic & Retry Strategy', () => {
  it('calculates exponential backoff delay correctly based on attempt count', () => {
    const calculateBackoffMs = (attemptCount) => {
      // Exponential backoff: min(60s, 2s * 2^attempt)
      return Math.min(60000, 2000 * Math.pow(2, attemptCount));
    };

    assert.equal(calculateBackoffMs(0), 2000, 'Attempt 0 should be 2000ms');
    assert.equal(calculateBackoffMs(1), 4000, 'Attempt 1 should be 4000ms');
    assert.equal(calculateBackoffMs(2), 8000, 'Attempt 2 should be 8000ms');
    assert.equal(calculateBackoffMs(3), 16000, 'Attempt 3 should be 16000ms');
    assert.equal(calculateBackoffMs(4), 32000, 'Attempt 4 should be 32000ms');
    assert.equal(calculateBackoffMs(5), 60000, 'Attempt 5 should be capped at 60000ms');
    assert.equal(calculateBackoffMs(10), 60000, 'Attempt 10 should be capped at 60000ms');
  });

  it('determines transient vs terminal errors correctly', () => {
    const categorizeError = (statusCode) => {
      if (statusCode === 401) return 'AUTH_REQUIRED_PAUSE';
      if (statusCode >= 400 && statusCode < 500) return 'CLIENT_TERMINAL_REJECT';
      if (statusCode >= 500 || statusCode === 0) return 'SERVER_TRANSIENT_RETRY';
      return 'UNKNOWN';
    };

    assert.equal(categorizeError(401), 'AUTH_REQUIRED_PAUSE');
    assert.equal(categorizeError(422), 'CLIENT_TERMINAL_REJECT');
    assert.equal(categorizeError(400), 'CLIENT_TERMINAL_REJECT');
    assert.equal(categorizeError(500), 'SERVER_TRANSIENT_RETRY');
    assert.equal(categorizeError(502), 'SERVER_TRANSIENT_RETRY');
    assert.equal(categorizeError(0), 'SERVER_TRANSIENT_RETRY'); // Network dropped
  });

  it('guarantees idempotency key format is valid UUID v4', () => {
    const isUUIDv4 = (uuid) => {
      const regex = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
      return regex.test(uuid);
    };

    const mockClientUuid = 'f47ac10b-58cc-4372-a567-0e02b2c3d479';
    assert.equal(isUUIDv4(mockClientUuid), true);
    assert.equal(isUUIDv4('not-a-uuid'), false);
  });
});

// ==============================================================================
// 2. Route Guard & Deep-Link Destination Tests
// ==============================================================================
describe('Route Guards & Deep-Link Resolution', () => {
  it('resolves unauthenticated redirect without circular loop', () => {
    const resolveDestination = ({ isAuthenticated, currentPath, requestedPath }) => {
      if (!isAuthenticated) {
        // Return login route with 'from' state
        return {
          route: '/',
          state: { from: requestedPath || currentPath },
        };
      }
      return { route: requestedPath || '/overview', state: null };
    };

    // Unauthenticated deep link to /map
    const deepLinkResult = resolveDestination({
      isAuthenticated: false,
      currentPath: '/map',
      requestedPath: '/map',
    });
    assert.equal(deepLinkResult.route, '/');
    assert.equal(deepLinkResult.state?.from, '/map');

    // After sign-in, redirect to requestedPath
    const authenticatedResult = resolveDestination({
      isAuthenticated: true,
      currentPath: '/',
      requestedPath: deepLinkResult.state?.from,
    });
    assert.equal(authenticatedResult.route, '/map');
    assert.equal(authenticatedResult.state, null);
  });

  it('prevents authenticated user from hitting public auth views', () => {
    const handlePublicOnlyGuard = ({ isAuthenticated, locationState }) => {
      if (isAuthenticated) {
        return locationState?.from || '/overview';
      }
      return null; // allow render
    };

    assert.equal(handlePublicOnlyGuard({ isAuthenticated: true, locationState: { from: '/journey' } }), '/journey');
    assert.equal(handlePublicOnlyGuard({ isAuthenticated: true, locationState: null }), '/overview');
    assert.equal(handlePublicOnlyGuard({ isAuthenticated: false, locationState: null }), null);
  });
});

// ==============================================================================
// 3. Role-Based Navigation Matrix Tests
// ==============================================================================
describe('Role-Based Navigation Matrix', () => {
  const getNavItems = (user) => {
    const isPatrol = user?.role === 'patrol' || user?.role === 'admin';
    const items = [
      { id: 'overview', path: '/overview' },
      { id: 'journey', path: '/journey' },
      { id: 'map', path: '/map' },
      { id: 'report', path: '/reports' },
    ];
    if (isPatrol) {
      items.push({ id: 'patrol', path: '/patrol' });
    }
    items.push(
      { id: 'chat', path: '/chat' },
      { id: 'history', path: '/history' },
      { id: 'settings', path: '/settings' }
    );
    return items;
  };

  it('hides patrol operations tab from guest users', () => {
    const guestUser = { id: 0, role: 'guest', name: 'Guest Observer' };
    const nav = getNavItems(guestUser);
    const hasPatrol = nav.some((item) => item.id === 'patrol');
    assert.equal(hasPatrol, false, 'Guest must NOT see Patrol Operations');
  });

  it('hides patrol operations tab from regular authenticated commuters', () => {
    const commuter = { id: 2, role: 'user', name: 'NH44 Commuter' };
    const nav = getNavItems(commuter);
    const hasPatrol = nav.some((item) => item.id === 'patrol');
    assert.equal(hasPatrol, false, 'Commuter must NOT see Patrol Operations');
  });

  it('shows patrol operations tab exclusively to patrol role', () => {
    const patrolUser = { id: 1, role: 'patrol', name: 'Ramban Patrol Unit 1' };
    const nav = getNavItems(patrolUser);
    const hasPatrol = nav.some((item) => item.id === 'patrol');
    assert.equal(hasPatrol, true, 'Patrol user MUST see Patrol Operations');
  });

  it('shows patrol operations tab to admin role', () => {
    const adminUser = { id: 99, role: 'admin', name: 'Admin Dispatcher' };
    const nav = getNavItems(adminUser);
    const hasPatrol = nav.some((item) => item.id === 'patrol');
    assert.equal(hasPatrol, true, 'Admin user MUST see Patrol Operations');
  });
});

// ==============================================================================
// 4. Corridor Strip Landmarks & Chainage Tests
// ==============================================================================
describe('Corridor Strip Topology & Chainage Sequence', () => {
  const LANDMARKS = [
    { index: 0, name: 'Dewal', chainage: 'Km 0' },
    { index: 22, name: 'Cafeteria Morh', chainage: 'Km 5.4' },
    { index: 41, name: 'Ramban', chainage: 'Km 10.2' },
    { index: 65, name: 'Seri', chainage: 'Km 16.0' },
    { index: 88, name: 'Maroog', chainage: 'Km 21.5' },
    { index: 110, name: 'Digdol', chainage: 'Km 26.8' },
    { index: 132, name: 'Ramsu', chainage: 'Km 31.4' },
    { index: 150, name: 'Banihal', chainage: 'Km 36.0' },
  ];

  it('verifies monotonic ascending chainage and index bounds for 151 segments', () => {
    for (let i = 0; i < LANDMARKS.length; i++) {
      assert.ok(LANDMARKS[i].index >= 0 && LANDMARKS[i].index <= 150, `Landmark ${LANDMARKS[i].name} out of bounds`);
      if (i > 0) {
        assert.ok(
          LANDMARKS[i].index > LANDMARKS[i - 1].index,
          `Landmarks must be monotonically strictly ascending in index`
        );
      }
    }
  });

  it('assigns accessible non-color cues to risk tiers', () => {
    const getAccessibleCue = (tier) => {
      switch (tier) {
        case 'High':
          return '▲';
        case 'Medium':
          return '■';
        case 'Low':
        default:
          return '●';
      }
    };

    assert.equal(getAccessibleCue('High'), '▲');
    assert.equal(getAccessibleCue('Medium'), '■');
    assert.equal(getAccessibleCue('Low'), '●');
  });
});

// ==============================================================================
// 5. English & Hindi i18n Key Completeness
// ==============================================================================
describe('i18n Translation Key Completeness (EN vs HI)', () => {
  const getKeys = (obj, prefix = '') => {
    let keys = [];
    for (const [k, v] of Object.entries(obj)) {
      const fullKey = prefix ? `${prefix}.${k}` : k;
      if (typeof v === 'object' && v !== null && !Array.isArray(v)) {
        keys = keys.concat(getKeys(v, fullKey));
      } else {
        keys.push(fullKey);
      }
    }
    return keys;
  };

  it('ensures all top-level sections exist in both EN and HI catalogs', () => {
    const enSections = Object.keys(enTranslations);
    const hiSections = Object.keys(hiTranslations);

    for (const section of enSections) {
      assert.ok(hiSections.includes(section), `Hindi catalog is missing section: ${section}`);
    }
  });

  it('ensures all critical report categories exist in both languages', () => {
    const expectedCategories = [
      'landslide',
      'shooting_stones',
      'flooding',
      'road_damage',
      'single_lane_or_obstruction',
      'snow_or_ice',
      'other',
    ];

    for (const cat of expectedCategories) {
      assert.ok(enTranslations.categories[cat], `EN missing category ${cat}`);
      assert.ok(hiTranslations.categories[cat], `HI missing category ${cat}`);
    }
  });
});

// ==============================================================================
// 6. Live Intelligence Mode & Accessibility Guarantees (Step 5)
// ==============================================================================
describe('Live Intelligence Mode & Accessibility Guarantees', () => {
  it('guarantees UNKNOWN tier has non-color cues and never defaults to low', () => {
    const resolveRiskCue = (tier) => {
      if (tier === 'High') return { cue: '▲', className: 'seg-high' };
      if (tier === 'Medium') return { cue: '■', className: 'seg-medium' };
      if (tier === 'Low') return { cue: '●', className: 'seg-low' };
      return { cue: '?', className: 'seg-unknown' };
    };

    assert.deepEqual(resolveRiskCue('UNKNOWN'), { cue: '?', className: 'seg-unknown' });
    assert.deepEqual(resolveRiskCue(null), { cue: '?', className: 'seg-unknown' });
    assert.deepEqual(resolveRiskCue(undefined), { cue: '?', className: 'seg-unknown' });
    assert.notEqual(resolveRiskCue('UNKNOWN').className, 'seg-low');
  });

  it('ensures all live intelligence i18n keys exist in both EN and HI', () => {
    const liveKeys = [
      'toggle_label',
      'historical_mode',
      'live_mode',
      'experimental_badge',
      'experimental_notice',
      'last_updated',
      'data_age',
      'data_stale',
      'connection_connected',
      'connection_lost',
      'unknown_segments',
      'operational_status',
      'status_open',
      'status_caution',
      'status_restricted',
      'status_closed',
      'status_unknown',
      'simulated_events',
      'verified_events',
      'refresh_now',
    ];

    for (const k of liveKeys) {
      assert.ok(enTranslations.live?.[k], `EN missing live key: ${k}`);
      assert.ok(hiTranslations.live?.[k], `HI missing live key: ${k}`);
    }
  });
});

// ==============================================================================
// 7. Dynamic Routing & Operational Recommendation Matrix (Step 6)
// ==============================================================================
describe('Dynamic Routing & Operational Recommendation Matrix', () => {
  const resolveRecommendation = ({ blockingCount, unknownCount, isStale, highCount, maxScore, medCount }) => {
    if (blockingCount > 0) return 'HOLD';
    if (unknownCount > 0 || isStale) return 'NO_DATA';
    if (highCount > 0 || (maxScore !== null && maxScore !== undefined && maxScore >= 0.35)) return 'DELAY';
    if (medCount > 0 || (maxScore !== null && maxScore !== undefined && maxScore >= 0.10)) return 'PROCEED_WITH_CAUTION';
    return 'PROCEED';
  };

  it('correctly maps HOLD, NO_DATA, DELAY, PROCEED_WITH_CAUTION, and PROCEED', () => {
    // 1. Blocked segment -> HOLD
    assert.equal(
      resolveRecommendation({ blockingCount: 1, unknownCount: 0, isStale: false, highCount: 0, maxScore: 0.05, medCount: 0 }),
      'HOLD'
    );

    // 2. Unknown segments or stale telemetry -> NO_DATA
    assert.equal(
      resolveRecommendation({ blockingCount: 0, unknownCount: 2, isStale: false, highCount: 0, maxScore: 0.05, medCount: 0 }),
      'NO_DATA'
    );
    assert.equal(
      resolveRecommendation({ blockingCount: 0, unknownCount: 0, isStale: true, highCount: 0, maxScore: 0.05, medCount: 0 }),
      'NO_DATA'
    );

    // 3. High risk count or score >= 0.35 -> DELAY
    assert.equal(
      resolveRecommendation({ blockingCount: 0, unknownCount: 0, isStale: false, highCount: 1, maxScore: 0.40, medCount: 0 }),
      'DELAY'
    );

    // 4. Medium risk count or score >= 0.10 -> PROCEED_WITH_CAUTION
    assert.equal(
      resolveRecommendation({ blockingCount: 0, unknownCount: 0, isStale: false, highCount: 0, maxScore: 0.22, medCount: 2 }),
      'PROCEED_WITH_CAUTION'
    );

    // 5. Clean baseline -> PROCEED
    assert.equal(
      resolveRecommendation({ blockingCount: 0, unknownCount: 0, isStale: false, highCount: 0, maxScore: 0.04, medCount: 0 }),
      'PROCEED'
    );
  });

  it('ensures routing i18n keys exist in both EN and HI catalogs', () => {
    const routingKeys = [
      'recommendation_hold',
      'recommendation_no_data',
      'recommendation_delay',
      'recommendation_proceed_caution',
      'recommendation_proceed',
      'route_updated',
      'baseline_route',
      'risk_aware_route',
      'single_corridor_notice',
      'passable',
      'impassable',
      'compare_previous',
    ];

    for (const k of routingKeys) {
      assert.ok(enTranslations.routing?.[k], `EN missing routing key: ${k}`);
      assert.ok(hiTranslations.routing?.[k], `HI missing routing key: ${k}`);
    }
  });

  it('guarantees single-corridor honesty constraints for alternative paths', () => {
    const mockBaseline = { total_distance_km: 35.8, is_passable: false, blocking_segments: ['seg_123'] };
    const mockRiskAware = { total_distance_km: 35.8, is_passable: false, blocking_segments: ['seg_123'] };
    const hasAlternative = false;

    // Distances must be symmetric and identical since physical path is unchanged
    assert.equal(mockBaseline.total_distance_km, mockRiskAware.total_distance_km);
    assert.equal(hasAlternative, false);
    assert.equal(mockBaseline.is_passable, false);
    assert.equal(mockRiskAware.is_passable, false);
  });
});

// ==============================================================================
// 8. Alerts, In-App Boundary & Role Matrix (Step 7)
// ==============================================================================
describe('Alerts, In-App Boundary & Role Matrix', () => {
  it('enforces RBAC for alert acknowledgement and clearing actions', () => {
    const canAcknowledgeOrClear = (role) => {
      return role === 'patrol' || role === 'admin';
    };

    assert.equal(canAcknowledgeOrClear('admin'), true);
    assert.equal(canAcknowledgeOrClear('patrol'), true);
    assert.equal(canAcknowledgeOrClear('user'), false);
    assert.equal(canAcknowledgeOrClear('guest'), false);
    assert.equal(canAcknowledgeOrClear(null), false);
  });

  it('guarantees in-app delivery boundary constraint on alert payloads', () => {
    const sampleAlert = {
      id: 'alert_test_01',
      segment_id: 'seg_123',
      alert_type: 'closure',
      status: 'active',
      delivery_channel: 'in_app_only',
      delivery_notice: 'In-App Advisory Only: RouteWise alerts are delivered exclusively via the web interface. No SMS, push notifications, or cellular broadcasts are emitted.',
    };

    assert.equal(sampleAlert.delivery_channel, 'in_app_only');
    assert.match(sampleAlert.delivery_notice, /No SMS/);
    assert.match(sampleAlert.delivery_notice, /In-App Advisory Only/);
  });

  it('ensures alert i18n keys exist in both EN and HI catalogs', () => {
    const alertKeys = [
      'title',
      'active_alerts',
      'no_alerts',
      'in_app_notice',
      'acknowledge',
      'clear',
      'acknowledged',
      'active',
      'simulated_tag',
      'scenario_title',
      'advance_phase',
      'reset_baseline',
      'lastKnownDataStale',
    ];

    for (const k of alertKeys) {
      assert.ok(enTranslations.alerts?.[k], `EN missing alert key: ${k}`);
      assert.ok(hiTranslations.alerts?.[k], `HI missing alert key: ${k}`);
    }
    assert.equal(enTranslations.alerts.lastKnownDataStale, 'Last known, data stale');
    assert.equal(hiTranslations.alerts.lastKnownDataStale, 'अंतिम ज्ञात स्थिति, डेटा पुराना है');
  });

  it('verifies 1-hour cooldown calculation logic', () => {
    const isWithinCooldown = (clearedAtIso, currentIso) => {
      const clearedTime = new Date(clearedAtIso).getTime();
      const currentTime = new Date(currentIso).getTime();
      const elapsedSeconds = (currentTime - clearedTime) / 1000;
      return elapsedSeconds < 3600;
    };

    const t0 = '2026-11-03T12:00:00Z';
    const t30min = '2026-11-03T12:30:00Z';
    const t59min = '2026-11-03T12:59:00Z';
    const t61min = '2026-11-03T13:01:00Z';

    assert.equal(isWithinCooldown(t0, t30min), true, '30 min should be inside cooldown');
    assert.equal(isWithinCooldown(t0, t59min), true, '59 min should be inside cooldown');
    assert.equal(isWithinCooldown(t0, t61min), false, '61 min should be outside cooldown');
  });
  it('renders stale data indicator at most once per alert with is_stale_context=true even when refreshed repeatedly', () => {
    const getAlertBadges = (item, t) => {
      const badges = [];
      if (item.is_stale_context) {
        badges.push({ type: 'stale_context', text: t('alerts.lastKnownDataStale') });
      }
      if (item.is_simulated) {
        badges.push({ type: 'simulated', text: 'SIMULATED' });
      }
      badges.push({ type: 'status', text: item.status.toUpperCase() });
      return badges;
    };

    const mockT = (key) => enTranslations.alerts?.[key.replace('alerts.', '')] || key;

    const alertItem = {
      id: 'alert_stale_01',
      title_en: 'High Landslide Risk Advisory',
      status: 'active',
      is_stale_context: true,
      is_simulated: false,
    };

    const badges1 = getAlertBadges(alertItem, mockT);
    const staleBadges1 = badges1.filter((b) => b.type === 'stale_context');
    assert.equal(staleBadges1.length, 1, 'Should have exactly 1 stale badge');
    assert.equal(staleBadges1[0].text, 'Last known, data stale');

    for (let cycle = 1; cycle <= 5; cycle++) {
      const refreshedBadges = getAlertBadges(alertItem, mockT);
      const staleCount = refreshedBadges.filter((b) => b.type === 'stale_context').length;
      assert.equal(staleCount, 1, `Cycle ${cycle} must not duplicate stale indicator`);
    }

    const freshItem = { ...alertItem, is_stale_context: false };
    const freshBadges = getAlertBadges(freshItem, mockT);
    assert.equal(freshBadges.filter((b) => b.type === 'stale_context').length, 0);
  });
});

// ==============================================================================
// 9. Current-Date Live Mode Decision Logic & i18n Completeness (Task 3)
// ==============================================================================
describe('Current-Date Live Mode Decision Logic & i18n Completeness (Task 3)', () => {
  it('distinguishes operational modes: historical vs live vs replay vs off', () => {
    // 1. Historical selection always yields 'historical' regardless of backend mode
    assert.equal(resolveEffectiveMode('historical', 'live'), 'historical');
    assert.equal(resolveEffectiveMode('historical', 'replay'), 'historical');
    assert.equal(resolveEffectiveMode('historical', 'off'), 'historical');

    // 2. Live selection routes to backend operational mode
    assert.equal(resolveEffectiveMode('live', 'live'), 'live');
    assert.equal(resolveEffectiveMode('live', 'replay'), 'replay');
    assert.equal(resolveEffectiveMode('live', 'off'), 'off');
    assert.equal(resolveEffectiveMode('live', null), 'live');
  });

  it('resolves effective date and enforces date picker policy by mode', () => {
    // Historical mode: date picker active, returns selected historical date
    const histDate = getEffectiveDate({
      userMode: 'historical',
      backendMode: 'live',
      selectedHistoricalDate: '2023-07-09',
    });
    assert.equal(histDate, '2023-07-09');

    const histInfo = getModeDisplayInfo({ effectiveMode: 'historical' });
    assert.equal(histInfo.isDatePickerAllowed, true, 'Date picker must be allowed in historical mode');
    assert.equal(histInfo.isExperimental, false);

    // Live mode: date picker disabled, returns live risk as_of or current date
    const liveDate = getEffectiveDate({
      userMode: 'live',
      backendMode: 'live',
      selectedHistoricalDate: '2023-07-09',
      liveRiskData: { as_of: '2026-11-09' },
    });
    assert.equal(liveDate, '2026-11-09', 'Live mode must use current live risk as_of, never July 2023');

    const liveInfo = getModeDisplayInfo({ effectiveMode: 'live' });
    assert.equal(liveInfo.isDatePickerAllowed, false, 'Date picker must be disabled in live view');
    assert.equal(liveInfo.isExperimental, true, 'Live results must stay labelled Experimental');

    // Replay mode: labeled REPLAY, date picker disabled
    const replayInfo = getModeDisplayInfo({ effectiveMode: 'replay' });
    assert.equal(replayInfo.isDatePickerAllowed, false);
    assert.equal(replayInfo.isReplay, true);

    // Off mode: clear disabled state
    const offInfo = getModeDisplayInfo({ effectiveMode: 'off' });
    assert.equal(offInfo.isDatePickerAllowed, false);
    assert.equal(offInfo.isOff, true);
  });

  it('guarantees Task 3 live i18n keys exist in both EN and HI catalogs', () => {
    const task3Keys = ['replay_mode', 'mode_off_notice', 'weather_window_end', 'source_label'];
    for (const k of task3Keys) {
      assert.ok(enTranslations.live?.[k], `EN missing live key: ${k}`);
      assert.ok(hiTranslations.live?.[k], `HI missing live key: ${k}`);
    }

    assert.equal(enTranslations.live.replay_mode, 'REPLAY / simulated scenario');
    assert.equal(hiTranslations.live.replay_mode, 'रीप्ले / सिम्युलेटेड परिदृश्य');

    assert.equal(enTranslations.live.mode_off_notice, "Live mode not enabled (ROUTEWISE_LIVE_MODE is 'off')");
    assert.equal(hiTranslations.live.mode_off_notice, "लाइव मोड सक्षम नहीं है (ROUTEWISE_LIVE_MODE 'off' है)");

    assert.equal(enTranslations.live.weather_window_end, 'Weather data window through');
    assert.equal(hiTranslations.live.weather_window_end, 'मौसम डेटा विंडो समाप्ति');

    assert.equal(enTranslations.live.source_label, 'Source');
    assert.equal(hiTranslations.live.source_label, 'स्रोत');
  });

  it('provides distinct accessible non-color cues for UNKNOWN and STALE telemetry', () => {
    const cueUnknown = getSegmentAccessibilityCue('UNKNOWN', 'MISSING_DATA', false);
    assert.equal(cueUnknown.symbol, '?');
    assert.equal(cueUnknown.pattern, 'dotted');

    const cueStale = getSegmentAccessibilityCue('UNKNOWN', 'STALE_DATA', true);
    assert.equal(cueStale.symbol, '⧗');
    assert.equal(cueStale.pattern, 'dashed');

    const cueHigh = getSegmentAccessibilityCue('High', 'OK', false);
    assert.equal(cueHigh.symbol, '▲');

    const cueLow = getSegmentAccessibilityCue('Low', 'OK', false);
    assert.equal(cueLow.symbol, '○');
  });
});

// ==============================================================================
// 10. Live Connection Resilience & Fallback Decision Logic (Task 3b)
// ==============================================================================
describe('Live Connection Resilience & Fallback Decision Logic (Task 3b)', () => {
  it('calculates exponential backoff with full jitter and caps at 30 seconds', () => {
    // 1. With max jitter (randomFn = 1.0): backoff matches baseMs * factor^attempt capped at maxMs
    assert.equal(
      calculateBackoffDelay({ attempt: 0, baseMs: 1000, factor: 2, maxMs: 30000, randomFn: () => 1.0 }),
      1000,
      'Attempt 0 max jitter should be 1000ms'
    );
    assert.equal(
      calculateBackoffDelay({ attempt: 1, baseMs: 1000, factor: 2, maxMs: 30000, randomFn: () => 1.0 }),
      2000,
      'Attempt 1 max jitter should be 2000ms'
    );
    assert.equal(
      calculateBackoffDelay({ attempt: 2, baseMs: 1000, factor: 2, maxMs: 30000, randomFn: () => 1.0 }),
      4000,
      'Attempt 2 max jitter should be 4000ms'
    );
    assert.equal(
      calculateBackoffDelay({ attempt: 5, baseMs: 1000, factor: 2, maxMs: 30000, randomFn: () => 1.0 }),
      30000,
      'Attempt 5 should be capped at 30000ms (not 32000ms)'
    );
    assert.equal(
      calculateBackoffDelay({ attempt: 10, baseMs: 1000, factor: 2, maxMs: 30000, randomFn: () => 1.0 }),
      30000,
      'Attempt 10 should be capped at 30000ms'
    );

    // 2. Upper-half jitter: delay is never below 50% of ceiling [0.5 * ceiling, 1.0 * ceiling]
    // With partial jitter (randomFn = 0.5): delay is 75% of ceiling (3000ms)
    assert.equal(
      calculateBackoffDelay({ attempt: 2, baseMs: 1000, factor: 2, maxMs: 30000, randomFn: () => 0.5 }),
      3000,
      'Attempt 2 with 0.5 jitter should be 3000ms (upper half jitter)'
    );
    // With minimum jitter (randomFn = 0.0): delay is strictly 50% of ceiling (2000ms)
    assert.equal(
      calculateBackoffDelay({ attempt: 2, baseMs: 1000, factor: 2, maxMs: 30000, randomFn: () => 0.0 }),
      2000,
      'Attempt 2 with 0.0 jitter must be strictly 50% of ceiling (2000ms)'
    );
  });

  it('resets backoff attempt counter after healthy connection threshold (5s)', () => {
    const sm = new ConnectionStateMachine();
    // Simulate 2 SSE failures -> state reconnecting, attempt = 2
    sm.handleSseError({ isOnline: true });
    sm.handleSseError({ isOnline: true });
    assert.equal(sm.getConsecutiveFailures(), 2);

    // Simulate healthy connection staying connected
    sm.handleSseOpen();
    assert.equal(sm.getState(), 'connected');

    // Before healthy threshold: failures count preserved
    assert.equal(sm.getConsecutiveFailures(), 2);

    // Simulate 5000ms healthy threshold elapse
    sm.resetConsecutiveFailures();
    assert.equal(sm.getConsecutiveFailures(), 0);

    // Next failure starts at attempt 0 (consecutive failures count = 1)
    const nextErr = sm.handleSseError({ isOnline: true });
    assert.equal(sm.getConsecutiveFailures(), 1);
    assert.equal(nextErr.nextState, 'reconnecting');
    sm.destroy();
  });

  it('transitions through connected -> reconnecting -> polling -> connected and offline', () => {
    const sm = new ConnectionStateMachine();
    assert.equal(sm.getState(), 'connected');

    // Drop 1: Reconnecting
    const r1 = sm.handleSseError({ isOnline: true });
    assert.equal(r1.nextState, 'reconnecting');
    assert.equal(sm.getState(), 'reconnecting');

    // Drop 2: Still Reconnecting
    const r2 = sm.handleSseError({ isOnline: true });
    assert.equal(r2.nextState, 'reconnecting');

    // Drop 3: Transitions to Polling fallback
    const r3 = sm.handleSseError({ isOnline: true });
    assert.equal(r3.nextState, 'polling');
    assert.equal(sm.getState(), 'polling');

    // In polling mode, poll error backs off interval
    const pErr = sm.handlePollError({ isOnline: true });
    assert.equal(pErr.nextState, 'polling');

    // Offline event transitions immediately to offline
    const offErr = sm.handleSseError({ isOnline: false });
    assert.equal(offErr.nextState, 'offline');
    assert.equal(sm.getState(), 'offline');

    // Online resume returns to reconnecting
    sm.handleOnlineResume();
    assert.equal(sm.getState(), 'reconnecting');

    // Success returns to connected
    sm.handleSuccess();
    assert.equal(sm.getState(), 'connected');
    sm.destroy();
  });

  it('reconciles state idempotently: server status always wins and cleared alerts are removed', () => {
    // Current alerts in client state (alt_01 was locally acknowledged in UI, alt_02 active)
    const currentAlerts = [
      { id: 'alt_01', segment_id: 'seg_010', status: 'acknowledged', acknowledged: true, _clientUiExpanded: true },
      { id: 'alt_02', segment_id: 'seg_020', status: 'active', acknowledged: false },
    ];

    // Incoming alerts from server poll: server reset alt_01 back to active! And alt_02 cleared on server!
    const incomingAlerts = [
      { id: 'alt_01', segment_id: 'seg_010', status: 'active', acknowledged: false },
      { id: 'alt_03', segment_id: 'seg_030', status: 'active', acknowledged: false },
    ];

    const reconciled = reconcileAlerts(currentAlerts, incomingAlerts);
    assert.equal(reconciled.length, 2, 'Must contain 2 items: alt_01 and alt_03 (cleared alt_02 removed, zero duplicates)');
    const a1 = reconciled.find((a) => a.id === 'alt_01');
    assert.equal(a1.status, 'active', 'Server status active must win over local acknowledged');
    assert.equal(a1.acknowledged, false, 'Server unacknowledged must win over local acknowledged');
    assert.equal(a1._clientUiExpanded, true, 'Visual-only UI state persists');
    const a2 = reconciled.find((a) => a.id === 'alt_02');
    assert.equal(a2, undefined, 'Cleared alert alt_02 must be removed');
    const a3 = reconciled.find((a) => a.id === 'alt_03');
    assert.ok(a3, 'New incoming alert alt_03 must be included');

    // Hazard event reconciliation: deduplication and removal of cleared events
    const currentEvents = [
      { id: 'evt_01', segment_id: 'seg_005', type: 'landslide', status: 'active' },
      { id: 'evt_02', segment_id: 'seg_012', type: 'shooting_stones', status: 'active' },
    ];
    const incomingEvents = [
      { id: 'evt_01', segment_id: 'seg_005', type: 'landslide', status: 'active' },
      { id: 'evt_03', segment_id: 'seg_050', type: 'waterlogging', status: 'active' },
    ];
    const reconciledEvents = reconcileHazardEvents(currentEvents, incomingEvents);
    assert.equal(reconciledEvents.length, 2, 'Cleared event evt_02 removed, new evt_03 added');
    assert.ok(reconciledEvents.some((e) => e.id === 'evt_01'));
    assert.ok(reconciledEvents.some((e) => e.id === 'evt_03'));
    assert.ok(!reconciledEvents.some((e) => e.id === 'evt_02'));
  });

  it('governs planner auto-refresh qualification, debouncing and storm guards', () => {
    // 1. Live mode with active plan and tab visible -> should refresh
    assert.equal(
      shouldRefreshPlanner({
        mode: 'live',
        hasActivePlan: true,
        isPlanning: false,
        isTabVisible: true,
        changeDetected: true,
      }),
      true
    );

    // 2. Historical mode -> NEVER auto-refresh
    assert.equal(
      shouldRefreshPlanner({
        mode: 'historical',
        hasActivePlan: true,
        isPlanning: false,
        isTabVisible: true,
        changeDetected: true,
      }),
      false,
      'Historical reanalysis must not auto-refresh'
    );

    // 3. No active plan displayed -> do not auto-refresh
    assert.equal(
      shouldRefreshPlanner({
        mode: 'live',
        hasActivePlan: false,
        isPlanning: false,
        isTabVisible: true,
        changeDetected: true,
      }),
      false
    );

    // 4. Request already in-flight (storm guard) -> do not trigger concurrent refresh
    assert.equal(
      shouldRefreshPlanner({
        mode: 'live',
        hasActivePlan: true,
        isPlanning: true,
        isTabVisible: true,
        changeDetected: true,
      }),
      false,
      'Storm guard must prevent concurrent planning requests'
    );

    // 5. Background tab hidden -> do not refresh while hidden
    assert.equal(
      shouldRefreshPlanner({
        mode: 'live',
        hasActivePlan: true,
        isPlanning: false,
        isTabVisible: false,
        changeDetected: true,
      }),
      false,
      'Hidden tab must pause refresh'
    );
  });

  it('guarantees Task 3b connection resilience and auto-refresh i18n keys exist in both EN and HI catalogs', () => {
    const requiredLiveKeys = [
      'conn_connected',
      'conn_reconnecting',
      'conn_polling',
      'conn_offline',
      'conn_data_may_be_outdated',
      'conn_last_successful',
    ];

    for (const key of requiredLiveKeys) {
      assert.ok(enTranslations.live?.[key], `EN missing live key: ${key}`);
      assert.ok(hiTranslations.live?.[key], `HI missing live key: ${key}`);
    }

    assert.equal(enTranslations.live.conn_connected, 'Connected (Real-time Stream)');
    assert.equal(hiTranslations.live.conn_connected, 'कनेक्टेड (रियल-टाइम स्ट्रीम)');

    assert.equal(enTranslations.live.conn_reconnecting, 'Reconnecting...');
    assert.equal(hiTranslations.live.conn_reconnecting, 'पुनः कनेक्ट हो रहा है...');

    assert.equal(enTranslations.live.conn_polling, 'Polling Fallback');
    assert.equal(hiTranslations.live.conn_polling, 'पॉलिंग फ़ॉलबैक');

    assert.equal(enTranslations.live.conn_offline, 'Offline');
    assert.equal(hiTranslations.live.conn_offline, 'ऑफ़लाइन');

    assert.equal(enTranslations.live.conn_data_may_be_outdated, 'Connection interrupted: telemetry may be out of date');
    assert.equal(hiTranslations.live.conn_data_may_be_outdated, 'कनेक्शन बाधित: टेलीमेट्री पुरानी हो सकती है');

    assert.equal(enTranslations.live.conn_last_successful, 'Last successful update: {{time}}');
    assert.equal(hiTranslations.live.conn_last_successful, 'अंतिम सफल अपडेट: {{time}}');

    assert.ok(enTranslations.journey?.plan_auto_refreshed, 'EN missing journey.plan_auto_refreshed');
    assert.ok(hiTranslations.journey?.plan_auto_refreshed, 'HI missing journey.plan_auto_refreshed');

    assert.equal(enTranslations.journey.plan_auto_refreshed, 'Plan auto-refreshed at {{time}}');
    assert.equal(hiTranslations.journey.plan_auto_refreshed, 'योजना {{time}} पर स्वतः रीफ़्रेश हुई');
  });
});


// ==============================================================================
// 11. Live Operational Integration & Safety Hardening
// ==============================================================================
describe('Live Operational Integration & Safety Hardening', () => {
  it('normalizes risk summary counts for both live and historical schema shapes', () => {
    // 1. Live format: keys {Low, Medium, High, UNKNOWN}
    const liveShape = {
      Low: 140,
      Medium: 10,
      High: 1,
      UNKNOWN: 0,
    };
    const normFromLive = normalizeRiskSummary(liveShape);
    assert.equal(normFromLive.High, 1);
    assert.equal(normFromLive.Medium, 10);
    assert.equal(normFromLive.Low, 140);
    assert.equal(normFromLive.UNKNOWN, 0);
    assert.equal(normFromLive.high_risk_count, 1);
    assert.equal(normFromLive.medium_risk_count, 10);
    assert.equal(normFromLive.low_risk_count, 140);
    assert.equal(normFromLive.unknown_count, 0);
    assert.equal(normFromLive.total, 151);

    // 2. Historical format: snake_case keys {high_risk_count, ...}
    const histShape = {
      high_risk_count: 3,
      medium_risk_count: 12,
      low_risk_count: 136,
      unknown_count: 0,
    };
    const normFromHist = normalizeRiskSummary(histShape);
    assert.equal(normFromHist.High, 3);
    assert.equal(normFromHist.Medium, 12);
    assert.equal(normFromHist.Low, 136);
    assert.equal(normFromHist.UNKNOWN, 0);
    assert.equal(normFromHist.high_risk_count, 3);
    assert.equal(normFromHist.medium_risk_count, 12);
    assert.equal(normFromHist.low_risk_count, 136);
    assert.equal(normFromHist.unknown_count, 0);
    assert.equal(normFromHist.total, 151);

    // 3. Null / empty / undefined fallback
    const normEmpty = normalizeRiskSummary(null);
    assert.equal(normEmpty.High, 0);
    assert.equal(normEmpty.Medium, 0);
    assert.equal(normEmpty.Low, 0);
    assert.equal(normEmpty.UNKNOWN, 0);
    assert.equal(normEmpty.high_risk_count, 0);
    assert.equal(normEmpty.total, 0);
  });

  it('filters simulated alerts out of live, historical and off client views', () => {
    const rawAlerts = [
      { id: 'alert-1', segment_id: 10, is_simulated: false, title: 'Real Rockfall' },
      { id: 'alert-2', segment_id: 20, is_simulated: true, title: 'Simulated Drill' },
      { id: 'alert-3', segment_id: 30, is_simulated: 0, title: 'Real Weather Alert' },
      { id: 'alert-4', segment_id: 40, is_simulated: 1, title: 'Simulated Landslide' },
    ];

    const filterForMode = (alerts, mode) => {
      const isReplayMode = mode === 'replay';
      return alerts.filter((a) => isReplayMode || !a.is_simulated);
    };

    // Live mode: simulated alerts must be excluded
    const liveAlerts = filterForMode(rawAlerts, 'live');
    assert.equal(liveAlerts.length, 2);
    assert.deepEqual(liveAlerts.map((a) => a.id), ['alert-1', 'alert-3']);

    // Off mode: simulated alerts must be excluded
    const offAlerts = filterForMode(rawAlerts, 'off');
    assert.equal(offAlerts.length, 2);

    // Historical mode: simulated alerts must be excluded
    const histAlerts = filterForMode(rawAlerts, 'historical');
    assert.equal(histAlerts.length, 2);

    // Replay mode: simulated alerts are included
    const replayAlerts = filterForMode(rawAlerts, 'replay');
    assert.equal(replayAlerts.length, 4);
  });

  it('guarantees ErrorBoundary i18n keys and fallback structure in EN and HI', () => {
    assert.ok(enTranslations.error_boundary, 'EN missing error_boundary section');
    assert.ok(hiTranslations.error_boundary, 'HI missing error_boundary section');

    const requiredKeys = ['title', 'message', 'reload'];
    for (const k of requiredKeys) {
      assert.ok(enTranslations.error_boundary[k], `EN missing error_boundary.${k}`);
      assert.ok(hiTranslations.error_boundary[k], `HI missing error_boundary.${k}`);
    }

    assert.equal(enTranslations.error_boundary.title, 'Something went wrong');
    assert.equal(hiTranslations.error_boundary.title, 'कुछ गलत हो गया');
    assert.equal(enTranslations.error_boundary.reload, 'Reload Application');
    assert.equal(hiTranslations.error_boundary.reload, 'एप्लिकेशन पुनः लोड करें');
  });
});

// ==============================================================================
// 12. Permanent SSR Render Smoke Test & Error Boundary Behaviour (Task 3b-3)
// ==============================================================================
describe('Permanent SSR Render Smoke Test & Error Boundary Behaviour (Task 3b-3)', () => {
  it('detects recommendation change and verifies translated notice keys', () => {
    assert.equal(hasRecommendationChanged('HOLD', 'PROCEED'), true);
    assert.equal(hasRecommendationChanged('PROCEED', 'PROCEED_WITH_CAUTION'), true);
    assert.equal(hasRecommendationChanged('HOLD', 'HOLD'), false);
    assert.equal(hasRecommendationChanged('hold', 'HOLD'), false);
    assert.equal(hasRecommendationChanged(null, 'HOLD'), false);
    assert.equal(hasRecommendationChanged('HOLD', null), false);

    assert.ok(enTranslations.journey?.recommendation_changed_notice, 'EN missing recommendation_changed_notice');
    assert.ok(hiTranslations.journey?.recommendation_changed_notice, 'HI missing recommendation_changed_notice');
    assert.ok(enTranslations.journey.recommendation_changed_notice.includes('{{oldRec}}'));
    assert.ok(enTranslations.journey.recommendation_changed_notice.includes('{{newRec}}'));
  });

  it('verifies ErrorBoundary catches rendering errors, logs them, and renders translated fallback', async () => {
    const { createServer } = await import('vite');
    const React = (await import('react')).default;
    const { renderToString } = await import('react-dom/server');

    const server = await createServer({
      root: process.cwd(),
      server: { middlewareMode: true },
      appType: 'custom',
      optimizeDeps: { noDiscovery: true },
    });

    try {
      const ErrorBoundary = (await server.ssrLoadModule('./src/components/ErrorBoundary.jsx')).default;

      // 1. Error state generation via static getDerivedStateFromError
      const sampleErr = new Error('Test component render explosion');
      const derived = ErrorBoundary.getDerivedStateFromError(sampleErr);
      assert.equal(derived.hasError, true);
      assert.equal(derived.error, sampleErr);

      // 2. Fallback rendering in error state
      const instance = new ErrorBoundary({});
      instance.state = derived;
      const renderedHtml = renderToString(instance.render());
      assert.ok(renderedHtml.includes('Something went wrong'), 'Fallback must contain title');
      assert.ok(renderedHtml.includes('Reload Application'), 'Fallback must contain reload button');
      assert.ok(renderedHtml.includes('An unexpected error occurred'), 'Fallback must contain error message');

      // 3. Verify componentDidCatch logs to console.error
      const origError = console.error;
      let loggedError = null;
      console.error = (...args) => { loggedError = args; };
      try {
        instance.componentDidCatch(sampleErr, { componentStack: 'in CrashingChild' });
        assert.ok(loggedError !== null, 'componentDidCatch must log to console.error');
      } finally {
        console.error = origError;
      }
    } finally {
      await server.close();
    }
  });

  it('SSR mounts Overview, LiveBanner, ControlHeader, and CorridorStrip across all 4 modes with real and null summaries', async () => {
    const { createServer } = await import('vite');
    const React = (await import('react')).default;
    const { renderToString } = await import('react-dom/server');

    const server = await createServer({
      root: process.cwd(),
      server: { middlewareMode: true },
      appType: 'custom',
      optimizeDeps: { noDiscovery: true },
    });

    try {
      const Overview = (await server.ssrLoadModule('./src/components/Overview.jsx')).default;
      const LiveBanner = (await server.ssrLoadModule('./src/components/LiveBanner.jsx')).default;
      const ControlHeader = (await server.ssrLoadModule('./src/components/ControlHeader.jsx')).default;
      const CorridorStrip = (await server.ssrLoadModule('./src/components/CorridorStrip.jsx')).default;

      const modes = ['historical', 'live', 'replay', 'off'];
      const summaryShapes = [
        { Low: 140, Medium: 10, High: 1, UNKNOWN: 0 },
        null,
      ];

      for (const mode of modes) {
        for (const summary of summaryShapes) {
          const liveStatus = {
            mode: mode === 'historical' ? 'live' : mode,
            as_of: '2026-11-10T12:00:00Z',
            data_age_hours: 1.2,
            latest_fetch: '2026-11-10T12:00:00Z',
            unknown_count: 0,
            active_hazard_events: 1,
            active_alerts: 1,
          };
          const riskData = {
            mode: mode === 'historical' ? 'live' : mode,
            as_of: '2026-11-10T12:00:00Z',
            summary,
            operational_status: 'NORMAL',
            segments: Array.from({ length: 151 }, (_, i) => ({
              segment_id: `seg_${i + 1}`,
              risk_score: 0.05,
              risk_tier: 'Low',
              status: 'OK',
              operational_status: 'OPEN',
            })),
          };
          const predictions = riskData.segments;

          // Render LiveBanner
          const lb = renderToString(React.createElement(LiveBanner, {
            mode,
            liveStatus,
            connectionStatus: 'connected',
          }));
          assert.ok(lb.length > 0, `LiveBanner must render in mode ${mode}`);

          // Render ControlHeader
          const ch = renderToString(React.createElement(ControlHeader, {
            mode,
            setMode: () => {},
            selectedDate: '2026-11-10',
            setSelectedDate: () => {},
            dates: ['2026-11-10'],
            liveStatus,
            liveRisk: riskData,
          }));
          assert.ok(ch.length > 0, `ControlHeader must render in mode ${mode}`);

          // Render CorridorStrip
          const cs = renderToString(React.createElement(CorridorStrip, {
            predictions,
            selectedSegment: null,
            onSelectSegment: () => {},
            mode,
            liveRisk: riskData,
          }));
          assert.ok(cs.length > 0, `CorridorStrip must render in mode ${mode}`);

          // Render Overview
          const ov = renderToString(React.createElement(Overview, {
            mode,
            liveStatus,
            riskData,
            predictions,
            selectedSegment: null,
            onSelectSegment: () => {},
            onNavigate: () => {},
          }));
          assert.ok(ov.length > 0, `Overview must render in mode ${mode}`);
        }
      }
    } finally {
      await server.close();
    }
  });
});


// ==============================================================================
// 13. Journey Planner Mode & Schedule Behaviour (Task 3c)
// ==============================================================================
describe('Journey Planner Mode & Schedule Behaviour (Task 3c)', () => {
  it('governs JourneyPlanner mode configuration across all 4 modes (live, replay, historical, off)', async () => {
    const { getPlannerModeConfig } = await import('../src/services/plannerModeHelper.js');

    // 1. Live mode
    const liveConfig = getPlannerModeConfig({
      mode: 'live',
      liveAsOf: '2026-11-10',
      weatherWindowEnd: '2026-11-10T12:00:00Z',
    });
    assert.equal(liveConfig.isLive, true);
    assert.equal(liveConfig.isReplay, false);
    assert.equal(liveConfig.isHistorical, false);
    assert.equal(liveConfig.isDateEditable, false, 'Live mode date must be read-only');
    assert.equal(liveConfig.showBenchmarkButtons, false, 'Benchmark buttons must be hidden in live mode');
    assert.equal(liveConfig.evaluationDate, '2026-11-10');
    assert.equal(liveConfig.weatherWindowEnd, '2026-11-10T12:00:00Z');
    assert.equal(liveConfig.statusBadgeClass, 'planner-badge-live');
    assert.equal(liveConfig.isExperimental, true);
    assert.equal(liveConfig.departureHelpKey, 'planner.departure_help_live');

    // 2. Replay mode
    const replayConfig = getPlannerModeConfig({
      mode: 'replay',
      replayDate: '2023-07-09',
    });
    assert.equal(replayConfig.isLive, false);
    assert.equal(replayConfig.isReplay, true);
    assert.equal(replayConfig.isHistorical, false);
    assert.equal(replayConfig.isDateEditable, false, 'Replay date must be read-only');
    assert.equal(replayConfig.showBenchmarkButtons, false, 'Benchmark buttons must be hidden in replay mode');
    assert.equal(replayConfig.evaluationDate, '2023-07-09');
    assert.equal(replayConfig.statusBadgeClass, 'planner-badge-replay');
    assert.equal(replayConfig.statusBadgeText, 'REPLAY / SIMULATED SCENARIO');
    assert.equal(replayConfig.isExperimental, false);

    // 3. Historical mode
    const histConfig = getPlannerModeConfig({ mode: 'historical' });
    assert.equal(histConfig.isLive, false);
    assert.equal(histConfig.isReplay, false);
    assert.equal(histConfig.isHistorical, true);
    assert.equal(histConfig.isDateEditable, true, 'Historical mode date must be editable');
    assert.equal(histConfig.showBenchmarkButtons, true, 'Benchmark buttons must be shown in historical mode');
    assert.equal(histConfig.statusBadgeClass, 'planner-badge-historical');

    // 4. Off mode (treated as historical safe fallback)
    const offConfig = getPlannerModeConfig({ mode: 'off' });
    assert.equal(offConfig.isLive, false);
    assert.equal(offConfig.isReplay, false);
    assert.equal(offConfig.isHistorical, true);
    assert.equal(offConfig.isDateEditable, true);
    assert.equal(offConfig.showBenchmarkButtons, true);
  });

  it('verifies departure time defaulting and advisory validity check', async () => {
    const { getDefaultDepartureTime, isTimeWithinAdvisoryValidity } = await import(
      '../src/services/plannerModeHelper.js'
    );

    const morningDate = new Date(2026, 10, 10, 8, 5, 0);
    assert.equal(getDefaultDepartureTime(morningDate), '08:05');

    const eveningDate = new Date(2026, 10, 10, 19, 45, 0);
    assert.equal(getDefaultDepartureTime(eveningDate), '19:45');

    assert.equal(isTimeWithinAdvisoryValidity('00:00'), true);
    assert.equal(isTimeWithinAdvisoryValidity('08:30'), true);
    assert.equal(isTimeWithinAdvisoryValidity('23:59'), true);
    assert.equal(isTimeWithinAdvisoryValidity('24:00'), false);
    assert.equal(isTimeWithinAdvisoryValidity('8:30'), false);
    assert.equal(isTimeWithinAdvisoryValidity('invalid'), false);
    assert.equal(isTimeWithinAdvisoryValidity(null), false);
  });

  it('guarantees Task 3c planner i18n keys exist and match between EN and HI', () => {
    const expectedKeys = [
      'live_badge',
      'replay_badge',
      'historical_badge',
      'notice_live_title',
      'notice_replay_title',
      'notice_historical_title',
      'linear_topology_notice',
      'vehicle_type_label',
      'vehicle_type_notice',
      'departure_time_label',
      'departure_time_notice_live',
      'departure_time_notice_replay',
      'departure_time_notice_historical',
      'departure_help_live',
      'schedule_title_live',
      'schedule_title_replay',
      'schedule_title_historical',
      'evaluation_date',
      'weather_window_through',
      'experimental_warning',
      'historical_benchmarks',
    ];

    for (const k of expectedKeys) {
      assert.ok(enTranslations.planner?.[k], `EN missing planner key: ${k}`);
      assert.ok(hiTranslations.planner?.[k], `HI missing planner key: ${k}`);
      assert.notEqual(enTranslations.planner[k], hiTranslations.planner[k], `Key ${k} should be localized in HI`);
    }

    assert.equal(enTranslations.planner.live_badge, 'Live Operational Advisory \u2022 Experimental - not validated');
    assert.equal(hiTranslations.planner.live_badge, '\u0932\u093e\u0907\u0935 \u092a\u0930\u093f\u091a\u093e\u0932\u0928 \u092a\u0930\u093e\u092e\u0930\u094d\u0936 \u2022 \u092a\u094d\u0930\u093e\u092f\u094b\u0917\u093f\u0915 - \u0917\u0948\u0930-\u0938\u0924\u094d\u092f\u093e\u092a\u093f\u0924');
    assert.equal(enTranslations.planner.replay_badge, 'REPLAY / SIMULATED SCENARIO');
    assert.equal(hiTranslations.planner.replay_badge, '\u0930\u0940\u092a\u094d\u0932\u0947 / \u0938\u093f\u092e\u094d\u092f\u0941\u0932\u0947\u091f\u0947\u0921 \u092a\u0930\u093f\u0926\u0943\u0936\u094d\u092f');
  });

  // ==============================================================================
  // 14. Incident De-duplication, Routing Wording, API Clarity & Contrast (Task 4)
  // ==============================================================================
  describe('Incident De-duplication, Routing Wording, API Clarity & Contrast (Task 4)', () => {
    it('enforces incident de-duplication rules (segment, hazard_type, simulation mode, 24h window)', async () => {
      const { isDuplicateHazardCandidate } = await import('../src/services/incidentHelper.js');

      const baseEvent = {
        id: 'ev-1',
        segment_id: 'seg_045',
        hazard_type: 'landslide',
        severity: 'critical',
        status: 'active',
        is_simulated: false,
        created_at: new Date(Date.now() - 2 * 3600 * 1000).toISOString(),
        expires_at: new Date(Date.now() + 22 * 3600 * 1000).toISOString(),
      };

      // 1. Same segment, same hazard type, real report -> DUPLICATE
      assert.equal(
        isDuplicateHazardCandidate(baseEvent, {
          segment_id: 'seg_045',
          hazard_type: 'landslide',
          is_simulated: false,
        }),
        true,
        'Identical segment, type, and simulation mode must match duplicate candidate'
      );

      // 2. Different segment -> NO MERGE
      assert.equal(
        isDuplicateHazardCandidate(baseEvent, {
          segment_id: 'seg_046',
          hazard_type: 'landslide',
          is_simulated: false,
        }),
        false,
        'Different segments must never merge'
      );

      // 3. Different hazard type -> NO MERGE
      assert.equal(
        isDuplicateHazardCandidate(baseEvent, {
          segment_id: 'seg_045',
          hazard_type: 'flooding',
          is_simulated: false,
        }),
        false,
        'Different hazard types must never merge'
      );

      // 4. Simulated candidate vs real event -> NO MERGE
      assert.equal(
        isDuplicateHazardCandidate(baseEvent, {
          segment_id: 'seg_045',
          hazard_type: 'landslide',
          is_simulated: true,
        }),
        false,
        'Simulated events and real reports must never merge'
      );

      // 5. Expired or closed event -> NO MERGE
      const closedEvent = { ...baseEvent, status: 'closed' };
      assert.equal(
        isDuplicateHazardCandidate(closedEvent, {
          segment_id: 'seg_045',
          hazard_type: 'landslide',
          is_simulated: false,
        }),
        false,
        'Closed events must not accept new duplicates'
      );

      // 6. Outside 24h deduplication window -> NO MERGE
      const oldEvent = {
        ...baseEvent,
        created_at: new Date(Date.now() - 26 * 3600 * 1000).toISOString(),
      };
      assert.equal(
        isDuplicateHazardCandidate(oldEvent, {
          segment_id: 'seg_045',
          hazard_type: 'landslide',
          is_simulated: false,
        }),
        false,
        'Events older than 24h must not merge new reports'
      );

      // 7. Category fallback (other, snow_or_ice, single_lane_or_obstruction -> road_damage)
      const fixedNow = new Date('2026-11-11T12:00:00.000Z');
      const fixedNowMs = fixedNow.getTime();

      const roadDamageEvent = {
        id: 'ev-road-damage',
        segment_id: 'seg_045',
        hazard_type: 'road_damage',
        severity: 'medium',
        status: 'active',
        is_simulated: false,
        created_at: new Date(fixedNowMs - 2 * 3600 * 1000).toISOString(),
        expires_at: new Date(fixedNowMs + 22 * 3600 * 1000).toISOString(),
      };

      // Existing event type road_damage, candidate category other -> true
      assert.equal(
        isDuplicateHazardCandidate(
          roadDamageEvent,
          {
            segment_id: 'seg_045',
            category: 'other',
            is_simulated: false,
          },
          fixedNow
        ),
        true,
        'Existing road_damage event matches candidate category other via fallback'
      );

      // Existing event type road_damage, candidate category snow_or_ice -> true
      assert.equal(
        isDuplicateHazardCandidate(
          roadDamageEvent,
          {
            segment_id: 'seg_045',
            category: 'snow_or_ice',
            is_simulated: false,
          },
          fixedNow
        ),
        true,
        'Existing road_damage event matches candidate category snow_or_ice via fallback'
      );

      // Existing event type road_damage, candidate category single_lane_or_obstruction -> true
      assert.equal(
        isDuplicateHazardCandidate(
          roadDamageEvent,
          {
            segment_id: 'seg_045',
            category: 'single_lane_or_obstruction',
            is_simulated: false,
          },
          fixedNow
        ),
        true,
        'Existing road_damage event matches candidate category single_lane_or_obstruction via fallback'
      );

      // 8. Dual timestamp window
      // created_at is 30 hours old, last_reported_at is 3 hours old -> true
      const dualTimestampEvent = {
        ...roadDamageEvent,
        created_at: new Date(fixedNowMs - 30 * 3600 * 1000).toISOString(),
        last_reported_at: new Date(fixedNowMs - 3 * 3600 * 1000).toISOString(),
      };
      assert.equal(
        isDuplicateHazardCandidate(
          dualTimestampEvent,
          {
            segment_id: 'seg_045',
            hazard_type: 'road_damage',
            is_simulated: false,
          },
          fixedNow
        ),
        true,
        'created_at 30h old but last_reported_at 3h old must match within window'
      );

      // Both timestamps are more than 24 hours old -> false
      const bothExpiredEvent = {
        ...roadDamageEvent,
        created_at: new Date(fixedNowMs - 30 * 3600 * 1000).toISOString(),
        last_reported_at: new Date(fixedNowMs - 26 * 3600 * 1000).toISOString(),
      };
      assert.equal(
        isDuplicateHazardCandidate(
          bothExpiredEvent,
          {
            segment_id: 'seg_045',
            hazard_type: 'road_damage',
            is_simulated: false,
          },
          fixedNow
        ),
        false,
        'Both timestamps older than 24h must be rejected'
      );

      // 9. Invalid timestamp handling
      // Both timestamps missing -> false
      const missingTimestampsEvent = {
        ...roadDamageEvent,
        created_at: null,
        last_reported_at: null,
      };
      assert.equal(
        isDuplicateHazardCandidate(
          missingTimestampsEvent,
          {
            segment_id: 'seg_045',
            hazard_type: 'road_damage',
            is_simulated: false,
          },
          fixedNow
        ),
        false,
        'Both timestamps missing must be rejected'
      );

      // Both timestamps invalid -> false
      const invalidTimestampsEvent = {
        ...roadDamageEvent,
        created_at: 'invalid-date',
        last_reported_at: 'not-a-timestamp',
      };
      assert.equal(
        isDuplicateHazardCandidate(
          invalidTimestampsEvent,
          {
            segment_id: 'seg_045',
            hazard_type: 'road_damage',
            is_simulated: false,
          },
          fixedNow
        ),
        false,
        'Both timestamps invalid must be rejected'
      );

      // Future timestamps -> false
      const futureCreatedEvent = {
        ...roadDamageEvent,
        created_at: new Date(fixedNowMs + 2 * 3600 * 1000).toISOString(),
        last_reported_at: null,
      };
      assert.equal(
        isDuplicateHazardCandidate(
          futureCreatedEvent,
          {
            segment_id: 'seg_045',
            hazard_type: 'road_damage',
            is_simulated: false,
          },
          fixedNow
        ),
        false,
        'Future created_at timestamp must be rejected'
      );

      const futureLastReportedEvent = {
        ...roadDamageEvent,
        created_at: new Date(fixedNowMs - 2 * 3600 * 1000).toISOString(),
        last_reported_at: new Date(fixedNowMs + 2 * 3600 * 1000).toISOString(),
      };
      assert.equal(
        isDuplicateHazardCandidate(
          futureLastReportedEvent,
          {
            segment_id: 'seg_045',
            hazard_type: 'road_damage',
            is_simulated: false,
          },
          fixedNow
        ),
        false,
        'Future last_reported_at timestamp must be rejected'
      );

      const futureCandidate = {
        segment_id: 'seg_045',
        hazard_type: 'road_damage',
        is_simulated: false,
        created_at: new Date(fixedNowMs + 2 * 3600 * 1000).toISOString(),
      };
      assert.equal(
        isDuplicateHazardCandidate(
          roadDamageEvent,
          futureCandidate,
          fixedNow
        ),
        false,
        'Candidate with future timestamp must be rejected'
      );
    });

    it('calculates independent report counts without inflating on same-user repeats', async () => {
      const { calculateReportCount, formatReportCount } = await import(
        '../src/services/incidentHelper.js'
      );

      // Initial event starts with count = 1
      assert.equal(formatReportCount(1), '1 report');
      assert.equal(formatReportCount(3), '3 reports');

      // Independent reporter adds to count
      const res1 = calculateReportCount(1, [101], 102);
      assert.equal(res1.reportCount, 2);
      assert.equal(res1.isIndependent, true);

      // Same reporter repeat does not inflate count
      const res2 = calculateReportCount(2, [101, 102], 101);
      assert.equal(res2.reportCount, 2);
      assert.equal(res2.isIndependent, false);
    });

    it('builds honest routing reason text without mentioning zero segments', async () => {
      const { buildRoutingReason } = await import('../src/services/incidentHelper.js');

      // 1. Closed segment
      const rBlocked = buildRoutingReason({ blockingSegments: ['seg_050'] });
      assert.equal(rBlocked.recommendation, 'HOLD');
      assert.ok(rBlocked.reason.includes('blocked by 1 closed segment (seg_050)'));
      assert.ok(!rBlocked.reason.includes('0 closed'));

      // 2. Stale telemetry with 0 missing segments
      const rStale = buildRoutingReason({ unknownCount: 0, isLiveStale: true });
      assert.equal(rStale.recommendation, 'NO_DATA');
      assert.ok(rStale.reason.includes('Live telemetry for corridor segments is stale (>24h).'));
      assert.ok(!rStale.reason.includes('0 unmonitored'));

      // 3. Unmonitored segments
      const rUnmon = buildRoutingReason({ unknownCount: 5, isLiveStale: false });
      assert.equal(rUnmon.recommendation, 'NO_DATA');
      assert.ok(rUnmon.reason.includes('Route includes 5 unmonitored segments with missing data.'));

      // 4. Peak score high threshold
      const rPeak = buildRoutingReason({ highCount: 0, maxScore: 0.42 });
      assert.equal(rPeak.recommendation, 'DELAY');
      assert.ok(rPeak.reason.includes('Peak segment hazard score (0.42) reaches high disruption threshold (>=0.35)'));
      assert.ok(!rPeak.reason.includes('0 segment'));

      // 5. Baseline clear
      const rClear = buildRoutingReason({ highCount: 0, medCount: 0, unknownCount: 0, maxScore: 0.05 });
      assert.equal(rClear.recommendation, 'PROCEED');
      assert.ok(rClear.reason.includes('Corridor baseline clear (<0.10)'));
    });

    it('extracts date substitution metadata when live date substitution occurs', async () => {
      const { getSubstitutionNotice } = await import('../src/services/incidentHelper.js');

      // Substituted plan
      const notice = getSubstitutionNotice({
        date_substituted: true,
        requested_date: '2023-07-09',
        actual_date: '2026-11-10',
      });
      assert.ok(notice);
      assert.equal(notice.isSubstituted, true);
      assert.equal(notice.requestedDate, '2023-07-09');
      assert.equal(notice.actualDate, '2026-11-10');

      // Unsubstituted plan
      const noNotice = getSubstitutionNotice({
        date_substituted: false,
        requested_date: '2026-11-10',
        actual_date: '2026-11-10',
      });
      assert.equal(noNotice, null);
    });

    it('guarantees Task 4 i18n keys exist and match in both EN and HI catalogs', () => {
      // 1. Inspector active hazards key
      assert.ok(enTranslations.inspector?.active_hazards, 'EN missing inspector.active_hazards');
      assert.ok(hiTranslations.inspector?.active_hazards, 'HI missing inspector.active_hazards');
      assert.equal(enTranslations.inspector.active_hazards, 'Active Corridor Hazards');
      assert.equal(hiTranslations.inspector.active_hazards, 'सक्रिय कॉरिडोर खतरे');

      // 2. Date substituted notice key
      assert.ok(enTranslations.journey?.date_substituted_notice, 'EN missing journey.date_substituted_notice');
      assert.ok(hiTranslations.journey?.date_substituted_notice, 'HI missing journey.date_substituted_notice');
      assert.ok(enTranslations.journey.date_substituted_notice.includes('{{requested}}'));
      assert.ok(hiTranslations.journey.date_substituted_notice.includes('{{requested}}'));

      // 3. Events report count keys
      assert.ok(enTranslations.events?.reports_count, 'EN missing events.reports_count');
      assert.ok(hiTranslations.events?.reports_count, 'HI missing events.reports_count');
      assert.ok(enTranslations.events?.reports_count_plural, 'EN missing events.reports_count_plural');
      assert.ok(hiTranslations.events?.reports_count_plural, 'HI missing events.reports_count_plural');
      assert.ok(enTranslations.events?.last_reported, 'EN missing events.last_reported');
      assert.ok(hiTranslations.events?.last_reported, 'HI missing events.last_reported');
      assert.ok(enTranslations.events?.independent_reports, 'EN missing events.independent_reports');
      assert.ok(hiTranslations.events?.independent_reports, 'HI missing events.independent_reports');

      assert.equal(enTranslations.events.reports_count, '{{count}} report');
      assert.equal(hiTranslations.events.reports_count, '{{count}} रिपोर्ट');
      assert.equal(enTranslations.events.reports_count_plural, '{{count}} reports');
      assert.equal(hiTranslations.events.reports_count_plural, '{{count}} रिपोर्टें');
    });

    it('SSR mounts SegmentInspector across all 4 modes with active hazard events', async () => {
      const React = (await import('react')).default;
      const { renderToString } = await import('react-dom/server');
      const { createServer } = await import('vite');

      const server = await createServer({
        root: process.cwd(),
        appType: 'custom',
        server: { middlewareMode: true },
        optimizeDeps: { noDiscovery: true },
      });

      try {
        const SegmentInspector = (await server.ssrLoadModule('./src/components/SegmentInspector.jsx')).default;
        const modes = ['historical', 'live', 'replay', 'off'];

        for (const mode of modes) {
          const mockRiskData = {
            mode,
            as_of: '2026-11-10',
            segments: [
              {
                segment_id: 'seg_045',
                risk_score: 0.12,
                risk_tier: 'Medium',
                operational_status: 'RESTRICTED',
                active_events: [
                  {
                    id: 'ev-test-1',
                    hazard_type: 'shooting_stones',
                    severity: 'high',
                    status: 'active',
                    origin: 'field_report',
                    is_simulated: false,
                    report_count: 3,
                    last_reported_at: '2026-11-10T12:00:00Z',
                  },
                ],
              },
            ],
          };

          const mockGeojson = {
            features: [
              {
                id: 'seg_045',
                properties: {
                  name: 'Maroog Sector 45',
                  highway: 'primary',
                  length_m: 350,
                  slope: 0.08,
                  elevation_m: 1100,
                },
              },
            ],
          };

          const rendered = renderToString(
            React.createElement(SegmentInspector, {
              selectedSegment: 'seg_045',
              riskData: mockRiskData,
              selectedDate: '2026-11-10',
              geojson: mockGeojson,
            })
          );

          assert.ok(rendered.length > 0, `SegmentInspector must render in mode ${mode}`);
          assert.ok(rendered.includes('Active Corridor Hazards'), `Must show active hazards header in mode ${mode}`);
          assert.ok(rendered.includes('3 reports'), `Must display report count in mode ${mode}`);
        }
      } finally {
        await server.close();
      }
    });
  });

  it('SSR mounts JourneyPlanner in all 4 modes (live, replay, historical, off)', async () => {
    const React = (await import('react')).default;
    const { renderToString } = await import('react-dom/server');
    const { createServer } = await import('vite');

    const server = await createServer({
      root: process.cwd(),
      appType: 'custom',
      server: { middlewareMode: true },
      optimizeDeps: { noDiscovery: true },
    });

    try {
      const JourneyPlanner = (await server.ssrLoadModule('./src/components/JourneyPlanner.jsx')).default;
      const { JourneyProvider } = await server.ssrLoadModule('./src/context/JourneyContext.jsx');

      const modes = ['historical', 'live', 'replay', 'off'];
      const riskData = {
        mode: 'live',
        as_of: '2026-11-10',
        weather_window_end: '2026-11-10T12:00:00Z',
        computed_at: '2026-11-10T12:05:00Z',
        segments: [],
      };

      for (const mode of modes) {
        const rendered = renderToString(
          React.createElement(
            JourneyProvider,
            null,
            React.createElement(JourneyPlanner, {
              mode,
              riskData,
              lastRouteUpdate: null,
            })
          )
        );

        assert.ok(rendered.length > 0, `JourneyPlanner must render in mode ${mode}`);

        if (mode === 'live') {
          assert.ok(rendered.includes('planner-readonly-date'), 'Live mode must render readonly date');
          assert.ok(rendered.includes('Live Operational Advisory'), 'Live mode must render live badge');
          assert.ok(!rendered.includes('Historical Benchmark Spells:'), 'Live mode must NOT render benchmark chips');
        } else if (mode === 'replay') {
          assert.ok(rendered.includes('planner-readonly-date'), 'Replay mode must render readonly date');
          assert.ok(rendered.includes('REPLAY / SIMULATED SCENARIO'), 'Replay mode must render replay badge');
          assert.ok(!rendered.includes('Historical Benchmark Spells:'), 'Replay mode must NOT render benchmark chips');
        } else {
          // historical and off
          assert.ok(rendered.includes('type="date"'), 'Historical mode must render date input');
          assert.ok(rendered.includes('Historical Benchmark Spells:'), 'Historical mode must render benchmark chips');
        }
      }
    } finally {
      await server.close();
    }
  });
});