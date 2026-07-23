"""
Ford Triplog

Track your Ford.

Home Assistant integration setup.

Version: 1.4.1
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

from .const import DOMAIN
from .coordinator import FordTriplogCoordinator
from .geo import FordTriplogGeo
from .storage import FordTriplogStorage
from .services import async_register_services
from .progress_manager import ProgressManager


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

    config = _build_config(entry,)


    coordinator = FordTriplogCoordinator(
        hass=hass,
        storage=storage,
        config=config,
        geo=geo,
    )

    await coordinator.async_setup()

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
