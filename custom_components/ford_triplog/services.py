"""
Ford Triplog

Charging-site service actions.

Version: 1.4.8
"""

from __future__ import annotations

import logging
import os
import shutil
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError

from .charging_database_builder import (
    ChargingDatabaseBuildError,
    ChargingDatabaseBuildResult,
    build_charging_database,
)
from .charging_site_lookup import (
    ChargingSiteDatabaseError,
    ChargingSiteLookup,
)
from .const import DOMAIN
from .countries import COUNTRIES

_LOGGER = logging.getLogger(__name__)

SERVICE_IMPORT_CHARGING_SITES = "import_charging_sites"
SERVICE_DOWNLOAD_CHARGING_DATABASE = "download_charging_database"

ATTR_FILE = "file"
ATTR_COUNTRY = "country"

CHARGING_SITE_DATABASE_DIRECTORY = "charging_sites"


IMPORT_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_FILE): vol.All(
            str,
            vol.Length(min=1),
        ),
    }
)

DOWNLOAD_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_COUNTRY): vol.All(
            str,
            str.upper,
            vol.In(tuple(sorted(COUNTRIES))),
        ),
    }
)


# ---------------------------------------------------------------------------
# NEW: Detect country_code from imported JSON file
# ---------------------------------------------------------------------------

def _detect_country_code(path: Path) -> str:
    """Extract country_code from imported JSON file."""
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as error:
        raise ServiceValidationError(
            f"Could not read JSON file: {error}"
        ) from error

    code = str(data.get("country_code", "")).strip().upper()

    if not code:
        raise ServiceValidationError(
            "The imported database does not contain a country_code field."
        )

    if code not in COUNTRIES:
        raise ServiceValidationError(
            f"Unsupported country code '{code}' in imported database."
        )

    return code


# ---------------------------------------------------------------------------
# NEW: Dynamic database path per country
# ---------------------------------------------------------------------------

def _database_path(hass: HomeAssistant, country_code: str) -> Path:
    """Return the persistent charging-site database path for one country."""
    return Path(
        hass.config.path(
            ".storage",
            "ford_triplog",
            CHARGING_SITE_DATABASE_DIRECTORY,
            "generated",
            f"charging_sites_{country_code.lower()}.json",
        )
    )


def _resolve_import_file(
    hass: HomeAssistant,
    configured_file: str,
) -> Path:
    """Resolve and validate a source file below the Home Assistant config path."""

    config_directory = Path(hass.config.path()).resolve()
    source_path = Path(configured_file)

    if source_path.is_absolute():
        raise ServiceValidationError(
            "Use a relative path below the Home Assistant configuration "
            "directory, for example import/charging_sites_de.json."
        )

    source_path = (config_directory / source_path).resolve()

    try:
        source_path.relative_to(config_directory)
    except ValueError as error:
        raise ServiceValidationError(
            "The import file must be located below the Home Assistant "
            "configuration directory."
        ) from error

    if source_path.suffix.lower() != ".json":
        raise ServiceValidationError(
            "The charging-site import file must be a JSON file."
        )

    if not source_path.is_file():
        raise ServiceValidationError(
            f"Charging-site import file not found: {source_path}"
        )

    return source_path


def _validate_import_file(source_path: Path) -> ChargingSiteLookup:
    """Validate the complete database by building a temporary lookup."""

    try:
        return ChargingSiteLookup(source_path)
    except ChargingSiteDatabaseError as error:
        raise ServiceValidationError(
            f"Charging-site database is invalid: {error}"
        ) from error
    except (OSError, TypeError, ValueError) as error:
        raise ServiceValidationError(
            f"Charging-site database could not be validated: {error}"
        ) from error


def _import_database(
    source_path: Path,
    target_path: Path,
) -> tuple[Path | None, ChargingSiteLookup]:
    """Backup, atomically replace and load the charging-site database."""

    target_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        source_is_target = source_path.samefile(target_path)
    except FileNotFoundError:
        source_is_target = False

    validated_source = _validate_import_file(source_path)

    if source_is_target:
        _LOGGER.info(
            "Charging-site database validated and activated in place: "
            "%s records, %s searchable sites, %s geohash cells",
            validated_source.site_count,
            validated_source.searchable_site_count,
            validated_source.index_cell_count,
        )
        return None, validated_source

    backup_path: Path | None = None

    if target_path.exists():
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup_path = target_path.with_name(
            f"{target_path.stem}_{timestamp}.bak.json"
        )
        shutil.copy2(target_path, backup_path)

    temporary_path = target_path.with_suffix(".json.tmp")

    try:
        shutil.copy2(source_path, temporary_path)
        os.replace(temporary_path, target_path)

        active_lookup = ChargingSiteLookup(target_path)
    except Exception:
        temporary_path.unlink(missing_ok=True)

        if backup_path is not None and backup_path.exists():
            shutil.copy2(backup_path, target_path)

        raise

    _LOGGER.info(
        "Charging-site database imported: %s records, %s searchable sites, "
        "%s geohash cells",
        validated_source.site_count,
        active_lookup.searchable_site_count,
        active_lookup.index_cell_count,
    )

    return backup_path, active_lookup


def _loaded_coordinators(hass: HomeAssistant) -> list[Any]:
    """Return all currently loaded Ford Triplog coordinators."""

    domain_data = hass.data.get(DOMAIN, {})

    coordinators: list[Any] = []

    for entry_data in domain_data.values():
        if not isinstance(entry_data, dict):
            continue

        coordinator = entry_data.get("coordinator")

        if coordinator is not None:
            coordinators.append(coordinator)

    return coordinators


# ---------------------------------------------------------------------------
# UPDATED: Import now detects country_code and stores per-country
# ---------------------------------------------------------------------------

async def async_import_charging_site_database(
    hass: HomeAssistant,
    source_path: Path,
    country_code: str | None = None,
) -> tuple[str, Path | None, ChargingSiteLookup]:
    """Import a validated database file and activate it immediately."""

    coordinators = _loaded_coordinators(hass)

    if not coordinators:
        raise ServiceValidationError(
            "Ford Triplog is not currently loaded."
        )

    if country_code is None:
        # Manual imports must determine the country from the JSON file.
        # File access and JSON parsing run outside Home Assistant's event loop.
        normalized_country_code = await hass.async_add_executor_job(
            _detect_country_code,
            source_path,
        )
    else:
        # Downloads already know the selected country and do not need to
        # reopen the generated JSON file merely to determine it again.
        normalized_country_code = str(country_code).strip().upper()

        if normalized_country_code not in COUNTRIES:
            supported = ", ".join(sorted(COUNTRIES))
            raise ServiceValidationError(
                f"Unsupported country code '{country_code}'. "
                f"Supported countries: {supported}."
            )

    target_path = _database_path(hass, normalized_country_code)

    try:
        backup_path, active_lookup = await hass.async_add_executor_job(
            _import_database,
            source_path,
            target_path,
        )
    except ServiceValidationError:
        raise
    except ChargingSiteDatabaseError as error:
        raise ServiceValidationError(
            f"Imported charging-site database could not be loaded: {error}"
        ) from error
    except OSError as error:
        raise ServiceValidationError(
            f"Charging-site database could not be imported: {error}"
        ) from error

    for coordinator in coordinators:
        coordinator.charging_site_lookup = active_lookup

    _LOGGER.info(
        "Charging-site import activated for %s; source=%s; target=%s; backup=%s",
        normalized_country_code,
        source_path,
        target_path,
        backup_path or "none",
    )

    return normalized_country_code, backup_path, active_lookup


# ---------------------------------------------------------------------------
# Download remains unchanged (already correct)
# ---------------------------------------------------------------------------

def _generated_database_path(
    hass: HomeAssistant,
    country_code: str,
) -> Path:
    """Return the generated database path for one country."""

    return Path(
        hass.config.path(
            ".storage",
            "ford_triplog",
            CHARGING_SITE_DATABASE_DIRECTORY,
            "generated",
            f"charging_sites_{country_code.lower()}.json",
        )
    )


async def async_download_charging_database(
    hass: HomeAssistant,
    country_code: str,
) -> tuple[ChargingDatabaseBuildResult, Path | None, ChargingSiteLookup]:
    """Download, build, import, and activate one country database."""

    normalized_country_code = str(country_code).strip().upper()

    if normalized_country_code not in COUNTRIES:
        supported = ", ".join(sorted(COUNTRIES))
        raise ServiceValidationError(
            f"Unsupported country code '{country_code}'. "
            f"Supported countries: {supported}."
        )

    output_path = _generated_database_path(
        hass,
        normalized_country_code,
    )

    progress_manager = hass.data[DOMAIN]["progress_manager"]

    try:
        build_result = await hass.async_add_executor_job(
            build_charging_database,
            normalized_country_code,
            output_path,
            progress_manager,
        )
    except ChargingDatabaseBuildError as error:
        raise ServiceValidationError(
            f"Charging-site database download failed: {error}"
        ) from error
    except (OSError, RuntimeError, ValueError) as error:
        raise ServiceValidationError(
            f"Charging-site database could not be generated: {error}"
        ) from error

    country_code, backup_path, active_lookup = await async_import_charging_site_database(
        hass,
        build_result.output_file,
        normalized_country_code,
    )

    _LOGGER.info(
        "Charging-site database downloaded and activated for %s: "
        "%s downloaded elements, %s indexed stations, %s geohash cells",
        build_result.country_code,
        build_result.downloaded_elements,
        build_result.indexed_stations,
        build_result.geohash_buckets,
    )

    return build_result, backup_path, active_lookup


# ---------------------------------------------------------------------------
# Service wrappers
# ---------------------------------------------------------------------------

async def async_import_charging_sites(
    hass: HomeAssistant,
    call: ServiceCall,
) -> None:
    """Import a charging-site database through the service action."""

    configured_file = call.data[ATTR_FILE]
    source_path = _resolve_import_file(hass, configured_file)

    await async_import_charging_site_database(
        hass,
        source_path,
    )


async def async_download_charging_database_service(
    hass: HomeAssistant,
    call: ServiceCall,
) -> None:
    """Download a charging-site database through the service action."""

    await async_download_charging_database(
        hass,
        call.data[ATTR_COUNTRY],
    )


async def async_register_services(hass: HomeAssistant) -> None:
    """Register Ford Triplog service actions once."""

    if not hass.services.has_service(
        DOMAIN,
        SERVICE_IMPORT_CHARGING_SITES,
    ):

        async def handle_import_charging_sites(
            call: ServiceCall,
        ) -> None:
            await async_import_charging_sites(hass, call)

        hass.services.async_register(
            DOMAIN,
            SERVICE_IMPORT_CHARGING_SITES,
            handle_import_charging_sites,
            schema=IMPORT_SCHEMA,
        )

        _LOGGER.debug(
            "Ford Triplog service registered: %s.%s",
            DOMAIN,
            SERVICE_IMPORT_CHARGING_SITES,
        )

    if not hass.services.has_service(
        DOMAIN,
        SERVICE_DOWNLOAD_CHARGING_DATABASE,
    ):

        async def handle_download_charging_database(
            call: ServiceCall,
        ) -> None:
            await async_download_charging_database_service(
                hass,
                call,
            )

        hass.services.async_register(
            DOMAIN,
            SERVICE_DOWNLOAD_CHARGING_DATABASE,
            handle_download_charging_database,
            schema=DOWNLOAD_SCHEMA,
        )

        _LOGGER.debug(
            "Ford Triplog service registered: %s.%s",
            DOMAIN,
            SERVICE_DOWNLOAD_CHARGING_DATABASE,
        )
