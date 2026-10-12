import React from 'react';
import { MapContainer, TileLayer, Polyline, Tooltip } from 'react-leaflet';

export default function CorridorMap({ geojson, riskData, onSelectSegment, selectedSegmentId }) {
  // Center coordinates for Ramban-Banihal NH-44 section
  const center = [33.342, 75.205];
  const zoom = 11;

  // Build quick lookup map: segment_id -> { risk_score, risk_tier }
  const riskLookup = React.useMemo(() => {
    const map = {};
    if (riskData && riskData.segments) {
      riskData.segments.forEach((s) => {
        map[s.segment_id] = s;
      });
    }
    return map;
  }, [riskData]);

  const getStyleForSegment = (segId) => {
    const isSelected = selectedSegmentId === segId;
    const r = riskLookup[segId];
    const tier = r ? r.risk_tier : 'UNKNOWN';

    let color = '#64748b'; // default unknown
    let weight = 3.5;

    if (tier === 'High') {
      color = '#ef4444';
      weight = isSelected ? 6.5 : 4.5;
    } else if (tier === 'Medium') {
      color = '#f59e0b';
      weight = isSelected ? 6.0 : 4.0;
    } else if (tier === 'Low') {
      color = '#10b981';
      weight = isSelected ? 5.5 : 3.5;
    }

    if (isSelected) {
      weight += 2;
    }

    return {
      color,
      weight,
      opacity: isSelected ? 1.0 : 0.85,
    };
  };

  return (
    <div className="map-card">
      <div className="map-header">
        <h2>NH-44 Highway Corridor Map (Ramban to Banihal)</h2>
        <span style={{ fontSize: 12, color: '#94a3b8' }}>
          Interactive Map • Click any segment to inspect
        </span>
      </div>

      <div className="map-container">
        <MapContainer
          center={center}
          zoom={zoom}
          scrollWheelZoom={true}
          style={{ height: '100%', width: '100%' }}
        >
          {/* OpenStreetMap tile layer */}
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />

          {geojson &&
            geojson.features &&
            geojson.features.map((feature) => {
              const segId = feature.id;
              // Coordinates in GeoJSON are [lon, lat]; Leaflet Polyline expects [lat, lon]
              const leafletPositions = feature.geometry.coordinates.map((coord) => [
                coord[1],
                coord[0],
              ]);
              const style = getStyleForSegment(segId);
              const r = riskLookup[segId];

              return (
                <Polyline
                  key={segId}
                  positions={leafletPositions}
                  pathOptions={style}
                  eventHandlers={{
                    click: () => onSelectSegment(feature),
                  }}
                >
                  <Tooltip sticky>
                    <div style={{ fontSize: 12, color: '#0f172a' }}>
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
              );
            })}
        </MapContainer>
      </div>
    </div>
  );
}
