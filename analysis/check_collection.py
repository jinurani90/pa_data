"""Daily health check: snapshots per day, gaps, and weather coverage. Read-only.

Run:  python analysis/check_collection.py
"""
import pandas as pd

from load_data import load_status

df = load_status()
snap = df.drop_duplicates("collected_at")[["collected_at", "temperature"]].sort_values("collected_at")
snap["gap_min"] = snap["collected_at"].diff().dt.total_seconds() / 60
snap["day"] = snap["collected_at"].dt.strftime("%Y-%m-%d")
out = snap.groupby("day").agg(
    snapshots=("collected_at", "size"),
    median_gap_min=("gap_min", "median"),
    longest_gap_min=("gap_min", "max"),
    weather_missing_pct=("temperature", lambda s: round(s.isna().mean() * 100, 1)),
).round(1)
print(out.to_string())
print("Full day at 3 minutes = 480 snapshots; at 15 minutes = 96.")
