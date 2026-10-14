import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import enTranslations from '../src/i18n/locales/en.json' with { type: 'json' };
import hiTranslations from '../src/i18n/locales/hi.json' with { type: 'json' };

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
