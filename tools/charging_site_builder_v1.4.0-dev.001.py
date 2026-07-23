"""
Ford Triplog

Charging-site builder for the Swiss charging database.

File: charging_site_builder_v1.4.0-dev.001.py
Version: 1.4.0-dev.001
Date: 2026-07-23

Purpose:
- Load the geohash-indexed charging_database_ch.json.
- Flatten all charging-station records.
- Conservatively group nearby OSM objects into logical charging sites.
- Keep unrelated operators at the same parking area separate.
- Preserve incomplete and unknown OSM objects as separate sites.
- Write charging_sites_ch.json for inspection and later lookup integration.

Phase 2 rule:
- The internal clustering radius is fixed and is not a user option.
- GPS detection tolerance will be implemented separately as a Home Assistant option.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any, Iterable


FILE_VERSION = "1.4.0-dev.001"
DEFAULT_INPUT_FILE = "charging_database_ch.json"
DEFAULT_OUTPUT_FILE = "charging_sites_ch.json"
DEFAULT_CLUSTER_RADIUS_M = 25.0
EARTH_RADIUS_M = 6_371_000.0


def load_database(database_file: Path) -> dict[str, Any]:
    """Load and minimally validate the geohash-indexed database."""

    with database_file.open("r", encoding="utf-8") as file_handle:
        database = json.load(file_handle)

    if not isinstance(database, dict):
        raise ValueError("Database root must be a JSON object.")

    data = database.get("data")
    if not isinstance(data, dict):
        raise ValueError("Database must contain a 'data' object.")

    return database


def flatten_stations(database: dict[str, Any]) -> list[dict[str, Any]]:
    """Return all station records from all geohash buckets."""

    stations: list[dict[str, Any]] = []

    for bucket in database["data"].values():
        if not isinstance(bucket, list):
            continue

        for station in bucket:
            if isinstance(station, dict):
                stations.append(station)

    return stations


def station_coordinates(station: dict[str, Any]) -> tuple[float, float] | None:
    """Read station coordinates from common normalized field layouts."""

    coordinate_pairs = (
        ("lat", "lon"),
        ("latitude", "longitude"),
    )

    for latitude_key, longitude_key in coordinate_pairs:
        latitude = station.get(latitude_key)
        longitude = station.get(longitude_key)

        if isinstance(latitude, (int, float)) and isinstance(
            longitude, (int, float)
        ):
            return float(latitude), float(longitude)

    location = station.get("location")
    if isinstance(location, dict):
        latitude = location.get("lat", location.get("latitude"))
        longitude = location.get("lon", location.get("longitude"))

        if isinstance(latitude, (int, float)) and isinstance(
            longitude, (int, float)
        ):
            return float(latitude), float(longitude)

    return None


def haversine_distance_m(
    latitude_1: float,
    longitude_1: float,
    latitude_2: float,
    longitude_2: float,
) -> float:
    """Calculate the great-circle distance between two coordinates."""

    lat_1 = math.radians(latitude_1)
    lon_1 = math.radians(longitude_1)
    lat_2 = math.radians(latitude_2)
    lon_2 = math.radians(longitude_2)

    delta_lat = lat_2 - lat_1
    delta_lon = lon_2 - lon_1

    haversine = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat_1) * math.cos(lat_2) * math.sin(delta_lon / 2) ** 2
    )

    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(haversine))


def normalize_identity(value: Any) -> str | None:
    """Normalize a brand/operator/network/name value for comparisons."""

    if not isinstance(value, str):
        return None

    value = unicodedata.normalize("NFKD", value)
    value = "".join(character for character in value if not unicodedata.combining(character))
    value = value.casefold().strip()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    value = re.sub(r"\s+", " ", value).strip()

    return value or None


def identity_values(station: dict[str, Any]) -> dict[str, str]:
    """Return normalized identity fields used by the merge decision."""

    values: dict[str, str] = {}

    for field in ("brand", "operator", "network", "name"):
        normalized = normalize_identity(station.get(field))
        if normalized:
            values[field] = normalized

    return values


def has_identity_conflict(
    identity_1: dict[str, str],
    identity_2: dict[str, str],
) -> bool:
    """Return True when both records provide incompatible strong identities."""

    strong_fields = ("brand", "operator", "network")

    values_1 = {identity_1[field] for field in strong_fields if field in identity_1}
    values_2 = {identity_2[field] for field in strong_fields if field in identity_2}

    if not values_1 or not values_2:
        return False

    return values_1.isdisjoint(values_2)


def identities_are_compatible(
    station_1: dict[str, Any],
    station_2: dict[str, Any],
) -> bool:
    """Conservatively decide whether two nearby records may form one site.

    Merge conditions:
    - At least one strong identity matches: brand, operator, or network.
    - Or both names match exactly and no strong identity conflicts.

    Unknown records are not merged merely because they are nearby.
    """

    identity_1 = identity_values(station_1)
    identity_2 = identity_values(station_2)

    strong_fields = ("brand", "operator", "network")

    for field in strong_fields:
        if (
            field in identity_1
            and field in identity_2
            and identity_1[field] == identity_2[field]
        ):
            return True

    if has_identity_conflict(identity_1, identity_2):
        return False

    name_1 = identity_1.get("name")
    name_2 = identity_2.get("name")

    return bool(name_1 and name_2 and name_1 == name_2)


class UnionFind:
    """Small union-find implementation for deterministic clustering."""

    def __init__(self, size: int) -> None:
        self.parent = list(range(size))
        self.rank = [0] * size

    def find(self, item: int) -> int:
        while self.parent[item] != item:
            self.parent[item] = self.parent[self.parent[item]]
            item = self.parent[item]
        return item

    def union(self, item_1: int, item_2: int) -> None:
        root_1 = self.find(item_1)
        root_2 = self.find(item_2)

        if root_1 == root_2:
            return

        if self.rank[root_1] < self.rank[root_2]:
            root_1, root_2 = root_2, root_1

        self.parent[root_2] = root_1

        if self.rank[root_1] == self.rank[root_2]:
            self.rank[root_1] += 1


def cluster_stations(
    stations: list[dict[str, Any]],
    cluster_radius_m: float,
) -> list[list[dict[str, Any]]]:
    """Group compatible nearby station records."""

    coordinates = [station_coordinates(station) for station in stations]
    union_find = UnionFind(len(stations))

    # A simple latitude grid keeps the comparison count manageable.
    latitude_cell_size = cluster_radius_m / 111_320.0
    longitude_cell_size = cluster_radius_m / 75_000.0

    cells: dict[tuple[int, int], list[int]] = {}

    for index, coordinate in enumerate(coordinates):
        if coordinate is None:
            continue

        latitude, longitude = coordinate
        cell = (
            math.floor(latitude / latitude_cell_size),
            math.floor(longitude / longitude_cell_size),
        )
        cells.setdefault(cell, []).append(index)

    for index, coordinate in enumerate(coordinates):
        if coordinate is None:
            continue

        latitude, longitude = coordinate
        cell_lat = math.floor(latitude / latitude_cell_size)
        cell_lon = math.floor(longitude / longitude_cell_size)

        for offset_lat in (-1, 0, 1):
            for offset_lon in (-1, 0, 1):
                neighbour_cell = (cell_lat + offset_lat, cell_lon + offset_lon)

                for other_index in cells.get(neighbour_cell, []):
                    if other_index <= index:
                        continue

                    other_coordinate = coordinates[other_index]
                    if other_coordinate is None:
                        continue

                    distance_m = haversine_distance_m(
                        latitude,
                        longitude,
                        other_coordinate[0],
                        other_coordinate[1],
                    )

                    if distance_m > cluster_radius_m:
                        continue

                    if identities_are_compatible(
                        stations[index],
                        stations[other_index],
                    ):
                        union_find.union(index, other_index)

    grouped: dict[int, list[dict[str, Any]]] = {}

    for index, station in enumerate(stations):
        grouped.setdefault(union_find.find(index), []).append(station)

    return list(grouped.values())


def first_nonempty(
    records: Iterable[dict[str, Any]],
    field: str,
) -> Any:
    """Return the first nonempty value for a field."""

    for record in records:
        value = record.get(field)
        if value not in (None, "", [], {}):
            return value

    return None


def unique_values(
    records: Iterable[dict[str, Any]],
    field: str,
) -> list[Any]:
    """Collect unique JSON-compatible values while preserving order."""

    values: list[Any] = []
    seen: set[str] = set()

    for record in records:
        value = record.get(field)

        if value in (None, "", [], {}):
            continue

        marker = json.dumps(value, ensure_ascii=False, sort_keys=True)

        if marker not in seen:
            seen.add(marker)
            values.append(value)

    return values


def site_quality(site: dict[str, Any]) -> str:
    """Classify the amount of useful data available for a site."""

    has_identity = any(
        site.get(field) for field in ("brand", "operator", "network", "name")
    )
    has_technical = any(
        site.get(field)
        for field in ("power_kw", "capacity", "connectors")
    )

    if has_identity and has_technical:
        return "detailed"

    if has_identity:
        return "location_only"

    if has_technical:
        return "technical_only"

    return "unknown"


def build_site(
    site_number: int,
    members: list[dict[str, Any]],
) -> dict[str, Any]:
    """Aggregate clustered records into one logical charging site."""

    coordinates = [
        coordinate
        for member in members
        if (coordinate := station_coordinates(member)) is not None
    ]

    if coordinates:
        latitude = sum(item[0] for item in coordinates) / len(coordinates)
        longitude = sum(item[1] for item in coordinates) / len(coordinates)
    else:
        latitude = None
        longitude = None

    brands = unique_values(members, "brand")
    operators = unique_values(members, "operator")
    networks = unique_values(members, "network")
    names = unique_values(members, "name")
    powers = unique_values(members, "power_kw")
    capacities = unique_values(members, "capacity")
    connectors = unique_values(members, "connectors")

    site = {
        "site_id": f"ch-site-{site_number:05d}",
        "latitude": round(latitude, 7) if latitude is not None else None,
        "longitude": round(longitude, 7) if longitude is not None else None,
        "brand": brands[0] if brands else None,
        "operator": operators[0] if operators else None,
        "network": networks[0] if networks else None,
        "name": names[0] if names else None,
        "brands": brands,
        "operators": operators,
        "networks": networks,
        "names": names,
        "power_kw": powers,
        "capacity": capacities,
        "connectors": connectors,
        "member_count": len(members),
        "osm_ids": [
            value
            for member in members
            if (value := member.get("id")) not in (None, "")
        ],
        "members": members,
    }

    site["quality"] = site_quality(site)

    return site


def build_sites(
    stations: list[dict[str, Any]],
    cluster_radius_m: float,
) -> list[dict[str, Any]]:
    """Build deterministic logical charging sites."""

    clusters = cluster_stations(stations, cluster_radius_m)

    clusters.sort(
        key=lambda members: (
            station_coordinates(members[0]) or (999.0, 999.0),
            str(members[0].get("id", "")),
        )
    )

    return [
        build_site(site_number, members)
        for site_number, members in enumerate(clusters, start=1)
    ]


def write_output(
    output_file: Path,
    source_database: Path,
    cluster_radius_m: float,
    stations: list[dict[str, Any]],
    sites: list[dict[str, Any]],
) -> None:
    """Write the site database and metadata."""

    quality_counts = Counter(site["quality"] for site in sites)
    grouped_site_count = sum(1 for site in sites if site["member_count"] > 1)

    payload = {
        "metadata": {
            "format": "ford_triplog_charging_sites",
            "version": FILE_VERSION,
            "source_database": source_database.name,
            "cluster_radius_m": cluster_radius_m,
            "station_records": len(stations),
            "charging_sites": len(sites),
            "grouped_sites": grouped_site_count,
            "quality": dict(sorted(quality_counts.items())),
        },
        "data": sites,
    }

    with output_file.open("w", encoding="utf-8") as file_handle:
        json.dump(payload, file_handle, ensure_ascii=False, indent=2)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build logical charging sites from charging_database_ch.json."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=Path(DEFAULT_INPUT_FILE),
        help=f"Input database, default: {DEFAULT_INPUT_FILE}",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(DEFAULT_OUTPUT_FILE),
        help=f"Output site database, default: {DEFAULT_OUTPUT_FILE}",
    )
    parser.add_argument(
        "--cluster-radius",
        type=float,
        default=DEFAULT_CLUSTER_RADIUS_M,
        help=(
            "Internal diagnostic clustering radius in metres. "
            f"Default: {DEFAULT_CLUSTER_RADIUS_M:g}"
        ),
    )
    return parser.parse_args()


def main() -> int:
    arguments = parse_arguments()

    if arguments.cluster_radius <= 0:
        raise ValueError("Cluster radius must be greater than zero.")

    database = load_database(arguments.input)
    stations = flatten_stations(database)
    sites = build_sites(stations, arguments.cluster_radius)

    write_output(
        output_file=arguments.output,
        source_database=arguments.input,
        cluster_radius_m=arguments.cluster_radius,
        stations=stations,
        sites=sites,
    )

    grouped_sites = [site for site in sites if site["member_count"] > 1]
    quality_counts = Counter(site["quality"] for site in sites)

    print("Ford Triplog Charging Site Builder")
    print(f"File version:          {FILE_VERSION}")
    print()
    print(f"Input stations:        {len(stations)}")
    print(f"Charging sites:        {len(sites)}")
    print(f"Grouped sites:         {len(grouped_sites)}")
    print(f"Cluster radius:        {arguments.cluster_radius:.1f} m")
    print()
    print("Quality")
    print("-------")

    for quality, count in sorted(quality_counts.items()):
        print(f"{quality:20} {count}")

    print()
    print(f"Output:                {arguments.output}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
