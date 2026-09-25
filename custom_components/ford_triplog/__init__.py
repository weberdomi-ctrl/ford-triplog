"""
Ford Triplog

Track your Ford.

Home Assistant integration setup.

Version: 2.5.0
Build: 25017
Changes: Global OCR/OSRM settings and safer OSRM match acceptance.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.const import Platform

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.SELECT,
]

from .const import (
    CONF_BATTERY_CAPACITY,
    CONF_VEHICLE_ID,
    CONF_VEHICLE_NAME,
    CONF_VEHICLE_TEST_ALIAS,
    CONF_VEHICLE_ALIAS_OF,
    DEFAULT_BATTERY_CAPACITY_KWH,
    CONF_JOURNEY_HOME_TIMEOUT,
    CONF_JOURNEY_HOME_ZONE,
    CONF_JOURNEY_MAX_GAP_HOURS,
    DEFAULT_JOURNEY_HOME_TIMEOUT,
    DEFAULT_JOURNEY_HOME_ZONE,
    DEFAULT_JOURNEY_MAX_GAP_HOURS,
    DOMAIN,
    NAME,
    STORAGE_DIR,
    VERSION,
    BUILD,
)
from .coordinator import FordTriplogCoordinator
from .database import FordTriplogDatabase
from .geo import FordTriplogGeo
from .storage import FordTriplogStorage
from .services import async_register_services
from .progress_manager import ProgressManager
from .journey_storage import FordTriplogJourneyStorage
from .journey_manager import FordTriplogJourneyManager
from .journey_rebuilder import FordTriplogJourneyRebuilder
from .charge_manager import FordTriplogChargeManager
from .receipt_storage import FordTriplogReceiptStorage, FordTriplogReceiptView
from .route_storage import FordTriplogRouteStorage
from .route_tracker import FordTriplogRouteTracker
from .vehicle_identity import (
    FordTriplogVehicleIdentity,
    async_detect_vehicle_identity,
)
from .vehicle_context import (
    ensure_vehicle_context,
    notify_vehicle_list_updated,
    remove_vehicle_context_if_unloaded,
    get_selected_vehicle_id,
    set_selected_vehicle_id,
)
from .global_settings import async_load_global_settings


_LOGGER = logging.getLogger(__name__)


def _build_config(
    entry: ConfigEntry,
) -> dict[str, Any]:
    """Return merged configuration."""

    config = {
        **entry.data,
        **entry.options,
    }
    config.setdefault(
        CONF_BATTERY_CAPACITY,
        DEFAULT_BATTERY_CAPACITY_KWH,
    )
    return config


async def _async_prepare_vehicle(
    hass: HomeAssistant,
    entry: ConfigEntry,
    config: dict[str, Any],
) -> tuple[int, dict[str, Any], FordTriplogVehicleIdentity]:
    """Resolve the ConfigEntry to one persistent vehicle registry row."""

    identity = async_detect_vehicle_identity(hass, config)

    configured_vehicle_id = config.get(CONF_VEHICLE_ID)
    preferred_vehicle_id: int | None = None
    if configured_vehicle_id is not None:
        try:
            preferred_vehicle_id = int(configured_vehicle_id)
        except (TypeError, ValueError):
            preferred_vehicle_id = None
    elif entry.unique_id in (None, DOMAIN):
        # Existing pre-2.5 installations are the legacy vehicle 1.
        preferred_vehicle_id = 1

    base_path = Path(hass.config.path(".storage", STORAGE_DIR))
    bootstrap_database = FordTriplogDatabase(
        hass,
        base_path,
        preferred_vehicle_id or 1,
    )
    await bootstrap_database.async_setup()

    configured_name = str(config.get(CONF_VEHICLE_NAME) or "").strip()
    detected_name = str(identity.name or identity.model or "").strip()
    vehicle_name = configured_name or detected_name or None

    vehicle = await bootstrap_database.async_ensure_vehicle(
        vin=identity.vin,
        name=vehicle_name,
        manufacturer=identity.manufacturer,
        model=identity.model,
        battery_capacity_kwh=config.get(
            CONF_BATTERY_CAPACITY,
            DEFAULT_BATTERY_CAPACITY_KWH,
        ),
        preferred_vehicle_id=preferred_vehicle_id,
        source=identity.source,
        allow_duplicate_vin=bool(config.get(CONF_VEHICLE_TEST_ALIAS, False)),
        alias_of_vehicle_id=config.get(CONF_VEHICLE_ALIAS_OF),
    )
    vehicle_id = int(vehicle["vehicle_id"])

    # Persist only the internal vehicle mapping and the user-facing name in
    # Home Assistant. VIN/model/manufacturer remain vehicle master data in DB.
    entry_data = dict(entry.data)
    changed = False
    if entry_data.get(CONF_VEHICLE_ID) != vehicle_id:
        entry_data[CONF_VEHICLE_ID] = vehicle_id
        changed = True
    if not entry_data.get(CONF_VEHICLE_NAME) and vehicle_name:
        entry_data[CONF_VEHICLE_NAME] = vehicle_name
        changed = True

    desired_unique_id = identity.unique_key
    unique_id = entry.unique_id
    if desired_unique_id and desired_unique_id != entry.unique_id:
        duplicate = next(
            (
                other
                for other in hass.config_entries.async_entries(DOMAIN)
                if other.entry_id != entry.entry_id
                and other.unique_id == desired_unique_id
            ),
            None,
        )
        if duplicate is None:
            unique_id = desired_unique_id
            changed = True

    title = entry.title
    if vehicle_name and (not title or title == NAME):
        title = f"{NAME} – {vehicle_name}"
        changed = True

    if changed:
        hass.config_entries.async_update_entry(
            entry,
            data=entry_data,
            unique_id=unique_id,
            title=title,
        )

    config[CONF_VEHICLE_ID] = vehicle_id
    if vehicle_name:
        config[CONF_VEHICLE_NAME] = vehicle_name

    _LOGGER.info(
        "Ford Triplog vehicle resolved: id=%s vin=%s name=%s source=%s",
        vehicle_id,
        identity.vin or "unknown",
        vehicle_name or vehicle.get("name") or "unknown",
        identity.source or "unknown",
    )

    return vehicle_id, vehicle, identity


def _configured_vehicle_ids(hass: HomeAssistant) -> set[int]:
    """Return vehicle ids still owned by Ford Triplog ConfigEntries.

    Disabled ConfigEntries count as configured. This is important: disabling a
    vehicle must never be interpreted as deleting its history. Legacy pre-2.5
    entries without an explicit vehicle id are treated as vehicle 1.
    """

    vehicle_ids: set[int] = set()
    for configured_entry in hass.config_entries.async_entries(DOMAIN):
        merged = {**configured_entry.data, **configured_entry.options}
        raw_vehicle_id = merged.get(CONF_VEHICLE_ID)
        try:
            vehicle_id = int(raw_vehicle_id)
        except (TypeError, ValueError):
            vehicle_id = 1 if configured_entry.unique_id in (None, DOMAIN) else None
        if vehicle_id is not None and vehicle_id >= 1:
            vehicle_ids.add(vehicle_id)
    return vehicle_ids


def _apply_vehicle_alias_updates(
    hass: HomeAssistant,
    *,
    removed_entry_id: str | None,
    promoted_vehicle_id: int | None,
    reparented_vehicle_ids: set[int] | list[int] | tuple[int, ...],
) -> None:
    """Keep duplicate-VIN ConfigEntry alias metadata consistent."""

    if promoted_vehicle_id is None:
        return

    affected = {int(value) for value in reparented_vehicle_ids}
    affected.add(int(promoted_vehicle_id))

    for other_entry in hass.config_entries.async_entries(DOMAIN):
        if removed_entry_id is not None and other_entry.entry_id == removed_entry_id:
            continue

        other_data = dict(other_entry.data)
        try:
            other_vehicle_id = int(other_data.get(CONF_VEHICLE_ID))
        except (TypeError, ValueError):
            continue

        if other_vehicle_id not in affected:
            continue

        changed = False
        if other_vehicle_id == int(promoted_vehicle_id):
            if other_data.pop(CONF_VEHICLE_ALIAS_OF, None) is not None:
                changed = True
            if other_data.pop(CONF_VEHICLE_TEST_ALIAS, None) is not None:
                changed = True
        else:
            if other_data.get(CONF_VEHICLE_ALIAS_OF) != int(promoted_vehicle_id):
                other_data[CONF_VEHICLE_ALIAS_OF] = int(promoted_vehicle_id)
                changed = True

        if changed:
            hass.config_entries.async_update_entry(other_entry, data=other_data)


async def _async_cleanup_orphaned_vehicles(
    hass: HomeAssistant,
    database: FordTriplogDatabase,
    current_vehicle_id: int,
) -> list[int]:
    """Remove vehicle rows left behind by older builds.

    Build 25013 removes a vehicle when its ConfigEntry is deleted. Vehicles
    deleted before that build can still exist in SQLite, including dependent
    trip/charge/journey/route rows. Only rows that are not referenced by any
    existing Ford Triplog ConfigEntry are considered orphaned.
    """

    configured_ids = _configured_vehicle_ids(hass)
    # The current ConfigEntry may have received its vehicle_id only moments
    # ago in _async_prepare_vehicle(). Keep it explicitly even if Home
    # Assistant has not yet reflected async_update_entry on the object.
    configured_ids.add(int(current_vehicle_id))
    vehicles = await database.async_list_vehicles()
    orphan_ids = [
        int(vehicle["vehicle_id"])
        for vehicle in vehicles
        if int(vehicle["vehicle_id"]) not in configured_ids
    ]
    if not orphan_ids:
        return []

    removed: list[int] = []
    for orphan_id in orphan_ids:
        # Receipt files are outside SQLite and therefore need explicit cleanup.
        try:
            receipt_storage = FordTriplogReceiptStorage(hass, orphan_id)
            await receipt_storage.async_setup()
            for receipt in await receipt_storage.async_list():
                receipt_id = str(receipt.get("receipt_id") or "").strip()
                if receipt_id:
                    await receipt_storage.async_remove(receipt_id)
        except (OSError, ValueError):
            _LOGGER.exception(
                "Unable to completely remove receipt files for orphaned Ford Triplog vehicle %s",
                orphan_id,
            )

        result = await database.async_delete_vehicle(orphan_id)
        if not result.get("deleted"):
            continue

        _apply_vehicle_alias_updates(
            hass,
            removed_entry_id=None,
            promoted_vehicle_id=result.get("promoted_vehicle_id"),
            reparented_vehicle_ids=result.get("reparented_vehicle_ids") or [],
        )
        removed.append(orphan_id)
        _LOGGER.info(
            "Ford Triplog orphaned vehicle %s removed from SQLite; removed=%s",
            orphan_id,
            result.get("deleted_counts") or {},
        )

    return removed


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> bool:
    """Set up Ford Triplog from a config entry."""

    config = _build_config(entry)
    vehicle_id, vehicle, identity = await _async_prepare_vehicle(
        hass,
        entry,
        config,
    )

    storage = FordTriplogStorage(
        hass,
        vehicle_id=vehicle_id,
    )

    await storage.async_setup()

    # OCR and OSRM are integration infrastructure, not vehicle properties.
    # Load/migrate them once and overlay the shared values onto every runtime.
    global_settings = await async_load_global_settings(
        hass,
        storage.database,
    )
    config.update(global_settings)

    removed_orphans = await _async_cleanup_orphaned_vehicles(
        hass,
        storage.database,
        vehicle_id,
    )
    if removed_orphans:
        # A stale primary row can promote a configured test alias. Re-read the
        # ConfigEntry and vehicle row before constructing the runtime.
        config = _build_config(entry)
        config.update(global_settings)
        vehicle = (
            await storage.database.async_get_vehicle(vehicle_id)
            or vehicle
        )
        notify_vehicle_list_updated(hass)

    geo = FordTriplogGeo(
        hass,
    )

    coordinator = FordTriplogCoordinator(
        hass=hass,
        storage=storage,
        config=config,
        geo=geo,
    )

    await coordinator.async_setup()

    # Statistics are derived data. Recalculate them from the currently
    # selected read backend on every integration setup/reload so switching
    # between JSON and SQLite cannot leave statistics from the previous
    # backend active.
    await coordinator.history.refresh_statistics()

    route_storage = FordTriplogRouteStorage(
        hass,
        vehicle_id=vehicle_id,
    )
    route_tracker = FordTriplogRouteTracker(
        hass=hass,
        storage=route_storage,
        config=config,
        start_point_correction_callback=(
            coordinator.async_handle_route_start_candidate
        ),
    )
    await route_tracker.async_setup()
    coordinator.route_tracker = route_tracker

    # Route Tracker Fix 06:
    # The Coordinator restores current_trip / Smart Trip pause state first.
    # Reattach the independent Route Tracker to that Trip and reload its
    # persisted GPS points before normal platform setup continues.
    recovery_trip = coordinator.current_trip
    recovery_paused = False

    if recovery_trip is None and coordinator.trip_pause_data is not None:
        recovery_trip = coordinator.trip_pause_data
        recovery_paused = True

    if recovery_trip is not None and recovery_trip.trip_id:
        await route_tracker.async_recover(
            recovery_trip.trip_id,
            paused=recovery_paused,
            start_latitude=recovery_trip.start_latitude,
            start_longitude=recovery_trip.start_longitude,
            start_timestamp=recovery_trip.start_time,
        )

    journey_storage = FordTriplogJourneyStorage(
        hass,
        vehicle_id=vehicle_id,
    )

    await journey_storage.async_setup()

    journey_manager = FordTriplogJourneyManager(
        hass=hass,
        storage=journey_storage,
        home_zone_entity_id=str(
            config.get(
                CONF_JOURNEY_HOME_ZONE,
                DEFAULT_JOURNEY_HOME_ZONE,
            )
        ),
        home_timeout_minutes=int(
            config.get(
                CONF_JOURNEY_HOME_TIMEOUT,
                DEFAULT_JOURNEY_HOME_TIMEOUT,
            )
        ),
        journey_max_gap_hours=int(
            config.get(
                CONF_JOURNEY_MAX_GAP_HOURS,
                DEFAULT_JOURNEY_MAX_GAP_HOURS,
            )
        ),
        battery_capacity_kwh=config.get(
            CONF_BATTERY_CAPACITY,
            DEFAULT_BATTERY_CAPACITY_KWH,
        ),
    )

    await journey_manager.async_setup()

    charge_manager = FordTriplogChargeManager(
        hass=hass,
        storage=storage,
        config=config,
        history=coordinator.history,
    )

    receipt_storage = FordTriplogReceiptStorage(
        hass,
        vehicle_id=vehicle_id,
    )
    await receipt_storage.async_setup()

    if not hass.data.setdefault(DOMAIN, {}).get("receipt_view_registered"):
        hass.http.register_view(FordTriplogReceiptView())
        hass.data[DOMAIN]["receipt_view_registered"] = True

    journey_rebuilder = FordTriplogJourneyRebuilder(
        source_storage=storage,
        journey_storage=journey_storage,
        battery_capacity_kwh=config.get(
            CONF_BATTERY_CAPACITY,
            DEFAULT_BATTERY_CAPACITY_KWH,
        ),
    )

    coordinator.journey_rebuilder = journey_rebuilder
    charge_manager.journey_rebuilder = journey_rebuilder

    await charge_manager.async_setup()

    await async_register_services(hass)

    hass.data.setdefault(
        DOMAIN,
        {},
    )

    if "progress_manager" not in hass.data[DOMAIN]:
        hass.data[DOMAIN]["progress_manager"] = ProgressManager()

    hass.data[DOMAIN][entry.entry_id] = {
        "progress_manager": hass.data[DOMAIN]["progress_manager"],
        "storage": storage,
        "database": storage.database,
        "history": coordinator.history,
        "geo": geo,
        "coordinator": coordinator,
        "config": config,
        "vehicle_id": vehicle_id,
        "vehicle": vehicle,
        "vehicle_identity": identity,
        "journey_storage": journey_storage,
        "journey_manager": journey_manager,
        "journey_rebuilder": journey_rebuilder,
        "charge_manager": charge_manager,
        "receipt_storage": receipt_storage,
        "route_storage": route_storage,
        "route_tracker": route_tracker,
    }

    # Initialize the shared manual/UI vehicle context. A valid existing
    # selection is kept when additional vehicle ConfigEntries are loaded.
    ensure_vehicle_context(hass, vehicle_id)
    notify_vehicle_list_updated(hass)

    entry.async_on_unload(
        entry.add_update_listener(
            entry_update_listener,
        )
    )

    await hass.config_entries.async_forward_entry_setups(
        entry,
        PLATFORMS,
    )

    _LOGGER.info(
        "Ford Triplog %s (build %s) initialized",
        VERSION,
        BUILD,
    )

    return True


async def async_unload_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> bool:
    """Unload a config entry."""

    runtime_data = hass.data.get(DOMAIN, {}).get(
        entry.entry_id,
        {},
    )
    coordinator = runtime_data.get("coordinator")

    route_tracker = runtime_data.get("route_tracker")

    if route_tracker is not None:
        await route_tracker.async_shutdown()

    if coordinator is not None:
        await coordinator.async_shutdown()

    unload_ok = await hass.config_entries.async_unload_platforms(
        entry,
        PLATFORMS,
    )

    if unload_ok:
        hass.data[DOMAIN].pop(
            entry.entry_id,
            None,
        )
        remove_vehicle_context_if_unloaded(
            hass,
            int(runtime_data.get("vehicle_id") or 1),
        )
        notify_vehicle_list_updated(hass)

        _LOGGER.debug(
            "Ford Triplog unloaded",
        )

    return unload_ok


async def async_remove_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> None:
    """Permanently remove one Ford Triplog vehicle.

    Home Assistant calls this hook only when the ConfigEntry itself is
    deleted. A normal options reload uses ``async_unload_entry`` and therefore
    keeps the vehicle registry and all history intact.
    """

    config = _build_config(entry)
    raw_vehicle_id = config.get(CONF_VEHICLE_ID)
    try:
        vehicle_id = int(raw_vehicle_id)
    except (TypeError, ValueError):
        # Legacy pre-2.5 entries map to vehicle 1.
        vehicle_id = 1 if entry.unique_id in (None, DOMAIN) else None

    if vehicle_id is None or vehicle_id < 1:
        _LOGGER.warning(
            "Ford Triplog ConfigEntry %s removed without a valid vehicle_id; "
            "SQLite vehicle cleanup skipped",
            entry.entry_id,
        )
        return

    # Remove managed receipt files before deleting their SQLite metadata.
    # Failure to remove one file must not leave the vehicle registry behind.
    try:
        receipt_storage = FordTriplogReceiptStorage(hass, vehicle_id)
        await receipt_storage.async_setup()
        for receipt in await receipt_storage.async_list():
            receipt_id = str(receipt.get("receipt_id") or "").strip()
            if receipt_id:
                await receipt_storage.async_remove(receipt_id)
    except (OSError, ValueError):
        _LOGGER.exception(
            "Unable to completely remove receipt files for Ford Triplog vehicle %s",
            vehicle_id,
        )

    base_path = Path(hass.config.path(".storage", STORAGE_DIR))
    database = FordTriplogDatabase(hass, base_path, vehicle_id)
    result = await database.async_delete_vehicle(vehicle_id)

    _apply_vehicle_alias_updates(
        hass,
        removed_entry_id=entry.entry_id,
        promoted_vehicle_id=result.get("promoted_vehicle_id"),
        reparented_vehicle_ids=result.get("reparented_vehicle_ids") or [],
    )

    remove_vehicle_context_if_unloaded(hass, vehicle_id)
    notify_vehicle_list_updated(hass)

    if result.get("deleted"):
        _LOGGER.info(
            "Ford Triplog vehicle %s permanently removed from SQLite; removed=%s",
            vehicle_id,
            result.get("deleted_counts") or {},
        )
    else:
        _LOGGER.debug(
            "Ford Triplog vehicle %s was already absent from SQLite",
            vehicle_id,
        )


async def entry_update_listener(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> None:
    """Reload the integration when options change.

    Preserve the shared dashboard vehicle context across the ConfigEntry
    reload. During an unload the selected vehicle runtime temporarily
    disappears, so the normal context fallback would otherwise switch the
    shared UI back to vehicle 1.
    """

    selected_vehicle_id = get_selected_vehicle_id(hass)

    await hass.config_entries.async_reload(
        entry.entry_id,
    )

    if selected_vehicle_id is None:
        return

    try:
        set_selected_vehicle_id(
            hass,
            int(selected_vehicle_id),
        )
    except (TypeError, ValueError):
        # The selected vehicle may genuinely have disappeared (for example
        # after deleting/disabling a ConfigEntry). In that case keep the
        # normal fallback selected by the vehicle context.
        _LOGGER.debug(
            "Ford Triplog vehicle context %s could not be restored after reload",
            selected_vehicle_id,
        )
