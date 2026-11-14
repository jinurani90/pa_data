"""Fetch YouTube's mostPopular chart for Ireland, the UK, and the US.

Set YOUTUBE_API_KEY in your environment before running:
    python fetch_youtube.py

Each run writes one timestamped JSON file under data/raw/.
"""

from datetime import datetime, timezone
import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen
import ssl
import certifi


API_URL = "https://www.googleapis.com/youtube/v3/videos"
REGIONS = {"IE": "Ireland", "GB": "United Kingdom", "US": "United States"}
OUTPUT_DIR = Path("data/raw")


def fetch_chart(api_key: str, region_code: str) -> dict:
    """Fetch up to 50 mostPopular videos for one region."""
    params = {
        "key": api_key,
        "part": "snippet,contentDetails,statistics",
        "chart": "mostPopular",
        "regionCode": region_code,
        "maxResults": 50,
    }
    request_url = f"{API_URL}?{urlencode(params)}"
    try:
        #with urlopen(request_url, timeout=30) as response:
        ssl_context = ssl.create_default_context(cafile=certifi.where())
        with urlopen(request_url, timeout=30, context=ssl_context) as response:
            return json.load(response)
    except HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"YouTube API returned HTTP {exc.code}: {details}") from exc
    except URLError as exc:
        raise RuntimeError(f"Could not reach YouTube API: {exc.reason}") from exc


def main() -> None:
    api_key = os.environ.get("YOUTUBE_API_KEY")
    if not api_key:
        raise SystemExit(
            "Missing YOUTUBE_API_KEY. Create an API key in Google Cloud Console, "
            "then set it in your terminal before running this script."
        )

    captured_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    snapshot = {"captured_at_utc": captured_at, "regions": {}}

    for code, name in REGIONS.items():
        result = fetch_chart(api_key, code)
        videos = []
        for rank, video in enumerate(result.get("items", []), start=1):
            snippet = video.get("snippet", {})
            details = video.get("contentDetails", {})
            stats = video.get("statistics", {})
            videos.append(
                {
                    "rank": rank,
                    "video_id": video.get("id"),
                    "title": snippet.get("title"),
                    "channel_id": snippet.get("channelId"),
                    "channel_title": snippet.get("channelTitle"),
                    "category_id": snippet.get("categoryId"),
                    "published_at": snippet.get("publishedAt"),
                    "duration": details.get("duration"),
                    "view_count": stats.get("viewCount"),
                    "like_count": stats.get("likeCount"),
                    "comment_count": stats.get("commentCount"),
                }
            )
        snapshot["regions"][code] = {"name": name, "videos": videos}
        print(f"{name}: fetched {len(videos)} videos")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    filename = datetime.now(timezone.utc).strftime("snapshot_%Y%m%dT%H%M%SZ.json")
    output_path = OUTPUT_DIR / filename
    output_path.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n")
    print(f"Saved snapshot to {output_path}")


if __name__ == "__main__":
    main()
