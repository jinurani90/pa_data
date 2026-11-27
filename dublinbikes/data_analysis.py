import glob
import pandas as pd

# Folder saved one CSV per day
#DATA_FOLDER = "dublinbikes/data/bikes/csv"
import os
DATA_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "bikes", "csv")
print("Looking in:", DATA_FOLDER) #given by chatgpt

# Find every daily status file, e.g. status_2026-11-15.csv
files = sorted(glob.glob(DATA_FOLDER + "/status_*.csv"))
print("Files found:", len(files))

# Read each day and stack them into one big table
parts = []
for f in files:
    day = pd.read_csv(f, dtype={"station_id": str})
    if len(day) > 0:          # skip empty files
        parts.append(day)

if len(parts) == 0:
    raise SystemExit("No CSV files found - check the folder path above") #taken from chatgpt
df = pd.concat(parts, ignore_index=True)
print("Total rows:", len(df))
print(df.head())
# ---------- STEP 2: CLEANING ----------
print("Cleaning data...")
# 1. Turn the time text into real date-times so we can sort and subtract them
df["collected_at"] = pd.to_datetime(df["collected_at"], utc=True)

# to identify the hours when stations are not renting, we can filter the DataFrame for rows where "is_renting" is False and then extract the hour from the "collected_at" column. We can then count the occurrences of each hour and sort them by hour.
print("Hours when stations are not renting:")
not_renting = df[df["is_renting"] == False]
print(not_renting["collected_at"].dt.tz_convert("Europe/Dublin").dt.hour.value_counts().sort_index())

# 2. Remove duplicate rows (same station at the same time)
before = len(df)
df = df.drop_duplicates(subset=["station_id", "collected_at"])
print("Duplicates removed:", before - len(df))

print(df["is_installed"].value_counts())
print(df["is_renting"].value_counts())

# 3. Keep only stations that are working (installed and renting)
before = len(df)
df = df[(df["is_installed"] == 1) & (df["is_renting"] == 1)]
print("Out-of-service rows removed:", before - len(df))

# 4. Check missing values in each column
print("Missing values per column:")
print(df.isna().sum())

print("Rows after cleaning:", len(df))
print("Stations:", df["station_id"].nunique())

# ---------- STEP 3: FILL MISSING WEATHER ----------

print("\nFilling missing weather...")
weather_file= os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "weather", "weather_backfill_15min.csv")
weather = pd.read_csv(weather_file)
weather["slot_utc"] = pd.to_datetime(weather["slot_utc"], utc=True)

weather_cols = ["temperature", "humidity", "wind_speed", "precipitation", "weather_code"]
weather = weather[["slot_utc"] + weather_cols]

# Round each bike reading down to its 15-minute slot, eg. 08:07 becomes 08:00
df["slot_utc"] = df["collected_at"].dt.floor("15min")

print("Missing temperature before:", df["temperature"].isna().sum())

# Join the backfill on to the bike data by slot
df = df.merge(weather, on="slot_utc", how="left", suffixes=("", "_backfill"))

# Fill only the empty cells, then drop the helper columns
for col in weather_cols:
    df[col] = df[col].fillna(df[col + "_backfill"])
    df = df.drop(columns=[col + "_backfill"])

print("Missing temperature after:", df["temperature"].isna().sum())
print("Rows:", len(df))

# ---------- STEP 4: BIKE CHANGE PER STATION ----------
print("\n\n....Calculating bike changes...")

# Put each station's readings in time order
df = df.sort_values(["station_id", "collected_at"]).reset_index(drop=True)
print(df.head())
# Change in bikes since the station's previous reading
df["bike_change"] = df.groupby("station_id")["num_bikes"].diff()

# Real minutes since the station's previous reading
df["minutes_since_last"] = df.groupby("station_id")["collected_at"].diff().dt.total_seconds() / 60

# Remove each station's first reading (nothing to compare it with)
df = df.dropna(subset=["bike_change", "minutes_since_last"])

# Remove big gaps, e.g. the overnight closure, so they don't count as one huge change
df = df[df["minutes_since_last"] <= 30]

# Change per hour, so different gaps are comparable
df["change_per_hour"] = df["bike_change"] / df["minutes_since_last"] * 60

print(df[["station_id", "collected_at", "num_bikes", "bike_change", "minutes_since_last", "change_per_hour"]].head(10))
print("Rows after removal of 1st reading and large gaps:", len(df))
print(df["minutes_since_last"].describe())

# ---------- STEP 5: CATEGORISE CHANGES ----------
print("Categorising changes...")

redistribution_constant = 5  # just a guess - a change of 5 bikes in one reading is probably a redistribution, not normal usage


def categorise(change):
    if abs(change) >= redistribution_constant:
        return "possible redistribution"
    elif change > 0:
        return "net increase"
    elif change < 0:
        return "net decrease"
    else:
        return "no change"

df["change_type"] = df["bike_change"].apply(categorise)

print(df["change_type"].value_counts())
print((df["change_type"].value_counts(normalize=True) * 100).round(1))
# ---------- SAVE CLEAN DATA ----------
df.to_csv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "clean_data.csv"), index=False)
print("Saved clean_data.csv")
