"""Feature engineering: raw snapshots -> one feature table (Paul's points 2 and 3).

Every feature at time t uses only readings at or before t (same station, sorted by time).
Only the two TARGET columns look forward, and they are never model inputs.
Old 15-minute rows and new 3-minute rows are both kept; minutes_since_last shows which is which.

Run:  python analysis/features.py   ->  data/features/features.csv.gz  (rebuilt each time)
"""
from pathlib import Path

import numpy as np
import pandas as pd

from load_data import ROOT, load_all

LOCAL_TZ = "Europe/Dublin"
OPENING = [(0, 30), (5 * 60, 24 * 60)]   # feed opening_hours on 22 Nov 2026: 00:00-00:30, 05:00-24:00
NEAR_EMPTY_MAX = 2
HORIZON_MIN = 60


def value_at(times, values, offset_min, tol_min, direction):
    """Value at t + offset (matched by TIME, not by row), within a tolerance."""
    left = pd.DataFrame({"k": times + pd.to_timedelta(int(offset_min), unit="min")})
    right = pd.DataFrame({"k": times, "v": values})
    m = pd.merge_asof(left, right, on="k", direction=direction,
                      tolerance=pd.to_timedelta(int(tol_min), unit="min"))
    return m["v"].to_numpy()


def future_target(t, bikes, ok, max_gap_min=20):
    """near_empty_60m = 1 if the station has <= 2 bikes at ANY reading in (t, t+60 min].
    No label (NaN) if the window is not covered (no reading 54-66 min ahead, a gap over
    20 minutes inside it) or the station is out of service at any reading in it."""
    ts = t.astype("int64").to_numpy() // 10**9
    n = len(ts)
    out = np.full(n, np.nan)
    for i in range(n):
        j = np.searchsorted(ts, ts[i] + HORIZON_MIN * 60, side="right")
        if j <= i + 1 or ts[j - 1] - ts[i] < (HORIZON_MIN - 6) * 60:
            continue
        w = slice(i + 1, j)
        gaps = np.diff(ts[i:j])
        if gaps.max() > max_gap_min * 60 or not ok[w].all():
            continue
        out[i] = float(bikes[w].min() <= NEAR_EMPTY_MAX)
    return out


def station_features(g):
    g = g.sort_values("collected_at").copy()
    t = g["collected_at"].reset_index(drop=True)
    b = g["num_bikes"].astype(float).to_numpy()
    g["minutes_since_last"] = g["collected_at"].diff().dt.total_seconds() / 60
    g["delta_bikes"] = g["num_bikes"].diff()                       # change since previous reading
    g["delta_docks"] = g["num_docks_available"].diff()
    g["rate_bikes_per_min"] = g["delta_bikes"] / g["minutes_since_last"]
    idx = g.set_index("collected_at")
    changed = (g["delta_bikes"].fillna(0) != 0).astype(int).to_numpy()
    absd = g["delta_bikes"].abs().fillna(0).to_numpy()
    for w in (15, 30, 60):                                         # windows end at t: past only
        r = idx["num_bikes"].rolling(f"{w}min")
        g[f"roll_mean_{w}m"] = r.mean().to_numpy()
        g[f"roll_std_{w}m"] = r.std().to_numpy()
    g["changes_per_hour"] = pd.Series(changed, index=idx.index).rolling("60min").sum().to_numpy()
    g["abs_change_60m"] = pd.Series(absd, index=idx.index).rolling("60min").sum().to_numpy()
    for lag in (15, 30, 60):
        g[f"bikes_lag_{lag}m"] = value_at(t, b, -lag, 4, "backward")
    g["delta_bikes_15m"] = g["num_bikes"] - g["bikes_lag_15m"]
    g["delta_bikes_60m"] = g["num_bikes"] - g["bikes_lag_60m"]
    # TARGETS (future). Never use as features.
    g["bikes_in_60m"] = value_at(t, b, HORIZON_MIN, 6, "forward")
    g["near_empty_60m"] = future_target(t, b, g["in_service"].to_numpy().astype(bool))
    return g


def add_time(df):
    local = df["collected_at"].dt.tz_convert(LOCAL_TZ)
    df["date_local"] = local.dt.strftime("%Y-%m-%d")
    df["hour"] = local.dt.hour
    df["weekday"] = local.dt.dayofweek
    df["is_weekend"] = (df["weekday"] >= 5).astype(int)
    df["slot_30"] = local.dt.hour * 2 + local.dt.minute // 30
    frac = (local.dt.hour + local.dt.minute / 60) / 24
    df["hour_sin"] = np.sin(2 * np.pi * frac)
    df["hour_cos"] = np.cos(2 * np.pi * frac)
    mins = local.dt.hour * 60 + local.dt.minute
    df["system_open"] = np.any([(mins >= a) & (mins < b) for a, b in OPENING], axis=0).astype(int)
    return df


def build_features(root=ROOT):
    df = add_time(load_all(root))
    df["fill_ratio"] = np.where(df["capacity"] > 0, df["num_bikes"] / df["capacity"], np.nan)
    tot = df["mechanical"] + df["electrical"]
    df["ebike_share"] = np.where(tot > 0, df["electrical"] / tot, np.nan)
    df["near_empty_now"] = (df["num_bikes"] <= NEAR_EMPTY_MAX).astype(int)
    df["is_raining"] = (df["precipitation"] > 0).astype(int)
    df["in_service"] = (df["system_open"].astype(bool) & df["is_installed"] & df["is_renting"]).astype(int)
    df = pd.concat([station_features(g) for _, g in df.groupby("station_id", sort=True)],
                   ignore_index=True)
    print(f"feature rows: {len(df)}, labelled rows: {int(df['near_empty_60m'].notna().sum())}, "
          f"positive share: {df['near_empty_60m'].mean():.3f}")
    return df


if __name__ == "__main__":
    out = ROOT / "data" / "features" / "features.csv.gz"
    out.parent.mkdir(parents=True, exist_ok=True)
    build_features().to_csv(out, index=False)
    print("saved", out)
