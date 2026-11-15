"""Collect Dublin Bikes station status and Dublin weather to daily CSV files."""


"""Collect Dublin Bikes station status and Dublin weather to daily CSV files."""

import csv
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

PROJECT_DIR = Path(__file__).resolve().parents[1]

DATA_DIR = PROJECT_DIR / "data" / "bikes" / "csv"
LOG_DIR = PROJECT_DIR / "logs"
STATE_FILE = DATA_DIR / "last_updated.txt"

USER_AGENT = (
    os.environ.get("BIKES_USER_AGENT")
    or os.environ.get("AE_USER_AGENT")
    or "jinu-ca2-bikes/1.0"
)

COLUMNS = [
    "collected_at", "feed_last_updated", "station_id", "num_bikes",
    "mechanical", "electrical", "num_bikes_disabled", "num_docks_available",
    "num_docks_disabled", "is_installed", "is_renting", "is_returning",
    "last_reported", "temperature", "humidity", "wind_speed",
    "precipitation", "weather_code",
]

DATA_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_DIR / "collect_bikes.log"),
    ],
)


def get_json(url: str, retries: int = 3) -> dict:
    """Fetch JSON with retries and an identifying User-Agent."""
    delay = 5
    for attempt in range(1, retries + 1):
        try:
            response = requests.get(
                url, timeout=30, headers={"User-Agent": USER_AGENT}
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
    stations = get_json(INFO_URL)["data"]["stations"]
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


def collect_once() -> int:
    status = get_json(STATUS_URL)
    feed_time = status["last_updated"]
    if STATE_FILE.exists() and STATE_FILE.read_text(encoding="utf-8").strip() == str(feed_time):
        logging.info("Feed has not changed since %s; skipping", feed_time)
        return 0

    try:
        weather = get_json(WEATHER_URL).get("current", {})
    except requests.RequestException as exc:
        logging.error("Weather request failed; saving bike data without weather: %s", exc)
        weather = {}

    now = datetime.now(timezone.utc)
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
            "temperature": weather.get("temperature_2m"),
            "humidity": weather.get("relative_humidity_2m"),
            "wind_speed": weather.get("wind_speed_10m"),
            "precipitation": weather.get("precipitation"),
            "weather_code": weather.get("weather_code"),
        })

    output = DATA_DIR / f"status_{now.strftime('%Y-%m-%d')}.csv"
    new_file = not output.exists()
    with output.open("a", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=COLUMNS)
        if new_file:
            writer.writeheader()
        writer.writerows(rows)

    STATE_FILE.write_text(str(feed_time), encoding="utf-8")
    logging.info("Saved %d station rows to %s", len(rows), output)
    return len(rows)


if __name__ == "__main__":
    save_stations()
    collect_once()
