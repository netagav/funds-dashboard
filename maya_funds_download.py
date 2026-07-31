from pathlib import Path

import requests

URL = "https://maya.tase.co.il/api/v1/funds/file"
OUTPUT_PATH = Path(__file__).resolve().parent / "funds.csv"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Content-Type": "application/json",
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://maya.tase.co.il",
    "Referer": "https://maya.tase.co.il/he/funds/all",
}


def download_funds_csv(output_path: Path = OUTPUT_PATH) -> None:
    session = requests.Session()

    session.get(
        "https://maya.tase.co.il/he/funds/all",
        headers=HEADERS,
        timeout=30,
    )

    response = session.post(URL, headers=HEADERS, json={}, timeout=60)
    response.raise_for_status()

    with open(output_path, "wb") as f:
        f.write(response.content)

    print(f"Saved {len(response.content):,} bytes to {output_path}")
    print("Content-Type:", response.headers.get("Content-Type"))
    print("x-total-count:", response.headers.get("x-total-count"))


if __name__ == "__main__":
    download_funds_csv()