What the project does

A GitHub Actions workflow saves a snapshot of every Dublin Bikes station
about every 3 minutes, along with the current Dublin weather. Each day goes
into its own CSV file. The analysis looks at **how the number of bikes at
each station changes between snapshots**, using the **real number of
minutes** between them. It then asks when, where and in what weather bikes
are used most.

## Folder layout

| Path | What it is |
|---|---|
| `.github/workflows/collect_bikes.yml` | Runs the collector on a schedule |
| `dublinbikes/collectors/bikes_collect.py` | Fetches bikes (GBFS) and weather (Open-Meteo), and appends to today's CSV |
| `dublinbikes/data/bikes/csv/status_*.csv` | One CSV of station snapshots per day |
| `dublinbikes/data/weather/weather_backfill_15min.csv` | Past weather in 15-minute slots, used to fill early gaps |
| `dublinbikes/data_analysis.py` | Steps 1 to 5: load, clean, fill weather, bike changes, categories |
| `dublinbikes/pattern.py` | Step 6: hourly, weekday/weekend, station and rain patterns |
| `dublinbikes/results.py` | Step 7: summary results table, saved as `results.csv` |
| `dublinbikes/database.py` | Step 8: stores the data in a SQLite relational database |

`clean_data.csv` and `dublinbikes.db` are generated files, so they are not
stored on GitHub.

## The steps, one by one

### Step 1: load the data (`data_analysis.py`)
Finds every `status_*.csv` with `glob`, reads each one with pandas, skips
empty files, and joins them with `pd.concat`. The folder path is built from
`__file__`, so the script works from any folder.

### Step 2: clean
- Turns `collected_at` into real UTC dates.
- Removes duplicate station and time rows (there were none).
- Keeps only rows where the station is installed and renting.
  **Why:** stations stop renting overnight (about 00:30 to 05:00), so those
  rows don't show real usage. About 93% of the non-renting rows fell between
  midnight and 5am.

### Step 3: fill missing weather
The early files had no weather. Each reading is rounded down to its
15-minute slot (`dt.floor("15min")`), matched to the backfill file with a
left merge, and only the empty cells are filled with `fillna`. The number of
missing weather rows went from 32,986 to 0.

### Step 4: bike change per station
- Sorts by station, then by time.
- `bike_change` is the number of bikes compared with that station's previous
  reading (`groupby("station_id")` and `diff()`).
- `minutes_since_last` is the real number of minutes between readings. The
  median is about 3.0.
- Gaps over 30 minutes are dropped, so they don't count as one huge change.
- `change_per_hour = bike_change / minutes_since_last * 60`, so different gaps
  can be compared fairly.

### Step 5: categorise each change
| Category | Rule |
|---|---|
| possible redistribution | the change is 5 or more bikes, up or down (exploratory threshold) |
| net increase | the change is above 0 |
| net decrease | the change is below 0 |
| no change | the change is 0 |

Redistribution is checked first, because a change of +6 is also above 0.

### Step 6: patterns (`pattern.py`)
Converts the times to Dublin local time, then measures activity as
`abs(change_per_hour)`, leaving out possible van moves. It compares:
1. activity by hour
2. weekdays against weekends, hour by hour
3. the busiest stations by total bikes moved
4. rain (`precipitation > 0`) against no rain

### Step 7: results table (`results.py`)
Puts the key numbers in one table and saves it as `results.csv`.

### Step 8: relational database (`database.py`)
Stores the clean data in SQLite, a file database built into Python, as
three linked tables:

| Table | Key | Holds |
|---|---|---|
| `stations` | `station_id` (primary key) | one row per station |
| `weather` | `slot_utc` (primary key) | one row per 15-minute weather slot |
| `readings` | `reading_id`, plus foreign keys `station_id` and `slot_utc` | each bike reading with its change and category |

Example queries: the top 5 busiest stations, and a **JOIN** of readings with
weather to compare activity in rain and no rain.

## Results

| Measure | Value |
|---|---|
| Rows after cleaning | 410,111 |
| Stations | 113 |
| Busiest hour (Dublin time) | 8:00 |
| Activity at busiest hour | 8.49 bikes/hour |
| Weekday activity at 08:00 | 10.68 bikes/hour |
| Weekend activity at 08:00 | 1.21 bikes/hour |
| Busiest station (ID) | 69 (2,130 bikes moved) |
| Activity when raining | 3.21 bikes/hour |
| Activity when not raining | 3.92 bikes/hour |
| Readings with no change | 83.0% |
| Possible redistribution | 0.3% |

**What this means**
- **Commuting:** at 8am, weekdays are about 9 times busier than weekends.
- **Rain:** activity is about 18% lower when it rains. This is a link seen
  over a short period, not proof that rain causes it.
- **Quiet most of the time:** 83% of 3-minute readings show no change, and
  only 0.3% look like van redistribution.

## Limitations
- Only about two weeks of data, all in November.
- The threshold of 5 bikes for redistribution is a guess, not confirmed by
  the operator.
- The weather is for central Dublin, not for each station.
- The 30-minute gap cut-off is a choice I made.

