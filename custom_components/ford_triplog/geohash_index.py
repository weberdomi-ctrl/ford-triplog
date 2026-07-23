"""
Ford Triplog

Build a geohash index from normalized charging-station data.

File: geohash_index_v1.4.0-dev.001.py
Version: 1.4.0-dev.001
Date: 2026-07-23

Purpose:
- Read normalized charging-station data.
- Assign each station to a geohash bucket.
- Write a deterministic, compact index for fast offline lookup.
- Include metadata for later Home Assistant integration.
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


FILE_VERSION = "1.4.0-dev.001"
DATABASE_FORMAT_VERSION = "1"
COUNTRY_CODE = "CH"
COUNTRY_NAME = "Switzerland"
GEOHASH_PRECISION = 6

GEOHASH_ALPHABET = "0123456789bcdefghjkmnpqrstuvwxyz"


def load_stations(input_file: Path) -> list[dict[str, Any]]:
    """Load normalized charging-station data."""

    with input_file.open("r", encoding="utf-8") as file_handle:
        data = json.load(file_handle)

    if not isinstance(data, list):
        raise ValueError("The normalized JSON must contain a list.")

    stations = [item for item in data if isinstance(item, dict)]

    if len(stations) != len(data):
        print(
            "Warning: "
            f"{len(data) - len(stations)} invalid entries were ignored."
        )

    return stations


def encode_geohash(
    latitude: float,
    longitude: float,
    precision: int = GEOHASH_PRECISION,
) -> str:
    """Encode latitude and longitude as a standard base32 geohash."""

    if not -90.0 <= latitude <= 90.0:
        raise ValueError(f"Invalid latitude: {latitude}")

    if not -180.0 <= longitude <= 180.0:
        raise ValueError(f"Invalid longitude: {longitude}")

    if precision < 1:
        raise ValueError("Geohash precision must be at least 1.")

    latitude_interval = [-90.0, 90.0]
    longitude_interval = [-180.0, 180.0]

    geohash: list[str] = []
    bit_value = 0
    bit_count = 0
    use_longitude = True

    while len(geohash) < precision:
        if use_longitude:
            midpoint = sum(longitude_interval) / 2

            if longitude >= midpoint:
                bit_value = (bit_value << 1) | 1
                longitude_interval[0] = midpoint
            else:
                bit_value <<= 1
                longitude_interval[1] = midpoint
        else:
            midpoint = sum(latitude_interval) / 2

            if latitude >= midpoint:
                bit_value = (bit_value << 1) | 1
                latitude_interval[0] = midpoint
            else:
                bit_value <<= 1
                latitude_interval[1] = midpoint

        use_longitude = not use_longitude
        bit_count += 1

        if bit_count == 5:
            geohash.append(GEOHASH_ALPHABET[bit_value])
            bit_value = 0
            bit_count = 0

    return "".join(geohash)


def valid_coordinates(station: dict[str, Any]) -> tuple[float, float] | None:
    """Return valid numeric coordinates or None."""

    latitude = station.get("lat")
    longitude = station.get("lon")

    if (
        not isinstance(latitude, (int, float))
        or isinstance(latitude, bool)
        or not isinstance(longitude, (int, float))
        or isinstance(longitude, bool)
    ):
        return None

    latitude_float = float(latitude)
    longitude_float = float(longitude)

    if not -90.0 <= latitude_float <= 90.0:
        return None

    if not -180.0 <= longitude_float <= 180.0:
        return None

    return latitude_float, longitude_float


def build_index(
    stations: list[dict[str, Any]],
    precision: int,
) -> tuple[dict[str, list[dict[str, Any]]], int]:
    """Group stations by geohash."""

    buckets: dict[str, list[dict[str, Any]]] = {}
    skipped = 0

    for station in stations:
        coordinates = valid_coordinates(station)

        if coordinates is None:
            skipped += 1
            continue

        latitude, longitude = coordinates
        geohash = encode_geohash(latitude, longitude, precision)

        buckets.setdefault(geohash, []).append(station)

    for bucket_stations in buckets.values():
        bucket_stations.sort(
            key=lambda station: (
                str(station.get("brand", "")).casefold(),
                str(station.get("name", "")).casefold(),
                str(station.get("id", "")),
            )
        )

    sorted_buckets = {
        geohash: buckets[geohash]
        for geohash in sorted(buckets)
    }

    return sorted_buckets, skipped


def calculate_bucket_statistics(
    buckets: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    """Calculate useful index statistics."""

    sizes = [len(stations) for stations in buckets.values()]

    if not sizes:
        return {
            "bucket_count": 0,
            "smallest_bucket": 0,
            "largest_bucket": 0,
            "average_bucket_size": 0.0,
        }

    size_counter = Counter(sizes)

    return {
        "bucket_count": len(sizes),
        "smallest_bucket": min(sizes),
        "largest_bucket": max(sizes),
        "average_bucket_size": round(sum(sizes) / len(sizes), 2),
        "bucket_size_distribution": {
            str(size): count
            for size, count in sorted(size_counter.items())
        },
    }


def build_database(
    buckets: dict[str, list[dict[str, Any]]],
    station_count: int,
) -> dict[str, Any]:
    """Build the final geohash database object."""

    statistics = calculate_bucket_statistics(buckets)

    return {
        "metadata": {
            "database_format_version": DATABASE_FORMAT_VERSION,
            "generator": "Ford Triplog",
            "generator_file_version": FILE_VERSION,
            "generated_utc": datetime.now(timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z"),
            "country_code": COUNTRY_CODE,
            "country_name": COUNTRY_NAME,
            "station_count": station_count,
            "geohash_precision": GEOHASH_PRECISION,
            **statistics,
        },
        "data": buckets,
    }


def save_database(
    database: dict[str, Any],
    output_file: Path,
) -> None:
    """Write the geohash database as UTF-8 JSON."""

    with output_file.open("w", encoding="utf-8") as file_handle:
        json.dump(
            database,
            file_handle,
            ensure_ascii=False,
            separators=(",", ":"),
        )


def print_largest_buckets(
    buckets: dict[str, list[dict[str, Any]]],
    limit: int = 10,
) -> None:
    """Print the largest geohash buckets."""

    largest = sorted(
        (
            (geohash, len(stations))
            for geohash, stations in buckets.items()
        ),
        key=lambda item: (-item[1], item[0]),
    )

    print(f"Largest geohash buckets (top {limit})")
    print("--------------------------------")

    for geohash, count in largest[:limit]:
        print(f"{geohash}: {count}")

    print()


def main() -> None:
    """Build the charging-station geohash index."""

    tools_directory = Path(__file__).parent
    input_path = tools_directory / "charging_stations_ch_normalized.json"
    output_path = tools_directory / "charging_database_ch.json"

    stations = load_stations(input_path)
    buckets, skipped = build_index(stations, GEOHASH_PRECISION)
    indexed_station_count = sum(
        len(bucket_stations)
        for bucket_stations in buckets.values()
    )

    database = build_database(
        buckets=buckets,
        station_count=indexed_station_count,
    )
    save_database(database, output_path)

    statistics = database["metadata"]

    print("Ford Triplog Charging Database Geohash Indexer")
    print(f"File version: {FILE_VERSION}")
    print()
    print(f"Input stations:       {len(stations)}")
    print(f"Indexed stations:     {indexed_station_count}")
    print(f"Skipped stations:     {skipped}")
    print(f"Geohash precision:    {GEOHASH_PRECISION}")
    print(f"Geohash buckets:      {statistics['bucket_count']}")
    print(f"Smallest bucket:      {statistics['smallest_bucket']}")
    print(f"Largest bucket:       {statistics['largest_bucket']}")
    print(f"Average bucket size:  {statistics['average_bucket_size']}")
    print()
    print_largest_buckets(buckets)
    print(f"Database saved: {output_path}")


if __name__ == "__main__":
    main()
