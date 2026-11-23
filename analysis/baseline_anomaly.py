"""Historical baseline per station, weekday and 30-minute slot, and anomaly scores
(Paul's points 6, 7 and 8). Each date is compared ONLY with earlier dates (expanding).

A slot is scored only with at least 3 earlier same-weekday days (or 5 days in a
weekday/weekend pool). Until then it is 'insufficient_history' and never an anomaly.

Run:  python analysis/baseline_anomaly.py  ->  data/features/anomaly_scores_30min.csv,
                                                anomalies_to_investigate_30min.csv
"""
import numpy as np
import pandas as pd

from load_data import ROOT

MIN_DAYS, MIN_POOL = 3, 5
ROBUST_Z_FLAG, Z_FLAG, MIN_ABS_DEV = 3.5, 3.0, 3


def slot_table(df):
    d = df[df["in_service"] == 1]
    agg = {"num_bikes": "mean", "precipitation": "max"}
    if "step_label" in d:
        d = d.assign(redis_step=(d["step_label"] == "likely_redistribution").astype(int))
        agg["redis_step"] = "sum"
    out = d.groupby(["station_id", "date_local", "weekday", "is_weekend", "slot_30"], as_index=False).agg(agg)
    return out.rename(columns={"num_bikes": "bikes"})


def _base(hist, keys):
    b = hist.groupby(keys)["bikes"].agg(b_mean="mean", b_median="median", b_std="std",
                                        n_days="size").reset_index()
    m = hist.merge(b[keys + ["b_median"]], on=keys)
    m["ad"] = (m["bikes"] - m["b_median"]).abs()
    return b.merge(m.groupby(keys)["ad"].median().rename("b_mad").reset_index(), on=keys)


def score_expanding(slots):
    dates = sorted(slots["date_local"].unique())
    out = []
    for d in dates[1:]:
        hist, today = slots[slots["date_local"] < d], slots[slots["date_local"] == d]
        k1, k2 = ["station_id", "weekday", "slot_30"], ["station_id", "is_weekend", "slot_30"]
        t = today.merge(_base(hist, k1), on=k1, how="left")
        p = _base(hist, k2).rename(columns=lambda c: c if c in k2 else c + "_p")
        t = t.merge(p, on=k2, how="left")
        main = t["n_days"].fillna(0) >= MIN_DAYS
        pool = ~main & (t["n_days_p"].fillna(0) >= MIN_POOL)
        for c in ["b_mean", "b_median", "b_std", "b_mad"]:
            t[c] = np.where(main, t[c], np.where(pool, t[c + "_p"], np.nan))
        t["baseline_type"] = np.where(main, "same_weekday", np.where(pool, "pooled", "insufficient_history"))
        out.append(t.drop(columns=[c for c in t if c.endswith("_p")]))
    s = pd.concat(out, ignore_index=True)
    s["deviation"] = s["bikes"] - s["b_median"]
    s["z"] = (s["bikes"] - s["b_mean"]) / s["b_std"].clip(lower=1.0)
    s["robust_z"] = 0.6745 * s["deviation"] / s["b_mad"].clip(lower=1.0)
    s["is_anomaly"] = (((s["robust_z"].abs() >= ROBUST_Z_FLAG) | (s["z"].abs() >= Z_FLAG))
                       & (s["deviation"].abs() >= MIN_ABS_DEV)
                       & (s["baseline_type"] != "insufficient_history")).astype(int)
    s = s.sort_values(["station_id", "date_local", "slot_30"])
    g = s.groupby(["station_id", "date_local"])["is_anomaly"]
    s["sustained"] = ((s["is_anomaly"] == 1) & ((g.shift(1) == 1) | (g.shift(-1) == 1))).astype(int)
    share = s.groupby(["date_local", "slot_30"])["is_anomaly"].mean().rename("city_share_anomalous")
    return s.merge(share.reset_index(), on=["date_local", "slot_30"], how="left")


if __name__ == "__main__":
    feats = ROOT / "data" / "features"
    src = feats / "features_labelled.csv.gz"
    df = pd.read_csv(src if src.exists() else feats / "features.csv.gz", dtype={"station_id": str}, low_memory=False)
    sc = score_expanding(slot_table(df))
    sc.to_csv(feats / "anomaly_scores_30min.csv", index=False)
    an = sc[sc["is_anomaly"] == 1].sort_values("robust_z", key=lambda x: -x.abs())
    an.to_csv(feats / "anomalies_to_investigate_30min.csv", index=False)
    print(sc["baseline_type"].value_counts().to_string())
    print("flagged slots:", len(an), "sustained:", int(sc["sustained"].sum()))
