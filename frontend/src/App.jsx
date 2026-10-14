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
} from "./services/api";

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

  // Derive active tab from pathname
  const currentPath = location.pathname.replace(/^\//, "") || "overview";

  return (
    <div className="app-layout">
      {/* Sidebar Navigation */}
      <Navigation
        theme={theme}
        setTheme={setTheme}
        health={health}
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
                  onNavigate={(tab) => navigate(`/${tab}`)}
                />
              }
            />
            <Route
              path="journey"
              element={<JourneyPlanner onNavigateToMap={() => navigate("/map")} />}
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
                  />

                  <div className="main-grid" style={{ marginTop: 16 }}>
                    <CorridorMap
                      geojson={geojson}
                      riskData={riskData}
                      selectedDate={selectedDate}
                      onSelectSegment={setSelectedSegment}
                      selectedSegmentId={selectedSegment?.id}
                      theme={theme}
                    />

                    <div className="sidebar">
                      <RiskSummaryCard
                        summary={riskData?.summary}
                        metadata={riskData?.metadata}
                      />

                      <SegmentInspector
                        selectedSegment={selectedSegment}
                        riskData={riskData}
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
              selectedDate={selectedDate}
              setSelectedDate={setSelectedDate}
              riskData={riskData}
              setRiskData={setRiskData}
              selectedSegment={selectedSegment}
              setSelectedSegment={setSelectedSegment}
              isLoading={isLoading}
              setIsLoading={setIsLoading}
              error={error}
              setError={setError}
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
          <AppContent />
        </JourneyProvider>
      </AuthProvider>
    </BrowserRouter>
  );
}
