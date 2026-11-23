"""Load ALL collected Dublin Bikes data (old and new) without changing any file.

Reads:  data/bikes/csv/status_*.csv        (every day file, old 15-minute and new 3-minute)
        data/bikes/recovered/status_*.csv  (rows restored from Git history, if any)
        data/weather/weather_backfill_15min.csv (optional, made by backfill_weather.py)
Empty files (for example status_2026-11-2012.csv) are skipped, never deleted.

Use in a notebook:
    import sys; sys.path.append("analysis")
    from load_data import load_all
    df = load_all()          # one row per station per snapshot, weather filled where possible
"""
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]          # the dublinbikes/ folder
WEATHER_COLS = ["temperature", "humidity", "wind_speed", "precipitation", "weather_code"]


def list_status_files(root=ROOT):
    root = Path(root)
    files = sorted((root / "data" / "bikes" / "csv").glob("status_*.csv"))
    files += sorted((root / "data" / "bikes" / "recovered").glob("status_*.csv"))
    return [f for f in files if f.stat().st_size > 10]      # skip empty files


def load_status(root=ROOT):
    parts = []
    for f in list_status_files(root):
        d = pd.read_csv(f, dtype={"station_id": str})
        d["source_file"] = f.name
        parts.append(d)
    df = pd.concat(parts, ignore_index=True)
    n_raw = len(df)
    df["collected_at"] = pd.to_datetime(df["collected_at"], utc=True)
    for c in ["is_installed", "is_renting", "is_returning"]:
        df[c] = df[c].astype(str).str.strip().str.lower().isin(["true", "1", "1.0"])
    # The same snapshot can only appear twice if a file was restored twice: keep one copy.
    df = df.drop_duplicates(["station_id", "collected_at"], keep="first")
    df = df.sort_values(["station_id", "collected_at"]).reset_index(drop=True)
    print(f"status files: {len(list_status_files(root))}, rows read: {n_raw}, "
          f"after removing exact duplicates: {len(df)}, stations: {df['station_id'].nunique()}")
    return df


def attach_weather(df, root=ROOT):
    """Keep the live weather; fill ONLY the empty cells from the backfill file.
    Adds weather_source = live / backfill / missing. Bike rows are never dropped."""
    df = df.copy()
    df["weather_source"] = np.where(df["temperature"].notna(), "live", "missing")
    bf_path = Path(root) / "data" / "weather" / "weather_backfill_15min.csv"
    if bf_path.exists():
        bf = pd.read_csv(bf_path)
        bf["slot_utc"] = pd.to_datetime(bf["slot_utc"], utc=True)
        bf = bf.rename(columns={c: f"bf_{c}" for c in WEATHER_COLS})
        df["slot_utc"] = df["collected_at"].dt.floor("15min")
        df = df.merge(bf[["slot_utc"] + [f"bf_{c}" for c in WEATHER_COLS]], on="slot_utc", how="left")
        fill = df["temperature"].isna() & df["bf_temperature"].notna()
        for c in WEATHER_COLS:
            df[c] = df[c].where(df[c].notna(), df[f"bf_{c}"])
        df.loc[fill, "weather_source"] = "backfill"
        df = df.drop(columns=["slot_utc"] + [f"bf_{c}" for c in WEATHER_COLS])
    print(df.drop_duplicates("collected_at")["weather_source"].value_counts().to_string())
    return df


def load_stations(root=ROOT):
    st = pd.read_csv(Path(root) / "data" / "bikes" / "csv" / "stations.csv", dtype={"station_id": str})
    st["capacity"] = pd.to_numeric(st["capacity"], errors="coerce")
    return st


def load_all(root=ROOT):
    df = attach_weather(load_status(root), root)
    df = df.merge(load_stations(root)[["station_id", "name", "lat", "lon", "capacity"]],
                  on="station_id", how="left")
    return df.sort_values(["station_id", "collected_at"]).reset_index(drop=True)


if __name__ == "__main__":
    d = load_all()
    print(d["collected_at"].min(), "to", d["collected_at"].max())
