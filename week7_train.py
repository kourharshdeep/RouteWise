"""
RouteWise - Week 7: train the ST-GNN, tune, and score on held-out years.

Run this in Google Colab (GPU optional, the model is small). Needs week6_stgnn.py in the same folder.

What it does (from the revised plan)
  - trains the ST-GNN from week6_stgnn.py with weighted BCE
  - early stopping on the 2023 validation year (average precision)
  - repeats over five random seeds and reports mean and spread
  - scores on 2024-25 with precision-recall metrics (not accuracy)
  - compares against the logistic-regression baselines, including rainfall-only
  - saves stgnn_best.pt (model + normalisation stats + segment order together) and stgnn_metrics.json

Colab usage
  from google.colab import drive; drive.mount('/content/drive')
  %cd /content/drive/MyDrive/<your RouteWise folder>
  !python week7_train.py --data-dir . --out-dir .

Quick tuning: try --hidden 16 / 32 / 64 and --lr 1e-3 / 3e-3, keep the setting with the best mean validation AP.
"""
import argparse
import json
from pathlib import Path

import numpy as np
import torch

import week6_stgnn as w6


def weighted_bce(logits, y, m, pos_weight):
    """Same loss as week6 masked_bce, but keeps pos_weight on the same device as the logits (GPU-safe)."""
    pw = torch.tensor(float(pos_weight), dtype=logits.dtype, device=logits.device)
    loss = torch.nn.functional.binary_cross_entropy_with_logits(logits, y, pos_weight=pw, reduction="none")
    return (loss * m).sum() / m.sum().clamp(min=1.0)


def predict(model, data, part, device):
    s = torch.as_tensor(data["static"]).to(device)
    model.eval()
    ys, ps = [], []
    with torch.no_grad():
        for x, y, m in w6.make_batches(data, part):
            p = torch.sigmoid(model(x.to(device), s)).cpu()
            keep = m.bool()
            ys.append(y[keep].numpy())
            ps.append(p[keep].numpy())
    return w6._scores(np.concatenate(ys), np.concatenate(ps))


def train_one(data, seed, args, device):
    torch.manual_seed(seed)
    np.random.seed(seed)
    model = w6.make_model(data["arr"].shape[2], data["static"].shape[1], data["A_hat"],
                          hidden=args.hidden, dropout=args.dropout).to(device)
    opt = torch.optim.Adam(model.parameters(), lr=args.lr, weight_decay=args.weight_decay)
    pos_weight = w6.pos_weight_from_train(data)
    s = torch.as_tensor(data["static"]).to(device)

    best_ap, best_state, bad = -1.0, None, 0
    for epoch in range(args.epochs):
        model.train()
        total, n = 0.0, 0
        for x, y, m in w6.make_batches(data, "train", args.batch_dates, shuffle=True, seed=seed * 1000 + epoch):
            x, y, m = x.to(device), y.to(device), m.to(device)
            opt.zero_grad()
            loss = weighted_bce(model(x, s), y, m, pos_weight)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            total += loss.item()
            n += 1
        val = predict(model, data, "val", device)
        val_ap = val["average_precision"] or 0.0
        print(f"  seed {seed} epoch {epoch + 1:3d}  train_loss={total / max(n, 1):.4f}  val_AP={val_ap:.4f}")
        if val_ap > best_ap:
            best_ap, bad = val_ap, 0
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
        else:
            bad += 1
            if bad >= args.patience:
                print(f"  early stop at epoch {epoch + 1}")
                break

    model.load_state_dict(best_state)
    return model, best_state, {"val": predict(model, data, "val", device),
                               "test": predict(model, data, "test", device)}


def summarize(runs, part, key):
    vals = [r[part][key] for r in runs if r[part][key] is not None]
    if not vals:
        return {"mean": None, "std": None}
    return {"mean": float(np.mean(vals)), "std": float(np.std(vals))}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=".")
    ap.add_argument("--out-dir", default=".")
    ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--epochs", type=int, default=60)
    ap.add_argument("--patience", type=int, default=8)
    ap.add_argument("--hidden", type=int, default=32)
    ap.add_argument("--dropout", type=float, default=0.2)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--weight-decay", type=float, default=1e-5)
    ap.add_argument("--batch-dates", type=int, default=16)
    args, _ = ap.parse_known_args()

    w6.DATA_DIR = Path(args.data_dir)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"device: {device}")

    print("Building data...")
    data = w6.build_data()

    print("Baselines...")
    baselines = w6.run_baselines(data)

    runs, best = [], {"val_ap": -1.0}
    for seed in range(args.seeds):
        print(f"\n=== seed {seed} ===")
        model, state, res = train_one(data, seed, args, device)
        runs.append(res)
        print(f"  seed {seed}: val AP={res['val']['average_precision']}  test AP={res['test']['average_precision']}")
        v = res["val"]["average_precision"] or 0.0
        if v > best["val_ap"]:
            best = {"val_ap": v, "seed": seed, "state": state}

    metrics = {
        "config": vars(args),
        "stgnn": {
            "per_seed": runs,
            "val_average_precision": summarize(runs, "val", "average_precision"),
            "test_average_precision": summarize(runs, "test", "average_precision"),
            "test_best_f1": summarize(runs, "test", "best_f1"),
        },
        "baselines": baselines,
        "best_seed_by_validation": best["seed"],
    }
    (out_dir / "stgnn_metrics.json").write_text(json.dumps(metrics, indent=2))

    # model, normalisation statistics and segment order are saved together
    torch.save({
        "state_dict": best["state"],
        "hyperparams": {"hidden": args.hidden, "dropout": args.dropout,
                        "f_dyn": int(data["arr"].shape[2]), "f_static": int(data["static"].shape[1]),
                        "window": w6.WINDOW},
        "A_hat": data["A_hat"],
        "norm": data["norm"],
        "segment_order": data["segs"],
        "dynamic_columns": data["dyn_cols"],
        "rain_columns": data["rain_cols"],
        "static_columns": data["stat_cols"],
    }, out_dir / "stgnn_best.pt")

    t = metrics["stgnn"]["test_average_precision"]
    print("\n=== Summary (test 2024-25, average precision) ===")
    print(f"  ST-GNN ({args.seeds} seeds): {t['mean']:.4f} +/- {t['std']:.4f}" if t["mean"] is not None else "  ST-GNN: no positives in test")
    for name, r in baselines.items():
        print(f"  {name:22s}: {r['test']['average_precision']}")
    print(f"  base rate in test: {baselines[next(iter(baselines))]['test'].get('base_rate')}")
    print(f"\nSaved {out_dir / 'stgnn_best.pt'} and {out_dir / 'stgnn_metrics.json'}")


if __name__ == "__main__":
    main()