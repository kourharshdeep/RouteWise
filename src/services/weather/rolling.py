"""Rolling Atmospheric Metrics Computation.

Directly adapted from week2b_process_weather.py:
- Rolling rainfall 3-day sum: precip_3d_mm = rolling(3, min_periods=1).sum()
- Rolling rainfall 7-day sum: precip_7d_mm = rolling(7, min_periods=1).sum()
Recent rainfall over 3 and 7 days is a primary trigger for mountain landslides and shooting stones.
"""
from __future__ import annotations

from typing import Optional, Set, Tuple
import pandas as pd


def compute_rolling_precipitation(
    df: pd.DataFrame,
    history_df: Optional[pd.DataFrame] = None,
    segment_col: str = "segment_id",
    date_col: str = "obs_date",
    precip_col: str = "precip_mm",
    flag_incomplete: bool = False,
) -> pd.DataFrame:
    """Computes precip_3d_mm and precip_7d_mm per segment sorted by date.
    
    Ensures that for each segment, observations are chronologically ordered, and
    computes rolling sums matching the methodology of week2b_process_weather.py.
    When history_df is provided, historical observations from preceding days are
    prepended so incremental single-day fetches compute true full-window sums.
    """
    if df.empty:
        return df.copy()

    if precip_col not in df.columns:
        raise ValueError(f"Column '{precip_col}' required to compute rolling precipitation.")

    target_keys: Optional[Set[Tuple[str, str]]] = None
    if history_df is not None and not history_df.empty:
        target_keys = set(zip(df[segment_col].astype(str), df[date_col].astype(str)))
        work_df = pd.concat([history_df, df], ignore_index=True)
        # Drop duplicates on segment and date, preserving latest fetched values
        work_df = work_df.drop_duplicates(subset=[segment_col, date_col], keep="last")
        flag_incomplete = True
    else:
        work_df = df.copy()

    # Standardize date sorting
    work_df = work_df.sort_values([segment_col, date_col]).reset_index(drop=True)

    # Rolling rainfall sums matching week2b_process_weather.py
    work_df["precip_3d_mm"] = (
        work_df.groupby(segment_col)[precip_col]
        .transform(lambda s: s.rolling(3, min_periods=1).sum())
        .round(4)
    )
    work_df["precip_7d_mm"] = (
        work_df.groupby(segment_col)[precip_col]
        .transform(lambda s: s.rolling(7, min_periods=1).sum())
        .round(4)
    )

    # Check 7-day lookback completeness when requested or history is attached
    if flag_incomplete:
        if "quality_flag" not in work_df.columns:
            work_df["quality_flag"] = "OK"

        count_7 = work_df.groupby(segment_col)[precip_col].transform(lambda s: s.rolling(7).count())
        date_diff_6 = work_df.groupby(segment_col)[date_col].transform(
            lambda s: (pd.to_datetime(s) - pd.to_datetime(s).shift(6)).dt.days
        )
        is_complete_7d = (count_7 == 7) & (date_diff_6 == 6)

        # Flag incomplete windows unless already marked with MISSING_DATA
        mask_partial = (~is_complete_7d) & (work_df["quality_flag"] != "MISSING_DATA")
        work_df.loc[mask_partial, "quality_flag"] = "PARTIAL_WINDOW"

    if target_keys is not None:
        mask = [
            (s, d) in target_keys
            for s, d in zip(work_df[segment_col].astype(str), work_df[date_col].astype(str))
        ]
        res = work_df[mask].copy().reset_index(drop=True)
        return res

    return work_df


