"""RouteWise Week 07: Automated Calibration and Threshold Tests.

Verifies Brier score calculation, reliability curves, threshold scan
properties, and monotonic risk tier mapping.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import numpy as np
import pytest

from src.models.calibration import (
    assign_risk_tier,
    compute_brier_score,
    compute_reliability_curve,
    evaluate_threshold,
    scan_validation_thresholds,
)


def test_brier_score_known_vectors() -> None:
    """Verifies that compute_brier_score produces mathematically exact mean squared error."""
    # Perfect predictions: error = 0
    y_true = np.array([0, 1, 1, 0])
    y_prob = np.array([0.0, 1.0, 1.0, 0.0])
    assert compute_brier_score(y_true, y_prob) == 0.0

    # Completely inverted predictions: error = 1.0
    y_inv = np.array([1.0, 0.0, 0.0, 1.0])
    assert compute_brier_score(y_true, y_inv) == 1.0

    # Uniform 0.5 predictions: error = (0.5^2) = 0.25
    y_half = np.array([0.5, 0.5, 0.5, 0.5])
    assert compute_brier_score(y_true, y_half) == 0.25


def test_reliability_curve_properties() -> None:
    """Verifies binning structure and Expected Calibration Error computation."""
    y_true = np.array([0, 0, 0, 1, 1, 1, 1, 1])
    y_prob = np.array([0.1, 0.15, 0.2, 0.6, 0.7, 0.8, 0.9, 0.95])

    res = compute_reliability_curve(y_true, y_prob, n_bins=5)

    assert res["n_bins"] == 5
    assert len(res["bin_counts"]) == 5
    assert sum(res["bin_counts"]) == len(y_true)
    assert 0.0 <= res["expected_calibration_error"] <= 1.0


def test_evaluate_threshold_calculation() -> None:
    """Verifies confusion matrix arithmetic and precision/recall trade-offs."""
    y_true = np.array([1, 1, 0, 0, 1, 0])
    y_prob = np.array([0.9, 0.4, 0.3, 0.1, 0.6, 0.7])
    # At threshold 0.5:
    # predictions: [1, 0, 0, 0, 1, 1]
    # TP: items 0, 4 (2)
    # FP: item 5 (1)
    # FN: item 1 (1)
    # TN: items 2, 3 (2)

    perf = evaluate_threshold(y_true, y_prob, threshold=0.5)

    assert perf.threshold == 0.5
    assert perf.tp == 2
    assert perf.fp == 1
    assert perf.fn == 1
    assert perf.tn == 2
    assert pytest.approx(perf.precision, 0.001) == 2.0 / 3.0
    assert pytest.approx(perf.recall, 0.001) == 2.0 / 3.0
    assert pytest.approx(perf.false_negative_rate, 0.001) == 1.0 / 3.0


def test_assign_risk_tier_monotonicity() -> None:
    """Verifies that risk scores map monotonically to Low, Medium, High, or UNKNOWN."""
    thresholds = (0.10, 0.35)

    # Normal scores
    assert assign_risk_tier(0.04, thresholds, status="OK") == "Low"
    assert assign_risk_tier(0.0999, thresholds, status="OK") == "Low"
    assert assign_risk_tier(0.10, thresholds, status="OK") == "Medium"
    assert assign_risk_tier(0.25, thresholds, status="OK") == "Medium"
    assert assign_risk_tier(0.3499, thresholds, status="OK") == "Medium"
    assert assign_risk_tier(0.35, thresholds, status="OK") == "High"
    assert assign_risk_tier(0.85, thresholds, status="OK") == "High"

    # Edge and failure conditions
    assert assign_risk_tier(None, thresholds, status="OK") == "UNKNOWN"
    assert assign_risk_tier(0.05, thresholds, status="MISSING_DATA") == "UNKNOWN"
    assert assign_risk_tier(0.05, thresholds, status="STALE_DATA") == "UNKNOWN"
    assert assign_risk_tier(0.95, thresholds, status="STALE_DATA") == "UNKNOWN"


def test_threshold_scan_monotonic_recall() -> None:
    """Verifies that increasing thresholds monotonically decreases recall and increases false negatives."""
    y_true = np.array([1, 1, 1, 1, 0, 0, 0, 0, 0, 0])
    y_prob = np.array([0.8, 0.6, 0.4, 0.2, 0.7, 0.5, 0.3, 0.2, 0.1, 0.05])

    thresholds = [0.1, 0.3, 0.5, 0.7]
    scan = scan_validation_thresholds(y_true, y_prob, thresholds)

    recalls = [p.recall for p in scan]
    fns = [p.fn for p in scan]

    # Recall must be non-increasing
    for i in range(len(recalls) - 1):
        assert recalls[i] >= recalls[i + 1]

    # False negatives must be non-decreasing
    for i in range(len(fns) - 1):
        assert fns[i] <= fns[i + 1]
