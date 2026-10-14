import React, { useEffect, useState, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import {
  MapContainer,
  TileLayer,
  Polyline,
  Tooltip,
  CircleMarker,
  Popup,
  useMap,
} from 'react-leaflet';
import {
  AlertTriangle,
  Layers,
  Shield,
  CloudRain,
  MapPin,
  CheckCircle,
  ExternalLink,
  Info,
} from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import {
  fetchPublicReports,
  fetchPatrolReports,
  fetchAlongRouteServices,
  fetchCorridorWeather,
} from '../services/api';

// Invalidation controller ensures Leaflet resizes correctly on tab and theme switches
function MapController({ theme, isDrawerOpen }) {
  const map = useMap();
  useEffect(() => {
    const timer = setTimeout(() => {
      map.invalidateSize();
    }, 150);
    return () => clearTimeout(timer);
  }, [map, theme, isDrawerOpen]);

  return null;
}

export default function CorridorMap({
  geojson,
  riskData,
  onSelectSegment,
  selectedSegmentId,
  theme = 'dark',
  selectedDate = '2023-07-09',
  isDrawerOpen = false,
}) {
  const { t } = useTranslation();
  const { isPatrol } = useAuth();
  const isLight = theme === 'light';

  // Center coordinates for Ramban-Banihal NH-44 section
  const center = [33.342, 75.205];
  const zoom = 11;
  const [hasTileError, setHasTileError] = useState(false);

  // Layer Toggles
  const [showRiskLayer, setShowRiskLayer] = useState(true);
  const [showReportsLayer, setShowReportsLayer] = useState(true);
  const [showWeatherLayer, setShowWeatherLayer] = useState(false);
  const [showServicesLayer, setShowServicesLayer] = useState(true);

  // Layer Data
  const [fieldReports, setFieldReports] = useState([]);
  const [alongServices, setAlongServices] = useState([]);
  const [weatherData, setWeatherData] = useState(null);

  // Reset tile error status when theme changes
  useEffect(() => {
    setHasTileError(false);
  }, [theme]);

  // Load field reports
  useEffect(() => {
    let isMounted = true;
    async function loadReports() {
      try {
        if (isPatrol) {
          const res = await fetchPatrolReports({ limit: 100 });
          if (isMounted) setFieldReports(res.items || []);
        } else {
          const publicReps = await fetchPublicReports();
          if (isMounted) setFieldReports(publicReps || []);
        }
      } catch (err) {
        console.warn('Failed to load map incident reports:', err);
      }
    }
    loadReports();
    return () => {
      isMounted = false;
    };
  }, [isPatrol]);

  // Load along-route services
  useEffect(() => {
    let isMounted = true;
    async function loadServices() {
      try {
        const data = await fetchAlongRouteServices();
        if (isMounted) setAlongServices(data);
      } catch (err) {
        console.warn('Failed to load services on map:', err);
      }
    }
    loadServices();
    return () => {
      isMounted = false;
    };
  }, []);

  // Load weather overlay if toggled
  useEffect(() => {
    let isMounted = true;
    async function loadWeather() {
      if (!showWeatherLayer || !selectedDate) return;
      try {
        const data = await fetchCorridorWeather(selectedDate);
        if (isMounted) setWeatherData(data);
      } catch (err) {
        console.warn('Failed to load map weather overlay:', err);
      }
    }
    loadWeather();
    return () => {
      isMounted = false;
    };
  }, [showWeatherLayer, selectedDate]);

  // Build quick lookup map: segment_id -> { risk_score, risk_tier }
  const riskLookup = useMemo(() => {
    const map = {};
    if (riskData && riskData.segments) {
      riskData.segments.forEach((s) => {
        map[s.segment_id] = s;
      });
    }
    return map;
  }, [riskData]);

  // Theme-adaptive Basemap Tiles
  const tileUrl = isLight
    ? 'https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png'
    : 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png';
  const tileAttribution =
    '&copy; <a href="https://carto.com/" target="_blank" rel="noopener noreferrer">CARTO</a> &copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">OpenStreetMap</a>';

  // Read semantic color tokens dynamically from CSS properties
  const getStyleForSegment = (segId) => {
    const isSelected = selectedSegmentId === segId;
    const r = riskLookup[segId];
    const tier = r ? r.risk_tier : 'UNKNOWN';

    // Weather overlay mode: color by rainfall if enabled
    if (showWeatherLayer && weatherData?.segments?.[segId]) {
      const p = weatherData.segments[segId].precip_mm || 0;
      let wColor = isLight ? '#0284c7' : '#38bdf8';
      if (p > 20) wColor = isLight ? '#4338ca' : '#818cf8';
      else if (p > 5) wColor = isLight ? '#0369a1' : '#0ea5e9';
      return {
        color: wColor,
        weight: isSelected ? 7 : 4.5,
        opacity: isSelected ? 1.0 : 0.85,
      };
    }

    // Risk overlay mode (Semantic Tokens)
    let color = isLight ? '#64748b' : '#94a3b8'; // Unknown / Neutral
    let weight = 3.5;

    if (tier === 'High') {
      color = isLight ? '#dc2626' : '#ef4444'; // var(--risk-high)
      weight = isSelected ? 6.5 : 4.5;
    } else if (tier === 'Medium') {
      color = isLight ? '#d97706' : '#f59e0b'; // var(--risk-medium)
      weight = isSelected ? 6.0 : 4.0;
    } else if (tier === 'Low') {
      color = isLight ? '#059669' : '#10b981'; // var(--risk-low)
      weight = isSelected ? 5.5 : 3.5;
    }

    if (isSelected) weight += 2;

    return {
      color,
      weight,
      opacity: isSelected ? 1.0 : 0.9,
    };
  };

  const casingColor = isLight ? '#ffffff' : '#0b0f19';

  return (
    <div className="map-card" role="region" aria-label="NH-44 Corridor Leaflet Map">
      {/* Map Header with Layer Toggles */}
      <div className="map-header">
        <div>
          <h2>NH-44 Highway Corridor Map (Ramban to Banihal)</h2>
          <span className="map-header-sub">
            Interactive Corridor Topology • 151 Monitored Segments • Click any segment or pin to inspect
          </span>
        </div>

        {/* Layer Controls Bar */}
        <div className="map-layer-toggles">
          <button
            type="button"
            className={`map-layer-btn ${showRiskLayer ? 'active' : ''}`}
            onClick={() => setShowRiskLayer(!showRiskLayer)}
            title="Toggle ST-GNN Risk Heatmap"
          >
            <Shield size={13} />
            <span>Risk Layer</span>
          </button>

          <button
            type="button"
            className={`map-layer-btn ${showReportsLayer ? 'active' : ''}`}
            onClick={() => setShowReportsLayer(!showReportsLayer)}
            title="Toggle Field Incident Reports"
          >
            <AlertTriangle size={13} />
            <span>Field Reports ({fieldReports.length})</span>
          </button>

          <button
            type="button"
            className={`map-layer-btn ${showWeatherLayer ? 'active' : ''}`}
            onClick={() => setShowWeatherLayer(!showWeatherLayer)}
            title="Toggle Historical Weather Rain Overlay (ERA5-Land)"
          >
            <CloudRain size={13} />
            <span>Weather Layer</span>
          </button>

          <button
            type="button"
            className={`map-layer-btn ${showServicesLayer ? 'active' : ''}`}
            onClick={() => setShowServicesLayer(!showServicesLayer)}
            title="Toggle Along-Route Emergency & Fuel Facilities"
          >
            <MapPin size={13} />
            <span>Services ({alongServices.length})</span>
          </button>
        </div>
      </div>

      <div className="map-container">
        {hasTileError && (
          <div className="map-tile-fallback-notice" role="status">
            <AlertTriangle size={14} style={{ color: 'var(--warning)', flexShrink: 0 }} />
            <span>Basemap tiles temporarily unavailable. Corridor segments and incident inspection remain fully active.</span>
          </div>
        )}

        {showWeatherLayer && (
          <div className="weather-overlay-badge">
            <CloudRain size={13} />
            <span>ERA5-Land Retrospective Rainfall Overlay ({selectedDate})</span>
          </div>
        )}

        <MapContainer
          center={center}
          zoom={zoom}
          scrollWheelZoom={true}
          style={{ height: '100%', width: '100%' }}
        >
          <MapController theme={theme} isDrawerOpen={isDrawerOpen} />

          {/* Theme-Adaptive Leaflet Tile Layer */}
          <TileLayer
            key={`${theme}-${hasTileError ? 'err' : 'ok'}`}
            attribution={tileAttribution}
            url={tileUrl}
            maxZoom={19}
            eventHandlers={{
              tileerror: () => setHasTileError(true),
            }}
          />

          {/* 1. Highway Corridor Segments Polyline Layer */}
          {showRiskLayer &&
            geojson &&
            geojson.features &&
            geojson.features.map((feature) => {
              const segId = feature.id;
              const isSelected = selectedSegmentId === segId;
              const leafletPositions = feature.geometry.coordinates.map((coord) => [
                coord[1],
                coord[0],
              ]);
              const style = getStyleForSegment(segId);
              const r = riskLookup[segId];

              return (
                <React.Fragment key={segId}>
                  {/* High-contrast background casing line */}
                  <Polyline
                    positions={leafletPositions}
                    pathOptions={{
                      color: casingColor,
                      weight: style.weight + 2.5,
                      opacity: 0.95,
                    }}
                    interactive={false}
                  />

                  {/* Foreground risk-colored segment line */}
                  <Polyline
                    positions={leafletPositions}
                    pathOptions={style}
                    eventHandlers={{
                      click: () => onSelectSegment(segId),
                    }}
                  >
                    <Tooltip sticky className="map-segment-tooltip">
                      <div className="tooltip-content">
                        <strong>Segment:</strong> {segId}
                        <br />
                        <strong>Tier:</strong> {r ? r.risk_tier : 'Unknown'}
                        <br />
                        <strong>Score:</strong>{' '}
                        {r?.risk_score !== null && r?.risk_score !== undefined
                          ? (r.risk_score * 100).toFixed(1) + '%'
                          : 'N/A'}
                      </div>
                    </Tooltip>
                  </Polyline>
                </React.Fragment>
              );
            })}

          {/* 2. Field Incident Reports Layer */}
          {showReportsLayer &&
            fieldReports.map((rep) => {
              const isVerified = rep.status === 'verified' || rep.status === 'assigned';
              const markerColor = isVerified
                ? (isLight ? '#dc2626' : '#ef4444')
                : (isLight ? '#f59e0b' : '#fbbf24');

              return (
                <CircleMarker
                  key={rep.id}
                  center={[rep.latitude, rep.longitude]}
                  radius={isVerified ? 7 : 6}
                  pathOptions={{
                    color: markerColor,
                    fillColor: markerColor,
                    fillOpacity: isVerified ? 0.9 : 0.5,
                    weight: isVerified ? 2 : 1.5,
                    dashArray: isVerified ? undefined : '3, 3',
                  }}
                >
                  <Popup className="map-incident-popup">
                    <div className="incident-popup-card">
                      <div className="popup-badge-row">
                        <span className="badge badge-category">
                          {t(`categories.${rep.category}`, rep.category)}
                        </span>
                        <span className={`badge badge-status-${rep.status}`}>
                          {t(`status.${rep.status}`, rep.status)}
                        </span>
                        {rep.is_simulated && (
                          <span className="badge badge-simulated">{t('app.simulated_badge')}</span>
                        )}
                      </div>
                      {rep.description && <p className="popup-desc">{rep.description}</p>}
                      <div className="popup-footer">
                        <span>Reported: {new Date(rep.created_at).toLocaleDateString()}</span>
                        {rep.nearest_segment_id && (
                          <button
                            type="button"
                            className="popup-seg-link"
                            onClick={() => onSelectSegment(rep.nearest_segment_id)}
                          >
                            Inspect Segment
                          </button>
                        )}
                      </div>
                    </div>
                  </Popup>
                </CircleMarker>
              );
            })}

          {/* 3. Along-Route Services Layer */}
          {showServicesLayer &&
            alongServices.map((svc) => {
              let svcColor = isLight ? '#0284c7' : '#38bdf8';
              if (svc.type === 'hospital') svcColor = isLight ? '#dc2626' : '#f87171';
              else if (svc.type === 'police') svcColor = isLight ? '#2563eb' : '#60a5fa';
              else if (svc.type === 'fuel') svcColor = isLight ? '#d97706' : '#fbbf24';

              return (
                <CircleMarker
                  key={svc.id}
                  center={[svc.lat, svc.lon]}
                  radius={5.5}
                  pathOptions={{
                    color: svcColor,
                    fillColor: svcColor,
                    fillOpacity: 0.85,
                    weight: 2,
                  }}
                >
                  <Popup className="map-service-popup">
                    <div className="service-popup-card">
                      <strong>{svc.name}</strong>
                      <div className="svc-popup-type">{svc.type.toUpperCase()}</div>
                      {svc.notes && <p className="svc-popup-notes">{svc.notes}</p>}
                      <div className="svc-popup-source">
                        Source: {svc.source} {svc.verified && '(Verified)'}
                      </div>
                    </div>
                  </Popup>
                </CircleMarker>
              );
            })}
        </MapContainer>
      </div>
    </div>
  );
}
