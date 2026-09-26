"""
Ford Triplog

Track your Ford.

Home Assistant binary sensor platform.

Version: 2.0.2
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback

from .const import (
    DOMAIN,
    VEHICLE_SOURCE_HEALTH_UNAVAILABLE,
)
from .vehicle_context import CoordinatorVehicleRuntimeProxy


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities,
) -> None:
    """Set up Ford Triplog binary sensors."""

    data = hass.data[DOMAIN][entry.entry_id]
    try:
        vehicle_id = int(data.get("vehicle_id") or 1)
    except (TypeError, ValueError):
        vehicle_id = 1
    if vehicle_id != 1:
        return

    coordinator = CoordinatorVehicleRuntimeProxy(hass, entry.entry_id)

    async_add_entities(
        [
            FordTriplogActiveTripBinarySensor(coordinator),
            FordTriplogVehicleSourceConnectivityBinarySensor(coordinator),
        ]
    )


class FordTriplogActiveTripBinarySensor(
    BinarySensorEntity
):
    """Binary sensor showing active trip state."""

    _attr_has_entity_name = True
    _attr_translation_key = "trip_active"
    _attr_unique_id = "ford_triplog_trip_active"
    _attr_icon = "mdi:car-connected"

    def __init__(
        self,
        coordinator,
    ) -> None:
        """Initialize sensor."""

        self.coordinator = coordinator

    async def async_added_to_hass(self) -> None:
        """Subscribe to coordinator updates when the entity is active."""

        self.async_on_remove(
            self.coordinator.async_add_listener(
                self._handle_coordinator_update
            )
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
        """Return coordinator availability."""

        return self.coordinator.last_update_success

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

class FordTriplogVehicleSourceConnectivityBinarySensor(BinarySensorEntity):
    """Binary sensor exposing the configured vehicle source health."""

    _attr_has_entity_name = True
    _attr_translation_key = "vehicle_source_connectivity"
    _attr_unique_id = "ford_triplog_vehicle_source_connectivity"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_icon = "mdi:car-connected"

    def __init__(self, coordinator) -> None:
        self.coordinator = coordinator

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            self.coordinator.async_add_listener(
                self._handle_coordinator_update
            )
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()

    @property
    def is_on(self) -> bool:
        return (
            self.coordinator.vehicle_source_health
            != VEHICLE_SOURCE_HEALTH_UNAVAILABLE
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        unavailable_since = self.coordinator.vehicle_source_unavailable_since
        return {
            "health_state": self.coordinator.vehicle_source_health,
            "unavailable_since": (
                unavailable_since.isoformat()
                if unavailable_since is not None
                else None
            ),
            "grace_seconds": (
                self.coordinator.vehicle_source_unavailable_grace_seconds
            ),
            "monitored_entities": list(
                self.coordinator.vehicle_source_monitored_entities
            ),
            "unavailable_entities": list(
                self.coordinator.vehicle_source_unavailable_entities
            ),
        }

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success

    @property
    def device_info(self) -> dict[str, Any]:
        return {
            "identifiers": {(DOMAIN, "ford_triplog")},
            "name": "Ford Triplog",
            "manufacturer": "Ford",
            "model": "Triplog",
        }

