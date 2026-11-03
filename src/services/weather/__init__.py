"""RouteWise Weather Service Package.

Provides weather observation abstraction, replay ingestion, rolling feature computation,
and isolated runtime storage.
"""
from __future__ import annotations

from src.services.weather.base import (
    EXPECTED_DYNAMIC_FEATURES,
    WeatherProvider,
    load_checkpoint_dynamic_columns,
    load_csv_dynamic_columns,
)
from src.services.weather.replay import ReplayProvider
from src.services.weather.rolling import compute_rolling_precipitation
from src.services.weather.storage import WeatherStorage, weather_storage

__all__ = [
    "EXPECTED_DYNAMIC_FEATURES",
    "WeatherProvider",
    "load_checkpoint_dynamic_columns",
    "load_csv_dynamic_columns",
    "ReplayProvider",
    "WeatherStorage",
    "weather_storage",
    "compute_rolling_precipitation",
]
