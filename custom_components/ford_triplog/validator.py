"""
Ford Triplog

Validate normalized OpenStreetMap charging-station data.

File: validator_v1.4.0-dev.002.py
Version: 1.4.0-dev.002
Date: 2026-07-23

Changes since 1.4.0-dev.001:
- Version included in the filename and output.
- Added canonical brand statistics.
- Added detection of inconsistent brand capitalization.
- Prepared country bounds as configurable constants.
"""

from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable


FILE_VERSION = "1.4.0-dev.002"

COUNTRY_CODE = "CH"
COUNTRY_NAME = "Switzerland"

# Broad Swiss bounds, including border areas.
LATITUDE_MIN = 45.75
LATITUDE_MAX = 47.85
LONGITUDE_MIN = 5.75
LONGITUDE_MAX = 10.70

NEARBY_DISTANCE_METERS = 20.0
MAX_NEARBY_EXAMPLES = 20
TOP_RESULT_LIMIT = 20


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
            f"{len(data) - len(stations)} non-object entries were ignored."
        )

    return stations


def has_value(station: dict[str, Any], key: str) -> bool:
    """Return True when a field contains a meaningful value."""

    value = station.get(key)

    if value is None:
        return False

    if isinstance(value, str):
        return bool(value.strip())

    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)

    return True


def print_field_coverage(
    stations: list[dict[str, Any]],
    fields: Iterable[tuple[str, str]],
) -> None:
    """Print coverage statistics for selected fields."""

    total = len(stations)

    print("Field coverage")
    print("--------------")

    for key, label in fields:
        count = sum(has_value(station, key) for station in stations)
        percentage = (count / total * 100) if total else 0.0
        print(f"{label + ':':29} {count:6} ({percentage:5.1f}%)")

    print()


def print_counter(
    title: str,
    counter: Counter[str],
    limit: int = TOP_RESULT_LIMIT,
) -> None:
    """Print the most common values from a counter."""

    print(title)
    print("-" * len(title))

    if not counter:
        print("No values available.")
        print()
        return

    for value, count in counter.most_common(limit):
        print(f"{value:36} {count:6}")

    print()


def collect_string_values(
    stations: list[dict[str, Any]],
    key: str,
) -> Counter[str]:
    """Count non-empty string values for a field."""

    counter: Counter[str] = Counter()

    for station in stations:
        value = station.get(key)

        if isinstance(value, str):
            value = value.strip()

            if value:
                counter[value] += 1

    return counter


def collect_connector_values(
    stations: list[dict[str, Any]],
) -> Counter[str]:
    """Count normalized connector values."""

    counter: Counter[str] = Counter()

    for station in stations:
        connectors = station.get("connectors")

        if not isinstance(connectors, list):
            continue

        for connector in connectors:
            if isinstance(connector, str) and connector.strip():
                counter[connector.strip()] += 1

    return counter


def coordinates_are_valid(station: dict[str, Any]) -> bool:
    """Return True when latitude and longitude are numeric."""

    latitude = station.get("lat")
    longitude = station.get("lon")

    return (
        isinstance(latitude, (int, float))
        and not isinstance(latitude, bool)
        and isinstance(longitude, (int, float))
        and not isinstance(longitude, bool)
    )


def coordinates_inside_country_bounds(station: dict[str, Any]) -> bool:
    """Return True when coordinates are inside configured bounds."""

    if not coordinates_are_valid(station):
        return False

    latitude = float(station["lat"])
    longitude = float(station["lon"])

    return (
        LATITUDE_MIN <= latitude <= LATITUDE_MAX
        and LONGITUDE_MIN <= longitude <= LONGITUDE_MAX
    )


def haversine_distance_meters(
    latitude_1: float,
    longitude_1: float,
    latitude_2: float,
    longitude_2: float,
) -> float:
    """Calculate the great-circle distance between two coordinates."""

    earth_radius_meters = 6_371_000.0

    lat_1 = math.radians(latitude_1)
    lat_2 = math.radians(latitude_2)
    delta_lat = math.radians(latitude_2 - latitude_1)
    delta_lon = math.radians(longitude_2 - longitude_1)

    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat_1)
        * math.cos(lat_2)
        * math.sin(delta_lon / 2) ** 2
    )

    return earth_radius_meters * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def find_nearby_pairs(
    stations: list[dict[str, Any]],
    maximum_distance_meters: float,
) -> list[tuple[str, str, float]]:
    """
    Find nearby station pairs using a small geographic grid.

    This avoids comparing every station with every other station.
    """

    valid_stations = [
        station
        for station in stations
        if coordinates_are_valid(station)
        and isinstance(station.get("id"), str)
    ]

    cell_size_degrees = maximum_distance_meters / 111_320.0
    grid: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
    nearby_pairs: list[tuple[str, str, float]] = []

    for station in valid_stations:
        latitude = float(station["lat"])
        longitude = float(station["lon"])

        cell_x = math.floor(longitude / cell_size_degrees)
        cell_y = math.floor(latitude / cell_size_degrees)

        for offset_x in (-1, 0, 1):
            for offset_y in (-1, 0, 1):
                nearby_cell = (cell_x + offset_x, cell_y + offset_y)

                for other in grid.get(nearby_cell, []):
                    distance = haversine_distance_meters(
                        latitude,
                        longitude,
                        float(other["lat"]),
                        float(other["lon"]),
                    )

                    if distance <= maximum_distance_meters:
                        nearby_pairs.append(
                            (
                                str(other["id"]),
                                str(station["id"]),
                                distance,
                            )
                        )

        grid[(cell_x, cell_y)].append(station)

    nearby_pairs.sort(key=lambda item: item[2])

    return nearby_pairs


def find_duplicate_osm_ids(
    stations: list[dict[str, Any]],
) -> list[str]:
    """Return duplicate normalized station IDs."""

    ids = [
        station["id"]
        for station in stations
        if isinstance(station.get("id"), str)
    ]

    counts = Counter(ids)

    return sorted(
        station_id
        for station_id, count in counts.items()
        if count > 1
    )


def find_brand_spelling_variants(
    stations: list[dict[str, Any]],
) -> list[tuple[str, list[tuple[str, int]]]]:
    """
    Find brands whose values differ only by capitalization or spacing.
    """

    groups: dict[str, Counter[str]] = defaultdict(Counter)

    for station in stations:
        brand = station.get("brand")

        if not isinstance(brand, str):
            continue

        cleaned = " ".join(brand.strip().split())

        if not cleaned:
            continue

        groups[cleaned.casefold()][cleaned] += 1

    variants: list[tuple[str, list[tuple[str, int]]]] = []

    for normalized_key, spellings in groups.items():
        if len(spellings) > 1:
            variants.append(
                (
                    normalized_key,
                    spellings.most_common(),
                )
            )

    variants.sort(
        key=lambda item: sum(count for _, count in item[1]),
        reverse=True,
    )

    return variants


def print_brand_spelling_variants(
    variants: list[tuple[str, list[tuple[str, int]]]],
) -> None:
    """Print inconsistent brand spellings."""

    print("Brand spelling variants")
    print("-----------------------")

    if not variants:
        print("No case-only or spacing-only brand variants found.")
        print()
        return

    for _, spellings in variants[:TOP_RESULT_LIMIT]:
        formatted = ", ".join(
            f"{spelling} ({count})"
            for spelling, count in spellings
        )
        print(formatted)

    print()


def validate(stations: list[dict[str, Any]]) -> None:
    """Run and print all validation checks."""

    print("Ford Triplog Charging Database Validator")
    print(f"File version: {FILE_VERSION}")
    print(f"Country: {COUNTRY_NAME} ({COUNTRY_CODE})")
    print()
    print(f"Stations total: {len(stations):16}")
    print()

    print_field_coverage(
        stations,
        (
            ("name", "Name available"),
            ("operator", "Operator available"),
            ("network", "Network available"),
            ("brand", "Brand available"),
            ("power_kw", "Power available"),
            ("capacity", "Capacity available"),
            ("connectors", "Connectors available"),
            ("access", "Access available"),
            ("fee", "Fee available"),
            ("opening_hours", "Opening hours available"),
        ),
    )

    print_counter(
        "Connector statistics",
        collect_connector_values(stations),
    )
    print_counter(
        "Top operators",
        collect_string_values(stations, "operator"),
    )
    print_counter(
        "Top networks",
        collect_string_values(stations, "network"),
    )
    print_counter(
        "Top brands",
        collect_string_values(stations, "brand"),
    )

    print_brand_spelling_variants(
        find_brand_spelling_variants(stations)
    )

    missing_coordinates = sum(
        not coordinates_are_valid(station)
        for station in stations
    )
    outside_bounds = sum(
        coordinates_are_valid(station)
        and not coordinates_inside_country_bounds(station)
        for station in stations
    )
    duplicate_ids = find_duplicate_osm_ids(stations)
    nearby_pairs = find_nearby_pairs(
        stations,
        NEARBY_DISTANCE_METERS,
    )

    print("Validation checks")
    print("-----------------")
    print(f"Missing coordinates:            {missing_coordinates}")
    print(f"Outside {COUNTRY_CODE} bounds:          {outside_bounds}")
    print(f"Duplicate OSM IDs:              {len(duplicate_ids)}")
    print(
        "Nearby station pairs "
        f"(<= {NEARBY_DISTANCE_METERS:.0f} m): "
        f"{len(nearby_pairs)}"
    )
    print()

    if duplicate_ids:
        print("Duplicate OSM IDs")
        print("-----------------")

        for station_id in duplicate_ids[:MAX_NEARBY_EXAMPLES]:
            print(station_id)

        print()

    print("Example nearby station pairs")
    print("----------------------------")

    if not nearby_pairs:
        print("No nearby station pairs found.")
        return

    for station_id_1, station_id_2, distance in nearby_pairs[
        :MAX_NEARBY_EXAMPLES
    ]:
        print(
            f"{station_id_1} <-> {station_id_2}: "
            f"{distance:.1f} m"
        )


if __name__ == "__main__":
    tools_directory = Path(__file__).parent
    input_path = tools_directory / "charging_stations_ch_normalized.json"

    normalized_stations = load_stations(input_path)
    validate(normalized_stations)
