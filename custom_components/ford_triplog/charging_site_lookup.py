"""Charging-site database lookup for Ford Triplog.

The lookup loads the generated ``charging_sites_ch.json`` file once, builds an
in-memory geohash index, and resolves vehicle coordinates to a logical charging
site within a configurable GPS tolerance.

This module has no Home Assistant imports. It can therefore be tested
independently and loaded by the Ford Triplog coordinator through
``hass.async_add_executor_job``.
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Final

DEFAULT_TOLERANCE_M: Final = 10.0
DEFAULT_GEOHASH_PRECISION: Final = 6
EARTH_RADIUS_M: Final = 6_371_000.0
GEOHASH_ALPHABET: Final = "0123456789bcdefghjkmnpqrstuvwxyz"


class ChargingSiteDatabaseError(ValueError):
    """Raised when the charging-site database cannot be used."""


def haversine_distance_m(
    latitude_1: float,
    longitude_1: float,
    latitude_2: float,
    longitude_2: float,
) -> float:
    """Return the great-circle distance between two coordinates in metres."""

    lat_1 = math.radians(latitude_1)
    lon_1 = math.radians(longitude_1)
    lat_2 = math.radians(latitude_2)
    lon_2 = math.radians(longitude_2)

    delta_lat = lat_2 - lat_1
    delta_lon = lon_2 - lon_1

    value = (
        math.sin(delta_lat / 2.0) ** 2
        + math.cos(lat_1)
        * math.cos(lat_2)
        * math.sin(delta_lon / 2.0) ** 2
    )
    value = min(1.0, max(0.0, value))

    return 2.0 * EARTH_RADIUS_M * math.asin(math.sqrt(value))


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
    """Encode coordinates as a geohash without an external dependency."""

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
    """Return south, west, north and east bounds for a geohash."""

    if not geohash:
        raise ValueError("Geohash must not be empty.")

    latitude_interval = [-90.0, 90.0]
    longitude_interval = [-180.0, 180.0]
    use_longitude = True

    for character in geohash:
        try:
            value = GEOHASH_ALPHABET.index(character)
        except ValueError as error:
            raise ValueError(
                f"Invalid geohash character: {character}"
            ) from error

        for mask in (16, 8, 4, 2, 1):
            interval = (
                longitude_interval if use_longitude else latitude_interval
            )
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
    """Return the current geohash and its eight neighbouring cells."""

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


def _site_coordinates(
    site: dict[str, Any],
) -> tuple[float, float] | None:
    """Read valid coordinates from a charging-site record."""

    latitude = site.get("latitude")
    longitude = site.get("longitude")

    if (
        not isinstance(latitude, (int, float))
        or isinstance(latitude, bool)
        or not isinstance(longitude, (int, float))
        or isinstance(longitude, bool)
    ):
        return None

    latitude = float(latitude)
    longitude = float(longitude)

    try:
        validate_coordinate(latitude, longitude)
    except ValueError:
        return None

    return latitude, longitude


def _compact_site(site: dict[str, Any]) -> dict[str, Any]:
    """Return the stable fields required by Ford Triplog."""

    return {
        "site_id": site.get("site_id"),
        "latitude": site.get("latitude"),
        "longitude": site.get("longitude"),
        "name": site.get("name"),
        "brand": site.get("brand"),
        "operator": site.get("operator"),
        "network": site.get("network"),
        "power_kw": site.get("power_kw", []),
        "capacity": site.get("capacity", []),
        "connectors": site.get("connectors", []),
        "quality": site.get("quality"),
        "member_count": site.get("member_count", 1),
        "osm_ids": site.get("osm_ids", []),
    }


class ChargingSiteLookup:
    """Indexed lookup for logical charging sites."""

    def __init__(
        self,
        database_file: str | Path,
        geohash_precision: int = DEFAULT_GEOHASH_PRECISION,
    ) -> None:
        """Load the database and build its in-memory index."""

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
        """Read and validate the JSON database."""

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
        except OSError as error:
            raise ChargingSiteDatabaseError(
                f"Charging-site database could not be read: {error}"
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

            coordinates = _site_coordinates(site)

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
        """Return the number of records in the database."""

        return len(self.sites)

    @property
    def searchable_site_count(self) -> int:
        """Return the number of records with valid coordinates."""

        return len(self._coordinate_sites)

    @property
    def index_cell_count(self) -> int:
        """Return the number of occupied geohash cells."""

        return len(self._geohash_index)

    def _nearest_from_candidates(
        self,
        latitude: float,
        longitude: float,
        candidates: Iterable[tuple[float, float, dict[str, Any]]],
    ) -> tuple[float, dict[str, Any]] | None:
        """Return the nearest candidate and its distance."""

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
        """Return candidates from the local nine-cell geohash area."""

        candidates: list[tuple[float, float, dict[str, Any]]] = []

        for cell in surrounding_geohashes(
            latitude,
            longitude,
            self.geohash_precision,
        ):
            candidates.extend(self._geohash_index.get(cell, []))

        return candidates

    def find(
        self,
        latitude: float,
        longitude: float,
        tolerance_m: float = DEFAULT_TOLERANCE_M,
    ) -> dict[str, Any] | None:
        """Return the nearest charging site inside the GPS tolerance.

        ``None`` is returned when no charging site is close enough.
        """

        latitude = float(latitude)
        longitude = float(longitude)
        tolerance_m = float(tolerance_m)

        validate_coordinate(latitude, longitude)

        if not math.isfinite(tolerance_m) or tolerance_m <= 0.0:
            raise ValueError(
                "Tolerance must be a finite number greater than zero."
            )

        nearest = self._nearest_from_candidates(
            latitude,
            longitude,
            self._indexed_candidates(latitude, longitude),
        )

        if nearest is None:
            return None

        distance_m, site = nearest

        if distance_m > tolerance_m:
            return None

        result = _compact_site(site)
        result["distance_m"] = round(distance_m, 1)
        return result
