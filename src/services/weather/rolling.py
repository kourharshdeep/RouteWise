"""Rolling Atmospheric Metrics Computation.

Directly adapted from week2b_process_weather.py:
- Rolling rainfall 3-day sum: precip_3d_mm = rolling(3, min_periods=1).sum()
- Rolling rainfall 7-day sum: precip_7d_mm = rolling(7, min_periods=1).sum()
Recent rainfall over 3 and 7 days is a primary trigger for mountain landslides and shooting stones.
"""
from __future__ import annotations

import pandas as pd


def compute_rolling_precipitation(
    df: pd.DataFrame,
    segment_col: str = "segment_id",
    date_col: str = "obs_date",
    precip_col: str = "precip_mm",
) -> pd.DataFrame:
    """Computes precip_3d_mm and precip_7d_mm per segment sorted by date.
    
    Ensures that for each segment, observations are chronologically ordered, and
    computes rolling sums matching the methodology of week2b_process_weather.py.
    """
    res = df.copy()
    if precip_col not in res.columns:
        raise ValueError(f"Column '{precip_col}' required to compute rolling precipitation.")

    # Standardize date sorting
    res = res.sort_values([segment_col, date_col])

    # Rolling rainfall sums matching week2b_process_weather.py exactly
    res["precip_3d_mm"] = (
        res.groupby(segment_col)[precip_col]
        .transform(lambda s: s.rolling(3, min_periods=1).sum())
        .round(4)
    )
    res["precip_7d_mm"] = (
        res.groupby(segment_col)[precip_col]
        .transform(lambda s: s.rolling(7, min_periods=1).sum())
        .round(4)
    )

    return res
