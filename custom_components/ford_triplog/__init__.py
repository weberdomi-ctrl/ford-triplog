"""
Ford Triplog

Track your Ford.

Home Assistant integration setup.

Version: 2.0.1-dev
Phase: 3 - Historical route date selection
Build: Enable Select platform

Changes:
- Restores the Route Tracker from the Coordinator's active or paused Trip
  after a Home Assistant/integration reload.
- Enables the Home Assistant Select platform for Route History date selection.
"""

from __future__ import annotations

import logging
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
    CONF_JOURNEY_HOME_TIMEOUT,
    CONF_JOURNEY_HOME_ZONE,
    CONF_JOURNEY_MAX_GAP_HOURS,
    DEFAULT_JOURNEY_HOME_TIMEOUT,
    DEFAULT_JOURNEY_HOME_ZONE,
    DEFAULT_JOURNEY_MAX_GAP_HOURS,
    DOMAIN,
)
from .coordinator import FordTriplogCoordinator
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


_LOGGER = logging.getLogger(__name__)



def _build_config(
    entry: ConfigEntry,
) -> dict[str, Any]:
    """Return merged configuration."""

    return {
        **entry.data,
        **entry.options,
    }


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> bool:
    """Set up Ford Triplog from a config entry."""

    storage = FordTriplogStorage(
        hass,
    )

    await storage.async_setup()

    geo = FordTriplogGeo(
        hass,
    )

    config = _build_config(entry)


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

    route_storage = FordTriplogRouteStorage(hass)
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
            CONF_BATTERY_CAPACITY
        ),
    )

    await journey_manager.async_setup()

    charge_manager = FordTriplogChargeManager(
        hass=hass,
        storage=storage,
    )

    await charge_manager.async_setup()

    receipt_storage = FordTriplogReceiptStorage(hass)
    await receipt_storage.async_setup()

    if not hass.data.setdefault(DOMAIN, {}).get("receipt_view_registered"):
        hass.http.register_view(FordTriplogReceiptView())
        hass.data[DOMAIN]["receipt_view_registered"] = True

    journey_rebuilder = FordTriplogJourneyRebuilder(
        source_storage=storage,
        journey_storage=journey_storage,
        battery_capacity_kwh=config.get(
            CONF_BATTERY_CAPACITY
        ),
    )

    # Issue #15
    # Allow the coordinator to trigger automatic Journey rebuilds
    # after a trip has been saved successfully.
    coordinator.journey_rebuilder = journey_rebuilder

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
        "history": coordinator.history,
        "geo": geo,
        "coordinator": coordinator,
        "config": config,
        "journey_storage": journey_storage,
        "journey_manager": journey_manager,
        "journey_rebuilder": journey_rebuilder,
        "charge_manager": charge_manager,
        "receipt_storage": receipt_storage,
        "route_storage": route_storage,
        "route_tracker": route_tracker,
    }

    entry.async_on_unload(
        entry.add_update_listener(
            entry_update_listener,
        )
    )

    await hass.config_entries.async_forward_entry_setups(
        entry,
        PLATFORMS,
    )

    _LOGGER.debug(
        "Ford Triplog initialized",
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
