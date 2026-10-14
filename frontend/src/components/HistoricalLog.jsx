import React, { useState, useEffect } from 'react';
import { fetchDisruptions, fetchDisruptionStats } from '../services/api';
import {
  History,
  Search,
  Filter,
  ExternalLink,
  AlertTriangle,
  RefreshCw,
  MapPin,
  Calendar,
  Layers,
  ChevronLeft,
  ChevronRight,
  TrendingUp,
} from 'lucide-react';

export default function HistoricalLog() {
  const [events, setEvents] = useState([]);
  const [stats, setStats] = useState(null);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(15);

  const [selectedYear, setSelectedYear] = useState('');
  const [selectedType, setSelectedType] = useState('all');
  const [selectedClosure, setSelectedClosure] = useState('all');
  const [searchQuery, setSearchQuery] = useState('');

  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);

  // Load stats once on mount
  useEffect(() => {
    async function loadStats() {
      try {
        const statsData = await fetchDisruptionStats();
        setStats(statsData);
      } catch (err) {
        console.warn('Failed to load stats:', err);
      }
    }
    loadStats();
  }, []);

  // Load events on filter change
  useEffect(() => {
    async function loadEvents() {
      try {
        setIsLoading(true);
        setError(null);
        const data = await fetchDisruptions({
          year: selectedYear || undefined,
          disruptionType: selectedType,
          closure: selectedClosure,
          query: searchQuery || undefined,
          page,
          pageSize,
        });
        setEvents(data.events);
        setTotal(data.total);
      } catch (err) {
        console.error('Failed to load historical disruptions:', err);
        setError(err.message || 'Failed to load historical records');
      } finally {
        setIsLoading(false);
      }
    }
    loadEvents();
  }, [selectedYear, selectedType, selectedClosure, searchQuery, page, pageSize]);

  const totalPages = Math.ceil(total / pageSize) || 1;

  const getTypeBadge = (type) => {
    const t = type.toLowerCase();
    if (t.includes('landslide')) {
      return (
        <span className="tier-badge" style={{ color: 'var(--danger)', borderColor: 'var(--danger-border)' }}>
          Landslide
        </span>
      );
    } else if (t.includes('shooting')) {
      return (
        <span className="tier-badge" style={{ color: 'var(--warning)', borderColor: 'var(--warning-border)' }}>
          Shooting Stones
        </span>
      );
    } else if (t.includes('snow')) {
      return (
        <span className="tier-badge" style={{ color: 'var(--info)', borderColor: 'var(--info-border)' }}>
          Snow Closure
        </span>
      );
    } else {
      return (
        <span className="tier-badge" style={{ color: 'var(--text-muted)', borderColor: 'var(--border-default)' }}>
          {type}
        </span>
      );
    }
  };

  return (
    <div className="history-container">
      {/* Header */}
      <div className="history-header-card">
        <div className="brand-section">
          <div className="brand-icon">
            <History size={22} />
          </div>
          <div>
            <h2>Verified Corridor Disruption Observations</h2>
            <p>Ground-Truth Disruption Event Archive (2018–2025) • NH-44 Ramban–Banihal</p>
          </div>
        </div>

        <div className="retrospective-banner" style={{ marginTop: 12 }}>
          <AlertTriangle size={16} style={{ flexShrink: 0, marginTop: 2 }} />
          <div>
            <strong>Ground-Truth Event Archive:</strong> These records represent verified historical highway
            closures collected from regional traffic police alerts, government advisories, and corroborated news reports.
            Each event was snapped to nearest corridor graph edges to train and validate the ST-GNN predictive model.
          </div>
        </div>
      </div>

      {/* Stats Summary Row */}
      {stats && (
        <div className="history-stats-grid">
          <div className="stat-card">
            <span className="stat-number">{stats.total_events}</span>
            <span className="stat-label">Verified Closures</span>
            <span className="stat-sub">2018–2025 Archive</span>
          </div>

          <div className="stat-card">
            <span className="stat-number" style={{ color: 'var(--danger)' }}>
              {stats.by_type.landslide || 0}
            </span>
            <span className="stat-label">Landslide Events</span>
            <span className="stat-sub">Major slope failures</span>
          </div>

          <div className="stat-card">
            <span className="stat-number" style={{ color: 'var(--warning)' }}>
              {stats.by_type.shooting_stones || 0}
            </span>
            <span className="stat-label">Shooting Stones</span>
            <span className="stat-sub">High-velocity rockfall</span>
          </div>

          <div className="stat-card">
            <span className="stat-number" style={{ color: 'var(--info)' }}>
              {stats.by_type.snow || 0}
            </span>
            <span className="stat-label">Snow Blockages</span>
            <span className="stat-sub">Jawahar Tunnel sector</span>
          </div>
        </div>
      )}

      {/* Filter and Search Bar */}
      <div className="filter-controls-card">
        <div className="filter-row">
          {/* Search input */}
          <div className="filter-search-box">
            <Search size={16} className="search-icon" />
            <input
              type="text"
              placeholder="Search by location (e.g. Panthyal, Digdol, Cafeteria Morh)..."
              value={searchQuery}
              onChange={(e) => {
                setSearchQuery(e.target.value);
                setPage(1);
              }}
            />
          </div>

          {/* Year Filter */}
          <div className="filter-select-group">
            <label>Year:</label>
            <select
              value={selectedYear}
              onChange={(e) => {
                setSelectedYear(e.target.value);
                setPage(1);
              }}
              className="filter-select"
            >
              <option value="">All Years</option>
              {['2025', '2024', '2023', '2022', '2021', '2020', '2019', '2018'].map((y) => (
                <option key={y} value={y}>
                  {y}
                </option>
              ))}
            </select>
          </div>

          {/* Hazard Type Filter */}
          <div className="filter-select-group">
            <label>Hazard Type:</label>
            <select
              value={selectedType}
              onChange={(e) => {
                setSelectedType(e.target.value);
                setPage(1);
              }}
              className="filter-select"
            >
              <option value="all">All Types</option>
              <option value="landslide">Landslide</option>
              <option value="shooting_stones">Shooting Stones</option>
              <option value="snow">Snow</option>
            </select>
          </div>

          {/* Closure Filter */}
          <div className="filter-select-group">
            <label>Closure:</label>
            <select
              value={selectedClosure}
              onChange={(e) => {
                setSelectedClosure(e.target.value);
                setPage(1);
              }}
              className="filter-select"
            >
              <option value="all">All Closures</option>
              <option value="full">Full Closure</option>
              <option value="partial">Partial / One-Way</option>
            </select>
          </div>
        </div>
      </div>

      {/* Table of Events */}
      <div className="history-table-card">
        {isLoading ? (
          <div className="state-box state-loading">
            <RefreshCw size={24} className="spin-icon" style={{ animation: 'spin 1s linear infinite' }} />
            <span>Loading historical disruption log...</span>
          </div>
        ) : error ? (
          <div className="state-box state-error">
            <AlertTriangle size={24} />
            <span>{error}</span>
          </div>
        ) : events.length === 0 ? (
          <div className="state-box">
            <History size={32} style={{ color: 'var(--text-dim)' }} />
            <span>No historical disruption records match your query.</span>
          </div>
        ) : (
          <>
            <div className="table-responsive">
              <table className="history-table">
                <thead>
                  <tr>
                    <th>Date</th>
                    <th>Location</th>
                    <th>Type</th>
                    <th>Closure</th>
                    <th>Duration</th>
                    <th>Snapped Graph Segment</th>
                    <th>Observations & Source</th>
                  </tr>
                </thead>
                <tbody>
                  {events.map((evt) => (
                    <tr key={evt.id}>
                      <td style={{ fontWeight: 600, whiteSpace: 'nowrap' }}>
                        <Calendar size={13} style={{ display: 'inline', marginRight: 4, color: 'var(--text-muted)' }} />
                        {evt.date}
                      </td>
                      <td>
                        <strong>{evt.location_desc}</strong>
                        <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                          {evt.lat.toFixed(3)}°N, {evt.lon.toFixed(3)}°E
                        </div>
                      </td>
                      <td>{getTypeBadge(evt.disruption_type)}</td>
                      <td>
                        <span className="badge badge-pill">{evt.closure}</span>
                      </td>
                      <td>{evt.duration_hours ? `${evt.duration_hours} hrs` : 'N/A'}</td>
                      <td>
                        {evt.segment_id ? (
                          <span style={{ fontFamily: 'monospace', fontSize: 11, color: 'var(--accent-secondary)' }}>
                            {evt.segment_id}
                          </span>
                        ) : (
                          <span style={{ color: 'var(--text-dim)' }}>Unmapped</span>
                        )}
                      </td>
                      <td>
                        <div style={{ fontSize: 12, lineHeight: 1.4, color: 'var(--text-secondary)' }}>
                          {evt.notes}
                        </div>
                        {evt.source_url && (
                          <a
                            href={evt.source_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="source-link"
                          >
                            <span>{evt.source_name || 'Source Report'}</span>
                            <ExternalLink size={12} style={{ marginLeft: 3 }} />
                          </a>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Pagination */}
            <div className="pagination-bar">
              <span className="pagination-info">
                Showing {(page - 1) * pageSize + 1} to {Math.min(page * pageSize, total)} of {total} records
              </span>

              <div className="pagination-buttons">
                <button
                  type="button"
                  className="page-btn"
                  onClick={() => setPage(page - 1)}
                  disabled={page <= 1}
                >
                  <ChevronLeft size={16} /> Prev
                </button>
                <span className="page-indicator">
                  Page {page} of {totalPages}
                </span>
                <button
                  type="button"
                  className="page-btn"
                  onClick={() => setPage(page + 1)}
                  disabled={page >= totalPages}
                >
                  Next <ChevronRight size={16} />
                </button>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
