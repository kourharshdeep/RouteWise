import React, { useState, useEffect } from "react";
import {
  BrowserRouter,
  Routes,
  Route,
  Navigate,
  useNavigate,
  useLocation,
  Outlet,
} from "react-router-dom";
import "./App.css";
import { AuthProvider, useAuth } from "./context/AuthContext";
import { JourneyProvider } from "./context/JourneyContext";
import {
  fetchHealth,
  fetchAvailableDates,
  fetchCorridorSegments,
  fetchCorridorRisk,
  fetchLiveStatus,
  fetchLiveRisk,
  getLiveStreamUrl,
  fetchActiveAlerts,
  fetchActiveEvents,
} from "./services/api";
import { resolveEffectiveMode, getEffectiveDate } from "./services/liveModeHelper";
import {
  ConnectionStateMachine,
  reconcileAlerts,
  reconcileHazardEvents,
  RESILIENCE_CONFIG,
} from "./services/connectionResilience";

import Navigation from "./components/Navigation";
import Overview from "./components/Overview";
import JourneyPlanner from "./components/JourneyPlanner";
import ControlHeader from "./components/ControlHeader";
import CorridorMap from "./components/CorridorMap";
import RiskSummaryCard from "./components/RiskSummaryCard";
import SegmentInspector from "./components/SegmentInspector";
import ChatAssistant from "./components/ChatAssistant";
import HistoricalLog from "./components/HistoricalLog";
import SettingsView from "./components/SettingsView";
import WelcomeView from "./components/WelcomeView";
import SignInView from "./components/SignInView";
import SignUpView from "./components/SignUpView";
import IncidentReporter from "./components/IncidentReporter";
import AlertDrawer from "./components/AlertDrawer";
import ErrorBoundary from "./components/ErrorBoundary";
import PatrolDashboard from "./components/PatrolDashboard";
import ProtectedRoute from "./components/ProtectedRoute";

import { AlertCircle, RefreshCw } from "lucide-react";

/**
 * Dashboard Shell Layout for all authenticated application routes
 */
function DashboardLayout({
  theme,
  setTheme,
  health,
  availableDates,
  geojson,
  selectedDate,
  setSelectedDate,
  riskData,
  setRiskData,
  selectedSegment,
  setSelectedSegment,
  isLoading,
  setIsLoading,
  error,
  setError,
  dashboardMode,
  setDashboardMode,
  liveStatus,
  connectionStatus,
  lastSuccessfulUpdate,
  onRefreshLive,
  isLiveUpdated,
  lastRouteUpdate,
  alerts,
  isAlertDrawerOpen,
  setIsAlertDrawerOpen,
  refreshAlerts,
  onScenarioStepped,
}) {
  const navigate = useNavigate();
  const location = useLocation();

  // Handle date change on Map view
  const handleDateChange = async (newDate) => {
    if (!newDate || newDate === selectedDate) return;
    try {
      setIsLoading(true);
      setError(null);
      setSelectedDate(newDate);

      const riskRes = await fetchCorridorRisk(newDate);
      setRiskData(riskRes);
    } catch (err) {
      console.error("Failed to load risk for date:", newDate, err);
      setError(`Failed to retrieve risk forecast for ${newDate}: ${err.message}`);
    } finally {
      setIsLoading(false);
    }
  };

  const handleRetry = () => {
    window.location.reload();
  };

  const handleSelectSegment = (segOrId) => {
    if (!segOrId) {
      setSelectedSegment(null);
      return;
    }
    if (typeof segOrId === "string") {
      const feat = geojson?.features?.find((f) => f.id === segOrId);
      if (feat) {
        setSelectedSegment(feat);
      } else {
        setSelectedSegment({ id: segOrId, properties: {} });
      }
    } else {
      setSelectedSegment(segOrId);
    }
  };

  // Derive active tab from pathname
  const currentPath = location.pathname.replace(/^\//, "") || "overview";
  const isReplayMode = dashboardMode === "replay" || (dashboardMode === "live" && liveStatus?.mode === "replay");
  const visibleAlerts = (alerts || []).filter((a) => isReplayMode || !a.is_simulated);

  return (
    <div className="app-layout">
      {/* Sidebar Navigation */}
      <Navigation
        theme={theme}
        setTheme={setTheme}
        health={health}
        activeAlertCount={visibleAlerts.length}
        onOpenAlerts={() => setIsAlertDrawerOpen(true)}
      />

      {/* Main Content Area */}
      <div className="app-main-content">
        {/* Mobile Header Bar */}
        <header className="mobile-top-bar">
          <div className="mobile-brand">
            <div className="brand-icon" style={{ width: 30, height: 30, fontSize: 14 }}>
              RW
            </div>
            <span style={{ fontWeight: 700, fontSize: 16 }}>RouteWise</span>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <span
              className="badge badge-pill"
              style={{ textTransform: "capitalize", fontSize: 11 }}
            >
              {currentPath}
            </span>
          </div>
        </header>

        {/* Global Connection / System Error Alert */}
        {error && (
          <div className="state-box state-error" style={{ margin: "16px 24px" }}>
            <AlertCircle size={24} />
            <div>
              <strong>Service Notice:</strong> {error}
            </div>
            <button
              type="button"
              className="sample-btn"
              onClick={handleRetry}
              style={{ marginTop: 8 }}
            >
              <RefreshCw
                size={13}
                style={{ display: "inline", marginRight: 4 }}
              />
              Retry Connection
            </button>
          </div>
        )}

        {/* Global Initial Loading State */}
        {isLoading && !riskData && (
          <div className="state-box state-loading" style={{ margin: "40px auto" }}>
            <RefreshCw
              size={32}
              className="spin-icon"
              style={{ animation: "spin 1s linear infinite" }}
            />
            <span style={{ fontSize: 15, fontWeight: 500 }}>
              Retrieving RouteWise corridor topology and ST-GNN risk forecasts...
            </span>
          </div>
        )}

        {/* View Switcher / Outlet Container */}
        <div className="view-container">
          <Routes>
            <Route
              path="overview"
              element={
                <Overview
                  health={health}
                  riskData={riskData}
                  selectedDate={selectedDate}
                  selectedSegment={selectedSegment}
                  onSelectSegment={handleSelectSegment}
                  geojson={geojson}
                  onNavigate={(tab) => navigate(`/${tab}`)}
                  mode={dashboardMode}
                  onModeChange={setDashboardMode}
                  liveStatus={liveStatus}
                  connectionStatus={connectionStatus}
                  lastSuccessfulUpdate={lastSuccessfulUpdate}
                  onRefreshLive={onRefreshLive}
                  isLiveUpdated={isLiveUpdated}
                  onScenarioStepped={onScenarioStepped}
                />
              }
            />
            <Route
              path="journey"
              element={
                <JourneyPlanner
                  onNavigateToMap={() => navigate("/map")}
                  mode={dashboardMode}
                  lastRouteUpdate={lastRouteUpdate}
                  riskData={riskData}
                />
              }
            />
            <Route
              path="map"
              element={
                <div className="map-view-layout">
                  <ControlHeader
                    health={health}
                    selectedDate={selectedDate}
                    onDateChange={handleDateChange}
                    availableDates={availableDates}
                    isLoading={isLoading}
                    mode={dashboardMode}
                    onModeChange={setDashboardMode}
                    liveStatus={liveStatus}
                    connectionStatus={connectionStatus}
                    lastSuccessfulUpdate={lastSuccessfulUpdate}
                    onRefreshLive={onRefreshLive}
                  />

                  <div className="main-grid" style={{ marginTop: 16 }}>
                    <CorridorMap
                      geojson={geojson}
                      riskData={riskData}
                      selectedDate={selectedDate}
                      onSelectSegment={handleSelectSegment}
                      selectedSegmentId={selectedSegment?.id}
                      theme={theme}
                      mode={dashboardMode}
                      isLiveUpdated={isLiveUpdated}
                    />

                    <div className="sidebar">
                      <RiskSummaryCard
                        summary={riskData?.summary}
                        metadata={riskData?.metadata}
                      />

                      <SegmentInspector
                        selectedSegment={selectedSegment}
                        riskData={riskData}
                        selectedDate={selectedDate}
                        geojson={geojson}
                      />
                    </div>
                  </div>
                </div>
              }
            />
            <Route
              path="reports"
              element={<IncidentReporter onNavigateToSignIn={() => navigate("/auth/signin")} />}
            />
            <Route path="patrol" element={<PatrolDashboard />} />
            <Route path="chat" element={<ChatAssistant />} />
            <Route path="history" element={<HistoricalLog />} />
            <Route
              path="settings"
              element={<SettingsView theme={theme} setTheme={setTheme} />}
            />
            <Route path="*" element={<Navigate to="/overview" replace />} />
          </Routes>
        </div>
      </div>

      {/* Corridor Alert Drawer (Step 7) */}
      <AlertDrawer
        isOpen={isAlertDrawerOpen}
        onClose={() => setIsAlertDrawerOpen(false)}
        alerts={visibleAlerts}
        onAlertUpdated={refreshAlerts}
      />
    </div>
  );
}

/**
 * Route Guard for Unauthenticated Flow:
 * If authenticated user lands on / or /auth/*, redirect to /overview.
 */
function PublicOnlyRoute({ children }) {
  const { isAuthenticated, isLoading } = useAuth();
  const location = useLocation();

  if (isLoading) {
    return (
      <div className="state-box state-loading" style={{ margin: "80px auto", minHeight: "60vh" }}>
        <RefreshCw
          size={32}
          className="spin-icon"
          style={{ animation: "spin 1s linear infinite" }}
        />
        <span style={{ fontSize: 15, fontWeight: 500, color: "var(--text-muted)" }}>
          Checking RouteWise session...
        </span>
      </div>
    );
  }

  if (isAuthenticated) {
    const destination = location.state?.from || "/overview";
    return <Navigate to={destination} replace />;
  }

  return children;
}

function AppContent() {
  const [theme, setTheme] = useState(
    () => localStorage.getItem("routewise-theme") || "dark"
  );

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    document.body.setAttribute("data-theme", theme);
    localStorage.setItem("routewise-theme", theme);
  }, [theme]);

  // Core Corridor Data states (Preserved from existing application)
  const [health, setHealth] = useState(null);
  const [availableDates, setAvailableDates] = useState(null);
  const [geojson, setGeojson] = useState(null);
  const [selectedDate, setSelectedDate] = useState("2023-07-09");
  const [riskData, setRiskData] = useState(null);
  const [selectedSegment, setSelectedSegment] = useState(null);

  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);

  // Real-Time Intelligence & Connection Resilience States
  const [dashboardMode, setDashboardMode] = useState("historical"); // 'historical' | 'live'
  const [liveStatus, setLiveStatus] = useState(null);
  const [connectionStatus, setConnectionStatus] = useState("connected"); // 'connected' | 'reconnecting' | 'polling' | 'offline'
  const [lastSuccessfulUpdate, setLastSuccessfulUpdate] = useState(null);
  const [isLiveUpdated, setIsLiveUpdated] = useState(false);
  const [lastRouteUpdate, setLastRouteUpdate] = useState(null);
  const [alerts, setAlerts] = useState([]);
  const [isAlertDrawerOpen, setIsAlertDrawerOpen] = useState(false);

  const refreshAlerts = async () => {
    try {
      const res = await fetchActiveAlerts();
      setAlerts((prev) => reconcileAlerts(prev, res.alerts || []));
    } catch (err) {
      console.debug("Failed to refresh active alerts:", err);
    }
  };

  useEffect(() => {
    refreshAlerts();
  }, []);

  // Mode change handler
  const handleModeChange = async (newMode) => {
    if (newMode === dashboardMode) return;
    setDashboardMode(newMode);
    if (newMode === "historical") {
      try {
        setIsLoading(true);
        const histRisk = await fetchCorridorRisk(selectedDate);
        setRiskData(histRisk);
      } catch (err) {
        console.error("Failed to restore historical risk:", err);
      } finally {
        setIsLoading(false);
      }
    } else if (newMode === "live") {
      try {
        setIsLoading(true);
        const [statusRes, riskRes] = await Promise.all([
          fetchLiveStatus().catch(() => null),
          fetchLiveRisk().catch((err) => {
            console.warn("Live risk fetch failed:", err);
            return null;
          }),
        ]);
        if (statusRes) setLiveStatus(statusRes);
        if (riskRes) {
          setRiskData(riskRes);
        } else if (statusRes?.mode === "off") {
          setRiskData({
            as_of: null,
            computed_at: null,
            experimental: false,
            disclaimer: "Live mode not enabled",
            summary: { Low: 0, Medium: 0, High: 0, UNKNOWN: 151 },
            operational_summary: { OPEN: 0, CAUTION: 0, RESTRICTED: 0, CLOSED: 0, UNKNOWN: 151 },
            segments: [],
          });
        }
      } catch (err) {
        console.error("Failed to load live data on mode switch:", err);
      } finally {
        setIsLoading(false);
      }
    }
  };

  const handleScenarioStepped = async () => {
    try {
      setIsLoading(true);
      const [statusRes, riskRes, alertRes] = await Promise.all([
        fetchLiveStatus(),
        fetchLiveRisk(),
        fetchActiveAlerts(),
      ]);
      setLiveStatus(statusRes);
      setRiskData(riskRes);
      setAlerts(alertRes.alerts || []);
      setIsLiveUpdated(true);
      setTimeout(() => setIsLiveUpdated(false), 1400);
    } catch (err) {
      console.error("Failed to sync scenario state:", err);
    } finally {
      setIsLoading(false);
    }
  };

  const handleRefreshLive = async () => {
    try {
      setIsLoading(true);
      const [statusRes, riskRes] = await Promise.all([
        fetchLiveStatus(),
        fetchLiveRisk(),
      ]);
      setLiveStatus(statusRes);
      setRiskData(riskRes);
      setIsLiveUpdated(true);
      setTimeout(() => setIsLiveUpdated(false), 1400);
    } catch (err) {
      console.error("Failed to refresh live telemetry:", err);
    } finally {
      setIsLoading(false);
    }
  };

  // Real-Time Intelligence & SSE Stream / Reconnection / Polling Management
  useEffect(() => {
    if (dashboardMode !== "live") return;

    let isMounted = true;
    let pollTimer = null;
    let reconnectTimer = null;
    let sseProbeTimer = null;
    let es = null;

    const stateMachine = new ConnectionStateMachine({
      onStateChange: (newState) => {
        if (isMounted) setConnectionStatus(newState);
      },
    });

    const reconcileAll = async () => {
      if (!isMounted) return;
      try {
        const [st, rk, alRes] = await Promise.all([
          fetchLiveStatus().catch(() => null),
          fetchLiveRisk().catch(() => null),
          fetchActiveAlerts().catch(() => null),
        ]);
        if (!isMounted) return;
        if (st) setLiveStatus(st);
        if (rk) setRiskData(rk);
        if (alRes?.alerts) {
          setAlerts((prev) => reconcileAlerts(prev, alRes.alerts));
        }
        stateMachine.handleSuccess();
        setLastSuccessfulUpdate(new Date().toISOString());
        setIsLiveUpdated(true);
        setTimeout(() => isMounted && setIsLiveUpdated(false), 1400);
      } catch (err) {
        console.warn("Telemetry reconciliation error:", err);
      }
    };

    const cleanupSse = () => {
      if (es) {
        try {
          es.close();
        } catch (e) {}
        es = null;
      }
    };

    const cleanupTimers = () => {
      if (reconnectTimer) {
        clearTimeout(reconnectTimer);
        reconnectTimer = null;
      }
      if (pollTimer) {
        clearInterval(pollTimer);
        pollTimer = null;
      }
      if (sseProbeTimer) {
        clearTimeout(sseProbeTimer);
        sseProbeTimer = null;
      }
    };

    const pollOnce = async () => {
      if (!isMounted) return;
      try {
        const [st, rk, alRes] = await Promise.all([
          fetchLiveStatus().catch(() => null),
          fetchLiveRisk().catch(() => null),
          fetchActiveAlerts().catch(() => null),
        ]);
        if (!isMounted) return;
        if (st && rk) {
          setLiveStatus(st);
          setRiskData(rk);
          if (alRes?.alerts) {
            setAlerts((prev) => reconcileAlerts(prev, alRes.alerts));
          }
          stateMachine.handleSuccess();
          setLastSuccessfulUpdate(new Date().toISOString());
          setIsLiveUpdated(true);
          setTimeout(() => isMounted && setIsLiveUpdated(false), 1400);
        } else {
          const pollErr = stateMachine.handlePollError({ isOnline: navigator.onLine });
          setConnectionStatus(pollErr.nextState);
        }
      } catch (err) {
        console.warn("Fallback poll error:", err);
        const pollErr = stateMachine.handlePollError({ isOnline: navigator.onLine });
        setConnectionStatus(pollErr.nextState);
      }
    };

    const startPollingFallback = (initialDelayMs = 0) => {
      if (pollTimer) return;
      if (initialDelayMs > 0) {
        setTimeout(pollOnce, initialDelayMs);
      } else {
        pollOnce();
      }
      pollTimer = setInterval(pollOnce, RESILIENCE_CONFIG.BASE_POLL_MS);

      // In the background, periodically probe SSE reconnection
      scheduleSseProbe();
    };

    const scheduleSseProbe = () => {
      if (!isMounted || es) return;
      if (sseProbeTimer) clearTimeout(sseProbeTimer);
      sseProbeTimer = setTimeout(() => {
        if (!isMounted) return;
        if (stateMachine.getState() === "polling") {
          connectSse();
        }
      }, RESILIENCE_CONFIG.MAX_RECONNECT_MS);
    };

    const handleSseFailure = () => {
      if (!isMounted) return;
      cleanupSse();
      const res = stateMachine.handleSseError({ isOnline: navigator.onLine });
      setConnectionStatus(res.nextState);

      if (res.shouldPoll) {
        startPollingFallback(res.delayMs);
      } else {
        if (reconnectTimer) clearTimeout(reconnectTimer);
        reconnectTimer = setTimeout(() => {
          if (isMounted) connectSse();
        }, res.delayMs);
      }
    };

    const connectSse = () => {
      if (!isMounted) return;
      cleanupSse();

      try {
        es = new EventSource(getLiveStreamUrl());

        es.onopen = () => {
          if (!isMounted) return;
          stateMachine.handleSuccess();
          setConnectionStatus("connected");
          setLastSuccessfulUpdate(new Date().toISOString());
          if (pollTimer) {
            clearInterval(pollTimer);
            pollTimer = null;
          }
          reconcileAll();
        };

        es.addEventListener("status", (e) => {
          if (!isMounted) return;
          try {
            const parsed = JSON.parse(e.data);
            setLiveStatus(parsed);
            stateMachine.handleSuccess();
            setLastSuccessfulUpdate(new Date().toISOString());
          } catch (err) {
            console.debug("SSE status parse error:", err);
          }
        });

        es.addEventListener("risk_update", (e) => {
          if (!isMounted) return;
          try {
            const parsed = JSON.parse(e.data);
            if (parsed.segments && parsed.segments.length > 0) {
              setRiskData(parsed);
            } else {
              fetchLiveRisk().then((d) => isMounted && setRiskData(d)).catch(() => {});
            }
            stateMachine.handleSuccess();
            setLastSuccessfulUpdate(new Date().toISOString());
            setIsLiveUpdated(true);
            setTimeout(() => isMounted && setIsLiveUpdated(false), 1400);
          } catch (err) {
            console.debug("SSE risk parse error:", err);
          }
        });

        es.addEventListener("event_update", () => {
          if (!isMounted) return;
          reconcileAll();
        });

        es.addEventListener("alert", () => {
          if (!isMounted) return;
          refreshAlerts();
          fetchLiveRisk().then((d) => isMounted && setRiskData(d)).catch(() => {});
          stateMachine.handleSuccess();
          setLastSuccessfulUpdate(new Date().toISOString());
        });

        es.addEventListener("route_update", (e) => {
          if (!isMounted) return;
          try {
            const parsed = JSON.parse(e.data);
            const d = new Date(parsed.timestamp || Date.now());
            const hh = String(d.getHours()).padStart(2, "0");
            const mm = String(d.getMinutes()).padStart(2, "0");
            setLastRouteUpdate({
              time: `${hh}:${mm}`,
              reason: parsed.reason || "hazard_update",
              eventId: parsed.event_id,
              timestamp: parsed.timestamp || new Date().toISOString(),
            });
            stateMachine.handleSuccess();
            setLastSuccessfulUpdate(new Date().toISOString());
          } catch (err) {
            console.debug("SSE route_update parse error:", err);
          }
        });

        es.addEventListener("heartbeat", () => {
          if (!isMounted) return;
          stateMachine.handleSuccess();
          setConnectionStatus("connected");
        });

        es.onerror = () => {
          handleSseFailure();
        };
      } catch (err) {
        console.warn("EventSource creation error:", err);
        handleSseFailure();
      }
    };

    // Tab visibility handling: pause retries when tab is hidden, resume on visibility
    const handleVisibilityChange = () => {
      if (!isMounted) return;
      if (document.visibilityState === "visible") {
        stateMachine.handleOnlineResume();
        if (stateMachine.getState() !== "connected") {
          connectSse();
        }
      } else {
        if (reconnectTimer) {
          clearTimeout(reconnectTimer);
          reconnectTimer = null;
        }
      }
    };

    const handleOnline = () => {
      if (!isMounted) return;
      stateMachine.handleOnlineResume();
      connectSse();
    };

    const handleOffline = () => {
      if (!isMounted) return;
      stateMachine.handleSseError({ isOnline: false });
      setConnectionStatus("offline");
      cleanupSse();
      cleanupTimers();
    };

    document.addEventListener("visibilitychange", handleVisibilityChange);
    window.addEventListener("online", handleOnline);
    window.addEventListener("offline", handleOffline);

    // Initial connection attempt
    connectSse();

    return () => {
      isMounted = false;
      cleanupSse();
      cleanupTimers();
      stateMachine.destroy();
      document.removeEventListener("visibilitychange", handleVisibilityChange);
      window.removeEventListener("online", handleOnline);
      window.removeEventListener("offline", handleOffline);
    };
  }, [dashboardMode]);

  // Initial load: Health, Available Dates, and Corridor Highway GeoJSON
  useEffect(() => {
    async function initDashboard() {
      try {
        setIsLoading(true);
        setError(null);

        const [healthRes, datesRes, geojsonRes] = await Promise.all([
          fetchHealth().catch(() => ({ status: "degraded" })),
          fetchAvailableDates().catch(() => null),
          fetchCorridorSegments(),
        ]);

        setHealth(healthRes);
        setAvailableDates(datesRes);
        setGeojson(geojsonRes);

        // Fetch risk for initial benchmark date
        const initialDate = "2023-07-09";
        const riskRes = await fetchCorridorRisk(initialDate);
        setRiskData(riskRes);
        setSelectedDate(initialDate);
      } catch (err) {
        console.error("Initialization error:", err);
        setError(err.message || "Failed to initialize RouteWise dashboard.");
      } finally {
        setIsLoading(false);
      }
    }

    initDashboard();
  }, []);

  const displayDate = getEffectiveDate({
    userMode: dashboardMode,
    backendMode: liveStatus?.mode,
    selectedHistoricalDate: selectedDate,
    liveRiskData: riskData,
    liveStatus: liveStatus,
  });

  return (
    <Routes>
      {/* Public Landing & Authentication Routes */}
      <Route
        path="/"
        element={
          <PublicOnlyRoute>
            <WelcomeView theme={theme} setTheme={setTheme} health={health} />
          </PublicOnlyRoute>
        }
      />
      <Route
        path="/auth/signin"
        element={
          <PublicOnlyRoute>
            <SignInView theme={theme} setTheme={setTheme} />
          </PublicOnlyRoute>
        }
      />
      <Route
        path="/auth/signup"
        element={
          <PublicOnlyRoute>
            <SignUpView theme={theme} setTheme={setTheme} />
          </PublicOnlyRoute>
        }
      />

      {/* Protected Dashboard Routes */}
      <Route
        path="/*"
        element={
          <ProtectedRoute>
            <DashboardLayout
              theme={theme}
              setTheme={setTheme}
              health={health}
              availableDates={availableDates}
              geojson={geojson}
              selectedDate={displayDate}
              setSelectedDate={setSelectedDate}
              riskData={riskData}
              setRiskData={setRiskData}
              selectedSegment={selectedSegment}
              setSelectedSegment={setSelectedSegment}
              isLoading={isLoading}
              setIsLoading={setIsLoading}
              error={error}
              setError={setError}
              dashboardMode={dashboardMode}
              setDashboardMode={handleModeChange}
              liveStatus={liveStatus}
              connectionStatus={connectionStatus}
              lastSuccessfulUpdate={lastSuccessfulUpdate}
              onRefreshLive={handleRefreshLive}
              isLiveUpdated={isLiveUpdated}
              lastRouteUpdate={lastRouteUpdate}
              alerts={alerts}
              isAlertDrawerOpen={isAlertDrawerOpen}
              setIsAlertDrawerOpen={setIsAlertDrawerOpen}
              refreshAlerts={refreshAlerts}
              onScenarioStepped={handleScenarioStepped}
            />
          </ProtectedRoute>
        }
      />
    </Routes>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <JourneyProvider>
          <ErrorBoundary>
            <AppContent />
          </ErrorBoundary>
        </JourneyProvider>
      </AuthProvider>
    </BrowserRouter>
  );
}
