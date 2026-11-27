import os
import pandas as pd

CLEAN_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "clean_data.csv")
df = pd.read_csv(CLEAN_FILE, dtype={"station_id": str})
df["collected_at"] = pd.to_datetime(df["collected_at"], utc=True)