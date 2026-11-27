"""Customer activity versus likely redistribution 

There is NO ground truth: the feed never says when a van came. These are rule-based
labels ("likely redistribution"). Only 3-minute steps (from 18 Nov 2026) are labelled;
older 15-minute steps are marked gap_unknown because a 15-minute change can mix many trips.
Thresholds are starting points: choose them on TRAINING dates and report the sensitivity.

Run:  python analysis/patterns.py  ->  data/features/features_labelled.csv.gz, redistribution_episodes.csv
"""
import numpy as np
import pandas as pd

from load_data import ROOT

ABS_THRESHOLD = 5     # change of 5+ bikes in one 3-minute step ...
K_STD = 3.0           # ... that is also > 3 x this station's usual step std (training dates)
BURST_THRESHOLD = 8   # or a net change of 8+ within 9 minutes
MAX_STEP_MIN = 6      # a longer step is a gap


def train_dates(df, share=0.6):
    d = sorted(df["date_local"].unique())
    return set(d[:max(int(len(d) * share), 1)])


def label_steps(df, abs_threshold=ABS_THRESHOLD, k=K_STD, burst=BURST_THRESHOLD):
    df = df.sort_values(["station_id", "collected_at"]).copy()
    short = df["minutes_since_last"] <= MAX_STEP_MIN
    tr = df["date_local"].isin(train_dates(df)) & short & (df["delta_bikes"].abs() < abs_threshold)
    std = df[tr].groupby("station_id")["delta_bikes"].std().clip(lower=0.5)
    df["station_step_std"] = df["station_id"].map(std).fillna(1.0)
    net9 = []
    for _, g in df.groupby("station_id", sort=True):
        s = g.set_index("collected_at")["delta_bikes"].fillna(0).rolling("9min").sum()
        net9.append(s.to_numpy())
    df["net_change_9m"] = np.concatenate(net9)
    a = df["delta_bikes"].abs()
    prev_ok = df.groupby("station_id")["in_service"].shift(1)
    reset = (df["num_bikes"] == 0) & (df["num_docks_available"] == 0)
    big = (a >= abs_threshold) & (a > k * df["station_step_std"])
    burst_hit = (df["net_change_9m"].abs() >= burst) & (a >= 2)
    df["step_label"] = np.select(
        [~short, reset, (df["in_service"] == 0) | (prev_ok == 0), big | burst_hit, a > 0],
        ["gap_unknown", "feed_reset_or_outage", "not_in_service", "likely_redistribution",
         "customer_activity"], default="no_change")
    df["redistribution_dir"] = np.where(df["step_label"] == "likely_redistribution",
                                        np.where(df["delta_bikes"] > 0, "delivery", "collection"), "")
    # Backward-looking model features: what happened in the last 60 minutes
    df["redis_delta"] = np.where(df["step_label"] == "likely_redistribution", df["delta_bikes"], 0.0)
    parts = []
    for _, g in df.groupby("station_id", sort=True):
        i = g.set_index("collected_at")
        g = g.copy()
        g["redis_net_60m"] = i["redis_delta"].rolling("60min").sum().to_numpy()
        g["redis_steps_60m"] = (i["redis_delta"] != 0).astype(int).rolling("60min").sum().to_numpy()
        parts.append(g)
    return pd.concat(parts, ignore_index=True).drop(columns=["redis_delta"])


def episodes(lab):
    r = lab[lab["step_label"] == "likely_redistribution"].sort_values(["station_id", "collected_at"])
    new = (r["station_id"] != r["station_id"].shift()) | \
          (r["collected_at"].diff().dt.total_seconds() / 60 > 9)
    r = r.assign(ep=new.cumsum())
    ep = r.groupby("ep").agg(station_id=("station_id", "first"), start=("collected_at", "min"),
                             end=("collected_at", "max"), steps=("collected_at", "size"),
                             net_change=("delta_bikes", "sum"))
    ep["direction"] = np.where(ep["net_change"] > 0, "delivery", "collection")
    return ep.reset_index(drop=True)


def sensitivity(df):
    rows = []
    for a in (3, 4, 5, 6, 8):
        for k in (2, 3, 4):
            lab = label_steps(df, a, k)
            rows.append({"abs_threshold": a, "k": k,
                         "likely_redistribution_steps": int((lab["step_label"] == "likely_redistribution").sum())})
    return pd.DataFrame(rows)


if __name__ == "__main__":
    feats = ROOT / "data" / "features"
    df = pd.read_csv(feats / "features.csv.gz", dtype={"station_id": str}, low_memory=False)
    df["collected_at"] = pd.to_datetime(df["collected_at"], utc=True)
    lab = label_steps(df)
    lab.to_csv(feats / "features_labelled.csv.gz", index=False)
    episodes(lab).to_csv(feats / "redistribution_episodes.csv", index=False)
    sensitivity(df).to_csv(feats / "threshold_sensitivity.csv", index=False)
    print(lab["step_label"].value_counts().to_string())
