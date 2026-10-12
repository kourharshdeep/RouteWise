import React, { useState, useEffect } from "react";
import "./App.css";
import {
  fetchHealth,
  fetchAvailableDates,
  fetchCorridorSegments,
  fetchCorridorRisk,
} from "./services/api";
import ControlHeader from "./components/ControlHeader";
import CorridorMap from "./components/CorridorMap";
import RiskSummaryCard from "./components/RiskSummaryCard";
import SegmentInspector from "./components/SegmentInspector";
import { AlertCircle, RefreshCw, Sun, Moon } from "lucide-react";

export default function App() {
  const [theme, setTheme] = useState(
    () => localStorage.getItem("routewise-theme") || "dark",
  );

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    document.body.setAttribute("data-theme", theme);
    localStorage.setItem("routewise-theme", theme);
  }, [theme]);
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

        // Fetch risk for initial date
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

  // Handle date change
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
      setError(
        `Failed to retrieve risk forecast for ${newDate}: ${err.message}`,
      );
    } finally {
      setIsLoading(false);
    }
  };

  const handleRetry = () => {
    window.location.reload();
  };

  return (
    <div className="dashboard-container">
      <div className="theme-toggle-row">
        <label className="theme-switch" title="Toggle light/dark mode">
          <Sun size={17} className="theme-icon" />

          <input
            type="checkbox"
            checked={theme === "dark"}
            onChange={() => setTheme(theme === "dark" ? "light" : "dark")}
            aria-label="Toggle dark mode"
          />

          <span className="theme-slider">
            <span className="theme-knob" />
          </span>

          <Moon size={17} className="theme-icon" />
        </label>
      </div>
      <ControlHeader
        health={health}
        selectedDate={selectedDate}
        onDateChange={handleDateChange}
        availableDates={availableDates}
        isLoading={isLoading}
      />

      {error && (
        <div className="state-box state-error">
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

      {isLoading && !riskData && (
        <div className="state-box state-loading">
          <RefreshCw
            size={28}
            className="spin-icon"
            style={{ animation: "spin 1s linear infinite" }}
          />
          <span>
            Retrieving RouteWise corridor topology and risk forecasts...
          </span>
        </div>
      )}

      <div className="main-grid">
        <CorridorMap
          geojson={geojson}
          riskData={riskData}
          onSelectSegment={setSelectedSegment}
          selectedSegmentId={selectedSegment?.id}
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
  );
}
