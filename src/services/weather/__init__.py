"""RouteWise Weather Service Package.

Provides weather observation abstraction, replay ingestion, Open-Meteo live fetching,
clustering, rolling feature computation, and isolated runtime storage.
"""
from __future__ import annotations

from src.services.weather.base import (
    EXPECTED_DYNAMIC_FEATURES,
    WeatherProvider,
    load_checkpoint_dynamic_columns,
    load_csv_dynamic_columns,
)
from src.services.weather.clustering import GridCluster, build_corridor_grid_clusters
from src.services.weather.open_meteo import OpenMeteoProvider
from src.services.weather.replay import ReplayProvider
from src.services.weather.rolling import compute_rolling_precipitation
from src.services.weather.scheduler import WeatherScheduler, weather_scheduler
from src.services.weather.storage import WeatherStorage, weather_storage

__all__ = [
    "EXPECTED_DYNAMIC_FEATURES",
    "WeatherProvider",
    "load_checkpoint_dynamic_columns",
    "load_csv_dynamic_columns",
    "GridCluster",
    "build_corridor_grid_clusters",
    "OpenMeteoProvider",
    "ReplayProvider",
    "compute_rolling_precipitation",
    "WeatherScheduler",
    "weather_scheduler",
    "WeatherStorage",
    "weather_storage",
]
