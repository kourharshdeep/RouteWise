"""RouteWise Week 07: ST-GNN Model Inference Engine.

Provides versioned CPU inference for road segment disruption risk on the
Ramban-Banihal NH-44 corridor using the trained ST-GNN checkpoint.

Adheres to core operating principles:
- Raw outputs are advisory risk scores (relative ranking), not calibrated event probabilities.
- Explicit status tagging: distinguishes normal evaluation ('OK') from 'MISSING_DATA'
  and 'STALE_DATA'.
- Never defaults to 'Low' risk when inputs are missing, out-of-order, or stale.
"""
from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
import torch
import torch.nn as nn


class STGNNModule(nn.Module):
    """Spatio-Temporal Graph Neural Network architecture matching week6_stgnn.py."""

    def __init__(
        self,
        f_dyn: int,
        f_static: int,
        A_hat: np.ndarray,
        hidden: int = 32,
        dropout: float = 0.2,
    ) -> None:
        super().__init__()
        self.register_buffer("A", torch.as_tensor(A_hat, dtype=torch.float32))
        self.gc1 = nn.Linear(f_dyn, hidden)
        self.gc2 = nn.Linear(hidden, hidden)
        self.gru = nn.GRU(hidden, hidden, batch_first=True)
        self.drop = nn.Dropout(dropout)
        self.head = nn.Sequential(
            nn.Linear(hidden + f_static, hidden),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(hidden, 1),
        )

    def forward(self, x: torch.Tensor, s: torch.Tensor) -> torch.Tensor:
        """Forward pass.
        
        Args:
            x: Dynamic features [B, W, N, F_dyn] where B=batch dates, W=window days,
               N=number of segments, F_dyn=dynamic features.
            s: Static features [N, F_static].
            
        Returns:
            Logits of shape [B, N].
        """
        B, W, N, _ = x.shape
        # Spatial graph convolution across segments
        h = torch.relu(self.A @ self.gc1(x))
        h = self.drop(torch.relu(self.A @ self.gc2(h)))
        # Reshape for GRU over the W temporal steps: [B * N, W, hidden]
        h = h.permute(0, 2, 1, 3).reshape(B * N, W, -1)
        _, hn = self.gru(h)
        hn = hn[-1].reshape(B, N, -1)
        # Broadcast static features across batch: [B, N, F_static]
        s_expanded = s.unsqueeze(0).expand(B, -1, -1)
        # Concatenate temporal representation and static attributes
        combined = torch.cat([hn, s_expanded], dim=-1)
        return self.head(combined).squeeze(-1)


@dataclass(frozen=True)
class SegmentPrediction:
    """Typed prediction record for a single corridor road segment."""

    segment_id: str
    risk_score: Optional[float]  # Raw sigmoid output in [0.0, 1.0], None if missing/stale
    risk_tier: str  # "Low", "Medium", "High", or "UNKNOWN"
    status: str  # "OK", "MISSING_DATA", "STALE_DATA"
    is_stale: bool
    model_version: str
    prediction_horizon_hours: int
    data_timestamp: str
    warning: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class RiskInferenceEngine:
    """Loads stgnn_best.pt and evaluates segment disruption risk on CPU."""

    def __init__(
        self,
        checkpoint_path: str | Path = "stgnn_best.pt",
        device: str = "cpu",
    ) -> None:
        self.checkpoint_path = Path(checkpoint_path)
        if not self.checkpoint_path.exists():
            raise FileNotFoundError(f"Checkpoint not found at: {self.checkpoint_path}")

        self.device = torch.device(device)
        self.model_version = self._calculate_checkpoint_hash()
        self._load_checkpoint()

    def _calculate_checkpoint_hash(self) -> str:
        """Returns the first 16 characters of the SHA-256 checkpoint checksum."""
        hasher = hashlib.sha256()
        with open(self.checkpoint_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                hasher.update(chunk)
        return hasher.hexdigest()[:16]

    def _load_checkpoint(self) -> None:
        """Loads model weights, normalization statistics, and segment metadata."""
        try:
            ckpt = torch.load(self.checkpoint_path, map_location=self.device, weights_only=False)
        except TypeError:
            ckpt = torch.load(self.checkpoint_path, map_location=self.device)
        self.hyperparams = ckpt["hyperparams"]
        self.A_hat = np.asarray(ckpt["A_hat"], dtype=np.float32)
        self.norm = ckpt["norm"]
        self.segment_order: List[str] = list(ckpt["segment_order"])
        self.dynamic_columns: List[str] = list(ckpt["dynamic_columns"])
        self.rain_columns: List[str] = list(ckpt["rain_columns"])
        self.static_columns: List[str] = list(ckpt["static_columns"])
        self.window_size: int = int(self.hyperparams.get("window", 7))

        self.seg_to_idx = {seg: i for i, seg in enumerate(self.segment_order)}
        self.n_segments = len(self.segment_order)

        # Pre-convert normalization vectors to float32 numpy arrays
        self.dyn_mean = np.asarray(self.norm["dyn_mean"], dtype=np.float32)
        self.dyn_std = np.asarray(self.norm["dyn_std"], dtype=np.float32)
        self.static_mean = np.asarray(self.norm["static_mean"], dtype=np.float32)
        self.static_std = np.asarray(self.norm["static_std"], dtype=np.float32)

        # Initialize neural network module
        self.model = STGNNModule(
            f_dyn=self.hyperparams["f_dyn"],
            f_static=self.hyperparams["f_static"],
            A_hat=self.A_hat,
            hidden=self.hyperparams["hidden"],
            dropout=self.hyperparams["dropout"],
        )
        self.model.load_state_dict(ckpt["state_dict"])
        self.model.to(self.device)
        self.model.eval()  # Disables dropout for deterministic inference

    def prepare_static_tensor(self, static_df: pd.DataFrame) -> torch.Tensor:
        """Formats and normalizes static segment features.
        
        Args:
            static_df: DataFrame containing 'segment_id' and numeric static columns.
            
        Returns:
            Normalized tensor of shape [151, 4].
        """
        missing_segs = set(self.segment_order) - set(static_df["segment_id"])
        if missing_segs:
            raise ValueError(f"static_df is missing {len(missing_segs)} corridor segments.")

        df = static_df.drop_duplicates("segment_id").set_index("segment_id")
        df = df.reindex(self.segment_order)

        missing_cols = [c for c in self.static_columns if c not in df.columns]
        if missing_cols:
            raise KeyError(f"static_df missing static columns: {missing_cols}")

        arr = df[self.static_columns].to_numpy(dtype=np.float32)
        norm_arr = np.nan_to_num((arr - self.static_mean) / self.static_std, nan=0.0)
        return torch.as_tensor(norm_arr, dtype=torch.float32, device=self.device)

    def extract_weather_window(
        self,
        weather_df: pd.DataFrame,
        target_date: pd.Timestamp | str,
    ) -> Tuple[Optional[torch.Tensor], str, Optional[str]]:
        """Extracts and normalizes the 7-day lookback window for target_date.
        
        Returns:
            (tensor [1, 7, 151, 7] or None, status, warning_message)
        """
        target_dt = pd.to_datetime(target_date)
        window_dates = pd.date_range(end=target_dt, periods=self.window_size, freq="D")

        # Filter weather for the corridor
        w_df = weather_df.copy()
        w_df["date"] = pd.to_datetime(w_df["date"])
        sub = w_df[w_df["date"].isin(window_dates) & w_df["segment_id"].isin(self.seg_to_idx)]

        # Check coverage
        present_dates = set(sub["date"].unique())
        if len(present_dates) < self.window_size:
            return None, "MISSING_DATA", (
                f"Incomplete weather window: expected {self.window_size} days, "
                f"found {len(present_dates)} days between {window_dates[0].date()} and {target_dt.date()}."
            )

        # Multi-index alignment: [dates, segments]
        full_index = pd.MultiIndex.from_product(
            [window_dates, self.segment_order], names=["date", "segment_id"]
        )
        wx = sub.drop_duplicates(["date", "segment_id"]).set_index(["date", "segment_id"])
        
        missing_cols = [c for c in self.dynamic_columns if c not in wx.columns]
        if missing_cols:
            return None, "MISSING_DATA", f"Missing weather columns: {missing_cols}"

        reindexed = wx[self.dynamic_columns].reindex(full_index)
        arr = reindexed.to_numpy(dtype=np.float32).copy().reshape(
            self.window_size, self.n_segments, len(self.dynamic_columns)
        )

        # Check if entire segments are missing
        nan_fraction = np.isnan(arr).mean()
        if nan_fraction > 0.25:
            return None, "MISSING_DATA", f"Excessive missing weather values: {nan_fraction * 100:.1f}% NaNs."

        # Apply log1p scaling to rain columns
        for c in self.rain_columns:
            j = self.dynamic_columns.index(c)
            arr[:, :, j] = np.log1p(np.clip(arr[:, :, j], 0.0, None))

        # Standardize using training statistics
        norm_arr = (arr - self.dyn_mean) / self.dyn_std
        norm_arr = np.nan_to_num(norm_arr, nan=0.0)

        # Reshape to [1, W, N, F]
        x_tensor = torch.as_tensor(norm_arr[None, ...], dtype=torch.float32, device=self.device)
        return x_tensor, "OK", None

    def predict_corridor(
        self,
        target_date: str | pd.Timestamp,
        weather_df: pd.DataFrame,
        static_df: pd.DataFrame,
        thresholds: Tuple[float, float] = (0.15, 0.35),
        eval_time: Optional[datetime] = None,
        stale_hours_limit: float = 24.0,
    ) -> List[SegmentPrediction]:
        """Evaluates disruption risk across all 151 segments on target_date.
        
        Args:
            target_date: Date to evaluate (e.g. '2023-07-09').
            weather_df: Daily weather observations dataframe.
            static_df: Static segment characteristics dataframe.
            thresholds: (tau_med, tau_high) risk tier cutoffs from validation set.
            eval_time: Current simulation or wall-clock time for staleness checking.
            stale_hours_limit: Maximum allowed age in hours before data is marked stale.
            
        Returns:
            List of 151 SegmentPrediction objects.
        """
        tau_med, tau_high = thresholds
        target_dt = pd.to_datetime(target_date)
        iso_timestamp = target_dt.strftime("%Y-%m-%dT00:00:00Z")

        # 1. Staleness check
        is_stale = False
        staleness_warning = None
        if eval_time is not None:
            eval_dt = eval_time if eval_time.tzinfo else eval_time.replace(tzinfo=timezone.utc)
            target_aware = target_dt.tz_localize("UTC") if target_dt.tzinfo is None else target_dt
            age_hours = (eval_dt - target_aware).total_seconds() / 3600.0
            if age_hours > stale_hours_limit:
                is_stale = True
                staleness_warning = (
                    f"Weather observation timestamp {iso_timestamp} is stale "
                    f"({age_hours:.1f}h > {stale_hours_limit}h limit)."
                )

        # 2. Weather window extraction & validation
        x_tensor, status, warning = self.extract_weather_window(weather_df, target_dt)
        if status != "OK" or x_tensor is None:
            # Handle missing data: explicitly UNKNOWN, never Low
            return [
                SegmentPrediction(
                    segment_id=seg,
                    risk_score=None,
                    risk_tier="UNKNOWN",
                    status="MISSING_DATA",
                    is_stale=is_stale,
                    model_version=self.model_version,
                    prediction_horizon_hours=24,
                    data_timestamp=iso_timestamp,
                    warning=warning,
                )
                for seg in self.segment_order
            ]

        # 3. Handle stale data: if stale, flag status and warning explicitly
        if is_stale:
            status = "STALE_DATA"
            warning = staleness_warning

        # 4. Prepare static features and forward pass
        s_tensor = self.prepare_static_tensor(static_df)
        with torch.no_grad():
            logits = self.model(x_tensor, s_tensor)
            scores = torch.sigmoid(logits).squeeze(0).cpu().numpy()

        # 5. Build structured predictions
        predictions: List[SegmentPrediction] = []
        for i, seg in enumerate(self.segment_order):
            score = float(scores[i])
            if status == "STALE_DATA":
                tier = "UNKNOWN"
            elif score >= tau_high:
                tier = "High"
            elif score >= tau_med:
                tier = "Medium"
            else:
                tier = "Low"

            predictions.append(
                SegmentPrediction(
                    segment_id=seg,
                    risk_score=round(score, 4),
                    risk_tier=tier,
                    status=status,
                    is_stale=is_stale,
                    model_version=self.model_version,
                    prediction_horizon_hours=24,
                    data_timestamp=iso_timestamp,
                    warning=warning,
                )
            )

        return predictions
