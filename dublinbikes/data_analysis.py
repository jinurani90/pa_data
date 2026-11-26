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