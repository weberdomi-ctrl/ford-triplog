"""
Ford Triplog

Track your Ford.

Home Assistant integration setup.

Version: 1.8.0
Release: 1.8.0 - Step 3
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
