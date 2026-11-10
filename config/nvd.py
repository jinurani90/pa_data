
import requests
import json


def fetch_nvd_data():

    # NVD API endpoint
    url = "https://services.nvd.nist.gov/rest/json/cves/2.0"

    # Request parameters
    params = {
        "resultsPerPage": 10
    }

    print("Connecting to NVD API...")

    try:
        response = requests.get(
            url,
            params=params,
            timeout=30
        )

        response.raise_for_status()

        data = response.json()

        print("Connection successful!")
        print("Total vulnerabilities available:", data.get("totalResults"))

        vulnerabilities = data.get("vulnerabilities", [])

        print("\nFetched vulnerability records:", len(vulnerabilities))

        # Display actual fetched data
        for item in vulnerabilities:

            cve = item.get("cve", {})

            cve_id = cve.get("id")

            description = next(
                (
                    d["value"]
                    for d in cve.get("descriptions", [])
                    if d.get("lang") == "en"
                ),
                "No description available"
            )

            print("\nCVE ID:", cve_id)
            print("Description:", description[:200])

        # Save the original API response as JSON
        with open("data/nvd_raw.json", "w") as file:
            json.dump(data, file, indent=4)

        print("\nRaw API response saved successfully.")

    except requests.exceptions.RequestException as error:
        print("API connection error:", error)


if __name__ == "__main__":
    fetch_nvd_data()

