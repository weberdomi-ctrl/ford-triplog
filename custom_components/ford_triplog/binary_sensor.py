"""
Ford Triplog

Track your Ford.

Home Assistant binary sensor platform.

Version: 1.0.0
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities,
) -> None:
    """Set up Ford Triplog binary sensors."""

    data = hass.data[DOMAIN][entry.entry_id]

    coordinator = data["coordinator"]

    async_add_entities(
        [
            FordTriplogActiveTripBinarySensor(
                coordinator
            )
        ]
    )


class FordTriplogActiveTripBinarySensor(
    BinarySensorEntity
):
    """Binary sensor showing active trip state."""

    _attr_has_entity_name = True
    _attr_name = "Trip Active"
    _attr_unique_id = "ford_triplog_trip_active"
    _attr_icon = "mdi:car-connected"

    def __init__(
        self,
        coordinator,
    ) -> None:
        """Initialize sensor."""

        self.coordinator = coordinator

        self.coordinator.async_add_listener(
            self._handle_coordinator_update
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle coordinator update."""
        self.async_write_ha_state()

    @property
    def is_on(self) -> bool:
        """Return active trip state."""

        return (
            self.coordinator.current_trip
            is not None
        )

    @property
    def available(self) -> bool:
        """Return availability."""

        return True

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device information."""

        return {
            "identifiers": {
                (
                    DOMAIN,
                    "ford_triplog",
                )
            },
            "name": "Ford Triplog",
            "manufacturer": "Ford",
            "model": "Triplog",
        }
