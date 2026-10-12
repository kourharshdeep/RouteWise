"""RouteWise Week 07: Automated Inference Engine Tests.

Verifies checkpoint loading, output contract, numerical determinism,
rejection of missing and stale data, and CPU execution performance.
"""
from __future__ import annotations

import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import numpy as np
import pandas as pd
import pytest
import torch

from src.models.inference import RiskInferenceEngine, SegmentPrediction


@pytest.fixture(scope="module")
def checkpoint_path() -> str:
    path = Path("stgnn_best.pt")
    assert path.exists(), "stgnn_best.pt must exist in repository root."
    return str(path)


@pytest.fixture(scope="module")
def engine(checkpoint_path: str) -> RiskInferenceEngine:
    return RiskInferenceEngine(checkpoint_path=checkpoint_path, device="cpu")


@pytest.fixture(scope="module")
def static_df() -> pd.DataFrame:
    path = Path("data/segment_static.csv")
    assert path.exists(), "data/segment_static.csv must exist."
    return pd.read_csv(path)


@pytest.fixture(scope="module")
def weather_df() -> pd.DataFrame:
    path = Path("data/weather_daily_by_segment.csv")
    assert path.exists(), "data/weather_daily_by_segment.csv must exist."
    return pd.read_csv(path)


def test_checkpoint_integrity_and_shapes(engine: RiskInferenceEngine) -> None:
    """Verifies that the loaded checkpoint contains expected shapes and corridor metadata."""
    assert engine.n_segments == 151
    assert len(engine.segment_order) == 151
    assert engine.A_hat.shape == (151, 151)
    assert len(engine.dynamic_columns) == 7
    assert len(engine.static_columns) == 4
    assert len(engine.rain_columns) == 3
    assert engine.window_size == 7
    assert engine.model_version == "68b04504eae6062c"

    # Verify model is in eval mode
    assert not engine.model.training


def test_inference_determinism_and_contract(
    engine: RiskInferenceEngine,
    weather_df: pd.DataFrame,
    static_df: pd.DataFrame,
) -> None:
    """Verifies that inference returns 151 typed predictions and is strictly deterministic."""
    target_date = "2023-07-09"

    # Run inference twice
    run1 = engine.predict_corridor(target_date, weather_df, static_df)
    run2 = engine.predict_corridor(target_date, weather_df, static_df)

    assert len(run1) == 151
    assert len(run2) == 151

    # Check contracts and bit-identical scores
    for p1, p2 in zip(run1, run2):
        assert isinstance(p1, SegmentPrediction)
        assert p1.segment_id == p2.segment_id
        assert p1.risk_score == p2.risk_score
        assert p1.risk_tier == p2.risk_tier
        assert p1.status == "OK"
        assert not p1.is_stale
        assert p1.risk_score is not None
        assert 0.0 <= p1.risk_score <= 1.0
        assert p1.risk_tier in ("Low", "Medium", "High")
        assert p1.model_version == engine.model_version
        assert p1.prediction_horizon_hours == 24
        assert p1.warning is None


def test_missing_weather_window_rejection(
    engine: RiskInferenceEngine,
    weather_df: pd.DataFrame,
    static_df: pd.DataFrame,
) -> None:
    """Verifies that incomplete weather windows return MISSING_DATA and UNKNOWN, never Low."""
    # Create an artificially truncated weather dataframe with only 3 days
    truncated_dates = ["2023-07-07", "2023-07-08", "2023-07-09"]
    truncated_weather = weather_df[weather_df["date"].isin(truncated_dates)].copy()

    predictions = engine.predict_corridor("2023-07-09", truncated_weather, static_df)

    assert len(predictions) == 151
    for p in predictions:
        assert p.status == "MISSING_DATA"
        assert p.risk_tier == "UNKNOWN"
        assert p.risk_score is None
        assert p.warning is not None
        assert "Incomplete weather window" in p.warning
        # CRITICAL: never represent missing data as Low risk
        assert p.risk_tier != "Low"


def test_stale_data_rejection(
    engine: RiskInferenceEngine,
    weather_df: pd.DataFrame,
    static_df: pd.DataFrame,
) -> None:
    """Verifies that stale weather observations are explicitly tagged as STALE_DATA and UNKNOWN."""
    target_date = "2023-07-09"
    # Simulate an evaluation time 72 hours after the weather timestamp
    eval_time = datetime(2023, 7, 12, 12, 0, tzinfo=timezone.utc)

    predictions = engine.predict_corridor(
        target_date=target_date,
        weather_df=weather_df,
        static_df=static_df,
        eval_time=eval_time,
        stale_hours_limit=24.0,
    )

    assert len(predictions) == 151
    for p in predictions:
        assert p.status == "STALE_DATA"
        assert p.is_stale is True
        assert p.risk_tier == "UNKNOWN"
        assert p.warning is not None
        assert "is stale" in p.warning
        # CRITICAL: never represent stale data as Low risk
        assert p.risk_tier != "Low"


def test_cpu_latency_benchmark(
    engine: RiskInferenceEngine,
    weather_df: pd.DataFrame,
    static_df: pd.DataFrame,
) -> None:
    """Measures CPU inference latency across 10 repeated passes."""
    target_date = "2023-07-09"
    latencies: list[float] = []

    # Warmup
    engine.predict_corridor(target_date, weather_df, static_df)

    # Benchmark 10 iterations
    for _ in range(10):
        t0 = time.perf_counter()
        engine.predict_corridor(target_date, weather_df, static_df)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        latencies.append(elapsed_ms)

    median_ms = float(np.median(latencies))
    p95_ms = float(np.percentile(latencies, 95))

    print(f"\n[Benchmark] Full corridor (151 segments) latency: median={median_ms:.2f}ms, p95={p95_ms:.2f}ms")
    # Verify execution completes in sub-second time on CPU without hanging
    assert median_ms < 500.0
    assert p95_ms < 1000.0
