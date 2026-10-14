import React, { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Cross,
  Shield,
  Fuel,
  Wrench,
  CheckCircle,
  AlertCircle,
  MapPin,
  ExternalLink,
} from 'lucide-react';
import { fetchAlongRouteServices } from '../services/api';

export default function AlongRouteServicesCard({ onSelectLocation }) {
  const { t } = useTranslation();
  const [services, setServices] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filterType, setFilterType] = useState('all');

  useEffect(() => {
    async function load() {
      try {
        const res = await fetchAlongRouteServices();
        setServices(res);
      } catch (err) {
        console.warn('Failed to load along-route services:', err);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  const getServiceIcon = (type) => {
    switch (type) {
      case 'hospital':
        return <span style={{ color: 'var(--danger)' }}>🏥</span>;
      case 'police':
        return <span style={{ color: 'var(--accent-primary)' }}>👮</span>;
      case 'fuel':
        return <span style={{ color: 'var(--warning)' }}>⛽</span>;
      case 'mechanic':
        return <span style={{ color: 'var(--text-muted)' }}>🔧</span>;
      default:
        return <MapPin size={16} />;
    }
  };

  const filtered = services.filter(
    (s) => filterType === 'all' || s.type === filterType
  );

  return (
    <div className="services-card" role="region" aria-label="Along-Route Emergency Services">
      <div className="services-header">
        <div>
          <h3 className="services-title">{t('services.title')}</h3>
          <p className="services-disclaimer">{t('services.disclaimer')}</p>
        </div>

        {/* Filter Pills */}
        <div className="services-filters">
          <button
            type="button"
            className={`svc-filter-pill ${filterType === 'all' ? 'active' : ''}`}
            onClick={() => setFilterType('all')}
          >
            All Facilities
          </button>
          <button
            type="button"
            className={`svc-filter-pill ${filterType === 'hospital' ? 'active' : ''}`}
            onClick={() => setFilterType('hospital')}
          >
            Hospitals
          </button>
          <button
            type="button"
            className={`svc-filter-pill ${filterType === 'police' ? 'active' : ''}`}
            onClick={() => setFilterType('police')}
          >
            Police & TCU
          </button>
          <button
            type="button"
            className={`svc-filter-pill ${filterType === 'fuel' ? 'active' : ''}`}
            onClick={() => setFilterType('fuel')}
          >
            Fuel Stations
          </button>
          <button
            type="button"
            className={`svc-filter-pill ${filterType === 'mechanic' ? 'active' : ''}`}
            onClick={() => setFilterType('mechanic')}
          >
            Recovery & Workshop
          </button>
        </div>
      </div>

      {loading ? (
        <div className="state-box state-loading" style={{ margin: '20px auto' }}>
          <span>Loading along-route emergency infrastructure...</span>
        </div>
      ) : filtered.length === 0 ? (
        <div className="state-box state-neutral" style={{ margin: '20px auto' }}>
          <span>No facilities found matching selected filter.</span>
        </div>
      ) : (
        <div className="services-grid">
          {filtered.map((s) => (
            <div key={s.id} className="service-item-box">
              <div className="svc-top-row">
                <div className="svc-icon-name">
                  {getServiceIcon(s.type)}
                  <strong>{s.name}</strong>
                </div>
                {s.verified ? (
                  <span className="badge badge-success" title="Verified public facility">
                    <CheckCircle size={11} style={{ display: 'inline', marginRight: 2 }} />
                    Verified
                  </span>
                ) : (
                  <span className="badge badge-simulated" title="Unverified demo placeholder">
                    Placeholder
                  </span>
                )}
              </div>

              <div className="svc-coords-text">
                GPS: {s.lat.toFixed(4)}°N, {s.lon.toFixed(4)}°E
              </div>

              {s.notes && <p className="svc-notes">{s.notes}</p>}

              <div className="svc-source-footer">
                <span>Source: {s.source}</span>
                <span>Checked: {s.last_checked}</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
