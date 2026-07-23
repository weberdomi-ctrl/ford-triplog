"""
Ford Triplog

Indexed charging-site lookup for the generated Swiss charging site database.

File: charging_site_lookup_v1.4.0-dev.002.py
Version: 1.4.0-dev.002
Date: 2026-07-23

Purpose:
- Load charging_sites_ch.json.
- Build an in-memory geohash index once during initialization.
- Search the current geohash cell and its eight neighbouring cells first.
- Apply a configurable GPS detection tolerance.
- Fall back to a complete scan only when needed for a diagnostic nearest-site
  result.
- Keep the public Python API compatible with version 1.4.0-dev.001.

Design:
- Geohash precision 6 is used by default.
- A precision-6 cell is substantially larger than the planned Ford Triplog
  GPS tolerances of 5 to 100 metres.
- The normal successful lookup therefore examines only a small number of
  candidates instead of all charging sites.
"""

from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable


FILE_VERSION = "1.4.0-dev.002"
DEFAULT_INPUT_FILE = "charging_sites_ch.json"
DEFAULT_TOLERANCE_M = 10.0
DEFAULT_GEOHASH_PRECISION = 6
EARTH_RADIUS_M = 6_371_000.0
GEOHASH_ALPHABET = "0123456789bcdefghjkmnpqrstuvwxyz"


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


def validate_coordinate(latitude: float, longitude: float) -> None:
    """Validate one latitude/longitude pair."""

    if not math.isfinite(latitude) or not math.isfinite(longitude):
        raise ValueError("Coordinates must be finite numbers.")

    if not -90.0 <= latitude <= 90.0:
        raise ValueError("Latitude must be between -90 and 90.")

    if not -180.0 <= longitude <= 180.0:
        raise ValueError("Longitude must be between -180 and 180.")


def geohash_encode(
    latitude: float,
    longitude: float,
    precision: int = DEFAULT_GEOHASH_PRECISION,
) -> str:
    """Encode one coordinate pair as a geohash without external packages."""

    validate_coordinate(latitude, longitude)

    if precision < 1:
        raise ValueError("Geohash precision must be at least 1.")

    latitude_interval = [-90.0, 90.0]
    longitude_interval = [-180.0, 180.0]

    result: list[str] = []
    current_value = 0
    bits_in_character = 0
    use_longitude = True

    while len(result) < precision:
        interval = longitude_interval if use_longitude else latitude_interval
        coordinate = longitude if use_longitude else latitude
        midpoint = (interval[0] + interval[1]) / 2.0

        current_value <<= 1

        if coordinate >= midpoint:
            current_value |= 1
            interval[0] = midpoint
        else:
            interval[1] = midpoint

        use_longitude = not use_longitude
        bits_in_character += 1

        if bits_in_character == 5:
            result.append(GEOHASH_ALPHABET[current_value])
            current_value = 0
            bits_in_character = 0

    return "".join(result)


def geohash_decode_bbox(geohash: str) -> tuple[float, float, float, float]:
    """Return south, west, north and east bounds for one geohash."""

    if not geohash:
        raise ValueError("Geohash must not be empty.")

    latitude_interval = [-90.0, 90.0]
    longitude_interval = [-180.0, 180.0]
    use_longitude = True

    for character in geohash:
        try:
            value = GEOHASH_ALPHABET.index(character)
        except ValueError as error:
            raise ValueError(f"Invalid geohash character: {character}") from error

        for mask in (16, 8, 4, 2, 1):
            interval = longitude_interval if use_longitude else latitude_interval
            midpoint = (interval[0] + interval[1]) / 2.0

            if value & mask:
                interval[0] = midpoint
            else:
                interval[1] = midpoint

            use_longitude = not use_longitude

    return (
        latitude_interval[0],
        longitude_interval[0],
        latitude_interval[1],
        longitude_interval[1],
    )


def surrounding_geohashes(
    latitude: float,
    longitude: float,
    precision: int,
) -> set[str]:
    """Return the current geohash cell and its eight neighbouring cells.

    Neighbour cells are obtained by encoding points one cell width or height
    away from the centre of the current cell. This avoids an external geohash
    dependency and correctly handles normal Swiss coordinates.
    """

    current = geohash_encode(latitude, longitude, precision)
    south, west, north, east = geohash_decode_bbox(current)

    cell_height = north - south
    cell_width = east - west
    centre_latitude = (south + north) / 2.0
    centre_longitude = (west + east) / 2.0

    cells: set[str] = set()

    for latitude_offset in (-cell_height, 0.0, cell_height):
        neighbour_latitude = max(
            -90.0,
            min(90.0, centre_latitude + latitude_offset),
        )

        for longitude_offset in (-cell_width, 0.0, cell_width):
            neighbour_longitude = centre_longitude + longitude_offset

            if neighbour_longitude > 180.0:
                neighbour_longitude -= 360.0
            elif neighbour_longitude < -180.0:
                neighbour_longitude += 360.0

            cells.add(
                geohash_encode(
                    neighbour_latitude,
                    neighbour_longitude,
                    precision,
                )
            )

    return cells


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
    """Load a charging-site database and perform indexed lookups."""

    def __init__(
        self,
        database_file: str | Path,
        geohash_precision: int = DEFAULT_GEOHASH_PRECISION,
    ) -> None:
        self.database_file = Path(database_file)
        self.geohash_precision = int(geohash_precision)
        self.metadata: dict[str, Any] = {}
        self.sites: list[dict[str, Any]] = []
        self._coordinate_sites: list[
            tuple[float, float, dict[str, Any]]
        ] = []
        self._geohash_index: dict[
            str,
            list[tuple[float, float, dict[str, Any]]]
        ] = {}

        if self.geohash_precision < 1:
            raise ValueError("Geohash precision must be at least 1.")

        self._load()

    def _load(self) -> None:
        """Load the database and build the geohash index."""

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
        geohash_index: defaultdict[
            str,
            list[tuple[float, float, dict[str, Any]]]
        ] = defaultdict(list)

        for site in data:
            if not isinstance(site, dict):
                continue

            coordinates = site_coordinates(site)

            if coordinates is None:
                continue

            indexed_site = (
                coordinates[0],
                coordinates[1],
                site,
            )
            coordinate_sites.append(indexed_site)

            geohash = geohash_encode(
                coordinates[0],
                coordinates[1],
                self.geohash_precision,
            )
            geohash_index[geohash].append(indexed_site)

        if not coordinate_sites:
            raise ChargingSiteDatabaseError(
                "Database contains no charging sites with valid coordinates."
            )

        self.metadata = metadata
        self.sites = data
        self._coordinate_sites = coordinate_sites
        self._geohash_index = dict(geohash_index)

    @property
    def site_count(self) -> int:
        return len(self.sites)

    @property
    def searchable_site_count(self) -> int:
        return len(self._coordinate_sites)

    @property
    def index_cell_count(self) -> int:
        return len(self._geohash_index)

    def _nearest_from_candidates(
        self,
        latitude: float,
        longitude: float,
        candidates: Iterable[tuple[float, float, dict[str, Any]]],
    ) -> tuple[float, dict[str, Any]] | None:
        """Return distance and site for the nearest candidate."""

        nearest_site: dict[str, Any] | None = None
        nearest_distance_m = math.inf

        for site_latitude, site_longitude, site in candidates:
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
            return None

        return nearest_distance_m, nearest_site

    def _indexed_candidates(
        self,
        latitude: float,
        longitude: float,
    ) -> list[tuple[float, float, dict[str, Any]]]:
        """Return candidates from the current and neighbouring geohashes."""

        cells = surrounding_geohashes(
            latitude,
            longitude,
            self.geohash_precision,
        )

        candidates: list[tuple[float, float, dict[str, Any]]] = []

        for cell in cells:
            candidates.extend(self._geohash_index.get(cell, []))

        return candidates

    def find_nearest(
        self,
        latitude: float,
        longitude: float,
    ) -> dict[str, Any]:
        """Return the globally nearest charging site.

        A complete scan is intentionally retained because this method has no
        distance limit and must remain exact.
        """

        latitude = float(latitude)
        longitude = float(longitude)
        validate_coordinate(latitude, longitude)

        nearest = self._nearest_from_candidates(
            latitude,
            longitude,
            self._coordinate_sites,
        )

        if nearest is None:
            raise ChargingSiteDatabaseError(
                "No searchable charging site is available."
            )

        distance_m, site = nearest

        return {
            "distance_m": round(distance_m, 1),
            "site": compact_site(site),
            "search_mode": "full_scan",
            "candidate_count": self.searchable_site_count,
        }

    def find(
        self,
        latitude: float,
        longitude: float,
        tolerance_m: float = DEFAULT_TOLERANCE_M,
    ) -> dict[str, Any]:
        """Find a charging site within the GPS detection tolerance.

        Normal successful lookups use only the geohash candidates. If no
        indexed candidate is inside the tolerance, a complete scan is used
        solely to provide the diagnostic ``nearest_site`` result.
        """

        latitude = float(latitude)
        longitude = float(longitude)
        validate_coordinate(latitude, longitude)

        tolerance_m = float(tolerance_m)

        if not math.isfinite(tolerance_m) or tolerance_m <= 0.0:
            raise ValueError(
                "Tolerance must be a finite number greater than zero."
            )

        candidates = self._indexed_candidates(latitude, longitude)
        indexed_nearest = self._nearest_from_candidates(
            latitude,
            longitude,
            candidates,
        )

        if indexed_nearest is not None:
            indexed_distance_m, indexed_site = indexed_nearest

            if indexed_distance_m <= tolerance_m:
                return {
                    "found": True,
                    "distance_m": round(indexed_distance_m, 1),
                    "tolerance_m": tolerance_m,
                    "site": compact_site(indexed_site),
                    "nearest_site": compact_site(indexed_site),
                    "search_mode": "geohash",
                    "candidate_count": len(candidates),
                }

        nearest = self.find_nearest(latitude, longitude)

        return {
            "found": nearest["distance_m"] <= tolerance_m,
            "distance_m": nearest["distance_m"],
            "tolerance_m": tolerance_m,
            "site": (
                nearest["site"]
                if nearest["distance_m"] <= tolerance_m
                else None
            ),
            "nearest_site": nearest["site"],
            "search_mode": "geohash_then_full_scan",
            "candidate_count": len(candidates),
        }


def print_result(result: dict[str, Any]) -> None:
    """Print one lookup result in a readable diagnostic format."""

    print("Lookup result")
    print("-------------")
    print(f"Found:                 {result['found']}")
    print(f"Distance:              {result['distance_m']:.1f} m")
    print(f"GPS tolerance:         {result['tolerance_m']:g} m")
    print(f"Search mode:           {result['search_mode']}")
    print(f"Indexed candidates:    {result['candidate_count']}")

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
    print(
        "Coordinates:           "
        f"{site.get('latitude')}, {site.get('longitude')}"
    )
    print(f"Members:               {site.get('member_count', 1)}")
    print(
        "Power:                 "
        f"{json.dumps(site.get('power_kw', []), ensure_ascii=False)}"
    )
    print(
        "Capacity:              "
        f"{json.dumps(site.get('capacity', []), ensure_ascii=False)}"
    )
    print(
        "Connectors:            "
        f"{json.dumps(site.get('connectors', []), ensure_ascii=False)}"
    )


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Find a logical charging site in charging_sites_ch.json."
        )
    )
    parser.add_argument("latitude", type=float, help="GPS latitude")
    parser.add_argument("longitude", type=float, help="GPS longitude")
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
        "--geohash-precision",
        type=int,
        default=DEFAULT_GEOHASH_PRECISION,
        help=(
            "Geohash precision used for the in-memory index, "
            f"default: {DEFAULT_GEOHASH_PRECISION}"
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

    lookup = ChargingSiteLookup(
        arguments.input,
        geohash_precision=arguments.geohash_precision,
    )
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
    print(f"Geohash precision:     {lookup.geohash_precision}")
    print(f"Geohash index cells:   {lookup.index_cell_count}")
    print()

    if arguments.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print_result(result)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
