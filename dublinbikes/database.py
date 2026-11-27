import os
import sqlite3
import pandas as pd

folder = os.path.dirname(os.path.abspath(__file__))
df = pd.read_csv(os.path.join(folder, "clean_data.csv"), dtype={"station_id": str})

# 1. Connect (creates the file if it doesn't exist)
db_path = os.path.join(folder, "dublinbikes.db")
conn = sqlite3.connect(db_path)
cur = conn.cursor()

# 2. Create the tables
cur.executescript("""
DROP TABLE IF EXISTS readings;
DROP TABLE IF EXISTS stations;
DROP TABLE IF EXISTS weather;

CREATE TABLE stations (
    station_id TEXT PRIMARY KEY
);

CREATE TABLE weather (
    slot_utc TEXT PRIMARY KEY,
    temperature REAL,
    humidity REAL,
    wind_speed REAL,
    precipitation REAL,
    weather_code INTEGER
);

CREATE TABLE readings (
    reading_id INTEGER PRIMARY KEY AUTOINCREMENT,
    station_id TEXT,
    collected_at TEXT,
    slot_utc TEXT,
    num_bikes INTEGER,
    num_docks_available INTEGER,
    bike_change REAL,
    minutes_since_last REAL,
    change_per_hour REAL,
    change_type TEXT,
    FOREIGN KEY (station_id) REFERENCES stations(station_id),
    FOREIGN KEY (slot_utc) REFERENCES weather(slot_utc)
);
""")

# 3. Fill the tables
stations = df[["station_id"]].drop_duplicates()
stations.to_sql("stations", conn, if_exists="append", index=False)

weather = df[["slot_utc", "temperature", "humidity", "wind_speed", "precipitation", "weather_code"]]
weather = weather.drop_duplicates(subset=["slot_utc"])
weather.to_sql("weather", conn, if_exists="append", index=False)

readings = df[["station_id", "collected_at", "slot_utc", "num_bikes", "num_docks_available",
               "bike_change", "minutes_since_last", "change_per_hour", "change_type"]]
readings.to_sql("readings", conn, if_exists="append", index=False)

# 4. Check it worked
for table in ["stations", "weather", "readings"]:
    count = cur.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    print(table, "rows:", count)

# 5. Example SQL queries
print("\nTop 5 busiest stations:")
print(pd.read_sql("""
    SELECT station_id, SUM(ABS(bike_change)) AS bikes_moved
    FROM readings
    WHERE change_type != 'possible redistribution'
    GROUP BY station_id
    ORDER BY bikes_moved DESC
    LIMIT 5
""", conn))
#list first 5 columns of stations of all tables
print(pd.read_sql(""" select * from stations limit 5""", conn))
#list first 5 columns of weather of all tables
print(pd.read_sql(""" select * from weather limit 5""", conn))
#list first 5 columns of readings of all tables     
print(pd.read_sql(""" select * from readings limit 5""", conn))

print("\nActivity in rain vs no rain (using a JOIN):")
print(pd.read_sql("""
    SELECT CASE WHEN w.precipitation > 0 THEN 'rain' ELSE 'no rain' END AS weather,
           ROUND(AVG(ABS(r.change_per_hour)), 2) AS avg_activity
    FROM readings r
    JOIN weather w ON r.slot_utc = w.slot_utc
    WHERE r.change_type != 'possible redistribution'
    GROUP BY weather
""", conn))

conn.close()
print("\nSaved database:", db_path)