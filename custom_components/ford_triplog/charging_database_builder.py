"""
Ford Triplog

Build a charging-site database directly from OpenStreetMap.

File: charging_database_builder.py
Version: 1.4.2
Date: 2026-07-23

Purpose:
- Validate a requested country against countries.py.
- Download charging stations through overpass.py.
- Normalize the raw OpenStreetMap data through normalizer.py.
- Run reusable validation checks from validator.py.
- Build the geohash index through geohash_index.py.
- Save the final Ford Triplog charging-site database as JSON.

This module is synchronous by design. Home Assistant must execute
build_charging_database() in an executor job.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
from time import perf_counter
from pathlib import Path
from typing import Any

from .charging_site_builder import (
    DEFAULT_CLUSTER_RADIUS_M,
    FILE_VERSION as CHARGING_SITE_BUILDER_VERSION,
    build_sites,
)
from .countries import COUNTRIES
from .geohash_index import (
    DATABASE_FORMAT_VERSION,
    FILE_VERSION as GEOHASH_INDEX_VERSION,
    GEOHASH_PRECISION,
    build_index,
    calculate_bucket_statistics,
    save_database,
)
from .normalizer import FILE_VERSION as NORMALIZER_VERSION
from .normalizer import normalize_data
from .overpass import download_overpass_data
from .validator import (
    FILE_VERSION as VALIDATOR_VERSION,
    coordinates_are_valid,
    find_duplicate_osm_ids,
)


FILE_VERSION = "1.4.2"

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ChargingDatabaseBuildResult:
    """Result returned after a successful database build."""

    country_code: str
    country_name: str
    output_file: Path
    downloaded_elements: int
    normalized_stations: int
    indexed_stations: int
    skipped_elements: int
    skipped_index_entries: int
    duplicate_osm_ids: int
    geohash_precision: int
    geohash_buckets: int


class ChargingDatabaseBuildError(RuntimeError):
    """Raised when a charging-site database cannot be built."""


def normalize_country_code(country_code: str) -> str:
    """Return and validate an uppercase ISO country code."""

    normalized = str(country_code).strip().upper()

    if normalized not in COUNTRIES:
        supported = ", ".join(sorted(COUNTRIES))
        raise ChargingDatabaseBuildError(
            f"Unsupported country code '{country_code}'. "
            f"Supported countries: {supported}."
        )

    return normalized


def _validate_normalized_stations(
    stations: list[dict[str, Any]],
) -> int:
    """
    Validate normalized stations using reusable validator functions.

    Country bounds are deliberately not checked here because the current
    validator.py contains Swiss bounds as module constants. Generic country
    bounds can be added later without duplicating validation logic here.
    """

    if not stations:
        raise ChargingDatabaseBuildError(
            "The normalized charging-station list is empty."
        )

    invalid_coordinates = sum(
        not coordinates_are_valid(station)
        for station in stations
    )

    if invalid_coordinates:
        raise ChargingDatabaseBuildError(
            f"{invalid_coordinates} normalized charging stations "
            "contain invalid coordinates."
        )

    duplicate_ids = find_duplicate_osm_ids(stations)

    if duplicate_ids:
        raise ChargingDatabaseBuildError(
            f"The normalized data contains {len(duplicate_ids)} "
            "duplicate OpenStreetMap IDs."
        )

    return len(duplicate_ids)


def _build_database_object(
    *,
    country_code: str,
    country_name: str,
    buckets: dict[str, list[dict[str, Any]]],
    station_count: int,
    sites: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build the final lookup-compatible charging-site database."""

    from collections import Counter
    from datetime import datetime, timezone

    statistics = calculate_bucket_statistics(buckets)
    quality_counts = Counter(
        str(site.get("quality", "unknown"))
        for site in sites
    )
    grouped_site_count = sum(
        int(site.get("member_count", 1)) > 1
        for site in sites
    )

    return {
        "metadata": {
            "format": "ford_triplog_charging_sites",
            "database_format_version": DATABASE_FORMAT_VERSION,
            "generator": "Ford Triplog",
            "generator_file_version": FILE_VERSION,
            "generated_utc": datetime.now(timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z"),
            "country_code": country_code,
            "country_name": country_name,
            "station_records": station_count,
            "charging_sites": len(sites),
            "grouped_sites": grouped_site_count,
            "cluster_radius_m": DEFAULT_CLUSTER_RADIUS_M,
            "geohash_precision": GEOHASH_PRECISION,
            "quality": dict(sorted(quality_counts.items())),
            "pipeline_versions": {
                "builder": FILE_VERSION,
                "normalizer": NORMALIZER_VERSION,
                "validator": VALIDATOR_VERSION,
                "geohash_index": GEOHASH_INDEX_VERSION,
                "charging_site_builder": CHARGING_SITE_BUILDER_VERSION,
            },
            **statistics,
        },
        "data": sites,
    }


def build_charging_database(
    country_code: str,
    output_file: Path,
) -> ChargingDatabaseBuildResult:
    """
    Download, normalize, validate, index, and save one country database.

    The output file is replaced only after the complete pipeline succeeds.
    """

    normalized_country_code = normalize_country_code(country_code)
    country = COUNTRIES[normalized_country_code]
    country_name = str(country["name"])
    iso_code = str(country["iso_code"])

    total_started = perf_counter()

    _LOGGER.info(
        "Charging database build started for %s (%s)",
        country_name,
        normalized_country_code,
    )

    try:
        stage_started = perf_counter()
        _LOGGER.info(
            "Step 1/6: Downloading OpenStreetMap charging data for %s",
            normalized_country_code,
        )
        raw_data = download_overpass_data(country_code=iso_code)

        elements = raw_data.get("elements")
        if not isinstance(elements, list):
            raise ChargingDatabaseBuildError(
                "The Overpass response contains no valid element list."
            )

        _LOGGER.info(
            "Step 1/6 completed: %s OpenStreetMap elements downloaded in %.1f s",
            len(elements),
            perf_counter() - stage_started,
        )

        stage_started = perf_counter()
        _LOGGER.info("Step 2/6: Normalizing OpenStreetMap data")
        stations, _source_counter, skipped_elements = normalize_data(raw_data)
        _LOGGER.info(
            "Step 2/6 completed: %s charging-station records normalized, "
            "%s elements skipped in %.1f s",
            len(stations),
            skipped_elements,
            perf_counter() - stage_started,
        )

        stage_started = perf_counter()
        _LOGGER.info("Step 3/6: Validating normalized charging-station records")
        duplicate_count = _validate_normalized_stations(stations)
        _LOGGER.info(
            "Step 3/6 completed: %s records validated in %.1f s",
            len(stations),
            perf_counter() - stage_started,
        )

        stage_started = perf_counter()
        _LOGGER.info(
            "Step 4/6: Building geohash index with precision %s",
            GEOHASH_PRECISION,
        )
        buckets, skipped_index_entries = build_index(
            stations,
            GEOHASH_PRECISION,
        )

        indexed_station_count = sum(
            len(bucket_stations)
            for bucket_stations in buckets.values()
        )

        if indexed_station_count == 0:
            raise ChargingDatabaseBuildError(
                "No charging stations could be added to the geohash index."
            )

        _LOGGER.info(
            "Step 4/6 completed: %s records indexed in %s geohash buckets, "
            "%s entries skipped in %.1f s",
            indexed_station_count,
            len(buckets),
            skipped_index_entries,
            perf_counter() - stage_started,
        )

        stage_started = perf_counter()
        _LOGGER.info(
            "Step 5/6: Grouping station records into logical charging sites "
            "with a %s m radius",
            DEFAULT_CLUSTER_RADIUS_M,
        )
        sites = build_sites(
            stations,
            DEFAULT_CLUSTER_RADIUS_M,
        )

        if not sites:
            raise ChargingDatabaseBuildError(
                "No logical charging sites could be built."
            )

        _LOGGER.info(
            "Step 5/6 completed: %s logical charging sites built in %.1f s",
            len(sites),
            perf_counter() - stage_started,
        )

        stage_started = perf_counter()
        _LOGGER.info(
            "Step 6/6: Writing charging database to %s",
            output_file,
        )
        database = _build_database_object(
            country_code=normalized_country_code,
            country_name=country_name,
            buckets=buckets,
            station_count=indexed_station_count,
            sites=sites,
        )

        output_file = Path(output_file)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        temporary_file = output_file.with_name(
            f".{output_file.name}.tmp"
        )

        save_database(database, temporary_file)
        temporary_file.replace(output_file)

        file_size_mib = output_file.stat().st_size / (1024 * 1024)
        _LOGGER.info(
            "Step 6/6 completed: database saved (%.2f MiB) in %.1f s",
            file_size_mib,
            perf_counter() - stage_started,
        )
        _LOGGER.info(
            "Charging database build completed for %s: %s sites in %.1f s",
            normalized_country_code,
            len(sites),
            perf_counter() - total_started,
        )

        return ChargingDatabaseBuildResult(
            country_code=normalized_country_code,
            country_name=country_name,
            output_file=output_file,
            downloaded_elements=len(elements),
            normalized_stations=len(stations),
            indexed_stations=indexed_station_count,
            skipped_elements=skipped_elements,
            skipped_index_entries=skipped_index_entries,
            duplicate_osm_ids=duplicate_count,
            geohash_precision=GEOHASH_PRECISION,
            geohash_buckets=len(buckets),
        )

    except ChargingDatabaseBuildError:
        _LOGGER.exception(
            "Charging database build failed for %s after %.1f s",
            normalized_country_code,
            perf_counter() - total_started,
        )
        raise
    except (OSError, RuntimeError, ValueError) as error:
        _LOGGER.exception(
            "Unexpected charging database build error for %s after %.1f s",
            normalized_country_code,
            perf_counter() - total_started,
        )
        raise ChargingDatabaseBuildError(
            f"Charging database build failed for "
            f"{normalized_country_code}: {error}"
        ) from error
