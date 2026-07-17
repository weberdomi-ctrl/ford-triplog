"""
Ford Triplog

Home Assistant sensor platform.

Version: 1.2.0
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import (
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from .utils import (
    format_address,
    format_address_short,
    format_duration,
)
from .icons import (
    ICON_TRIP_COUNT,
    ICON_DISTANCE,
    ICON_DURATION,
    ICON_DRIVING_TIME,
    ICON_SOC,
    ICON_START,
    ICON_DESTINATION,
)

from .const import DOMAIN

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
            # Last trip
            FordTriplogLastStartAddressSensor(coordinator, history),
            FordTriplogLastEndAddressSensor(coordinator, history),
            FordTriplogLastDistanceSensor(coordinator, history),
            FordTriplogLastConsumptionSensor(coordinator, history),
            FordTriplogLastEfficiencySensor(coordinator, history),
            FordTriplogLastAverageSpeedSensor(coordinator, history),
            FordTriplogLastDurationFormattedSensor(coordinator, history),
            FordTriplogLastDurationSensor(coordinator, history),
            FordTriplogLastSocSensor(coordinator, history),

            # Statistics
            FordTriplogDistanceSensor(coordinator, history),
            FordTriplogTotalEnergySensor(coordinator, history),
            FordTriplogAverageConsumptionSensor(coordinator, history),
            FordTriplogDurationFormattedSensor(coordinator, history),
            FordTriplogDurationSensor(coordinator, history),
            FordTriplogTripCountSensor(coordinator, history),
        ]
    )


class FordTriplogSensorBase(SensorEntity):
    """Base sensor."""

    _attr_has_entity_name = True

    def __init__(self, coordinator, history) -> None:
        self.coordinator = coordinator
        self.history = history
        self._value = None


    async def async_added_to_hass(self) -> None:
        """Entity added to Home Assistant."""

        self.coordinator.async_add_listener(
            self._handle_update
        )

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
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_icon = ICON_TRIP_COUNT

    def update_values(self, statistics, last_trip):
        self._value = statistics.get("trip_count", 0)


class FordTriplogDistanceSensor(FordTriplogSensorBase):
    _attr_name = "Total Distance"
    _attr_unique_id = "ford_triplog_total_distance"
    _attr_native_unit_of_measurement = "km"
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_icon = ICON_DISTANCE

    def update_values(self, statistics, last_trip):
        self._value = statistics.get("total_distance_km", 0)


class FordTriplogTotalEnergySensor(FordTriplogSensorBase):
    """Total energy used."""

    _attr_name = "Total Energy"
    _attr_unique_id = "ford_triplog_total_energy"
    _attr_native_unit_of_measurement = "kWh"
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_suggested_display_precision = 2
    _attr_icon = "mdi:lightning-bolt"

    def update_values(self, statistics, last_trip):
        self._value = statistics.get("total_energy_used_kwh", 0)


class FordTriplogAverageConsumptionSensor(FordTriplogSensorBase):
    """Average consumption over all trips."""

    _attr_name = "Average Consumption"
    _attr_unique_id = "ford_triplog_average_consumption"
    _attr_native_unit_of_measurement = "kWh/100 km"
    _attr_suggested_display_precision = 1
    _attr_icon = "mdi:chart-line"

    def update_values(self, statistics, last_trip):
        distance = statistics.get("total_distance_km", 0)
        energy = statistics.get("total_energy_used_kwh", 0)

        if distance > 0:
            self._value = round((energy / distance) * 100, 1)
        else:
            self._value = None


class FordTriplogDurationSensor(FordTriplogSensorBase):
    _attr_name = "Total Duration (Raw)"
    _attr_unique_id = "ford_triplog_total_duration"
    _attr_native_unit_of_measurement = "s"
    _attr_icon = ICON_DURATION

    def update_values(self, statistics, last_trip):
        self._value = statistics.get("total_duration_seconds", 0)
       
class FordTriplogDurationFormattedSensor(FordTriplogSensorBase):
    """Formatted total driving time."""

    _attr_name = "Total Driving Time"
    _attr_unique_id = "ford_triplog_total_duration_formatted"
    _attr_icon = ICON_DRIVING_TIME

    def update_values(self, statistics, last_trip):
        self._value = format_duration(
            statistics.get("total_duration_seconds")
        )


class FordTriplogLastDistanceSensor(FordTriplogSensorBase):
    _attr_name = "Last Distance"
    _attr_unique_id = "ford_triplog_last_trip_distance"
    _attr_native_unit_of_measurement = "km"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1
    _attr_icon = "mdi:map-marker-distance"

    def update_values(self, statistics, last_trip):
        self._value = last_trip.get("distance_km") if last_trip else None

class FordTriplogLastConsumptionSensor(FordTriplogSensorBase):
    """Energy used during the last trip."""
    _attr_name = "Last Consumption"
    _attr_unique_id = "ford_triplog_last_trip_consumption"
    _attr_native_unit_of_measurement = "kWh"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 2
    _attr_icon = "mdi:lightning-bolt"

    def update_values(self, statistics, last_trip):
        self._value = (
            last_trip.get("energy_used_kwh")
            if last_trip
            else None
        )        

class FordTriplogLastEfficiencySensor(FordTriplogSensorBase):
    """Average consumption of the last trip."""

    _attr_name = "Last Efficiency"
    _attr_unique_id = "ford_triplog_last_trip_efficiency"
    _attr_native_unit_of_measurement = "kWh/100 km"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1
    _attr_icon = "mdi:speedometer"

    def update_values(self, statistics, last_trip):
        self._value = (
            last_trip.get("consumption_kwh_100km")
            if last_trip
            else None
        )

class FordTriplogLastAverageSpeedSensor(FordTriplogSensorBase):
    """Average speed of the last trip."""

    _attr_name = "Last Average Speed"
    _attr_unique_id = "ford_triplog_last_trip_average_speed"
    _attr_native_unit_of_measurement = "km/h"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1
    _attr_icon = "mdi:speedometer-medium"

    def update_values(self, statistics, last_trip):
        self._value = (
            last_trip.get("average_speed_kmh")
            if last_trip
            else None
        )

class FordTriplogLastDurationSensor(FordTriplogSensorBase):
    _attr_name = "Last Duration (Raw)"
    _attr_unique_id = "ford_triplog_last_trip_duration"
    _attr_native_unit_of_measurement = "s"
    _attr_icon = "mdi:clock-outline"

    def update_values(self, statistics, last_trip):
        self._value = last_trip.get("duration_seconds") if last_trip else None

class FordTriplogLastDurationFormattedSensor(FordTriplogSensorBase):
    """Formatted duration of the last trip."""

    _attr_name = "Last Driving Time"
    _attr_unique_id = "ford_triplog_last_trip_duration_formatted"
    _attr_icon = "mdi:clock-time-eight-outline"

    def update_values(self, statistics, last_trip):
        self._value = format_duration(
            last_trip.get("duration_seconds")
            if last_trip
            else None
        )

class FordTriplogLastSocSensor(FordTriplogSensorBase):
    _attr_name = "Last SOC Used"
    _attr_unique_id = "ford_triplog_last_trip_soc_used"
    _attr_native_unit_of_measurement = "%"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = ICON_SOC

    def update_values(self, statistics, last_trip):
        self._value = last_trip.get("soc_used") if last_trip else None


class FordTriplogLastStartAddressSensor(FordTriplogSensorBase):
    _attr_name = "Last Start Address"
    _attr_unique_id = "ford_triplog_last_trip_start_address"
    _attr_icon = ICON_START

    def update_values(self, statistics, last_trip):
        self._value = format_address_short(
            last_trip.get("start_address")
            if last_trip
            else None
        )


class FordTriplogLastEndAddressSensor(FordTriplogSensorBase):
    _attr_name = "Last End Address"
    _attr_unique_id = "ford_triplog_last_trip_end_address"
    _attr_icon = ICON_DESTINATION

    def update_values(self, statistics, last_trip):
        self._value = format_address_short(
            last_trip.get("end_address")
            if last_trip
            else None
        )
