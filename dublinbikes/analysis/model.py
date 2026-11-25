"""60-minute near-empty model and the dispatch comparison (the research question).

Exactly 10 feature columns Split by DATE: first 60% of dates train,
next 20% validation, last 20% test. Never shuffled. Threshold chosen on validation only.
By default only 3-minute data (from 2026-11-18) is used, so every row has the same detail;
the older 15-minute rows stay in the files and are used for EDA and the baseline.

Run:  python analysis/model.py  ->  data/features/model_results.csv, dispatch_precision_at_10.csv
"""
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, f1_score, precision_score, recall_score
from sklearn.neighbors import KNeighborsClassifier
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.tree import DecisionTreeClassifier

from load_data import ROOT

TARGET = "near_empty_60m"
FEATURES = ["fill_ratio", "capacity", "delta_bikes_15m", "delta_bikes_60m", "changes_per_hour",
            "redis_net_60m", "hour_sin", "hour_cos", "is_weekend", "precipitation"]
assert len(FEATURES) == 10 and TARGET not in FEATURES and "bikes_in_60m" not in FEATURES
MODEL_FROM = "2026-11-18"


def split(df):
    d = sorted(df["date_local"].unique())
    a, b = int(len(d) * 0.6), int(len(d) * 0.8)
    return [df[df["date_local"].isin(x)] for x in (d[:a], d[a:b], d[b:])]


def pick_threshold(y, p):
    grid = np.linspace(0.05, 0.95, 91)
    ok = [t for t in grid if recall_score(y, p >= t, zero_division=0) >= 0.8]
    return max(ok) if ok else max(grid, key=lambda t: f1_score(y, p >= t, zero_division=0))


def precision_at_10(te, col):
    on_hour = te[te["collected_at"].dt.minute < 3]          # first 3-minute poll of each hour
    vals = [g.nlargest(10, col)[TARGET].mean()
            for _, g in on_hour.groupby(on_hour["collected_at"].dt.floor("h")) if len(g) >= 10]
    return round(float(np.mean(vals)), 3) if vals else np.nan, len(vals)


if __name__ == "__main__":
    feats = ROOT / "data" / "features"
    df = pd.read_csv(feats / "features_labelled.csv.gz", dtype={"station_id": str}, low_memory=False)
    df["collected_at"] = pd.to_datetime(df["collected_at"], utc=True)
    df = df[(df["date_local"] >= MODEL_FROM) & (df["in_service"] == 1) & df[TARGET].notna()]
    if df["date_local"].nunique() < 5:
        raise SystemExit("Need at least 5 labelled days. Collect more and rerun.")
    tr, va, te = split(df)
    print("train", tr["date_local"].min(), tr["date_local"].max(), "| valid", va["date_local"].min(),
          va["date_local"].max(), "| test", te["date_local"].min(), te["date_local"].max())
    models = {
        "LogisticRegression": LogisticRegression(max_iter=2000, class_weight="balanced"),
        "DecisionTree": DecisionTreeClassifier(max_depth=6, min_samples_leaf=50,
                                               class_weight="balanced", random_state=0),
        "RandomForest": RandomForestClassifier(n_estimators=200, min_samples_leaf=20, n_jobs=-1,
                                               class_weight="balanced_subsample", random_state=0),
        "KNN": KNeighborsClassifier(n_neighbors=25),
    }
    te = te.copy()
    y = te[TARGET].astype(int)
    rows = []
    for name, pred in [("Persistence (near empty now)", te["near_empty_now"] == 1),
                       ("Rule: fill <= 15% or drop >= 5 in 60 min",
                        (te["fill_ratio"] <= 0.15) | (te["delta_bikes_60m"] <= -5))]:
        rows.append({"model": name, "recall": recall_score(y, pred), "precision": precision_score(y, pred),
                     "f1": f1_score(y, pred), "pr_auc": np.nan, "threshold": np.nan})
    te["score_emptiest_now"] = -te["num_bikes"]
    for name, m in models.items():
        pipe = make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), m)
        pipe.fit(tr[FEATURES], tr[TARGET].astype(int))
        th = pick_threshold(va[TARGET].astype(int), pipe.predict_proba(va[FEATURES])[:, 1])
        p = pipe.predict_proba(te[FEATURES])[:, 1]
        te[f"score_{name}"] = p
        rows.append({"model": name, "recall": recall_score(y, p >= th), "precision": precision_score(y, p >= th),
                     "f1": f1_score(y, p >= th), "pr_auc": average_precision_score(y, p), "threshold": th})
    # The honest test: stations that are NOT near empty now (persistence gets all of these wrong)
    hard = te["near_empty_now"] == 0
    for name in models:
        p, th = te.loc[hard, f"score_{name}"], [r["threshold"] for r in rows if r["model"] == name][0]
        yh = y[hard]
        rows.append({"model": f"{name} (not low now)", "recall": recall_score(yh, p >= th, zero_division=0),
                     "precision": precision_score(yh, p >= th, zero_division=0),
                     "f1": f1_score(yh, p >= th, zero_division=0), "pr_auc": average_precision_score(yh, p),
                     "threshold": th})
    res = pd.DataFrame(rows).round(3)
    disp = pd.DataFrame([{"ranking": c.replace("score_", ""), "precision_at_10": precision_at_10(te, c)[0],
                          "hours": precision_at_10(te, c)[1]}
                         for c in ["score_emptiest_now"] + [f"score_{n}" for n in models]])
    # Same comparison among stations that still have 3+ bikes (where a forecast adds value)
    te_h = te[te["near_empty_now"] == 0].assign(score_lowest_fill=lambda d: -d["fill_ratio"])
    disp_h = pd.DataFrame([{"ranking": c.replace("score_", "") + " (not low now)",
                            "precision_at_10": precision_at_10(te_h, c)[0], "hours": precision_at_10(te_h, c)[1]}
                           for c in ["score_lowest_fill"] + [f"score_{n}" for n in models]])
    disp = pd.concat([disp, disp_h], ignore_index=True)
    res.to_csv(feats / "model_results.csv", index=False)
    disp.to_csv(feats / "dispatch_precision_at_10.csv", index=False)
    print(res.to_string(index=False)); print(disp.to_string(index=False))
