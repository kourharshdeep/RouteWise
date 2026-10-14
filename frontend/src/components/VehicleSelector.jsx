import React from 'react';
import { Car, Bike, Bus, Truck, ShieldAlert, Info, Check } from 'lucide-react';
import { useJourney } from '../context/JourneyContext';

export const VEHICLE_OPTIONS = [
  {
    type: 'Car',
    label: 'Passenger Car / SUV',
    icon: <Car size={24} />,
    speed: '45 km/h',
    vulnerability: 'Standard',
    badgeColor: 'var(--accent-secondary)',
    summary: 'Standard passenger vehicles. High agility; cautioned near rockfall zones.',
  },
  {
    type: 'Motorcycle',
    label: 'Motorcycle / 2-Wheeler',
    icon: <Bike size={24} />,
    speed: '40 km/h',
    vulnerability: 'Extreme',
    badgeColor: 'var(--danger)',
    summary: 'Extreme exposure to shooting stones, loose gravel & mud. Daylight transit only.',
  },
  {
    type: 'Bus',
    label: 'Passenger Bus / Transit',
    icon: <Bus size={24} />,
    speed: '32 km/h',
    vulnerability: 'High',
    badgeColor: 'var(--warning)',
    summary: 'Mass passenger transit. Mandatory staging hold if corridor risk is High (≥0.35).',
  },
  {
    type: 'Truck',
    label: 'Heavy Commercial Freight',
    icon: <Truck size={24} />,
    speed: '26 km/h',
    vulnerability: 'High Gradient',
    badgeColor: 'var(--risk-medium)',
    summary: 'Multi-axle cargo. High brake thermal load on steep slopes (>6%) & narrow turns.',
  },
  {
    type: 'Other',
    label: 'Emergency / Convoy',
    icon: <ShieldAlert size={24} />,
    speed: '35 km/h',
    vulnerability: 'Controlled',
    badgeColor: 'var(--accent-primary)',
    summary: 'Special emergency or police convoy. Requires dedicated traffic control protocol.',
  },
];

export default function VehicleSelector({ value, onChange }) {
  const { vehicleType, setVehicleType } = useJourney();
  const currentVehicle = value || vehicleType;

  const handleSelect = (vType) => {
    if (onChange) {
      onChange(vType);
    } else {
      setVehicleType(vType);
    }
  };

  return (
    <div className="vehicle-selector-wrapper">
      <div className="vehicle-selector-header">
        <label className="section-label">Select Vehicle Category</label>
        <span className="vehicle-selected-pill">
          Current: <strong>{currentVehicle}</strong>
        </span>
      </div>

      <div className="vehicle-grid">
        {VEHICLE_OPTIONS.map((opt) => {
          const isSelected = currentVehicle.toLowerCase() === opt.type.toLowerCase();
          return (
            <div
              key={opt.type}
              className={`vehicle-card ${isSelected ? 'selected' : ''}`}
              onClick={() => handleSelect(opt.type)}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => e.key === 'Enter' && handleSelect(opt.type)}
            >
              {isSelected && (
                <div className="vehicle-check-badge">
                  <Check size={12} style={{ color: 'var(--text-on-accent)' }} />
                </div>
              )}
              <div className="vehicle-icon-wrap" style={{ color: opt.badgeColor }}>
                {opt.icon}
              </div>
              <div className="vehicle-card-content">
                <div className="vehicle-title-row">
                  <span className="vehicle-type-name">{opt.type}</span>
                  <span
                    className="vehicle-vulnerability-tag"
                    style={{ borderColor: opt.badgeColor, color: opt.badgeColor }}
                  >
                    {opt.vulnerability}
                  </span>
                </div>
                <div className="vehicle-meta-row">
                  <span>Mtn Speed: ~{opt.speed}</span>
                </div>
                <p className="vehicle-desc">{opt.summary}</p>
              </div>
            </div>
          );
        })}
      </div>

      {/* Honest Scientific Note */}
      <div className="vehicle-scientific-note">
        <Info size={14} style={{ flexShrink: 0, marginTop: 1 }} />
        <div>
          <strong>Model Methodology & Applicability Notice:</strong> The RouteWise ST-GNN model evaluates
          geophysical landslide susceptibility from mountain slope gradient, elevation, curvature, and ERA5
          precipitation. Vehicle category does <em>not</em> alter the mountain's physical disruption probability,
          but dictates stopping distance, axle clearance, and personal casualty vulnerability.
        </div>
      </div>
    </div>
  );
}
