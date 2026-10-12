# RouteWise Model Card: ST-GNN Disruption Risk Forecaster

## 1. Model Overview

- **Model Name:** RouteWise Spatio-Temporal Graph Neural Network (ST-GNN)
- **Model Checkpoint:** `stgnn_best.pt`
- **Checkpoint SHA-256:** `68B04504EAE6062C84927917C05168C34FD17823BA5EF5C13F963D335054006E`
- **Version:** `1.0.0-w7` (`68b04504eae6062c`)
- **Framework:** PyTorch (CPU-compatible inference runtime)
- **Domain:** Disruption risk forecasting (landslide, snow, shooting stone) on mountain highway corridors.

---

## 2. Intended Use and Operating Scope

- **Pilot Corridor:** National Highway 44 (NH-44), Ramban to Banihal stretch in Jammu & Kashmir (latitude 33.211 to 33.475, longitude 75.161 to 75.262).
- **Network Resolution:** 151 road segments (derived from OpenStreetMap via OSMnx).
- **Target Disruption Types:** Geohazard road closures (landslides, debris flows, shooting stones, snow accumulation).
- **Forecast Horizon:** 24-hour forward lookahead ($T+1$) conditioned on the preceding 7-day environmental lookback window ($T-6$ to $T$).
- **Intended Users:** Highway maintenance controllers, emergency logistics dispatchers, and risk-aware routing engines.
- **Operational Status:** Advisory decision-support tool. It does **not** provide safety guarantees or replace official traffic police closures.

---

## 3. Architecture & Feature Representation

```
Weather Tensor [B, 7, 151, 7]
         │
         ▼
  Graph Conv 1 (Linear 7->32 + A_hat) -> ReLU
         │
         ▼
  Graph Conv 2 (Linear 32->32 + A_hat) -> ReLU -> Dropout(0.2)
         │
         ▼
  GRU (32 -> 32, batch_first=True) over 7 days
         │
  Final Temporal State hn [B, 151, 32]
         │
         ├──────────────────────────────┐
         ▼                              ▼
  Static Terrain [151, 4]      Concat -> [B, 151, 36]
                                        │
                                        ▼
                                 Linear(36, 32) -> ReLU -> Dropout(0.2)
                                        │
                                        ▼
                                 Linear(32, 1) -> Logits [B, 151]
                                        │
                                        ▼
                                 Sigmoid -> Advisory Risk Score [0.0, 1.0]
```

### 3.1 Input Features
- **Dynamic Weather (7 features):** `precip_mm`, `snowfall_mm_we`, `temp_mean_c`, `temp_min_c`, `snow_depth_m`, `precip_3d_mm`, `precip_7d_mm` from ERA5-Land reanalysis.
- **Pre-processing:** Log1p scaling on rainfall columns (`precip_mm`, `precip_3d_mm`, `precip_7d_mm`). Z-score standardisation using training period statistics ($\le 2022$).
- **Static Terrain (4 features):** `length_m`, `slope`, `elevation_m`, `is_primary_road` from SRTM DEM (~30 m resolution).
- **Spatial Topology:** Symmetric normalized adjacency matrix $\hat{A} = D^{-1/2}(A + I)D^{-1/2}$ representing 966 directed segment connections.

---

## 4. Chronological Data Split and Training Methodology

To prevent temporal leakage, data is strictly partitioned chronologically:

| Split | Time Period | Total Samples | Real Disruption Events | Base Rate | Role |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Train** | $\le$ 2022-12-31 | 855 | 28 | 3.27% | Model parameter optimization |
| **Validation** | 2023-01-01 to 2023-12-31 | 434 | 14 | 3.23% | Early stopping & threshold selection |
| **Held-out Test** | 2024-01-01 to 2025-12-31 | 680 | 22 | 3.24% | Unbiased final performance evaluation |

- **Class Imbalance Handling:** 1:30 negative sampling (50% uniform random days, 50% top 10% wet days). Training loss uses weighted binary cross-entropy ($pos\_weight \approx 30$).
- **Tuning:** Early stopping on validation average precision (AP). Best checkpoint selected from 5-seed training runs.

---

## 5. Performance and Baseline Comparison

### 5.1 Test Set Average Precision (Held-out 2024–2025)
*Rare-event metric where higher is better. Base rate = 0.032.*

| Model | Test Average Precision (AP) | Note |
| :--- | :--- | :--- |
| **Random Guessing** | 0.032 | Historical base rate |
| **Rainfall-Only Logistic Regression** | 0.105 | Single-variable environmental baseline |
| **All-Features Logistic Regression** | 0.174 | Tabular linear baseline with terrain + weather |
| **ST-GNN (5-seed mean $\pm$ std)** | **0.215 $\pm$ 0.041** | Multi-seed average across random initializations |
| **ST-GNN Best Checkpoint (`stgnn_best.pt`)** | **0.259** | Checkpoint selected by validation AP |

The ST-GNN achieves an **8.0x improvement over random guessing** and a **2.5x improvement over the rainfall-only baseline**.

### 5.2 Threshold Selection and Operational Trade-Offs

Thresholds were selected and frozen on the **2023 validation split** and subsequently evaluated on the **2024–2025 held-out test split**:

- **Validation Threshold Scan (Year 2023, 14 events):**
  - $\tau = 0.10$: Recall = 71.4% (10/14 events caught, FN = 4), Precision = 5.5%
  - $\tau = 0.15$: Recall = 57.1% (8/14 events caught, FN = 6), Precision = 5.8%
  - $\tau = 0.35$: Recall = 35.7% (5/14 events caught, FN = 9), Precision = 7.0%, FP = 66
- **Frozen Threshold Definitions:**
  - **`Low Risk` ($< 0.10$):** Background corridor risk.
  - **`Medium Risk` ($0.10 \le \text{score} < 0.35$):** Elevated risk; advisory to proceed with caution.
  - **`High Risk` ($\ge 0.35$):** Severe hazard susceptibility; advisory to hold or seek alternative route.

### 5.3 Performance on Held-Out Test Set Under Frozen Thresholds (22 Events)

| Metric | Medium Risk Tier ($\tau_{\text{med}} = 0.10$) | High Risk Tier ($\tau_{\text{high}} = 0.35$) |
| :--- | :--- | :--- |
| **True Positives (TP)** | 18 | 13 |
| **False Negatives (FN)** | **4 (18.2% missed)** | **9 (40.9% missed)** |
| **False Positives (FP)** | 249 | 90 |
| **True Negatives (TN)** | 409 | 568 (86.3% specificity) |
| **Test Recall** | **81.82%** | **59.09%** |
| **Test Precision** | **6.74%** | **12.62%** |
| **Test F1 Score** | 0.125 | 0.208 |

---

## 6. Calibration and Probabilistic Interpretation

- **Brier Score Loss:** 0.0787 on validation (2023), 0.0719 on test (2024–2025).
- **Empirical Reliability:**
  - Bin $[0.0, 0.2)$: 514 test samples, observed positive rate = **1.36%**.
  - Bin $[0.8, 1.0]$: 12 test samples, observed positive rate = **33.33%** (10x base rate).
  - Expected Calibration Error (ECE) = **0.1308**.
- **Crucial Semantic Designation:** Because the model was optimized with weighted BCE on sampled negatives, the scores represent an **Advisory Risk Index**, not frequentist event probabilities. RouteWise displays these as relative scores and semantic tiers (`Low`, `Medium`, `High`), avoiding uncalibrated probability claims.

---

## 7. Inference Latency Benchmark

Evaluated on local CPU across 1,821 historical dates (151 segments evaluated per date):
- **Median Latency:** 67.6 ms per full-corridor evaluation.
- **95th Percentile (p95):** 137.3 ms per full-corridor evaluation.
- **Mean Latency:** 69.8 ms per full-corridor evaluation.

---

## 8. Missing and Stale Data Handling

To prevent false reassurance, the inference engine enforces strict failure paths:
- **`MISSING_DATA`:** Lookback window $< 7$ days or missing segment topology. Returns `risk_tier: "UNKNOWN"` and `risk_score: null`. Never defaults to "Low risk".
- **`STALE_DATA`:** Input observation timestamp older than 24 hours. Returns `risk_tier: "UNKNOWN"`, `is_stale: true`, and an explicit warning.

---

## 9. Known Limitations and Failure Modes

1. **Small Positive Sample Size:** With only 22 historical events in the test split, test metrics carry inherent sampling noise.
2. **Coarse Meteorology:** ERA5-Land reanalysis is $\approx 9\text{ km}$ grid resolution, meaning neighboring segments share identical atmospheric forcings.
3. **Geocoding Imprecision:** Historical disruption locations are village-level approximations snapped to the highway within known spatial tolerances.
4. **Failure Modes:** Dry mechanical rockfall or cloudbursts with sub-daily precursors without antecedent rainfall are difficult to forecast from 24h synoptic data.
5. **Advisory Disclaimer:** RouteWise risk outputs are estimates intended for situational awareness and logistics prioritization. They do not guarantee highway passage or absence of slides.
