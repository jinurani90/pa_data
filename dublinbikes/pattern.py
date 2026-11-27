import os
import pandas as pd

CLEAN_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "clean_data.csv")
df = pd.read_csv(CLEAN_FILE, dtype={"station_id": str})
df["collected_at"] = pd.to_datetime(df["collected_at"], utc=True)
                                    
       # ----------  PATTERNS ----------
print("Finding patterns...")

# Use Dublin local time, not UTC, for hours and days
df["local_time"] = df["collected_at"].dt.tz_convert("Europe/Dublin")
df["hour"] = df["local_time"].dt.hour
df["day_name"] = df["local_time"].dt.day_name()
df["is_weekend"] = df["local_time"].dt.dayofweek >= 5

# Movement size per hour, without the possible van moves
riders = df[df["change_type"] != "possible redistribution"].copy()
riders["activity_per_hour"] = riders["change_per_hour"].abs()

# 1. Busiest hours
hourly = riders.groupby("hour")["activity_per_hour"].mean().round(2)
print("Average activity by hour:")
print(hourly)

# 2. Weekday vs weekend, by hour
week_pattern = riders.groupby(["is_weekend", "hour"])["activity_per_hour"].mean().unstack(0).round(2)
week_pattern.columns = ["weekday", "weekend"]
print("Weekday vs weekend:")
print(week_pattern)

# 3. Busiest stations (total bikes moved)
busiest = riders.groupby("station_id")["bike_change"].apply(lambda x: x.abs().sum()).sort_values(ascending=False)
print("Top 10 busiest stations:")
print(busiest.head(10))

# 4. Rain vs no rain
riders["raining"] = riders["precipitation"] > 0
rain = riders.groupby("raining")["activity_per_hour"].mean().round(2)
print("Activity when raining (True) vs not (False):")
print(rain)                             