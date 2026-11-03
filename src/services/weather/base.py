"""Abstract Weather Provider Base Class and Feature Specifications.

Honest Framing:
The RouteWise ST-GNN model was trained on ERA5-Land atmospheric reanalysis.
Dynamic features must strictly adhere to the 7 dynamic columns expected by the
model checkpoint in order and units:
[precip_mm, snowfall_mm_we, temp_mean_c, temp_min_c, snow_depth_m, precip_3d_mm, precip_7d_mm].
"""
from __future__ import annotations

import csv
from abc import ABC, abstractmethod
from datetime import date, datetime
from pathlib import Path
from typing import List, Sequence

import pandas as pd
import torch

# Standard dynamic feature names and order as verified from stgnn_best.pt and data/weather_daily_by_segment.csv
EXPECTED_DYNAMIC_FEATURES: List[str] = [
    "precip_mm",
    "snowfall_mm_we",
    "temp_mean_c",
    "temp_min_c",
    "snow_depth_m",
    "precip_3d_mm",
    "precip_7d_mm",
]


def load_checkpoint_dynamic_columns(checkpoint_path: Path | str = "stgnn_best.pt") -> List[str]:
    """Reads the exact dynamic feature column names and order from the checkpoint metadata."""
    path = Path(checkpoint_path)
    if not path.is_file():
        raise FileNotFoundError(f"Model checkpoint not found at {path}")
    ckpt = torch.load(path, map_location="cpu", weights_only=False)
    if not isinstance(ckpt, dict) or "dynamic_columns" not in ckpt:
        raise ValueError(f"Checkpoint at {path} does not contain 'dynamic_columns' metadata.")
    cols = list(ckpt["dynamic_columns"])
    return cols


def load_csv_dynamic_columns(csv_path: Path | str = "data/weather_daily_by_segment.csv") -> List[str]:
    """Reads the dynamic feature columns from the weather daily CSV header."""
    path = Path(csv_path)
    if not path.is_file():
        raise FileNotFoundError(f"Weather CSV not found at {path}")
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
    # The header starts with segment_id, date, followed by the 7 dynamic features
    if len(header) < 9 or header[0] != "segment_id" or header[1] != "date":
        raise ValueError(f"Unexpected CSV header format in {path}: {header}")
    return header[2:9]


class WeatherProvider(ABC):
    """Abstract base provider for fetching atmospheric weather observations.
    
    Subclasses must implement fetch() returning a pandas DataFrame with daily observations.
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Identifying name of the weather provider."""
        ...

    @abstractmethod
    def fetch(
        self,
        start_date: str | date,
        end_date: str | date | None = None,
        segments: Sequence[str] | None = None,
    ) -> pd.DataFrame:
        """Fetches weather observations for the specified date range and optional segments.
        
        Returns:
            pd.DataFrame containing:
                - segment_id: str
                - obs_date: str (YYYY-MM-DD)
                - 7 dynamic features in exact order
                - source: str
                - fetched_at: str (ISO UTC)
                - quality_flag: str ('OK', 'ESTIMATED', etc.)
        """
        ...
