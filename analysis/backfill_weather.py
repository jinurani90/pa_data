"""Backfill past Dublin weather in 15-minute steps, into a SEPARATE file.

It never opens the bike files for writing. It writes or extends
data/weather/weather_backfill_15min.csv (append-only: slots already saved are kept).

Source: Open-Meteo forecast API with start_date/end_date and minutely_15
(checked on 22 Nov 2026 for 15 to 22 Nov 2026: 768 values, none missing).

Run:  python analysis/backfill_weather.py
"""
from pathlib import Path

import pandas as pd
import requests

from load_data import ROOT, WEATHER_COLS, load_status

URL = ("https://api.open-meteo.com/v1/forecast?latitude=53.3498&longitude=-6.2603"
       "&minutely_15=temperature_2m,relative_humidity_2m,wind_speed_10m,precipitation,weather_code"
       "&start_date={start}&end_date={end}&timezone=UTC")
NAMES = {"temperature_2m": "temperature", "relative_humidity_2m": "humidity",
         "wind_speed_10m": "wind_speed", "precipitation": "precipitation", "weather_code": "weather_code"}


def main(root=ROOT):
    out = Path(root) / "data" / "weather" / "weather_backfill_15min.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    t = load_status(root)["collected_at"]
    start, end = t.min().strftime("%Y-%m-%d"), t.max().strftime("%Y-%m-%d")
    r = requests.get(URL.format(start=start, end=end), timeout=60,
                     headers={"User-Agent": "jinu-ca2-bikes/1.0 (weather backfill)"})
    r.raise_for_status()
    m = r.json()["minutely_15"]
    new = pd.DataFrame({"slot_utc": pd.to_datetime(m["time"]).tz_localize("UTC")})
    for api_name, col in NAMES.items():
        new[col] = m[api_name]
    new["source"] = "open-meteo forecast API minutely_15 (backfill)"
    new["downloaded_at"] = pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%dT%H:%M:%SZ")
    new = new[new["slot_utc"] <= pd.Timestamp.now(tz="UTC")]          # past slots only
    if out.exists():
        old = pd.read_csv(out)
        old["slot_utc"] = pd.to_datetime(old["slot_utc"], utc=True)
        new = new[~new["slot_utc"].isin(old["slot_utc"])]              # keep what is saved
        both = pd.concat([old, new], ignore_index=True)
    else:
        both = new
    both = both.sort_values("slot_utc")
    both["slot_utc"] = both["slot_utc"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    both[["slot_utc"] + WEATHER_COLS + ["source", "downloaded_at"]].to_csv(out, index=False)
    print(f"added {len(new)} new 15-minute slots; file now has {len(both)} -> {out}")


if __name__ == "__main__":
    main()
