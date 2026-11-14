
import requests
from datetime import datetime, timedelta, timezone

API_URL = "https://services.nvd.nist.gov/rest/json/cves/2.0"


def fetch_recently_modified():

    # Current UTC time
    end_time = datetime.now(timezone.utc)

    # Previous 24 hours
    start_time = end_time - timedelta(hours=24)

    params = {
        "lastModStartDate": start_time.strftime(
            "%Y-%m-%dT%H:%M:%S.000Z"
        ),
        "lastModEndDate": end_time.strftime(
            "%Y-%m-%dT%H:%M:%S.000Z"
        ),
        "resultsPerPage": 100
    }

    print("Checking recently modified NVD records...")
    print("From:", params["lastModStartDate"])
    print("To:", params["lastModEndDate"])

    try:
        response = requests.get(
            API_URL,
            params=params,
            timeout=60
        )

        response.raise_for_status()

        result = response.json()

        vulnerabilities = result.get("vulnerabilities", [])

        print("\nTotal matching records:", result.get("totalResults"))
        print("Records returned:", len(vulnerabilities))

        for item in vulnerabilities:

            cve = item["cve"]

            print("\nCVE ID:", cve.get("id"))
            print("Published:", cve.get("published"))
            print("Last Modified:", cve.get("lastModified"))

        print("\nAPI request completed successfully.")

    except requests.exceptions.RequestException as error:
        print("NVD API error:", error)


if __name__ == "__main__":
    fetch_recently_modified()
