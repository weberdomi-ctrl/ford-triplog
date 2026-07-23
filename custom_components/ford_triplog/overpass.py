"""
Ford Triplog

OpenStreetMap Overpass client.

File: overpass.py
Frozen phase: 1
Version: 1.4.0-phase1
Date: 2026-07-23
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import requests


OVERPASS_URLS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
)

REQUEST_TIMEOUT = 300
MAX_RETRIES = 3


def build_charging_station_query(country_code: str) -> str:
    """Create an Overpass query for all charging stations in one country."""

    return f"""
[out:json][timeout:240];

area["ISO3166-1"="{country_code}"]["admin_level"="2"]->.searchArea;

(
  node["amenity"="charging_station"](area.searchArea);
  way["amenity"="charging_station"](area.searchArea);
  relation["amenity"="charging_station"](area.searchArea);
);

out center tags;
""".strip()


def download_overpass_data(
    country_code: str,
    output_file: Path | None = None,
) -> dict[str, Any]:
    """
    Download charging station data from Overpass.

    If output_file is supplied, the unmodified response is also saved
    as readable JSON.
    """

    query = build_charging_station_query(country_code)
    last_error: Exception | None = None

    for attempt in range(1, MAX_RETRIES + 1):
        for overpass_url in OVERPASS_URLS:
            print(
                f"Overpass request: {overpass_url} "
                f"(attempt {attempt}/{MAX_RETRIES})"
            )

            try:
                response = requests.post(
                    overpass_url,
                    data={"data": query},
                    timeout=REQUEST_TIMEOUT,
                    headers={
                        "User-Agent": (
                            "Ford-Triplog-Charging-Database-Generator/1.4"
                        )
                    },
                )

                response.raise_for_status()
                data = response.json()

                elements = data.get("elements")

                if not isinstance(elements, list):
                    raise ValueError(
                        "The Overpass response contains no valid element list."
                    )

                if not elements:
                    raise ValueError(
                        f"Overpass returned no charging stations for "
                        f"country code {country_code}."
                    )

                print(f"Downloaded elements: {len(elements)}")

                if output_file is not None:
                    save_json(data, output_file)

                return data

            except (
                requests.RequestException,
                json.JSONDecodeError,
                ValueError,
            ) as err:
                last_error = err
                print(f"Request failed: {err}")

        if attempt < MAX_RETRIES:
            delay = attempt * 10
            print(f"Waiting {delay} seconds before retry...")
            time.sleep(delay)

    raise RuntimeError(
        "Overpass download failed after all attempts."
    ) from last_error


def save_json(data: dict[str, Any], output_file: Path) -> None:
    """Save JSON data in readable UTF-8 format."""

    output_file.parent.mkdir(parents=True, exist_ok=True)

    with output_file.open("w", encoding="utf-8") as file_handle:
        json.dump(
            data,
            file_handle,
            ensure_ascii=False,
            indent=2,
        )

    print(f"Raw data saved: {output_file}")


if __name__ == "__main__":
    from countries import COUNTRIES

    country_code = "CH"
    country = COUNTRIES[country_code]

    output_path = Path(__file__).parent / "overpass_ch_raw.json"

    result = download_overpass_data(
        country_code=country["iso_code"],
        output_file=output_path,
    )

    print(
        f"{country['name']}: "
        f"{len(result.get('elements', []))} charging station elements"
    )
