"""Run from the dublinbikes/ folder:  python -m pytest -q tests
These tests use small made-up data in a temporary folder. They never touch data/."""
import importlib
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "analysis"))
sys.path.insert(0, str(HERE.parent / "collectors"))
import features  # noqa: E402
import load_data  # noqa: E402

COLS = ["collected_at", "feed_last_updated", "station_id", "num_bikes", "mechanical", "electrical",
        "num_bikes_disabled", "num_docks_available", "num_docks_disabled", "is_installed", "is_renting",
        "is_returning", "last_reported", "temperature", "humidity", "wind_speed", "precipitation",
        "weather_code"]


def make_repo(tmp, minutes=180, step=3):
    csv = tmp / "data" / "bikes" / "csv"
    csv.mkdir(parents=True)
    pd.DataFrame({"station_id": ["1"], "name": ["Test"], "address": [""], "lat": [53.3], "lon": [-6.2],
                  "capacity": [20]}).to_csv(csv / "stations.csv", index=False)
    t = pd.date_range("2026-11-18 08:00", periods=minutes // step, freq=f"{step}min", tz="UTC")
    bikes = np.clip(15 - np.arange(len(t)) // 3, 0, 20)
    d = pd.DataFrame({c: 0 for c in COLS}, index=range(len(t)))
    d["collected_at"] = t.strftime("%Y-%m-%dT%H:%M:%SZ")
    d["feed_last_updated"] = d["collected_at"]
    d["station_id"], d["num_bikes"], d["num_docks_available"] = "1", bikes, 20 - bikes
    d[["is_installed", "is_renting", "is_returning"]] = True
    d["temperature"] = np.where(np.arange(len(t)) % 5 == 0, np.nan, 9.0)   # some blank weather
    d[COLS].to_csv(csv / "status_2026-11-18.csv", index=False)
    (csv / "status_2026-11-2012.csv").write_text("\r\n")                      # empty file like the repo
    return tmp, d


def test_loader_keeps_every_row_and_skips_empty(tmp_path):
    root, d = make_repo(tmp_path)
    df = load_data.load_all(root)
    assert len(df) == len(d)


def test_backfill_only_fills_blanks(tmp_path):
    root, d = make_repo(tmp_path)
    w = root / "data" / "weather"
    w.mkdir(parents=True)
    slots = pd.date_range("2026-11-18 08:00", periods=12, freq="15min", tz="UTC")
    pd.DataFrame({"slot_utc": slots.strftime("%Y-%m-%dT%H:%M:%SZ"), "temperature": 5.0, "humidity": 80,
                  "wind_speed": 10, "precipitation": 0.0, "weather_code": 3}).to_csv(
        w / "weather_backfill_15min.csv", index=False)
    df = load_data.load_all(root)
    assert len(df) == len(d)
    assert df["temperature"].notna().all()
    assert (df.loc[df["weather_source"] == "live", "temperature"] == 9.0).all()   # live never replaced


def test_target_looks_60_minutes_ahead(tmp_path):
    root, _ = make_repo(tmp_path)
    df = features.build_features(root)
    row = df.iloc[0]
    later = df[df["collected_at"] == row["collected_at"] + pd.to_timedelta(60, unit="min")]["num_bikes"].iloc[0]
    assert row["bikes_in_60m"] == later


def test_no_future_leakage(tmp_path):
    root, _ = make_repo(tmp_path)
    a = features.build_features(root)
    f = root / "data" / "bikes" / "csv" / "status_2026-11-18.csv"
    d = pd.read_csv(f)
    cut = pd.Timestamp("2026-11-18 09:30", tz="UTC")
    d.loc[pd.to_datetime(d["collected_at"], utc=True) > cut, "num_bikes"] = 20
    d.to_csv(f, index=False)                                          # temp copy only
    b = features.build_features(root)
    cols = ["delta_bikes", "delta_bikes_15m", "delta_bikes_60m", "roll_mean_60m", "changes_per_hour"]
    pd.testing.assert_frame_equal(a.loc[a["collected_at"] <= cut, cols].reset_index(drop=True),
                                  b.loc[b["collected_at"] <= cut, cols].reset_index(drop=True))


def test_collector_keeps_columns_and_caches_weather(tmp_path, monkeypatch):
    monkeypatch.setenv("BIKES_PROJECT_DIR", str(tmp_path))       # never the real repo
    import logging
    for h in list(logging.getLogger().handlers):                  # fresh log file in tmp_path
        logging.getLogger().removeHandler(h)
    import bikes_collect
    importlib.reload(bikes_collect)
    assert str(bikes_collect.DATA_DIR).startswith(str(tmp_path))
    calls = {"weather": 0, "n": 0}

    def fake(url, retries=3, timeout=15):
        if "open-meteo" in url:
            calls["weather"] += 1
            if calls["weather"] > 1:
                raise bikes_collect.requests.Timeout("slow")
            return {"current": {"time": "2026-11-22T10:30", "temperature_2m": 9.0}}
        calls["n"] += 1
        return {"last_updated": f"feed{calls['n']}", "data": {"stations": [
            {"station_id": "1", "num_vehicles_available": 3, "vehicle_types_available": []}]}}

    monkeypatch.setattr(bikes_collect, "get_json", fake)
    bikes_collect.collect_once()
    bikes_collect.collect_once()                    # weather not due yet: cached value reused
    out = pd.read_csv(next((tmp_path / "data" / "bikes" / "csv").glob("status_*.csv")))
    assert list(out.columns) == COLS
    assert out["temperature"].tolist() == [9.0, 9.0]
    assert calls["weather"] == 1
