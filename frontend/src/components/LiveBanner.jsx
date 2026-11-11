import React from "react";
import { useTranslation } from "react-i18next";
import {
  AlertTriangle,
  Radio,
  Wifi,
  WifiOff,
  RefreshCw,
  Clock,
  HelpCircle,
  Activity,
  History,
  Calendar,
} from "lucide-react";

export default function LiveBanner({
  mode = "historical",
  onModeChange,
  liveStatus,
  connectionStatus = "connected",
  lastSuccessfulUpdate = null,
  onRefresh,
  isLoading = false,
}) {
  const { t } = useTranslation();
  const isLive = mode === "live";
  const isStale =
    liveStatus?.data_age_hours > 24 || liveStatus?.stale_count > 0;
  const unknownCount = liveStatus?.unknown_count ?? 0;

  return (
    <div
      className={`live-experimental-banner ${isLive && isStale ? "stale" : ""}`}
      role="region"
      aria-label="RouteWise Operating Mode and Telemetry Status"
    >
      <div className="live-banner-left">
        {/* Operating Mode Toggle (Default: Historical) */}
        <div
          className="live-mode-toggle"
          role="group"
          aria-label={t("live.toggle_label")}
        >
          <button
            type="button"
            className={`live-toggle-btn ${!isLive ? "active" : ""}`}
            onClick={() => onModeChange && onModeChange("historical")}
            aria-pressed={!isLive}
          >
            <History size={13} aria-hidden="true" />
            <span>{t("live.historical_mode")}</span>
          </button>
          <button
            type="button"
            className={`live-toggle-btn ${isLive ? "active" : ""}`}
            onClick={() => onModeChange && onModeChange("live")}
            aria-pressed={isLive}
          >
            <Radio size={13} aria-hidden="true" />
            <span>{t("live.live_mode")}</span>
          </button>
        </div>

        {/* In Live Mode: Display Persistent Experimental Badge or Replay / Off notice */}
        {isLive &&
          (liveStatus?.mode === "off" ? (
            <span
              className="badge badge-neutral"
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 4,
                fontWeight: 600,
              }}
            >
              <AlertTriangle size={13} aria-hidden="true" />
              <span>{t("live.mode_off_notice")}</span>
            </span>
          ) : liveStatus?.mode === "replay" ? (
            <span
              className="live-experimental-badge replay"
              style={{
                background: "var(--accent-secondary)",
                color: "var(--text-on-accent-secondary, #ffffff)",
              }}
              title={t("live.replay_mode")}
            >
              <Activity size={13} aria-hidden="true" />
              <span>{t("live.replay_mode")}</span>
            </span>
          ) : (
            <span
              className="live-experimental-badge"
              title={t("live.experimental_notice")}
            >
              <Activity size={13} aria-hidden="true" />
              <span>{t("live.experimental_badge")}</span>
            </span>
          ))}

        {/* Stale Warning Badge if data age > 24h */}
        {isLive && isStale && (
          <span
            className="badge badge-warning"
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 4,
              fontWeight: 700,
            }}
          >
            <AlertTriangle size={13} aria-hidden="true" />
            <span>{t("live.data_stale")}</span>
          </span>
        )}
      </div>

      {/* Live Mode Telemetry Metadata & Connection State */}
      {isLive && (
        <div className="live-banner-meta">
          {/* Weather Window End */}
          {liveStatus?.latest_weather_date && (
            <div
              className="live-banner-item"
              title={t("live.weather_window_end")}
            >
              <Calendar
                size={13}
                style={{ color: "var(--text-muted)" }}
                aria-hidden="true"
              />
              <span>
                {t("live.weather_window_end")}:{" "}
                <strong>{liveStatus.latest_weather_date}</strong>
              </span>
            </div>
          )}

          {/* Data Age */}
          {liveStatus?.data_age_hours !== null &&
            liveStatus?.data_age_hours !== undefined && (
              <div
                className="live-banner-item"
                title={liveStatus?.latest_fetch || "Recent"}
              >
                <Clock
                  size={13}
                  style={{ color: "var(--text-muted)" }}
                  aria-hidden="true"
                />
                <span>
                  {t("live.data_age")}:{" "}
                  <strong>{liveStatus.data_age_hours.toFixed(1)}h</strong>
                </span>
              </div>
            )}

          {/* Last Updated Timestamp */}
          {liveStatus?.latest_fetch && (
            <div className="live-banner-item" title={liveStatus.latest_fetch}>
              <Clock
                size={13}
                style={{ color: "var(--text-muted)" }}
                aria-hidden="true"
              />
              <span>
                {t("live.last_updated")}:{" "}
                <strong>
                  {liveStatus.latest_fetch.length >= 16
                    ? liveStatus.latest_fetch.slice(11, 16) + " UTC"
                    : liveStatus.latest_fetch}
                </strong>
              </span>
            </div>
          )}

          {/* Unknown Segments Indicator */}
          {unknownCount > 0 && (
            <div
              className="live-banner-item"
              title="Missing or stale telemetry is designated UNKNOWN (never assumed safe)"
            >
              <HelpCircle
                size={13}
                style={{ color: "var(--text-dim)" }}
                aria-hidden="true"
              />
              <span style={{ color: "var(--text-dim)", fontWeight: 600 }}>
                {unknownCount} {t("live.unknown_segments")}
              </span>
            </div>
          )}

          {/* Connection Interrupted Warning & Last Successful Timestamp */}
          {connectionStatus !== "connected" && (
            <>
              <div
                className="live-banner-item"
                style={{
                  color: "var(--warning-text, var(--warning))",
                  background: "var(--warning-bg)",
                  border: "1px solid var(--warning-border)",
                  borderRadius: "4px",
                  padding: "2px 6px",
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 4,
                  fontSize: 11,
                  fontWeight: 600,
                }}
                role="alert"
              >
                <AlertTriangle size={12} aria-hidden="true" />
                <span>{t("live.conn_data_may_be_outdated")}</span>
              </div>
              {lastSuccessfulUpdate && (
                <div
                  className="live-banner-item"
                  title={lastSuccessfulUpdate}
                >
                  <Clock size={12} style={{ color: "var(--text-muted)" }} aria-hidden="true" />
                  <span>
                    {t("live.conn_last_successful", {
                      time:
                        lastSuccessfulUpdate.length >= 19
                          ? lastSuccessfulUpdate.slice(11, 19) + " UTC"
                          : lastSuccessfulUpdate,
                    })}
                  </span>
                </div>
              )}
            </>
          )}

          {/* Connection State Indicator (connected | reconnecting | polling | offline) */}
          <div
            className={`live-connection-indicator ${
              connectionStatus === "connected"
                ? "connected"
                : connectionStatus === "reconnecting"
                ? "reconnecting"
                : connectionStatus === "polling"
                ? "polling"
                : "offline"
            }`}
          >
            {connectionStatus === "connected" ? (
              <>
                <Wifi size={12} aria-hidden="true" />
                <span>{t("live.conn_connected")}</span>
              </>
            ) : connectionStatus === "reconnecting" ? (
              <>
                <RefreshCw size={12} className="spin-slow" aria-hidden="true" />
                <span>{t("live.conn_reconnecting")}</span>
              </>
            ) : connectionStatus === "polling" ? (
              <>
                <Activity size={12} aria-hidden="true" />
                <span>{t("live.conn_polling")}</span>
              </>
            ) : (
              <>
                <WifiOff size={12} aria-hidden="true" />
                <span>{t("live.conn_offline")}</span>
              </>
            )}
          </div>

          {/* Manual Refresh Action */}
          {onRefresh && (
            <button
              type="button"
              className="sample-btn"
              onClick={onRefresh}
              disabled={isLoading}
              title={t("live.refresh_now")}
              style={{ padding: "3px 8px", fontSize: 11 }}
            >
              <RefreshCw
                size={11}
                className={isLoading ? "spin-icon" : ""}
                style={{ display: "inline", marginRight: 4 }}
                aria-hidden="true"
              />
              {t("live.refresh_now")}
            </button>
          )}
        </div>
      )}
    </div>
  );
}
