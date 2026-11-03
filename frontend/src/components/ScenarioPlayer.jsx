import React, { useState } from 'react';
import {
  Play,
  SkipForward,
  RotateCcw,
  CloudRain,
  AlertOctagon,
  CheckCircle2,
  AlertTriangle,
  RefreshCw,
} from 'lucide-react';
import { stepReplayScenario } from '../services/api';

const SCENARIO_LABELS = [
    { step: 0, date: '2023-07-06', label: 'Step 0: Clear Baseline', color: 'var(--success, #22c55e)' },
    { step: 1, date: '2023-07-07', label: 'Step 1: Rain Onset', color: 'var(--accent-primary, #3b82f6)' },
    { step: 2, date: '2023-07-08', label: 'Step 2: Heavy Storm', color: 'var(--warning, #f97316)' },
    { step: 3, date: '2023-07-09', label: 'Step 3: Peak Cloudburst', color: 'var(--danger, #ef4444)' },
    { step: 4, date: '2023-07-10', label: 'Step 4: Post-Storm Clearance', color: 'var(--success, #22c55e)' },
];

export default function ScenarioPlayer({ onScenarioStepped }) {
  const [currentStep, setCurrentStep] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [scenarioData, setScenarioData] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);

  const handleRunStep = async (stepIdx) => {
    try {
      setIsLoading(true);
      setError(null);
      const res = await stepReplayScenario(stepIdx);
      setCurrentStep(stepIdx);
      setScenarioData(res);
      if (onScenarioStepped) {
        onScenarioStepped(res);
      }
    } catch (err) {
      setError(err.message || 'Failed to step scenario');
    } finally {
      setIsLoading(false);
    }
  };

  const handleNext = () => {
    const nextIdx = (currentStep + 1) % SCENARIO_LABELS.length;
    handleRunStep(nextIdx);
  };

  const handleReset = () => {
    handleRunStep(0);
  };

  return (
    <div className="scenario-player-card">
      <div className="scenario-player-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <CloudRain size={18} style={{ color: 'var(--accent-primary)' }} />
          <strong>Demo Replay: Multi-Day Storm Scenario (July 2023 Cloudburst)</strong>
        </div>
        <span className="badge badge-pill" style={{ fontSize: 10, borderColor: '#f97316', color: '#f97316' }}>
          SIMULATION REPLAY
        </span>
      </div>

      <p style={{ fontSize: 12, color: 'var(--text-muted)', margin: '6px 0 12px 0' }}>
        Step through the recorded 2023 monsoon storm progression to watch real-time alert triggers, corridor status shifts, and route recalculation in action.
      </p>

      {/* Step Indicators */}
      <div className="scenario-steps-track">
        {SCENARIO_LABELS.map((item) => {
          const isActive = currentStep === item.step;
          return (
            <button
              key={item.step}
              type="button"
              className={`scenario-step-pill ${isActive ? 'active' : ''}`}
              style={{ borderColor: isActive ? item.color : 'var(--border-color)' }}
              disabled={isLoading}
              onClick={() => handleRunStep(item.step)}
            >
              <span className="step-num">{item.step}</span>
              <span className="step-name">{item.date.slice(5)}</span>
            </button>
          );
        })}
      </div>

      {/* Active Step Details */}
      {scenarioData && (
        <div className="scenario-status-box">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              <strong style={{ fontSize: 13 }}>{scenarioData.title}</strong> ({scenarioData.date})
              <div style={{ fontSize: 12, color: 'var(--text-dim)', marginTop: 2 }}>{scenarioData.description}</div>
            </div>
            <div style={{ textAlign: 'right' }}>
              <span className={`badge ${scenarioData.route_recommendation === 'HOLD' ? 'badge-disconnected' : 'badge-connected'}`}>
                {scenarioData.route_recommendation}
              </span>
              <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>
                {scenarioData.active_alerts_count} Active Alerts
              </div>
            </div>
          </div>
        </div>
      )}

      {error && (
        <div className="auth-error-banner" style={{ margin: '8px 0' }}>
          <AlertOctagon size={14} />
          <span>{error}</span>
        </div>
      )}

      {/* Controls */}
      <div className="scenario-player-controls">
        <button
          type="button"
          className="sample-btn"
          disabled={isLoading}
          onClick={handleReset}
        >
          <RotateCcw size={14} style={{ marginRight: 4 }} />
          Reset to Baseline
        </button>

        <button
          type="button"
          className="plan-submit-btn"
          style={{ width: 'auto', padding: '6px 14px', fontSize: 12 }}
          disabled={isLoading}
          onClick={handleNext}
        >
          {isLoading ? (
            <>
              <RefreshCw size={14} className="spin-icon" style={{ marginRight: 6 }} />
              Stepping Scenario...
            </>
          ) : (
            <>
              <SkipForward size={14} style={{ marginRight: 6 }} />
              Advance to Next Storm Phase →
            </>
          )}
        </button>
      </div>
    </div>
  );
}
