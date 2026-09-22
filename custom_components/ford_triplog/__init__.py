"""
Ford Triplog

Track your Ford.

Home Assistant integration setup.

Version: 2.5.0
Build: 25011
Changes: Duplicate-VIN test vehicles and vehicle-style config entries.
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
)


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


async def entry_update_listener(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> None:
    """Reload the integration when options change."""

    await hass.config_entries.async_reload(
        entry.entry_id,
    )
