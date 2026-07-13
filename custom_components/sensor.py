"""
Ford Triplog

Home Assistant sensor platform.

Version: 1.0.1
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN


def format_address(address: dict[str, Any] | None) -> str | None:
    """Format address for display."""

    if not address:
        return None

    street = " ".join(
        filter(
            None,
            [
                address.get("road"),
                address.get("house_number"),
            ],
        )
    )

    city = " ".join(
        filter(
            None,
            [
                address.get("postcode"),
                address.get("city"),
            ],
        )
    )

    return ", ".join(
        filter(
            None,
            [
                street,
                city,
                address.get("country"),
            ],
        )
    )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities,
) -> None:
    """Set up sensors."""

    data = hass.data[DOMAIN][entry.entry_id]

    coordinator = data["coordinator"]
    history = data["history"]

    async_add_entities(
        [
            FordTriplogTripCountSensor(coordinator, history),
            FordTriplogDistanceSensor(coordinator, history),
            FordTriplogDurationSensor(coordinator, history),
            FordTriplogLastDistanceSensor(coordinator, history),
            FordTriplogLastDurationSensor(coordinator, history),
            FordTriplogLastSocSensor(coordinator, history),
            FordTriplogLastStartAddressSensor(coordinator, history),
            FordTriplogLastEndAddressSensor(coordinator, history),
        ]
    )


class FordTriplogSensorBase(SensorEntity):
    """Base sensor."""

    _attr_has_entity_name = True

    def __init__(self, coordinator, history) -> None:
        self.coordinator = coordinator
        self.history = history
        self._value = None

        coordinator.async_add_listener(
            self._handle_update
        )

    async def async_added_to_hass(self) -> None:
        await self.async_update()

    async def async_update(self) -> None:
        statistics = await self.history.get_statistics()
        last_trip = await self.history.get_last_trip()

        self.update_values(
            statistics,
            last_trip,
        )

    def update_values(self, statistics, last_trip):
        pass

    def _handle_update(self) -> None:
        self.hass.async_create_task(self._async_handle_update())

    async def _async_handle_update(self) -> None:
        await self.async_update()
        self.async_write_ha_state()

    @property
    def native_value(self):
        return self._value

    @property
    def available(self):
        return self._value is not None

    @property
    def device_info(self):
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


class FordTriplogTripCountSensor(FordTriplogSensorBase):
    _attr_name = "Trip Count"
    _attr_unique_id = "ford_triplog_trip_count"
    _attr_icon = "mdi:counter"

    def update_values(self, statistics, last_trip):
        self._value = statistics.get("trip_count", 0)


class FordTriplogDistanceSensor(FordTriplogSensorBase):
    _attr_name = "Total Distance"
    _attr_unique_id = "ford_triplog_total_distance"
    _attr_native_unit_of_measurement = "km"
    _attr_icon = "mdi:map-marker-distance"

    def update_values(self, statistics, last_trip):
        self._value = statistics.get("total_distance_km", 0)


class FordTriplogDurationSensor(FordTriplogSensorBase):
    _attr_name = "Total Duration"
    _attr_unique_id = "ford_triplog_total_duration"
    _attr_native_unit_of_measurement = "s"
    _attr_icon = "mdi:timer-outline"

    def update_values(self, statistics, last_trip):
        self._value = statistics.get("total_duration_seconds", 0)


class FordTriplogLastDistanceSensor(FordTriplogSensorBase):
    _attr_name = "Last Distance"
    _attr_unique_id = "ford_triplog_last_trip_distance"
    _attr_native_unit_of_measurement = "km"
    _attr_icon = "mdi:map-marker-distance"

    def update_values(self, statistics, last_trip):
        self._value = last_trip.get("distance_km") if last_trip else None


class FordTriplogLastDurationSensor(FordTriplogSensorBase):
    _attr_name = "Last Duration"
    _attr_unique_id = "ford_triplog_last_trip_duration"
    _attr_native_unit_of_measurement = "s"
    _attr_icon = "mdi:clock-outline"

    def update_values(self, statistics, last_trip):
        self._value = last_trip.get("duration_seconds") if last_trip else None


class FordTriplogLastSocSensor(FordTriplogSensorBase):
    _attr_name = "Last SOC Used"
    _attr_unique_id = "ford_triplog_last_trip_soc_used"
    _attr_native_unit_of_measurement = "%"
    _attr_icon = "mdi:battery-arrow-down-outline"

    def update_values(self, statistics, last_trip):
        self._value = last_trip.get("soc_used") if last_trip else None


class FordTriplogLastStartAddressSensor(FordTriplogSensorBase):
    _attr_name = "Last Start Address"
    _attr_unique_id = "ford_triplog_last_trip_start_address"
    _attr_icon = "mdi:map-marker-start"

    def update_values(self, statistics, last_trip):
        self._value = format_address(
            last_trip.get("start_address")
            if last_trip
            else None
        )


class FordTriplogLastEndAddressSensor(FordTriplogSensorBase):
    _attr_name = "Last End Address"
    _attr_unique_id = "ford_triplog_last_trip_end_address"
    _attr_icon = "mdi:map-marker-check"

    def update_values(self, statistics, last_trip):
        self._value = format_address(
            last_trip.get("end_address")
            if last_trip
            else None
        )
