
import requests
import json
from pathlib import Path
from datetime import datetime, timezone
import pandas as pd

# FIRST EPSS API
API_URL = "https://api.first.org/data/v1/epss"


def fetch_epss_data(cve_ids):

    print("\nConnecting to FIRST EPSS API...")

    params = {
        "cve": ",".join(cve_ids)
    }

    try:
        response = requests.get(
            API_URL,
            params=params,
            timeout=30
        )

        response.raise_for_status()

        data = response.json()

        records = data.get("data", [])

        print("\nAPI connection successful!")
        print("Total records:", data.get("total", 0))

        if not records:
            print("No EPSS records found.")
            return pd.DataFrame()

        # Convert JSON records into DataFrame
        df = pd.DataFrame(records)

        # Convert numeric fields
        df["epss"] = pd.to_numeric(df["epss"])
        df["percentile"] = pd.to_numeric(df["percentile"])

        print("\nEPSS DATA FETCHED:")
        print(df.to_string(index=False))

        # Create timestamp
        timestamp = datetime.now(
            timezone.utc
        ).strftime("%Y%m%d_%H%M%S")

        # Store raw JSON response
        output_dir = Path("data/raw/epss")
        output_dir.mkdir(parents=True, exist_ok=True)

        output_file = output_dir / f"epss_{timestamp}.json"

        with open(output_file, "w") as file:
            json.dump(data, file, indent=4)

        print("\nRaw JSON saved:", output_file)

        return df

    except requests.exceptions.RequestException as error:
        print("\nEPSS API error:", error)
        return pd.DataFrame()


if __name__ == "__main__":

    # Sample CVEs for testing
    test_cves = [
        "CVE-2021-44228",
        "CVE-2023-44487"
    ]

    epss_data = fetch_epss_data(test_cves)
