"""
Ford Triplog

Track your Ford.

Home Assistant integration setup.

Version: 0.8.5-dev
"""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import FordTriplogCoordinator
from .geo import FordTriplogGeo
from .history import FordTriplogHistory
from .storage import FordTriplogStorage

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [
    "sensor",
    "binary_sensor",
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> bool:
    """Set up Ford Triplog from a config entry."""

    storage = FordTriplogStorage(
        hass
    )

    await storage.async_setup()

    history = FordTriplogHistory(
        storage
    )

    geo = FordTriplogGeo(
        hass
    )

    coordinator = FordTriplogCoordinator(
        hass,
        storage,
        entry.data,
        geo,
    )

    await coordinator.async_setup()

    hass.data.setdefault(
        DOMAIN,
        {},
    )

    hass.data[DOMAIN][entry.entry_id] = {
        "storage": storage,
        "history": history,
        "geo": geo,
        "coordinator": coordinator,
        "config": entry.data,
    }

    await hass.config_entries.async_forward_entry_setups(
        entry,
        PLATFORMS,
    )

    _LOGGER.debug(
        "Ford Triplog initialized"
    )

    return True


async def async_unload_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> bool:
    """Unload Ford Triplog."""

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
            "Ford Triplog unloaded"
        )

    return unload_ok
