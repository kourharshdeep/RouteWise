"""RouteWise Week 07: Retrospective Risk Precomputation Script.

Precomputes segment disruption risk across the Ramban-Banihal NH-44 corridor
for the historical observation period (2021-01-06 to 2025-12-31) using the
trained ST-GNN checkpoint.

Adheres to core operating principles:
- Checks output collisions before writing; requires explicit --overwrite.
- Honestly metadata-tags results as retrospective historical reanalysis,
  never representing backtests as live operational forecasts.
- Measures and reports CPU inference latency (median and p95).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
import pandas as pd

# Add repo root to python path for imports
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.models.inference import RiskInferenceEngine


def precompute_corridor_risk(
    data_dir: str | Path = "data",
    checkpoint_path: str | Path = "stgnn_best.pt",
    output_path: str | Path = "cache/precomputed_risk_cache.json",
    start_date: str = "2021-01-06",
    end_date: str = "2025-12-31",
    thresholds: tuple[float, float] = (0.10, 0.35),
    overwrite: bool = False,
    sample_stride_days: int = 1,
) -> Dict[str, Any]:
    """Runs batch retrospective inference over the corridor historical dates."""
    data_path = Path(data_dir)
    out_file = Path(output_path)
    
    # 1. Output collision safeguard
    if out_file.exists() and not overwrite:
        raise FileExistsError(
            f"Target output file already exists at '{out_file}'. "
            f"Use --overwrite to replace it."
        )

    out_file.parent.mkdir(parents=True, exist_ok=True)

    # 2. Load model and data
    print(f"Loading checkpoint from: {checkpoint_path}")
    engine = RiskInferenceEngine(checkpoint_path=checkpoint_path, device="cpu")

    weather_file = data_path / "weather_daily_by_segment.csv"
    static_file = data_path / "segment_static.csv"
    if not weather_file.exists():
        raise FileNotFoundError(f"Weather data not found at: {weather_file}")
    if not static_file.exists():
        raise FileNotFoundError(f"Static segment data not found at: {static_file}")

    print("Loading weather and static datasets...")
    weather_df = pd.read_csv(weather_file)
    static_df = pd.read_csv(static_file)

    weather_df["date"] = pd.to_datetime(weather_df["date"])
    all_dates = pd.date_range(start=start_date, end=end_date, freq=f"{sample_stride_days}D")
    print(f"Evaluating {len(all_dates)} historical dates from {start_date} to {end_date} (stride={sample_stride_days})...")

    # 3. Batch evaluation with latency tracking
    latencies_ms: List[float] = []
    date_records: Dict[str, Dict[str, Any]] = {}

    for i, target_dt in enumerate(all_dates):
        t0 = time.perf_counter()
        predictions = engine.predict_corridor(
            target_date=target_dt,
            weather_df=weather_df,
            static_df=static_df,
            thresholds=thresholds,
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        latencies_ms.append(elapsed_ms)

        date_str = target_dt.strftime("%Y-%m-%d")
        date_records[date_str] = {
            p.segment_id: {
                "risk_score": p.risk_score,
                "risk_tier": p.risk_tier,
                "status": p.status,
            }
            for p in predictions
        }

        if (i + 1) % 250 == 0 or (i + 1) == len(all_dates):
            print(f"  Processed {i + 1:4d} / {len(all_dates):4d} dates | "
                  f"Last batch latency: {elapsed_ms:.2f} ms")

    # 4. Latency statistics
    median_latency = float(np.median(latencies_ms))
    p95_latency = float(np.percentile(latencies_ms, 95))
    mean_latency = float(np.mean(latencies_ms))

    # 5. Build structured cache bundle
    cache_bundle: Dict[str, Any] = {
        "metadata": {
            "dataset_type": "retrospective_historical_backtest",
            "meteorological_source": "ERA5-Land reanalysis via Copernicus CDS",
            "is_live_operational_forecast": False,
            "prediction_horizon_hours": 24,
            "lookback_window_days": 7,
            "model_version": engine.model_version,
            "corridor_segment_count": engine.n_segments,
            "thresholds": {
                "tau_med": thresholds[0],
                "tau_high": thresholds[1],
            },
            "date_range": {
                "start": start_date,
                "end": end_date,
            },
            "total_dates_evaluated": len(all_dates),
            "generated_at": pd.Timestamp.now("UTC").isoformat(),
            "cpu_inference_latency_ms": {
                "median": round(median_latency, 2),
                "p95": round(p95_latency, 2),
                "mean": round(mean_latency, 2),
            },
        },
        "daily_predictions": date_records,
    }

    # 6. Write output
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(cache_bundle, f)

    file_size_mb = out_file.stat().st_size / (1024 * 1024)
    print(f"\nPrecomputation complete.")
    print(f"  Output saved to: {out_file} ({file_size_mb:.2f} MB)")
    print(f"  CPU Latency per full corridor (151 segments): "
          f"median = {median_latency:.2f} ms, p95 = {p95_latency:.2f} ms")

    return cache_bundle


def main() -> None:
    parser = argparse.ArgumentParser(description="Precompute historical corridor risk scores.")
    parser.add_argument("--data-dir", default="data", help="Directory containing segment and weather CSVs")
    parser.add_argument("--checkpoint", default="stgnn_best.pt", help="Path to ST-GNN model checkpoint")
    parser.add_argument("--output", default="cache/precomputed_risk_cache.json", help="Destination JSON path")
    parser.add_argument("--start-date", default="2021-01-06", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end-date", default="2025-12-31", help="End date (YYYY-MM-DD)")
    parser.add_argument("--stride", type=int, default=1, help="Stride in days between evaluations")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing output file")
    args = parser.parse_args()

    precompute_corridor_risk(
        data_dir=args.data_dir,
        checkpoint_path=args.checkpoint,
        output_path=args.output,
        start_date=args.start_date,
        end_date=args.end_date,
        sample_stride_days=args.stride,
        overwrite=args.overwrite,
    )


if __name__ == "__main__":
    main()
