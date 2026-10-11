"""
RouteWise - Week 6: ST-GNN architecture + baselines.

What this file does
  1. Loads the four dataset files and builds 7-day window tensors per segment
     (rainfall log-scaled, everything standardised with TRAIN-period statistics only).
  2. Defines the ST-GNN: graph convolution over segment_adjacency, then a GRU over the 7 days,
     then a head that also sees the static segment features.
  3. Fits two baselines on the same samples: logistic regression on all features, and a
     rainfall-only logistic regression.
  4. Reports precision-recall metrics (average precision), not accuracy.

Week 7 imports build_data(), STGNN, make_batches(), evaluate() from here and does the
training (early stopping on 2023, five seeds, test on 2024-25).

Usage
  python week6_stgnn.py --check      # print columns of each file and stop
  python week6_stgnn.py              # data build + baselines (+ model smoke test if torch is installed)

If a file or column name differs from your files, edit CONFIG below. Nothing else needs to change.
"""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

# ----------------------------------------------------------------------------------------------
# CONFIG - edit these to match your CSV headers
# ----------------------------------------------------------------------------------------------
DATA_DIR = Path(".")  # folder holding the CSVs (in Colab: your Drive folder)
FILES = {
    "samples": "training_samples.csv",
    "static": "segment_static.csv",
    "adj": "segment_adjacency.csv",
    "weather": "weather_daily_by_segment.csv",
}
COL = {
    "seg": "segment_id",   # segment id column (in samples, static, weather)
    "date": "date",        # date column (in samples, weather)
    "label": "label",      # 0/1 disruption label (in samples)
    "adj_src": "src",      # adjacency: one segment of the pair
    "adj_dst": "dst",      # adjacency: the other segment
}
RAIN_KEYWORDS = ("rain", "precip")  # weather columns containing these are log1p-scaled
WINDOW = 7
TRAIN_END = "2022-12-31"   # train  : up to here
VAL_YEAR = 2023            # validate: this year (early stopping in Week 7)
TEST_YEARS = (2024, 2025)  # test   : held-out years
OUT_DIR = Path(".")


# ----------------------------------------------------------------------------------------------
# Loading
# ----------------------------------------------------------------------------------------------
def _read(name):
    path = DATA_DIR / FILES[name]
    if not path.exists():
        raise FileNotFoundError(f"{path} not found. Set DATA_DIR / FILES at the top of this file.")
    return pd.read_csv(path)


def _need(df, cols, name):
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise KeyError(
            f"{FILES[name]} has no column(s) {missing}. Its columns are: {list(df.columns)}. "
            f"Fix the COL dict at the top of week6_stgnn.py."
        )


def check_columns():
    for key in FILES:
        df = _read(key)
        print(f"\n{FILES[key]}  shape={df.shape}")
        print("  columns:", list(df.columns))
        print(df.head(2).to_string(max_cols=12))


# ----------------------------------------------------------------------------------------------
# Data build
# ----------------------------------------------------------------------------------------------
def build_data():
    samples, static, adj, weather = (_read(k) for k in ("samples", "static", "adj", "weather"))
    seg, date, label = COL["seg"], COL["date"], COL["label"]
    _need(samples, [seg, date, label], "samples")
    _need(static, [seg], "static")
    _need(adj, [COL["adj_src"], COL["adj_dst"]], "adj")
    _need(weather, [seg, date], "weather")

    samples[date] = pd.to_datetime(samples[date])
    weather[date] = pd.to_datetime(weather[date])

    segs = sorted(static[seg].unique())
    seg_idx = {s: i for i, s in enumerate(segs)}
    n_seg = len(segs)

    # ---- dynamic features: [T, N, F] -------------------------------------------------------
    dyn_cols = [c for c in weather.columns if c not in (seg, date) and pd.api.types.is_numeric_dtype(weather[c])]
    rain_cols = [c for c in dyn_cols if any(k in c.lower() for k in RAIN_KEYWORDS)]
    if not dyn_cols:
        raise ValueError("No numeric weather columns found.")
    dates = pd.date_range(weather[date].min(), weather[date].max(), freq="D")
    full_index = pd.MultiIndex.from_product([dates, segs], names=[date, seg])
    wx = weather.drop_duplicates([date, seg]).set_index([date, seg])[dyn_cols].reindex(full_index)
    arr = wx.to_numpy(dtype=np.float32).reshape(len(dates), n_seg, len(dyn_cols))
    for c in rain_cols:
        j = dyn_cols.index(c)
        arr[:, :, j] = np.log1p(np.clip(arr[:, :, j], 0, None))

    train_mask_t = dates <= pd.Timestamp(TRAIN_END)
    mu = np.nanmean(arr[train_mask_t], axis=(0, 1))
    sd = np.nanstd(arr[train_mask_t], axis=(0, 1))
    sd[sd < 1e-6] = 1.0
    arr = (arr - mu) / sd
    arr = np.nan_to_num(arr, nan=0.0)  # missing weather -> training mean

    # ---- static features: [N, Fs] ----------------------------------------------------------
    st = static.drop_duplicates(seg).set_index(seg).reindex(segs)
    stat_cols = [c for c in st.columns if pd.api.types.is_numeric_dtype(st[c])]
    s_arr = st[stat_cols].to_numpy(dtype=np.float32)
    s_mu, s_sd = np.nanmean(s_arr, axis=0), np.nanstd(s_arr, axis=0)
    s_sd[s_sd < 1e-6] = 1.0
    s_arr = np.nan_to_num((s_arr - s_mu) / s_sd, nan=0.0)

    # ---- adjacency: symmetric, self loops, D^-1/2 (A+I) D^-1/2 ------------------------------
    A = np.zeros((n_seg, n_seg), dtype=np.float32)
    for a, b in zip(adj[COL["adj_src"]], adj[COL["adj_dst"]]):
        if a in seg_idx and b in seg_idx:
            A[seg_idx[a], seg_idx[b]] = 1.0
            A[seg_idx[b], seg_idx[a]] = 1.0
    A += np.eye(n_seg, dtype=np.float32)
    d = A.sum(1)
    A_hat = A / np.sqrt(d[:, None] * d[None, :])

    # ---- samples -> (t index, segment index, label), split by period ------------------------
    date_idx = {d_: i for i, d_ in enumerate(dates)}
    samples = samples[samples[seg].isin(seg_idx) & samples[date].isin(date_idx)].copy()
    samples["t"] = samples[date].map(date_idx)
    samples["s"] = samples[seg].map(seg_idx)
    samples = samples[samples["t"] >= WINDOW - 1]  # need a full 7-day history
    yr = samples[date].dt.year
    split = {
        "train": samples[samples[date] <= pd.Timestamp(TRAIN_END)],
        "val": samples[yr == VAL_YEAR],
        "test": samples[yr.isin(TEST_YEARS)],
    }
    for k, v in split.items():
        print(f"  {k:5s}: {len(v):6d} samples, {int(v[label].sum()):4d} positives")

    return {
        "arr": arr, "static": s_arr, "A_hat": A_hat, "dates": dates, "segs": segs,
        "dyn_cols": dyn_cols, "rain_cols": rain_cols, "stat_cols": stat_cols,
        "split": {k: v[["t", "s", label]].to_numpy(dtype=np.int64) for k, v in split.items()},
        "norm": {"dyn_mean": mu.tolist(), "dyn_std": sd.tolist(),
                 "static_mean": s_mu.tolist(), "static_std": s_sd.tolist()},
    }


# ----------------------------------------------------------------------------------------------
# Baselines (logistic regression on the same samples)
# ----------------------------------------------------------------------------------------------
def _flat_features(data, rows, rain_only=False):
    arr, stat = data["arr"], data["static"]
    cols = [data["dyn_cols"].index(c) for c in data["rain_cols"]] if rain_only else list(range(arr.shape[2]))
    X = []
    for t, s, _ in rows:
        win = arr[t - WINDOW + 1: t + 1, s, :][:, cols].reshape(-1)
        X.append(win if rain_only else np.concatenate([win, stat[s]]))
    return np.asarray(X, dtype=np.float32), rows[:, 2]


def _scores(y, p):
    from sklearn.metrics import average_precision_score, precision_recall_curve
    if y.sum() == 0:
        return {"positives": 0, "average_precision": None, "best_f1": None}
    prec, rec, _ = precision_recall_curve(y, p)
    f1 = (2 * prec * rec / np.clip(prec + rec, 1e-12, None)).max()
    return {"positives": int(y.sum()), "n": int(len(y)),
            "base_rate": float(y.mean()),
            "average_precision": float(average_precision_score(y, p)),
            "best_f1": float(f1)}


def run_baselines(data):
    from sklearn.linear_model import LogisticRegression
    results = {}
    for name, rain_only in (("logreg_all_features", False), ("logreg_rainfall_only", True)):
        if rain_only and not data["rain_cols"]:
            print("  (no rainfall column detected - skipping rainfall-only baseline; check RAIN_KEYWORDS)")
            continue
        Xtr, ytr = _flat_features(data, data["split"]["train"], rain_only)
        clf = LogisticRegression(class_weight="balanced", max_iter=2000)
        clf.fit(Xtr, ytr)
        results[name] = {}
        for part in ("val", "test"):
            X, y = _flat_features(data, data["split"][part], rain_only)
            results[name][part] = _scores(y, clf.predict_proba(X)[:, 1])
    return results


# ----------------------------------------------------------------------------------------------
# ST-GNN
# ----------------------------------------------------------------------------------------------
def _torch():
    import torch
    import torch.nn as nn
    return torch, nn


def make_model(f_dyn, f_static, A_hat, hidden=32, dropout=0.2):
    torch, nn = _torch()

    class STGNN(nn.Module):
        """Graph conv (x2) per day -> GRU over the 7 days -> head with static features."""

        def __init__(self):
            super().__init__()
            self.register_buffer("A", torch.as_tensor(A_hat))
            self.gc1 = nn.Linear(f_dyn, hidden)
            self.gc2 = nn.Linear(hidden, hidden)
            self.gru = nn.GRU(hidden, hidden, batch_first=True)
            self.drop = nn.Dropout(dropout)
            self.head = nn.Sequential(
                nn.Linear(hidden + f_static, hidden), nn.ReLU(), nn.Dropout(dropout), nn.Linear(hidden, 1))

        def forward(self, x, s):
            # x: [B, W, N, F] window for every segment on B dates; s: [N, Fs] static features
            B, W, N, _ = x.shape
            h = torch.relu(self.A @ self.gc1(x))   # spatial mixing, [B, W, N, H]
            h = self.drop(torch.relu(self.A @ self.gc2(h)))
            h = h.permute(0, 2, 1, 3).reshape(B * N, W, -1)
            _, hn = self.gru(h)                      # temporal, last hidden state
            hn = hn[-1].reshape(B, N, -1)
            s = s.unsqueeze(0).expand(B, -1, -1)
            return self.head(torch.cat([hn, s], dim=-1)).squeeze(-1)  # logits [B, N]

    return STGNN()


def make_batches(data, part, batch_dates=16, shuffle=False, seed=0):
    """Yield (x [B,W,N,F], y [B,N], mask [B,N]) grouped by date. Only labelled (t, segment) pairs count."""
    torch, _ = _torch()
    rows = data["split"][part]
    n_seg = data["arr"].shape[1]
    by_t = {}
    for t, s, y in rows:
        by_t.setdefault(int(t), []).append((int(s), int(y)))
    ts = sorted(by_t)
    if shuffle:
        np.random.default_rng(seed).shuffle(ts)
    for i in range(0, len(ts), batch_dates):
        chunk = ts[i:i + batch_dates]
        x = np.stack([data["arr"][t - WINDOW + 1: t + 1] for t in chunk])
        y = np.zeros((len(chunk), n_seg), dtype=np.float32)
        m = np.zeros((len(chunk), n_seg), dtype=np.float32)
        for b, t in enumerate(chunk):
            for s, lab in by_t[t]:
                y[b, s], m[b, s] = lab, 1.0
        yield torch.as_tensor(x), torch.as_tensor(y), torch.as_tensor(m)


def masked_bce(logits, y, m, pos_weight):
    torch, _ = _torch()
    loss = torch.nn.functional.binary_cross_entropy_with_logits(
        logits, y, pos_weight=torch.as_tensor(pos_weight, dtype=logits.dtype), reduction="none")
    return (loss * m).sum() / m.sum().clamp(min=1.0)


def pos_weight_from_train(data):
    y = data["split"]["train"][:, 2]
    return float((len(y) - y.sum()) / max(y.sum(), 1))


def evaluate(model, data, part, batch_dates=16):
    torch, _ = _torch()
    model.eval()
    s = torch.as_tensor(data["static"])
    ys, ps = [], []
    with torch.no_grad():
        for x, y, m in make_batches(data, part, batch_dates):
            p = torch.sigmoid(model(x, s))
            keep = m.bool()
            ys.append(y[keep].numpy())
            ps.append(p[keep].numpy())
    return _scores(np.concatenate(ys), np.concatenate(ps))


def smoke_test(data):
    """One forward + backward pass to confirm shapes and loss wiring. Not training."""
    torch, _ = _torch()
    model = make_model(data["arr"].shape[2], data["static"].shape[1], data["A_hat"])
    s = torch.as_tensor(data["static"])
    x, y, m = next(make_batches(data, "train", batch_dates=4))
    logits = model(x, s)
    loss = masked_bce(logits, y, m, pos_weight_from_train(data))
    loss.backward()
    n_params = sum(p.numel() for p in model.parameters())
    print(f"  smoke test ok: x{tuple(x.shape)} -> logits{tuple(logits.shape)}, loss={loss.item():.4f}, params={n_params}")


# ----------------------------------------------------------------------------------------------
if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="print columns of each input file and stop")
    args = ap.parse_args()

    if args.check:
        check_columns()
        raise SystemExit

    print("Building data...")
    data = build_data()
    print(f"  segments={len(data['segs'])}, days={len(data['dates'])}, "
          f"dynamic features={len(data['dyn_cols'])} (rain: {data['rain_cols']}), static={len(data['stat_cols'])}")
    print(f"  suggested pos_weight={pos_weight_from_train(data):.1f}")

    print("Baselines...")
    results = run_baselines(data)
    out = OUT_DIR / "week6_baseline_metrics.json"
    out.write_text(json.dumps(results, indent=2))
    for name, r in results.items():
        for part in ("val", "test"):
            ap_ = r[part]["average_precision"]
            print(f"  {name:22s} {part:4s} AP={ap_ if ap_ is None else round(ap_, 4)} "
                  f"(base rate {r[part].get('base_rate', float('nan')):.4f})")
    print(f"  saved {out}")

    try:
        print("Model smoke test...")
        smoke_test(data)
    except ImportError:
        print("  PyTorch not installed here - skipped. Run this file in Colab (PyTorch is preinstalled).")