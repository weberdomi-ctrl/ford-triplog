"""
Ford Triplog

Charging-site lookup for the generated Swiss charging site database.

File: charging_site_lookup_v1.4.0-dev.001.py
Version: 1.4.0-dev.001
Date: 2026-07-23

Purpose:
- Load charging_sites_ch.json.
- Find the nearest logical charging site for GPS coordinates.
- Apply a configurable GPS detection tolerance.
- Return a compact result that is independent from individual OSM nodes.
- Provide both a reusable Python class and a command-line test interface.

This file is the first lookup step for Phase 2.
It intentionally uses a simple full scan. With roughly 3,400 charging sites,
this remains fast enough for testing and keeps the implementation transparent.
A spatial index can be added later without changing the public API.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any


FILE_VERSION = "1.4.0-dev.001"
DEFAULT_INPUT_FILE = "charging_sites_ch.json"
DEFAULT_TOLERANCE_M = 10.0
EARTH_RADIUS_M = 6_371_000.0


class ChargingSiteDatabaseError(ValueError):
    """Raised when the charging-site database is invalid."""


def haversine_distance_m(
    latitude_1: float,
    longitude_1: float,
    latitude_2: float,
    longitude_2: float,
) -> float:
    """Calculate the great-circle distance between two GPS coordinates."""

    lat_1 = math.radians(latitude_1)
    lon_1 = math.radians(longitude_1)
    lat_2 = math.radians(latitude_2)
    lon_2 = math.radians(longitude_2)

    delta_lat = lat_2 - lat_1
    delta_lon = lon_2 - lon_1

    haversine = (
        math.sin(delta_lat / 2.0) ** 2
        + math.cos(lat_1)
        * math.cos(lat_2)
        * math.sin(delta_lon / 2.0) ** 2
    )

    haversine = min(1.0, max(0.0, haversine))

    return 2.0 * EARTH_RADIUS_M * math.asin(math.sqrt(haversine))


def validate_coordinate(
    latitude: float,
    longitude: float,
) -> None:
    """Validate one latitude/longitude pair."""

    if not math.isfinite(latitude) or not math.isfinite(longitude):
        raise ValueError("Coordinates must be finite numbers.")

    if not -90.0 <= latitude <= 90.0:
        raise ValueError("Latitude must be between -90 and 90.")

    if not -180.0 <= longitude <= 180.0:
        raise ValueError("Longitude must be between -180 and 180.")


def site_coordinates(site: dict[str, Any]) -> tuple[float, float] | None:
    """Read and validate coordinates from one charging-site record."""

    latitude = site.get("latitude")
    longitude = site.get("longitude")

    if not isinstance(latitude, (int, float)) or isinstance(latitude, bool):
        return None

    if not isinstance(longitude, (int, float)) or isinstance(longitude, bool):
        return None

    latitude = float(latitude)
    longitude = float(longitude)

    try:
        validate_coordinate(latitude, longitude)
    except ValueError:
        return None

    return latitude, longitude


def compact_site(site: dict[str, Any]) -> dict[str, Any]:
    """Return the stable site fields needed by Ford Triplog at runtime."""

    return {
        "site_id": site.get("site_id"),
        "latitude": site.get("latitude"),
        "longitude": site.get("longitude"),
        "brand": site.get("brand"),
        "operator": site.get("operator"),
        "network": site.get("network"),
        "name": site.get("name"),
        "power_kw": site.get("power_kw", []),
        "capacity": site.get("capacity", []),
        "connectors": site.get("connectors", []),
        "quality": site.get("quality"),
        "member_count": site.get("member_count", 1),
        "osm_ids": site.get("osm_ids", []),
    }


class ChargingSiteLookup:
    """Load a charging-site database and perform nearest-site lookups."""

    def __init__(self, database_file: str | Path) -> None:
        self.database_file = Path(database_file)
        self.metadata: dict[str, Any] = {}
        self.sites: list[dict[str, Any]] = []
        self._coordinate_sites: list[
            tuple[float, float, dict[str, Any]]
        ] = []

        self._load()

    def _load(self) -> None:
        """Load and minimally validate charging_sites_ch.json."""

        try:
            with self.database_file.open(
                "r",
                encoding="utf-8",
            ) as file_handle:
                database = json.load(file_handle)
        except FileNotFoundError as error:
            raise ChargingSiteDatabaseError(
                f"Charging-site database not found: {self.database_file}"
            ) from error
        except json.JSONDecodeError as error:
            raise ChargingSiteDatabaseError(
                f"Invalid JSON in {self.database_file}: {error}"
            ) from error

        if not isinstance(database, dict):
            raise ChargingSiteDatabaseError(
                "Database root must be a JSON object."
            )

        metadata = database.get("metadata", {})
        data = database.get("data")

        if not isinstance(metadata, dict):
            raise ChargingSiteDatabaseError(
                "Database 'metadata' must be a JSON object."
            )

        if not isinstance(data, list):
            raise ChargingSiteDatabaseError(
                "Database must contain a 'data' list."
            )

        coordinate_sites: list[
            tuple[float, float, dict[str, Any]]
        ] = []

        for site in data:
            if not isinstance(site, dict):
                continue

            coordinates = site_coordinates(site)

            if coordinates is None:
                continue

            coordinate_sites.append(
                (
                    coordinates[0],
                    coordinates[1],
                    site,
                )
            )

        if not coordinate_sites:
            raise ChargingSiteDatabaseError(
                "Database contains no charging sites with valid coordinates."
            )

        self.metadata = metadata
        self.sites = data
        self._coordinate_sites = coordinate_sites

    @property
    def site_count(self) -> int:
        """Return the total number of site records in the database."""

        return len(self.sites)

    @property
    def searchable_site_count(self) -> int:
        """Return the number of sites with usable coordinates."""

        return len(self._coordinate_sites)

    def find_nearest(
        self,
        latitude: float,
        longitude: float,
    ) -> dict[str, Any]:
        """Return the nearest charging site without applying a tolerance."""

        latitude = float(latitude)
        longitude = float(longitude)
        validate_coordinate(latitude, longitude)

        nearest_site: dict[str, Any] | None = None
        nearest_distance_m = math.inf

        for site_latitude, site_longitude, site in self._coordinate_sites:
            distance_m = haversine_distance_m(
                latitude,
                longitude,
                site_latitude,
                site_longitude,
            )

            if distance_m < nearest_distance_m:
                nearest_distance_m = distance_m
                nearest_site = site

        if nearest_site is None:
            raise ChargingSiteDatabaseError(
                "No searchable charging site is available."
            )

        return {
            "distance_m": round(nearest_distance_m, 1),
            "site": compact_site(nearest_site),
        }

    def find(
        self,
        latitude: float,
        longitude: float,
        tolerance_m: float = DEFAULT_TOLERANCE_M,
    ) -> dict[str, Any]:
        """Find the nearest site and apply the GPS detection tolerance.

        The nearest site is always included for diagnostics. The ``found``
        field indicates whether its distance is within ``tolerance_m``.
        """

        tolerance_m = float(tolerance_m)

        if not math.isfinite(tolerance_m) or tolerance_m <= 0.0:
            raise ValueError(
                "Tolerance must be a finite number greater than zero."
            )

        nearest = self.find_nearest(latitude, longitude)
        distance_m = float(nearest["distance_m"])
        found = distance_m <= tolerance_m

        return {
            "found": found,
            "distance_m": distance_m,
            "tolerance_m": tolerance_m,
            "site": nearest["site"] if found else None,
            "nearest_site": nearest["site"],
        }


def print_result(result: dict[str, Any]) -> None:
    """Print one lookup result in a readable diagnostic format."""

    print("Lookup result")
    print("-------------")
    print(f"Found:                 {result['found']}")
    print(f"Distance:              {result['distance_m']:.1f} m")
    print(f"GPS tolerance:         {result['tolerance_m']:g} m")

    site = result["site"]
    nearest_site = result["nearest_site"]

    if site is None:
        print()
        print("No charging site is within the GPS tolerance.")
        print()
        print("Nearest site")
        print("------------")
        site = nearest_site
    else:
        print()
        print("Charging site")
        print("-------------")

    print(f"Site ID:               {site.get('site_id') or '-'}")
    print(f"Name:                  {site.get('name') or '-'}")
    print(f"Brand:                 {site.get('brand') or '-'}")
    print(f"Operator:              {site.get('operator') or '-'}")
    print(f"Network:               {site.get('network') or '-'}")
    print(f"Quality:               {site.get('quality') or '-'}")
    print(f"Coordinates:           "
          f"{site.get('latitude')}, {site.get('longitude')}")
    print(f"Members:               {site.get('member_count', 1)}")
    print(f"Power:                 "
          f"{json.dumps(site.get('power_kw', []), ensure_ascii=False)}")
    print(f"Capacity:              "
          f"{json.dumps(site.get('capacity', []), ensure_ascii=False)}")
    print(f"Connectors:            "
          f"{json.dumps(site.get('connectors', []), ensure_ascii=False)}")


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Find a logical charging site in charging_sites_ch.json."
        )
    )
    parser.add_argument(
        "latitude",
        type=float,
        help="GPS latitude",
    )
    parser.add_argument(
        "longitude",
        type=float,
        help="GPS longitude",
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=Path(DEFAULT_INPUT_FILE),
        help=f"Input database, default: {DEFAULT_INPUT_FILE}",
    )
    parser.add_argument(
        "--tolerance",
        type=float,
        default=DEFAULT_TOLERANCE_M,
        help=(
            "GPS detection tolerance in metres, "
            f"default: {DEFAULT_TOLERANCE_M:g}"
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the complete result as JSON",
    )

    return parser.parse_args()


def main() -> int:
    arguments = parse_arguments()

    lookup = ChargingSiteLookup(arguments.input)
    result = lookup.find(
        latitude=arguments.latitude,
        longitude=arguments.longitude,
        tolerance_m=arguments.tolerance,
    )

    print("Ford Triplog Charging Site Lookup")
    print(f"File version:          {FILE_VERSION}")
    print()
    print(f"Input file:            {arguments.input}")
    print(f"Charging sites:        {lookup.site_count}")
    print(f"Searchable sites:      {lookup.searchable_site_count}")
    print()

    if arguments.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print_result(result)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
