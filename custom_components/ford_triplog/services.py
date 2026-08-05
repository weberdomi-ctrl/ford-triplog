"""
Ford Triplog

Charging-site service actions.

Version: 1.9.1
Release: 1.9.1 - Manual charging-site database import
"""

from __future__ import annotations

import logging
import os
import shutil
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.dispatcher import async_dispatcher_send

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
from .journey_rebuilder import FordTriplogJourneyRebuilder
from .journey_storage import FordTriplogJourneyStorage
from .journey import build_pause_id
from .const import SIGNAL_LAST_JOURNEY_UPDATED
from .charge_manager import FordTriplogChargeManager

_LOGGER = logging.getLogger(__name__)

SERVICE_IMPORT_CHARGING_SITES = "import_charging_sites"
SERVICE_DOWNLOAD_CHARGING_DATABASE = "download_charging_database"
SERVICE_UPDATE_JOURNEYS = "update_journeys"
SERVICE_REBUILD_JOURNEYS = "rebuild_journeys"
SERVICE_DELETE_JOURNEYS = "delete_journeys"
SERVICE_SET_CHARGE_COST = "set_charge_cost"
SERVICE_CLEAR_CHARGE_COST = "clear_charge_cost"
SERVICE_EDIT_PAUSE = "edit_pause"
SERVICE_CLEAR_PAUSE_EDIT = "clear_pause_edit"

ATTR_FILE = "file"
ATTR_COUNTRY = "country"
ATTR_ENTRY_ID = "entry_id"
ATTR_START_DATE = "start_date"
ATTR_END_DATE = "end_date"
ATTR_CHARGE_ID = "charge_id"
ATTR_COST_TOTAL = "cost_total"
ATTR_CURRENCY = "currency"
ATTR_JOURNEY_ID = "journey_id"
ATTR_PAUSE_ID = "pause_id"
ATTR_CATEGORY = "category"
ATTR_TITLE = "title"
ATTR_NOTE = "note"
ATTR_LOCATION = "location"

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


JOURNEY_MAINTENANCE_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_ENTRY_ID): vol.All(
            str,
            vol.Length(min=1),
        ),
        vol.Optional(ATTR_START_DATE): vol.Coerce(date.fromisoformat),
        vol.Optional(ATTR_END_DATE): vol.Coerce(date.fromisoformat),
    }
)


SET_CHARGE_COST_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_ENTRY_ID): vol.All(
            str,
            vol.Length(min=1),
        ),
        vol.Required(ATTR_CHARGE_ID): vol.All(
            str,
            vol.Length(min=1),
        ),
        vol.Required(ATTR_COST_TOTAL): vol.All(
            vol.Coerce(float),
            vol.Range(min=0),
        ),
        vol.Required(ATTR_CURRENCY): vol.All(
            str,
            str.upper,
            vol.Length(min=3, max=3),
        ),
    }
)

CLEAR_CHARGE_COST_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_ENTRY_ID): vol.All(
            str,
            vol.Length(min=1),
        ),
        vol.Required(ATTR_CHARGE_ID): vol.All(
            str,
            vol.Length(min=1),
        ),
    }
)


EDIT_PAUSE_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_ENTRY_ID): vol.All(str, vol.Length(min=1)),
        vol.Required(ATTR_JOURNEY_ID): vol.All(str, vol.Length(min=1)),
        vol.Required(ATTR_PAUSE_ID): vol.All(str, vol.Length(min=1)),
        vol.Optional(ATTR_CATEGORY): vol.Any(None, str),
        vol.Optional(ATTR_TITLE): vol.Any(None, str),
        vol.Optional(ATTR_NOTE): vol.Any(None, str),
        vol.Optional(ATTR_LOCATION): vol.Any(None, str),
        vol.Optional(ATTR_COST_TOTAL): vol.Any(None, vol.All(vol.Coerce(float), vol.Range(min=0))),
        vol.Optional(ATTR_CURRENCY): vol.Any(None, vol.All(str, str.upper, vol.Length(min=3, max=3))),
    }
)

CLEAR_PAUSE_EDIT_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_ENTRY_ID): vol.All(str, vol.Length(min=1)),
        vol.Required(ATTR_JOURNEY_ID): vol.All(str, vol.Length(min=1)),
        vol.Required(ATTR_PAUSE_ID): vol.All(str, vol.Length(min=1)),
    }
)


# ---------------------------------------------------------------------------
# NEW: Detect country_code from imported JSON file
# ---------------------------------------------------------------------------

def _detect_country_code(path: Path) -> str:
    """Extract and validate the country code from an imported database."""

    try:
        with path.open("r", encoding="utf-8") as file_handle:
            database = json.load(file_handle)
    except Exception as error:
        raise ServiceValidationError(
            f"Could not read JSON file: {error}"
        ) from error

    if not isinstance(database, dict):
        raise ServiceValidationError(
            "The imported file does not contain a valid JSON object."
        )

    metadata = database.get("metadata")

    if not isinstance(metadata, dict):
        raise ServiceValidationError(
            "The imported database does not contain a metadata section."
        )

    database_format = str(metadata.get("format", "")).strip()

    if database_format != "ford_triplog_charging_sites":
        raise ServiceValidationError(
            "The imported file is not a Ford Triplog charging-site database."
        )

    database_format_version = str(
        metadata.get("database_format_version", "")
    ).strip()

    if database_format_version != "1":
        raise ServiceValidationError(
            "Unsupported charging-site database format version "
            f"'{database_format_version or 'unknown'}'."
        )

    code = str(metadata.get("country_code", "")).strip().upper()

    if not code:
        raise ServiceValidationError(
            "The imported database metadata does not contain a country_code."
        )

    if code not in COUNTRIES:
        raise ServiceValidationError(
            f"Unsupported country code '{code}' in imported database."
        )

    database_data = database.get("data")

    if not isinstance(database_data, list) or not database_data:
        raise ServiceValidationError(
            "The imported charging-site database does not contain any data."
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



# ---------------------------------------------------------------------------
# Journey maintenance services
# ---------------------------------------------------------------------------

def _validate_journey_date_range(
    start_date: date | None,
    end_date: date | None,
) -> None:
    """Validate an inclusive Journey maintenance date range."""

    if (
        start_date is not None
        and end_date is not None
        and start_date > end_date
    ):
        raise ServiceValidationError(
            "start_date must not be after end_date"
        )


def _extract_journey_rebuilder(
    runtime_data: Any,
) -> FordTriplogJourneyRebuilder | None:
    """Extract the Journey rebuilder from runtime data."""

    if isinstance(
        runtime_data,
        FordTriplogJourneyRebuilder,
    ):
        return runtime_data

    if isinstance(runtime_data, Mapping):
        candidate = runtime_data.get("journey_rebuilder")
        if isinstance(
            candidate,
            FordTriplogJourneyRebuilder,
        ):
            return candidate

    candidate = getattr(
        runtime_data,
        "journey_rebuilder",
        None,
    )

    if isinstance(
        candidate,
        FordTriplogJourneyRebuilder,
    ):
        return candidate

    return None


def _resolve_journey_rebuilder(
    hass: HomeAssistant,
    entry_id: str | None,
) -> FordTriplogJourneyRebuilder:
    """Resolve the Journey rebuilder for one config entry."""

    domain_data = hass.data.get(DOMAIN)

    if not isinstance(domain_data, Mapping):
        raise HomeAssistantError(
            "Ford Triplog is not initialized"
        )

    candidates: list[
        tuple[str, FordTriplogJourneyRebuilder]
    ] = []

    for candidate_entry_id, runtime_data in domain_data.items():
        rebuilder = _extract_journey_rebuilder(runtime_data)

        if rebuilder is not None:
            candidates.append(
                (
                    str(candidate_entry_id),
                    rebuilder,
                )
            )

    if entry_id is not None:
        normalized_entry_id = entry_id.strip()

        for candidate_entry_id, rebuilder in candidates:
            if candidate_entry_id == normalized_entry_id:
                return rebuilder

        raise HomeAssistantError(
            "No Journey rebuilder exists for config entry "
            f"{normalized_entry_id}"
        )

    if not candidates:
        raise HomeAssistantError(
            "No initialized Ford Triplog Journey rebuilder was found"
        )

    if len(candidates) > 1:
        raise HomeAssistantError(
            "Several Ford Triplog config entries are active. "
            "Specify entry_id."
        )

    return candidates[0][1]


def _extract_charge_manager(
    runtime_data: Any,
) -> FordTriplogChargeManager | None:
    """Extract the Charge Manager from runtime data."""

    if isinstance(runtime_data, FordTriplogChargeManager):
        return runtime_data

    if isinstance(runtime_data, Mapping):
        candidate = runtime_data.get("charge_manager")
        if isinstance(candidate, FordTriplogChargeManager):
            return candidate

    candidate = getattr(runtime_data, "charge_manager", None)
    if isinstance(candidate, FordTriplogChargeManager):
        return candidate

    return None


def _resolve_charge_manager(
    hass: HomeAssistant,
    entry_id: str | None,
) -> FordTriplogChargeManager:
    """Resolve the Charge Manager for one config entry."""

    domain_data = hass.data.get(DOMAIN)

    if not isinstance(domain_data, Mapping):
        raise HomeAssistantError(
            "Ford Triplog is not initialized"
        )

    candidates: list[tuple[str, FordTriplogChargeManager]] = []

    for candidate_entry_id, runtime_data in domain_data.items():
        manager = _extract_charge_manager(runtime_data)

        if manager is not None:
            candidates.append(
                (
                    str(candidate_entry_id),
                    manager,
                )
            )

    if entry_id is not None:
        normalized_entry_id = str(entry_id).strip()

        for candidate_entry_id, manager in candidates:
            if candidate_entry_id == normalized_entry_id:
                return manager

        raise HomeAssistantError(
            "No Charge Manager exists for config entry "
            f"{normalized_entry_id}"
        )

    if not candidates:
        raise HomeAssistantError(
            "No initialized Ford Triplog Charge Manager was found"
        )

    if len(candidates) > 1:
        raise HomeAssistantError(
            "Several Ford Triplog config entries are active. "
            "Specify entry_id."
        )

    return candidates[0][1]


def _extract_journey_storage(runtime_data: Any) -> FordTriplogJourneyStorage | None:
    if isinstance(runtime_data, FordTriplogJourneyStorage):
        return runtime_data
    if isinstance(runtime_data, Mapping):
        candidate = runtime_data.get("journey_storage")
        if isinstance(candidate, FordTriplogJourneyStorage):
            return candidate
    return None


def _resolve_journey_storage(hass: HomeAssistant, entry_id: str | None) -> FordTriplogJourneyStorage:
    domain_data = hass.data.get(DOMAIN)
    if not isinstance(domain_data, Mapping):
        raise HomeAssistantError("Ford Triplog is not initialized")
    candidates = [(str(eid), storage) for eid, runtime in domain_data.items() if (storage := _extract_journey_storage(runtime)) is not None]
    if entry_id is not None:
        for eid, storage in candidates:
            if eid == str(entry_id).strip():
                return storage
        raise HomeAssistantError(f"No Journey storage exists for config entry {entry_id}")
    if len(candidates) != 1:
        raise HomeAssistantError("Specify entry_id because the Journey storage is unavailable or ambiguous")
    return candidates[0][1]


def _valid_pause_ids(journey) -> set[str]:
    return {
        build_pause_id(current.item_id, following.item_id)
        for current, following in zip(journey.items, journey.items[1:])
        if current.end_time and following.start_time
    }


async def _async_edit_pause(hass: HomeAssistant, call: ServiceCall) -> dict[str, Any]:
    storage = _resolve_journey_storage(hass, call.data.get(ATTR_ENTRY_ID))
    journey_id = call.data[ATTR_JOURNEY_ID].strip()
    pause_id = call.data[ATTR_PAUSE_ID].strip()
    journey = await storage.load_journey_by_id(journey_id)
    if journey is None:
        raise ServiceValidationError(f"Journey not found: {journey_id}")
    if pause_id not in _valid_pause_ids(journey):
        raise ServiceValidationError(f"Pause not found in journey: {pause_id}")
    override = dict(journey.pause_overrides.get(pause_id, {}))
    for field_name in (ATTR_CATEGORY, ATTR_TITLE, ATTR_NOTE, ATTR_LOCATION, ATTR_COST_TOTAL, ATTR_CURRENCY):
        if field_name not in call.data:
            continue
        value = call.data[field_name]
        if isinstance(value, str):
            value = value.strip()
        if value in (None, ""):
            override.pop(field_name, None)
        else:
            override[field_name] = value
    override["updated_at"] = datetime.now(timezone.utc).isoformat()
    journey.pause_overrides[pause_id] = override
    await storage.save_archived_journey(journey)
    async_dispatcher_send(hass, SIGNAL_LAST_JOURNEY_UPDATED)
    return {"updated": True, "journey_id": journey_id, "pause_id": pause_id, "pause": override}


async def _async_clear_pause_edit(hass: HomeAssistant, call: ServiceCall) -> dict[str, Any]:
    storage = _resolve_journey_storage(hass, call.data.get(ATTR_ENTRY_ID))
    journey_id = call.data[ATTR_JOURNEY_ID].strip()
    pause_id = call.data[ATTR_PAUSE_ID].strip()
    journey = await storage.load_journey_by_id(journey_id)
    if journey is None:
        raise ServiceValidationError(f"Journey not found: {journey_id}")
    removed = journey.pause_overrides.pop(pause_id, None) is not None
    await storage.save_archived_journey(journey)
    async_dispatcher_send(hass, SIGNAL_LAST_JOURNEY_UPDATED)
    return {"updated": removed, "journey_id": journey_id, "pause_id": pause_id}


async def _async_set_charge_cost(
    hass: HomeAssistant,
    call: ServiceCall,
) -> dict[str, Any]:
    """Set manual costs for one archived charging session."""

    manager = _resolve_charge_manager(
        hass,
        call.data.get(ATTR_ENTRY_ID),
    )

    try:
        result = await manager.async_set_cost(
            call.data[ATTR_CHARGE_ID],
            cost_total=call.data[ATTR_COST_TOTAL],
            currency=call.data[ATTR_CURRENCY],
        )
    except ValueError as error:
        raise ServiceValidationError(str(error)) from error

    if not result.updated:
        if result.reason == "charge_not_found":
            raise ServiceValidationError(
                f"Charging session not found: {result.charge_id}"
            )

        raise HomeAssistantError(
            "Charging costs could not be saved"
        )

    return result.to_dict()


async def _async_clear_charge_cost(
    hass: HomeAssistant,
    call: ServiceCall,
) -> dict[str, Any]:
    """Clear costs from one archived charging session."""

    manager = _resolve_charge_manager(
        hass,
        call.data.get(ATTR_ENTRY_ID),
    )

    try:
        result = await manager.async_clear_cost(
            call.data[ATTR_CHARGE_ID],
        )
    except ValueError as error:
        raise ServiceValidationError(str(error)) from error

    if not result.updated:
        if result.reason == "charge_not_found":
            raise ServiceValidationError(
                f"Charging session not found: {result.charge_id}"
            )

        raise HomeAssistantError(
            "Charging costs could not be cleared"
        )

    return result.to_dict()


async def _async_execute_journey_maintenance(
    hass: HomeAssistant,
    call: ServiceCall,
    *,
    operation: str,
) -> dict[str, Any]:
    """Execute one Journey maintenance action."""

    start_date = call.data.get(ATTR_START_DATE)
    end_date = call.data.get(ATTR_END_DATE)

    _validate_journey_date_range(
        start_date,
        end_date,
    )

    rebuilder = _resolve_journey_rebuilder(
        hass,
        call.data.get(ATTR_ENTRY_ID),
    )

    if operation == "update":
        result = await rebuilder.async_update_journeys(
            start_date=start_date,
            end_date=end_date,
        )
    elif operation == "rebuild":
        result = await rebuilder.async_rebuild_journeys(
            start_date=start_date,
            end_date=end_date,
        )
    elif operation == "delete":
        result = await rebuilder.async_delete_journeys(
            start_date=start_date,
            end_date=end_date,
        )
    else:
        raise HomeAssistantError(
            f"Unsupported Journey maintenance operation: {operation}"
        )

    result_data = result.to_dict()

    _LOGGER.info(
        "Journey maintenance completed: %s",
        result_data,
    )

    return result_data

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

    if not hass.services.has_service(
        DOMAIN,
        SERVICE_UPDATE_JOURNEYS,
    ):

        async def handle_update_journeys(
            call: ServiceCall,
        ) -> dict[str, Any]:
            return await _async_execute_journey_maintenance(
                hass,
                call,
                operation="update",
            )

        hass.services.async_register(
            DOMAIN,
            SERVICE_UPDATE_JOURNEYS,
            handle_update_journeys,
            schema=JOURNEY_MAINTENANCE_SCHEMA,
            supports_response=True,
        )

        _LOGGER.debug(
            "Ford Triplog service registered: %s.%s",
            DOMAIN,
            SERVICE_UPDATE_JOURNEYS,
        )

    if not hass.services.has_service(
        DOMAIN,
        SERVICE_REBUILD_JOURNEYS,
    ):

        async def handle_rebuild_journeys(
            call: ServiceCall,
        ) -> dict[str, Any]:
            return await _async_execute_journey_maintenance(
                hass,
                call,
                operation="rebuild",
            )

        hass.services.async_register(
            DOMAIN,
            SERVICE_REBUILD_JOURNEYS,
            handle_rebuild_journeys,
            schema=JOURNEY_MAINTENANCE_SCHEMA,
            supports_response=True,
        )

        _LOGGER.debug(
            "Ford Triplog service registered: %s.%s",
            DOMAIN,
            SERVICE_REBUILD_JOURNEYS,
        )

    if not hass.services.has_service(
        DOMAIN,
        SERVICE_DELETE_JOURNEYS,
    ):

        async def handle_delete_journeys(
            call: ServiceCall,
        ) -> dict[str, Any]:
            return await _async_execute_journey_maintenance(
                hass,
                call,
                operation="delete",
            )

        hass.services.async_register(
            DOMAIN,
            SERVICE_DELETE_JOURNEYS,
            handle_delete_journeys,
            schema=JOURNEY_MAINTENANCE_SCHEMA,
            supports_response=True,
        )

        _LOGGER.debug(
            "Ford Triplog service registered: %s.%s",
            DOMAIN,
            SERVICE_DELETE_JOURNEYS,
        )

    if not hass.services.has_service(
        DOMAIN,
        SERVICE_SET_CHARGE_COST,
    ):

        async def handle_set_charge_cost(
            call: ServiceCall,
        ) -> dict[str, Any]:
            return await _async_set_charge_cost(
                hass,
                call,
            )

        hass.services.async_register(
            DOMAIN,
            SERVICE_SET_CHARGE_COST,
            handle_set_charge_cost,
            schema=SET_CHARGE_COST_SCHEMA,
            supports_response=True,
        )

        _LOGGER.debug(
            "Ford Triplog service registered: %s.%s",
            DOMAIN,
            SERVICE_SET_CHARGE_COST,
        )

    if not hass.services.has_service(
        DOMAIN,
        SERVICE_CLEAR_CHARGE_COST,
    ):

        async def handle_clear_charge_cost(
            call: ServiceCall,
        ) -> dict[str, Any]:
            return await _async_clear_charge_cost(
                hass,
                call,
            )

        hass.services.async_register(
            DOMAIN,
            SERVICE_CLEAR_CHARGE_COST,
            handle_clear_charge_cost,
            schema=CLEAR_CHARGE_COST_SCHEMA,
            supports_response=True,
        )

        _LOGGER.debug(
            "Ford Triplog service registered: %s.%s",
            DOMAIN,
            SERVICE_CLEAR_CHARGE_COST,
        )
    if not hass.services.has_service(DOMAIN, SERVICE_EDIT_PAUSE):
        async def handle_edit_pause(call: ServiceCall) -> dict[str, Any]:
            return await _async_edit_pause(hass, call)
        hass.services.async_register(DOMAIN, SERVICE_EDIT_PAUSE, handle_edit_pause, schema=EDIT_PAUSE_SCHEMA, supports_response=True)

    if not hass.services.has_service(DOMAIN, SERVICE_CLEAR_PAUSE_EDIT):
        async def handle_clear_pause_edit(call: ServiceCall) -> dict[str, Any]:
            return await _async_clear_pause_edit(hass, call)
        hass.services.async_register(DOMAIN, SERVICE_CLEAR_PAUSE_EDIT, handle_clear_pause_edit, schema=CLEAR_PAUSE_EDIT_SCHEMA, supports_response=True)

