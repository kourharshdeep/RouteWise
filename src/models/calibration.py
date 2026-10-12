"""RouteWise Week 07: Calibration and Threshold Analysis.

Evaluates model score calibration and determines defensible risk tier thresholds
(Low, Medium, High) using the 2023 validation split. Applies frozen thresholds
to the 2024-2025 held-out test split.

Adheres to core operating principles:
- Thresholds are selected and justified strictly on validation data (never tuned on test data).
- Explicit trade-off reporting: precision, recall, false negatives, and false positives.
- Evaluates Brier score and reliability curves; honestly documents when data sparsity
  precludes treating scores as calibrated frequentist probabilities.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

import numpy as np
import pandas as pd
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    precision_recall_curve,
    roc_auc_score,
)


@dataclass(frozen=True)
class ThresholdPerformance:
    """Performance metrics for a specific decision threshold cutoff."""

    threshold: float
    tp: int
    fp: int
    tn: int
    fn: int
    precision: float
    recall: float
    f1: float
    false_negative_rate: float


@dataclass(frozen=True)
class EvaluationSplitResult:
    """Evaluation summary on a specific data split."""

    split_name: str
    sample_count: int
    positive_event_count: int
    base_rate: float
    average_precision: float
    brier_score: float
    threshold_performance: Dict[str, ThresholdPerformance]


def compute_brier_score(y_true: np.ndarray, y_prob: np.ndarray) -> float:
    """Computes the Brier score loss: mean squared error between probabilities and binary labels."""
    return float(brier_score_loss(y_true, y_prob))


def compute_reliability_curve(
    y_true: np.ndarray,
    y_prob: np.ndarray,
    n_bins: int = 5,
) -> Dict[str, Any]:
    """Computes empirical calibration bins and Expected Calibration Error (ECE)."""
    bins = np.linspace(0.0, 1.0, n_bins + 1)
    bin_centers = 0.5 * (bins[:-1] + bins[1:])
    
    bin_true_prob = []
    bin_pred_prob = []
    bin_counts = []
    
    ece = 0.0
    total_samples = len(y_true)
    
    for i in range(n_bins):
        low, high = bins[i], bins[i + 1]
        mask = (y_prob >= low) & (y_prob < high if i < n_bins - 1 else y_prob <= high)
        count = int(np.sum(mask))
        bin_counts.append(count)
        if count > 0:
            mean_pred = float(np.mean(y_prob[mask]))
            mean_true = float(np.mean(y_true[mask]))
            bin_pred_prob.append(round(mean_pred, 4))
            bin_true_prob.append(round(mean_true, 4))
            ece += (count / total_samples) * abs(mean_pred - mean_true)
        else:
            bin_pred_prob.append(None)
            bin_true_prob.append(None)

    return {
        "n_bins": n_bins,
        "bins": [round(b, 4) for b in bins.tolist()],
        "bin_counts": bin_counts,
        "bin_pred_prob": bin_pred_prob,
        "bin_true_prob": bin_true_prob,
        "expected_calibration_error": round(float(ece), 4),
    }


def evaluate_threshold(
    y_true: np.ndarray,
    y_prob: np.ndarray,
    threshold: float,
) -> ThresholdPerformance:
    """Calculates confusion matrix and precision/recall trade-offs for a given threshold."""
    y_pred = (y_prob >= threshold).astype(int)
    tp = int(np.sum((y_true == 1) & (y_pred == 1)))
    fp = int(np.sum((y_true == 0) & (y_pred == 1)))
    tn = int(np.sum((y_true == 0) & (y_pred == 0)))
    fn = int(np.sum((y_true == 1) & (y_pred == 0)))

    prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0
    fnr = fn / (tp + fn) if (tp + fn) > 0 else 0.0

    return ThresholdPerformance(
        threshold=round(float(threshold), 4),
        tp=tp,
        fp=fp,
        tn=tn,
        fn=fn,
        precision=round(float(prec), 4),
        recall=round(float(rec), 4),
        f1=round(float(f1), 4),
        false_negative_rate=round(float(fnr), 4),
    )


def scan_validation_thresholds(
    y_true: np.ndarray,
    y_prob: np.ndarray,
    candidate_thresholds: Sequence[float] = (0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.50),
) -> List[ThresholdPerformance]:
    """Scans performance across candidate threshold cutoffs on the validation set."""
    return [evaluate_threshold(y_true, y_prob, t) for t in candidate_thresholds]


def assign_risk_tier(
    risk_score: float | None,
    thresholds: Tuple[float, float],
    status: str = "OK",
) -> str:
    """Maps a risk score to a risk tier using frozen thresholds.
    
    Args:
        risk_score: Model output in [0.0, 1.0], or None.
        thresholds: Tuple of (tau_med, tau_high).
        status: Status flag ("OK", "MISSING_DATA", "STALE_DATA").
        
    Returns:
        One of 'Low', 'Medium', 'High', or 'UNKNOWN'.
    """
    if status != "OK" or risk_score is None:
        return "UNKNOWN"
    tau_med, tau_high = thresholds
    if risk_score >= tau_high:
        return "High"
    elif risk_score >= tau_med:
        return "Medium"
    else:
        return "Low"
