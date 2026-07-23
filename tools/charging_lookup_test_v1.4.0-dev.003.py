"""
Ford Triplog

Offline lookup test for the geohash-indexed charging database.

File: charging_lookup_test_v1.4.0-dev.003.py
Version: 1.4.0-dev.003
Date: 2026-07-23

Purpose:
- Load charging_database_ch.json.
- Calculate the geohash for supplied coordinates.
- Search the current and eight neighbouring geohash buckets.
- Calculate exact distances using the Haversine formula.
- Return the nearest charging station with a confidence rating.
- Print the nearest candidates for transparent lookup testing.
- Optional radius mode scans the complete database for diagnostics.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any


FILE_VERSION = "1.4.0-dev.003"
DEFAULT_DATABASE_FILE = "charging_database_ch.json"
DEFAULT_MAX_DISTANCE_M = 500.0
GEOHASH_ALPHABET = "0123456789bcdefghjkmnpqrstuvwxyz"
EARTH_RADIUS_M = 6_371_000.0


def load_database(database_file: Path) -> dict[str, Any]:
    """Load and validate the charging database."""

    with database_file.open("r", encoding="utf-8") as file_handle:
        database = json.load(file_handle)

    if not isinstance(database, dict):
        raise ValueError("The charging database must contain a JSON object.")

    metadata = database.get("metadata")
    data = database.get("data")

    if not isinstance(metadata, dict):
        raise ValueError("Database metadata is missing or invalid.")

    if not isinstance(data, dict):
        raise ValueError("Database geohash data is missing or invalid.")

    precision = metadata.get("geohash_precision")

    if not isinstance(precision, int) or precision < 1:
        raise ValueError("Database geohash precision is missing or invalid.")

    return database


def encode_geohash(
    latitude: float,
    longitude: float,
    precision: int,
) -> str:
    """Encode latitude and longitude as a standard base32 geohash."""

    if not -90.0 <= latitude <= 90.0:
        raise ValueError(f"Invalid latitude: {latitude}")

    if not -180.0 <= longitude <= 180.0:
        raise ValueError(f"Invalid longitude: {longitude}")

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


def decode_geohash_bbox(geohash: str) -> tuple[float, float, float, float]:
    """Decode a geohash into its latitude/longitude bounding box."""

    latitude_interval = [-90.0, 90.0]
    longitude_interval = [-180.0, 180.0]
    use_longitude = True

    for character in geohash:
        try:
            value = GEOHASH_ALPHABET.index(character)
        except ValueError as error:
            raise ValueError(f"Invalid geohash character: {character}") from error

        for mask in (16, 8, 4, 2, 1):
            bit_is_set = bool(value & mask)

            if use_longitude:
                midpoint = sum(longitude_interval) / 2

                if bit_is_set:
                    longitude_interval[0] = midpoint
                else:
                    longitude_interval[1] = midpoint
            else:
                midpoint = sum(latitude_interval) / 2

                if bit_is_set:
                    latitude_interval[0] = midpoint
                else:
                    latitude_interval[1] = midpoint

            use_longitude = not use_longitude

    return (
        latitude_interval[0],
        latitude_interval[1],
        longitude_interval[0],
        longitude_interval[1],
    )


def neighbouring_geohashes(geohash: str) -> list[str]:
    """Return the current geohash and its eight direct neighbours."""

    (
        latitude_min,
        latitude_max,
        longitude_min,
        longitude_max,
    ) = decode_geohash_bbox(geohash)

    latitude_step = latitude_max - latitude_min
    longitude_step = longitude_max - longitude_min

    latitude_center = (latitude_min + latitude_max) / 2
    longitude_center = (longitude_min + longitude_max) / 2

    neighbours: set[str] = set()

    for latitude_offset in (-1, 0, 1):
        for longitude_offset in (-1, 0, 1):
            latitude = latitude_center + latitude_offset * latitude_step
            longitude = longitude_center + longitude_offset * longitude_step

            latitude = min(max(latitude, -90.0), 90.0)
            longitude = ((longitude + 180.0) % 360.0) - 180.0

            neighbours.add(
                encode_geohash(
                    latitude=latitude,
                    longitude=longitude,
                    precision=len(geohash),
                )
            )

    return sorted(neighbours)


def haversine_distance_m(
    latitude_1: float,
    longitude_1: float,
    latitude_2: float,
    longitude_2: float,
) -> float:
    """Calculate the great-circle distance between two coordinates."""

    latitude_1_rad = math.radians(latitude_1)
    latitude_2_rad = math.radians(latitude_2)
    latitude_delta = math.radians(latitude_2 - latitude_1)
    longitude_delta = math.radians(longitude_2 - longitude_1)

    haversine_value = (
        math.sin(latitude_delta / 2) ** 2
        + math.cos(latitude_1_rad)
        * math.cos(latitude_2_rad)
        * math.sin(longitude_delta / 2) ** 2
    )

    central_angle = 2 * math.atan2(
        math.sqrt(haversine_value),
        math.sqrt(1 - haversine_value),
    )

    return EARTH_RADIUS_M * central_angle


def confidence_for_distance(distance_m: float) -> str:
    """Return the confidence level for a station match."""

    if distance_m <= 100:
        return "high"

    if distance_m <= 300:
        return "medium"

    if distance_m <= 500:
        return "low"

    return "none"


def station_coordinates(
    station: dict[str, Any],
) -> tuple[float, float] | None:
    """Return valid station coordinates."""

    latitude = station.get("lat")
    longitude = station.get("lon")

    if (
        not isinstance(latitude, (int, float))
        or isinstance(latitude, bool)
        or not isinstance(longitude, (int, float))
        or isinstance(longitude, bool)
    ):
        return None

    return float(latitude), float(longitude)


def find_nearest_station(
    database: dict[str, Any],
    latitude: float,
    longitude: float,
    max_distance_m: float = DEFAULT_MAX_DISTANCE_M,
    search_radius_m: float | None = None,
) -> dict[str, Any]:
    """Find the nearest charging station around the supplied coordinates.

    Without search_radius_m, only the current and eight neighbouring
    geohash buckets are searched. With search_radius_m, the complete
    database is scanned and candidates inside the radius are returned.
    """

    metadata = database["metadata"]
    data = database["data"]
    precision = metadata["geohash_precision"]

    current_geohash = encode_geohash(
        latitude=latitude,
        longitude=longitude,
        precision=precision,
    )

    if search_radius_m is None:
        searched_geohashes = neighbouring_geohashes(current_geohash)
        station_sources = [
            station
            for geohash in searched_geohashes
            for station in data.get(geohash, [])
            if isinstance(station, dict)
        ]
        search_mode = "geohash"
    else:
        if search_radius_m <= 0:
            raise ValueError("Search radius must be greater than zero.")

        searched_geohashes = sorted(data)
        station_sources = [
            station
            for bucket in data.values()
            if isinstance(bucket, list)
            for station in bucket
            if isinstance(station, dict)
        ]
        search_mode = "radius"

    candidates: list[dict[str, Any]] = []

    for station in station_sources:
        coordinates = station_coordinates(station)

        if coordinates is None:
            continue

        station_latitude, station_longitude = coordinates
        distance_m = haversine_distance_m(
            latitude,
            longitude,
            station_latitude,
            station_longitude,
        )

        if search_radius_m is not None and distance_m > search_radius_m:
            continue

        candidates.append(
            {
                "distance_m": round(distance_m, 1),
                "station": station,
            }
        )

    candidates.sort(
        key=lambda item: (
            item["distance_m"],
            str(item["station"].get("brand", "")).casefold(),
            str(item["station"].get("name", "")).casefold(),
            str(item["station"].get("id", "")),
        )
    )

    common = {
        "query": {
            "lat": latitude,
            "lon": longitude,
            "geohash": current_geohash,
        },
        "search_mode": search_mode,
        "search_radius_m": search_radius_m,
        "searched_geohashes": searched_geohashes,
        "candidate_count": len(candidates),
        "candidates": candidates,
    }

    nearest = candidates[0] if candidates else None

    if nearest is None:
        return {
            "found": False,
            "reason": "no_candidates",
            **common,
        }

    distance_m = nearest["distance_m"]
    confidence = confidence_for_distance(distance_m)

    if distance_m > max_distance_m:
        return {
            "found": False,
            "reason": "outside_max_distance",
            "nearest_distance_m": distance_m,
            "nearest_station": nearest["station"],
            **common,
        }

    return {
        "found": True,
        "distance_m": distance_m,
        "confidence": confidence,
        "station": nearest["station"],
        **common,
    }


def format_value(value: Any) -> str:
    """Format optional station values for console output."""

    if value in (None, "", [], {}):
        return "-"

    return str(value)


def print_candidates(
    candidates: list[dict[str, Any]],
    limit: int = 10,
) -> None:
    """Print the nearest charging-station candidates."""

    print()
    print(f"Nearest candidates (top {limit})")
    print("---------------------------")

    for rank, candidate in enumerate(candidates[:limit], start=1):
        station = candidate["station"]

        print(f"{rank}. {candidate['distance_m']:.1f} m")
        print(f"   Brand:       {format_value(station.get('brand'))}")
        print(f"   Name:        {format_value(station.get('name'))}")
        print(f"   Operator:    {format_value(station.get('operator'))}")
        print(f"   Network:     {format_value(station.get('network'))}")
        print(f"   Power:       {format_value(station.get('power_kw'))} kW")
        print(f"   Capacity:    {format_value(station.get('capacity'))}")
        print(f"   Connectors:  {format_value(station.get('connectors'))}")
        print(f"   OSM ID:      {format_value(station.get('id'))}")
        print()


def print_result(result: dict[str, Any]) -> None:
    """Print a readable lookup result."""

    query = result["query"]

    print("Ford Triplog Charging Database Lookup")
    print(f"File version: {FILE_VERSION}")
    print()
    print(f"Query latitude:       {query['lat']}")
    print(f"Query longitude:      {query['lon']}")
    print(f"Query geohash:        {query['geohash']}")
    print(f"Search mode:          {result.get('search_mode', 'geohash')}")

    if result.get("search_radius_m") is not None:
        print(f"Search radius:        {result['search_radius_m']:.1f} m")
        print(f"Database buckets:     {len(result['searched_geohashes'])}")
    else:
        print(f"Searched buckets:     {len(result['searched_geohashes'])}")

    print(f"Candidate stations:   {result['candidate_count']}")
    print()

    if not result["found"]:
        print("Result: No charging station match")

        if result["reason"] == "no_candidates":
            print("Reason: No stations found in the searched geohash buckets.")
        elif result["reason"] == "outside_max_distance":
            print(
                "Reason: Nearest station is outside the configured "
                "maximum distance."
            )
            print(
                f"Nearest distance:     "
                f"{result['nearest_distance_m']:.1f} m"
            )

            station = result["nearest_station"]
            print(
                f"Nearest brand:        "
                f"{station.get('brand') or '-'}"
            )
            print(
                f"Nearest name:         "
                f"{station.get('name') or '-'}"
            )

        print_candidates(result.get("candidates", []))
        return

    station = result["station"]

    print("Result: Charging station found")
    print(f"Distance:             {result['distance_m']:.1f} m")
    print(f"Confidence:           {result['confidence']}")
    print(f"Brand:                {station.get('brand') or '-'}")
    print(f"Name:                 {station.get('name') or '-'}")
    print(f"Operator:             {station.get('operator') or '-'}")
    print(f"Network:              {station.get('network') or '-'}")
    print(f"Power:                {station.get('power_kw') or '-'} kW")
    print(f"Capacity:             {station.get('capacity') or '-'}")
    print(f"Connectors:           {station.get('connectors') or '-'}")
    print(f"OSM ID:               {station.get('id') or '-'}")

    print_candidates(result.get("candidates", []))


def parse_arguments() -> argparse.Namespace:
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(
        description=(
            "Find the nearest charging station in the Ford Triplog "
            "offline charging database."
        )
    )
    parser.add_argument("latitude", type=float)
    parser.add_argument("longitude", type=float)
    parser.add_argument(
        "--database",
        type=Path,
        default=Path(__file__).parent / DEFAULT_DATABASE_FILE,
        help="Path to charging_database_ch.json",
    )
    parser.add_argument(
        "--max-distance",
        type=float,
        default=DEFAULT_MAX_DISTANCE_M,
        help="Maximum accepted distance in metres",
    )
    parser.add_argument(
        "--radius",
        type=float,
        default=None,
        help=(
            "Diagnostic search radius in metres. When supplied, the complete "
            "database is scanned instead of only nine geohash buckets."
        ),
    )

    return parser.parse_args()


def main() -> None:
    """Run a charging-station lookup."""

    arguments = parse_arguments()
    database = load_database(arguments.database)

    result = find_nearest_station(
        database=database,
        latitude=arguments.latitude,
        longitude=arguments.longitude,
        max_distance_m=arguments.max_distance,
        search_radius_m=arguments.radius,
    )

    print_result(result)


if __name__ == "__main__":
    main()
