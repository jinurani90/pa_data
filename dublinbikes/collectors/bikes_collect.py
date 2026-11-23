"""Collect Dublin Bikes station status and Dublin weather to daily CSV files.

SAFE UPGRADE (22 Nov 2026): the bike CSV files keep the SAME path
(data/bikes/csv/status_YYYY-MM-DD.csv) and the SAME 18 columns in the same order.
Nothing is deleted or rewritten; rows are only appended.

Weather fix:
  * Open-Meteo "current" only changes every 15 minutes, so it is fetched at most
    once every 15 minutes (not on every 3-minute bike poll).
  * Every weather fetch (good or failed) is logged with Open-Meteo's own
    timestamp in a NEW file: data/weather/weather_YYYY-MM-DD.csv
  * The last good reading is kept in data/weather/last_weather.json and reused
    for bike rows for up to 30 minutes, so one slow request no longer blanks a snapshot.
"""

import csv
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

BASE_URL = "https://api.cyclocity.fr/contracts/dublin/gbfs/v3"
STATUS_URL = f"{BASE_URL}/station_status.json"
INFO_URL = f"{BASE_URL}/station_information.json"

WEATHER_URL = (
    "https://api.open-meteo.com/v1/forecast?latitude=53.3498&longitude=-6.2603"
    "&current=temperature_2m,relative_humidity_2m,wind_speed_10m,"
    "precipitation,weather_code"
)

# BIKES_PROJECT_DIR is only set by the tests, so they never write into the real data or log.
PROJECT_DIR = Path(os.environ.get("BIKES_PROJECT_DIR") or Path(__file__).resolve().parents[1])

DATA_DIR = PROJECT_DIR / "data" / "bikes" / "csv"
WEATHER_DIR = PROJECT_DIR / "data" / "weather"
WEATHER_STATE = WEATHER_DIR / "last_weather.json"
LOG_DIR = PROJECT_DIR / "logs"
STATE_FILE = DATA_DIR / "last_updated.txt"

WEATHER_EVERY_MIN = 15      # Open-Meteo "current" values change in 15-minute steps
WEATHER_MAX_AGE_MIN = 30    # reuse the last good reading for at most 30 minutes

USER_AGENT = (
    os.environ.get("BIKES_USER_AGENT")
    or os.environ.get("AE_USER_AGENT")
    or "jinu-ca2-bikes/1.0"
)

# SAME columns, SAME order as the files already in the repo. Do not change.
COLUMNS = [
    "collected_at", "feed_last_updated", "station_id", "num_bikes",
    "mechanical", "electrical", "num_bikes_disabled", "num_docks_available",
    "num_docks_disabled", "is_installed", "is_renting", "is_returning",
    "last_reported", "temperature", "humidity", "wind_speed",
    "precipitation", "weather_code",
]
WEATHER_COLUMNS = [
    "fetched_at", "status", "weather_time", "temperature", "humidity",
    "wind_speed", "precipitation", "weather_code", "error",
]

DATA_DIR.mkdir(parents=True, exist_ok=True)
WEATHER_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_DIR / "collect_bikes.log"),
    ],
)


def get_json(url: str, retries: int = 3, timeout: int = 15) -> dict:
    """Fetch JSON with retries and an identifying User-Agent."""
    delay = 5
    for attempt in range(1, retries + 1):
        try:
            response = requests.get(
                url, timeout=timeout, headers={"User-Agent": USER_AGENT}
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:
            logging.warning("Attempt %d failed for %s: %s", attempt, url, exc)
            if attempt == retries:
                raise
            time.sleep(delay)
            delay *= 2
    raise RuntimeError("Request retries exhausted")


def save_stations() -> None:
    """Write station metadata once, for joining status rows to locations."""
    path = DATA_DIR / "stations.csv"
    if path.exists():
        return
    stations = get_json(INFO_URL, retries=3, timeout=15)["data"]["stations"]
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["station_id", "name", "address", "lat", "lon", "capacity"])
        for station in stations:
            names = station.get("name", [])
            name = next((item.get("text", "") for item in names if item.get("text")), "")
            writer.writerow([
                station["station_id"], name, station.get("address", ""),
                station.get("lat", ""), station.get("lon", ""),
                station.get("capacity", ""),
            ])
    logging.info("Saved station metadata to %s", path)


def _minutes_since(iso_text, now):
    if not iso_text:
        return None
    then = datetime.strptime(iso_text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    return (now - then).total_seconds() / 60


def _append_weather_log(row: dict, now: datetime) -> None:
    path = WEATHER_DIR / f"weather_{now.strftime('%Y-%m-%d')}.csv"
    new_file = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=WEATHER_COLUMNS)
        if new_file:
            writer.writeheader()
        writer.writerow({k: row.get(k, "") for k in WEATHER_COLUMNS})


def get_weather(now: datetime) -> dict:
    """Return the latest good Open-Meteo reading (fresh, or at most 30 minutes old)."""
    state = {}
    if WEATHER_STATE.exists():
        try:
            state = json.loads(WEATHER_STATE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            state = {}

    age = _minutes_since(state.get("fetched_at"), now)
    if age is None or age >= WEATHER_EVERY_MIN - 1:          # due: about every 15 minutes
        fetched_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        try:
            current = get_json(WEATHER_URL, retries=2, timeout=20).get("current") or {}
            if not current:
                raise ValueError("no 'current' block in the Open-Meteo reply")
            state = {
                "fetched_at": fetched_at,
                "weather_time": current.get("time"),
                "temperature": current.get("temperature_2m"),
                "humidity": current.get("relative_humidity_2m"),
                "wind_speed": current.get("wind_speed_10m"),
                "precipitation": current.get("precipitation"),
                "weather_code": current.get("weather_code"),
            }
            WEATHER_STATE.write_text(json.dumps(state, indent=1), encoding="utf-8")
            _append_weather_log({**state, "status": "ok"}, now)
            age = 0
        except (requests.RequestException, ValueError) as exc:
            logging.error("Weather request failed: %s", exc)
            _append_weather_log({"fetched_at": fetched_at, "status": "error",
                                 "error": str(exc)[:200]}, now)

    if state and age is not None and age <= WEATHER_MAX_AGE_MIN:
        return state
    logging.warning("No weather reading from the last %d minutes; weather left empty",
                    WEATHER_MAX_AGE_MIN)
    return {}


def collect_once() -> int:
    status = get_json(STATUS_URL, retries=3, timeout=15)
    feed_time = status["last_updated"]
    if STATE_FILE.exists() and STATE_FILE.read_text(encoding="utf-8").strip() == str(feed_time):
        logging.info("Feed has not changed since %s; skipping", feed_time)
        return 0

    now = datetime.now(timezone.utc)
    weather = get_weather(now)
    collected_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    rows = []
    for station in status["data"]["stations"]:
        vehicle_counts = {
            item["vehicle_type_id"]: item["count"]
            for item in station.get("vehicle_types_available", [])
        }
        rows.append({
            "collected_at": collected_at,
            "feed_last_updated": feed_time,
            "station_id": station["station_id"],
            "num_bikes": station.get("num_vehicles_available"),
            "mechanical": vehicle_counts.get("mechanical", 0),
            "electrical": vehicle_counts.get("electrical", 0),
            "num_bikes_disabled": station.get("num_vehicles_disabled", 0),
            "num_docks_available": station.get("num_docks_available"),
            "num_docks_disabled": station.get("num_docks_disabled", 0),
            "is_installed": station.get("is_installed"),
            "is_renting": station.get("is_renting"),
            "is_returning": station.get("is_returning"),
            "last_reported": station.get("last_reported"),
            "temperature": weather.get("temperature"),
            "humidity": weather.get("humidity"),
            "wind_speed": weather.get("wind_speed"),
            "precipitation": weather.get("precipitation"),
            "weather_code": weather.get("weather_code"),
        })

    output = DATA_DIR / f"status_{now.strftime('%Y-%m-%d')}.csv"
    new_file = not output.exists()
    with output.open("a", newline="", encoding="utf-8") as stream:   # append only
        writer = csv.DictWriter(stream, fieldnames=COLUMNS)
        if new_file:
            writer.writeheader()
        writer.writerows(rows)

    STATE_FILE.write_text(str(feed_time), encoding="utf-8")
    logging.info("Saved %d station rows to %s (weather time %s)",
                 len(rows), output, weather.get("weather_time", "none"))
    return len(rows)


if __name__ == "__main__":
    save_stations()
    collect_once()
