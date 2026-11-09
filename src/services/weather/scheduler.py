"""Background Weather Fetch Scheduler for RouteWise.

Honest Framing & Fault Isolation:
- Controlled by ROUTEWISE_LIVE_MODE (off | replay | live).
- When mode is 'off', scheduler remains inert.
- When mode is 'live', queries OpenMeteoProvider every LIVE_WEATHER_INTERVAL_MINUTES.
- When mode is 'replay', advances ReplayProvider.
- Network or provider failures are logged, tracked, and NEVER crash the application.
  Failure allows data in weather_observation to naturally age into STALE status.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, Optional

from src.api.config import settings
from src.services.weather.base import WeatherProvider
from src.services.weather.open_meteo import OpenMeteoProvider
from src.services.weather.replay import ReplayProvider
from src.services.weather.storage import WeatherStorage, weather_storage

logger = logging.getLogger("weather_scheduler")


class WeatherScheduler:
    """Async background task scheduler managing live or replay weather ingestion."""

    def __init__(
        self,
        storage: Optional[WeatherStorage] = None,
        provider: Optional[WeatherProvider] = None,
    ) -> None:
        self.storage = storage or weather_storage
        self.provider = provider
        self.mode = settings.live_mode
        self.interval_minutes = settings.live_weather_interval_minutes

        self._task: Optional[asyncio.Task] = None
        self._running: bool = False
        self._last_fetch_time: Optional[str] = None
        self._last_status: str = "IDLE"
        self._last_error: Optional[str] = None
        self._consecutive_failures: int = 0
        self._records_fetched_last_run: int = 0

    def _get_provider(self) -> WeatherProvider:
        if self.provider is not None:
            return self.provider
        if self.mode == "live":
            return OpenMeteoProvider(storage=self.storage)
        elif self.mode == "replay":
            return ReplayProvider()
        else:
            raise RuntimeError(f"Cannot initialize provider in mode: '{self.mode}'")

    async def run_once(self) -> int:
        """Executes a single weather fetch and storage cycle safely."""
        if self.mode == "off":
            logger.debug("ROUTEWISE_LIVE_MODE is 'off'; skipping weather fetch.")
            return 0

        try:
            provider = self._get_provider()
            logger.info("Executing scheduled weather fetch using provider: %s", provider.provider_name)

            today = datetime.now(timezone.utc).date()
            if self.mode == "live":
                # For live mode, backfill at least 13 days (14 days total) to ensure all days in the
                # 7-day evaluation window have complete 7-day trailing lookback history without PARTIAL_WINDOW
                start_date = today - timedelta(days=13)
                end_date = today
            else:
                # For replay mode, fetch a known demonstration week or latest available
                start_date = date(2024, 7, 8)
                end_date = date(2024, 7, 15)

            # Offload synchronous fetch to thread pool to avoid blocking asyncio loop
            loop = asyncio.get_running_loop()
            df = await loop.run_in_executor(None, provider.fetch, start_date, end_date)

            if df.empty:
                logger.warning("Provider %s returned empty DataFrame.", provider.provider_name)
                self._last_status = "WARNING"
                self._last_error = "Provider returned empty DataFrame"
                self._consecutive_failures += 1
                return 0

            # Upsert into isolated runtime storage
            upserted = await loop.run_in_executor(None, self.storage.upsert_observations, df)

            # Recompute live risk after successful weather fetch
            try:
                from src.services.live_risk_service import LiveRiskService, live_risk_service
                risk_svc = LiveRiskService(storage=self.storage) if self.storage is not None else live_risk_service
                await loop.run_in_executor(None, risk_svc.compute_live_risk)
                logger.info("Live risk recomputed successfully following weather fetch.")
            except Exception as e:
                logger.error("Error recomputing live risk post-fetch: %s", e)

            self._last_fetch_time = datetime.now(timezone.utc).isoformat()
            self._last_status = "SUCCESS"
            self._last_error = None
            self._consecutive_failures = 0
            self._records_fetched_last_run = upserted

            logger.info(
                "Scheduled fetch complete: upserted %d observations into %s (provider: %s).",
                upserted,
                self.storage.db_path,
                provider.provider_name,
            )
            return upserted

        except Exception as exc:
            self._last_fetch_time = datetime.now(timezone.utc).isoformat()
            self._last_status = "ERROR"
            self._last_error = str(exc)
            self._consecutive_failures += 1
            logger.error(
                "Scheduled weather fetch failed (consecutive failures: %d): %s",
                self._consecutive_failures,
                exc,
                exc_info=True,
            )
            return 0

    async def _loop(self) -> None:
        """Periodic loop executing fetch every interval_minutes."""
        logger.info(
            "WeatherScheduler loop started (mode: %s, interval: %d min).",
            self.mode,
            self.interval_minutes,
        )
        while self._running:
            await self.run_once()
            try:
                await asyncio.sleep(self.interval_minutes * 60)
            except asyncio.CancelledError:
                break
        logger.info("WeatherScheduler loop stopped.")

    def start(self) -> None:
        """Starts the scheduler if mode is live or replay."""
        if self.mode == "off":
            logger.info("ROUTEWISE_LIVE_MODE is 'off'; WeatherScheduler will not start.")
            return

        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        """Gracefully halts the background scheduler."""
        if not self._running:
            return

        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    def get_status(self) -> Dict[str, Any]:
        """Returns health and execution metrics for monitoring."""
        return {
            "mode": self.mode,
            "is_running": self._running,
            "interval_minutes": self.interval_minutes,
            "provider": self.provider.provider_name if self.provider else ("open-meteo" if self.mode == "live" else "replay"),
            "last_fetch_time": self._last_fetch_time,
            "last_status": self._last_status,
            "last_error": self._last_error,
            "consecutive_failures": self._consecutive_failures,
            "records_last_run": self._records_fetched_last_run,
        }


weather_scheduler = WeatherScheduler()

