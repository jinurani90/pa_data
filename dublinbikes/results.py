import os
import pandas as pd

# 1. Load the clean data
folder = os.path.dirname(os.path.abspath(__file__))
df = pd.read_csv(os.path.join(folder, "clean_data.csv"), dtype={"station_id": str})
df["collected_at"] = pd.to_datetime(df["collected_at"], utc=True)

# 2. Add Dublin hour and weekend columns
df["local_time"] = df["collected_at"].dt.tz_convert("Europe/Dublin")
df["hour"] = df["local_time"].dt.hour
df["is_weekend"] = df["local_time"].dt.dayofweek >= 5

# 3. Keep rider movements only (no possible van moves)
riders = df[df["change_type"] != "possible redistribution"].copy()
riders["activity"] = riders["change_per_hour"].abs()
riders["bikes_moved"] = riders["bike_change"].abs()

# 4. Busiest hour
hourly = riders.groupby("hour")["activity"].mean()
busiest_hour = hourly.idxmax()
busiest_hour_value = round(hourly.max(), 2)

# 5. Weekday vs weekend at 8am
weekday_8 = riders[(riders["is_weekend"] == False) & (riders["hour"] == 8)]
weekend_8 = riders[(riders["is_weekend"] == True) & (riders["hour"] == 8)]
weekday_8_value = round(weekday_8["activity"].mean(), 2)
weekend_8_value = round(weekend_8["activity"].mean(), 2)

# 6. Busiest station
station_totals = riders.groupby("station_id")["bikes_moved"].sum()
busiest_station = station_totals.idxmax()
busiest_station_value = int(station_totals.max())

# 7. Rain vs no rain
rain_rows = riders[riders["precipitation"] > 0]
dry_rows = riders[riders["precipitation"] == 0]
rain_value = round(rain_rows["activity"].mean(), 2)
dry_value = round(dry_rows["activity"].mean(), 2)

# 8. Change type shares
total = len(df)
no_change_pct = round(len(df[df["change_type"] == "no change"]) / total * 100, 1)
redistribution_pct = round(len(df[df["change_type"] == "possible redistribution"]) / total * 100, 1)

# 9. Put it all in a table
results = pd.DataFrame({
    "Measure": [
        "Rows after cleaning",
        "Stations",
        "Busiest hour (Dublin time)",
        "Activity at busiest hour (bikes/hour)",
        "Weekday activity at 08:00 (bikes/hour)",
        "Weekend activity at 08:00 (bikes/hour)",
        "Busiest station (ID)",
        "Bikes moved at busiest station",
        "Activity when raining (bikes/hour)",
        "Activity when not raining (bikes/hour)",
        "Readings with no change (%)",
        "Possible redistribution (%)",
    ],
    "Value": [
        total,
        df["station_id"].nunique(),
        str(busiest_hour) + ":00",
        busiest_hour_value,
        weekday_8_value,
        weekend_8_value,
        busiest_station,
        busiest_station_value,
        rain_value,
        dry_value,
        no_change_pct,
        redistribution_pct,
    ],
})

print(results.to_string(index=False))
results.to_csv(os.path.join(folder, "results.csv"), index=False)
print("Saved results.csv")