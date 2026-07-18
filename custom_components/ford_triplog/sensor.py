"""
Ford Triplog

Home Assistant sensor platform.

Version: 1.2.0
"""

from __future__ import annotations

from typing import Any

from datetime import datetime

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
    format_datetime,
)
from .icons import (
    ICON_TRIP_COUNT,
    ICON_DISTANCE,
    ICON_DURATION,
    ICON_DRIVING_TIME,
    ICON_SOC,
    ICON_START,
    ICON_DESTINATION,
    ICON_START_TIME,
    ICON_END_TIME,
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
            FordTriplogLastStartTimeSensor(coordinator, history),
            FordTriplogLastEndTimeSensor(coordinator, history),
            FordTriplogLastDistanceSensor(coordinator, history),
            FordTriplogLastConsumptionSensor(coordinator, history),
            FordTriplogLastEfficiencySensor(coordinator, history),
            FordTriplogLastAverageSpeedSensor(coordinator, history),
            FordTriplogLastDurationFormattedSensor(coordinator, history),
            FordTriplogLastDurationSensor(coordinator, history),
            FordTriplogLastSocSensor(coordinator, history),
            FordTriplogLastChargeStartTimeSensor(coordinator,history,),
            FordTriplogLastChargeEndTimeSensor(coordinator,history,),
            FordTriplogLastChargeStartSocSensor(coordinator,history,),
            FordTriplogLastChargeEndSocSensor(coordinator,history,),
            FordTriplogLastChargeSocAddedSensor(coordinator,history,),
            FordTriplogLastChargeDurationSensor(coordinator,history,),
            FordTriplogLastChargeStartAddressSensor(coordinator,history,),
            FordTriplogLastTripStartSocSensor(coordinator,history,),
            FordTriplogLastTripEndSocSensor(coordinator,history,),
            FordTriplogLastTripSocUsedSensor(coordinator,history,),

            # Statistics
            FordTriplogDistanceSensor(coordinator, history),
            FordTriplogTotalEnergySensor(coordinator, history),
            FordTriplogAverageConsumptionSensor(coordinator, history),
            FordTriplogDurationFormattedSensor(coordinator, history),
            FordTriplogDurationSensor(coordinator, history),
            FordTriplogTripCountSensor(coordinator, history),         
            FordTriplogChargeCountSensor(coordinator,history,),
            FordTriplogAverageChargeSocAddedSensor(coordinator,history,),
            FordTriplogAverageChargeDurationSensor(coordinator,history,),
            FordTriplogAverageChargeStartSocSensor(coordinator,history,),
            FordTriplogAverageChargeEndSocSensor(coordinator,history,),
            FordTriplogAverageTripDistanceSensor(coordinator,history,),
            FordTriplogAverageTripDurationSensor(coordinator,history,),
            FordTriplogAverageTripEnergySensor(coordinator,history,),
            FordTriplogAverageTripSocUsedSensor(coordinator,history,),
            FordTriplogAverageTripConsumptionSensor(coordinator,history,),
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
        last_charge = await self.history.get_last_charge()

        self.update_values(
            statistics,
            last_trip,
            last_charge,
        )

    def update_values(
        self,
        statistics,
        last_trip,
        last_charge,
    ):
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

    def update_values(self, statistics, last_trip,last_charge):
        self._value = statistics.get("trip_count", 0)


class FordTriplogDistanceSensor(FordTriplogSensorBase):
    _attr_name = "Total Distance"
    _attr_unique_id = "ford_triplog_total_distance"
    _attr_native_unit_of_measurement = "km"
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_icon = ICON_DISTANCE

    def update_values(self, statistics, last_trip,last_charge):
        self._value = statistics.get("total_distance_km", 0)


class FordTriplogTotalEnergySensor(FordTriplogSensorBase):
    """Total energy used."""

    _attr_name = "Total Energy"
    _attr_unique_id = "ford_triplog_total_energy"
    _attr_native_unit_of_measurement = "kWh"
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_suggested_display_precision = 2
    _attr_icon = "mdi:lightning-bolt"

    def update_values(self, statistics, last_trip,last_charge):
        self._value = statistics.get("total_energy_used_kwh", 0)


class FordTriplogAverageConsumptionSensor(FordTriplogSensorBase):
    """Average consumption over all trips."""

    _attr_name = "Average Consumption"
    _attr_unique_id = "ford_triplog_average_consumption"
    _attr_native_unit_of_measurement = "kWh/100 km"
    _attr_suggested_display_precision = 1
    _attr_icon = "mdi:chart-line"

    def update_values(self, statistics, last_trip,last_charge):
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

    def update_values(self, statistics, last_trip,last_charge):
        self._value = statistics.get("total_duration_seconds", 0)
       
class FordTriplogDurationFormattedSensor(FordTriplogSensorBase):
    """Formatted total driving time."""

    _attr_name = "Total Driving Time"
    _attr_unique_id = "ford_triplog_total_duration_formatted"
    _attr_icon = ICON_DRIVING_TIME

    def update_values(self, statistics, last_trip,last_charge):
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

    def update_values(self, statistics, last_trip,last_charge):
        self._value = last_trip.get("distance_km") if last_trip else None

class FordTriplogLastConsumptionSensor(FordTriplogSensorBase):
    """Energy used during the last trip."""
    _attr_name = "Last Consumption"
    _attr_unique_id = "ford_triplog_last_trip_consumption"
    _attr_native_unit_of_measurement = "kWh"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 2
    _attr_icon = "mdi:lightning-bolt"

    def update_values(self, statistics, last_trip,last_charge):
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

    def update_values(self, statistics, last_trip,last_charge):
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

    def update_values(self, statistics, last_trip,last_charge):
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

    def update_values(self, statistics, last_trip,last_charge):
        self._value = last_trip.get("duration_seconds") if last_trip else None

class FordTriplogLastDurationFormattedSensor(FordTriplogSensorBase):
    """Formatted duration of the last trip."""

    _attr_name = "Last Driving Time"
    _attr_unique_id = "ford_triplog_last_trip_duration_formatted"
    _attr_icon = "mdi:clock-time-eight-outline"

    def update_values(self, statistics, last_trip,last_charge):
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

    def update_values(self, statistics, last_trip,last_charge):
        self._value = last_trip.get("soc_used") if last_trip else None


class FordTriplogLastStartAddressSensor(FordTriplogSensorBase):
    _attr_name = "Last Start Address"
    _attr_unique_id = "ford_triplog_last_trip_start_address"
    _attr_icon = ICON_START

    def update_values(self, statistics, last_trip,last_charge):
        self._value = format_address_short(
            last_trip.get("start_address")
            if last_trip
            else None
        )


class FordTriplogLastEndAddressSensor(FordTriplogSensorBase):
    _attr_name = "Last End Address"
    _attr_unique_id = "ford_triplog_last_trip_end_address"
    _attr_icon = ICON_DESTINATION

    def update_values(self, statistics, last_trip,last_charge):
        self._value = format_address_short(
            last_trip.get("end_address")
            if last_trip
            else None
        )

class FordTriplogLastStartTimeSensor(FordTriplogSensorBase):
    """Formatted start time of the last trip."""

    _attr_name = "Last Start Time"
    _attr_unique_id = "ford_triplog_last_trip_start_time"
    _attr_icon = ICON_START_TIME

    def update_values(self, statistics, last_trip,last_charge):
        self._value = format_datetime(
            last_trip.get("start_time")
            if last_trip
            else None
        )


class FordTriplogLastEndTimeSensor(FordTriplogSensorBase):
    """Formatted end time of the last trip."""

    _attr_name = "Last End Time"
    _attr_unique_id = "ford_triplog_last_trip_end_time"
    _attr_icon = ICON_END_TIME

    def update_values(self, statistics, last_trip,last_charge):
        self._value = format_datetime(
            last_trip.get("end_time")
            if last_trip
            else None
        )
        
class FordTriplogLastChargeStartTimeSensor(FordTriplogSensorBase):
    """Formatted start time of the last charging session."""

    _attr_name = "Last Charge Start Time"
    _attr_unique_id = "ford_triplog_last_charge_start_time"
    _attr_icon = "mdi:ev-station"

    def update_values(
        self,
        statistics,
        last_trip,
        last_charge,
    ):
        self._value = format_datetime(
            last_charge.get("start_time")
            if last_charge
            else None
        )

class FordTriplogLastChargeEndTimeSensor(FordTriplogSensorBase):
    """Formatted end time of the last charging session."""

    _attr_name = "Last Charge End Time"
    _attr_unique_id = "ford_triplog_last_charge_end_time"
    _attr_icon = "mdi:ev-station"

    def update_values(
        self,
        statistics,
        last_trip,
        last_charge,
    ):
        self._value = format_datetime(
            last_charge.get("end_time")
            if last_charge
            else None
        )        
class FordTriplogLastChargeStartSocSensor(FordTriplogSensorBase):
    """SOC at the start of the last charging session."""

    _attr_name = "Last Charge Start SOC"
    _attr_unique_id = "ford_triplog_last_charge_start_soc"
    _attr_native_unit_of_measurement = "%"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = ICON_SOC

    def update_values(
        self,
        statistics,
        last_trip,
        last_charge,
    ):
        self._value = (
            last_charge.get("start_soc")
            if last_charge
            else None
        )
class FordTriplogLastChargeEndSocSensor(FordTriplogSensorBase):
    """SOC at the end of the last charging session."""

    _attr_name = "Last Charge End SOC"
    _attr_unique_id = "ford_triplog_last_charge_end_soc"
    _attr_native_unit_of_measurement = "%"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = ICON_SOC

    def update_values(
        self,
        statistics,
        last_trip,
        last_charge,
    ):
        self._value = (
            last_charge.get("end_soc")
            if last_charge
            else None
        )

class FordTriplogLastChargeSocAddedSensor(FordTriplogSensorBase):
    """SOC added during the last charging session."""

    _attr_name = "Last Charge SOC Added"
    _attr_unique_id = "ford_triplog_last_charge_soc_added"
    _attr_native_unit_of_measurement = "%"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:battery-plus"

    def update_values(
        self,
        statistics,
        last_trip,
        last_charge,
    ):
        if not last_charge:
            self._value = None
            return

        start = last_charge.get("start_soc")
        end = last_charge.get("end_soc")

        if start is None or end is None:
            self._value = None
            return

        self._value = round(end - start, 1)        

class FordTriplogLastChargeDurationSensor(FordTriplogSensorBase):
    """Duration of the last charging session."""

    _attr_name = "Last Charge Duration"
    _attr_unique_id = "ford_triplog_last_charge_duration"
    _attr_native_unit_of_measurement = "s"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:clock-outline"

    def update_values(
        self,
        statistics,
        last_trip,
        last_charge,
    ):
        if not last_charge:
            self._value = None
            return

        start = last_charge.get("start_time")
        end = last_charge.get("end_time")

        if not start or not end:
            self._value = None
            return

        start_dt = datetime.fromisoformat(start)
        end_dt = datetime.fromisoformat(end)

        self._value = int(
            (end_dt - start_dt).total_seconds()
        )
class FordTriplogLastChargeStartAddressSensor(FordTriplogSensorBase):
    """Address of the last charging session."""

    _attr_name = "Last Charge Address"
    _attr_unique_id = "ford_triplog_last_charge_address"
    _attr_icon = "mdi:map-marker"

    def update_values(
        self,
        statistics,
        last_trip,
        last_charge,
    ):
        if not last_charge:
            self._value = None
            return

        address = last_charge.get("start_address")

        if isinstance(address, dict):
            road = address.get("road", "")
            house = address.get("house_number", "")
            postcode = address.get("postcode", "")
            city = address.get("city", "")

            street = f"{road} {house}".strip()

            if postcode or city:
                self._value = f"{street}, {postcode} {city}".strip(", ")
        else:
            self._value = street
    
class FordTriplogLastTripStartSocSensor(FordTriplogSensorBase):
    """SOC at the start of the last trip."""

    _attr_name = "Last Trip Start SOC"
    _attr_unique_id = "ford_triplog_last_trip_start_soc"
    _attr_native_unit_of_measurement = "%"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = ICON_SOC

    def update_values(
        self,
        statistics,
        last_trip,
        last_charge,
    ):
        self._value = (
            last_trip.get("start_soc")
            if last_trip
            else None
        )
class FordTriplogLastTripEndSocSensor(FordTriplogSensorBase):
    """SOC at the end of the last trip."""

    _attr_name = "Last Trip End SOC"
    _attr_unique_id = "ford_triplog_last_trip_end_soc"
    _attr_native_unit_of_measurement = "%"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = ICON_SOC

    def update_values(
        self,
        statistics,
        last_trip,
        last_charge,
    ):
        self._value = (
            last_trip.get("end_soc")
            if last_trip
            else None
        )

class FordTriplogLastTripSocUsedSensor(FordTriplogSensorBase):
    """SOC used during the last trip."""

    _attr_name = "Last Trip SOC Used"
    _attr_unique_id = "ford_triplog_last_trip_soc_used"
    _attr_native_unit_of_measurement = "%"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:battery-minus"

    def update_values(
        self,
        statistics,
        last_trip,
        last_charge,
    ):
        if not last_trip:
            self._value = None
            return

        start = last_trip.get("start_soc")
        end = last_trip.get("end_soc")

        if start is None or end is None:
            self._value = None
            return

        self._value = round(start - end, 1)

class FordTriplogChargeCountSensor(FordTriplogSensorBase):
    """Number of recorded charging sessions."""

    _attr_name = "Charge Count"
    _attr_unique_id = "ford_triplog_charge_count"
    _attr_icon = "mdi:counter"

    def update_values(
        self,
        statistics,
        last_trip,
        last_charge,
    ):
        self._value = (
            statistics.get("charge_count", 0)
            if statistics
            else 0
        )
class FordTriplogAverageChargeSocAddedSensor(FordTriplogSensorBase):
    """Average SOC added per charging session."""

    _attr_name = "Average Charge SOC Added"
    _attr_unique_id = "ford_triplog_average_charge_soc_added"
    _attr_native_unit_of_measurement = "%"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:battery-plus"

    def update_values(
        self,
        statistics,
        last_trip,
        last_charge,
    ):
        self._value = (
            statistics.get("average_soc_added")
            if statistics
            else None
        )
class FordTriplogAverageChargeDurationSensor(FordTriplogSensorBase):
    """Average charging duration."""

    _attr_name = "Average Charge Duration"
    _attr_unique_id = "ford_triplog_average_charge_duration"
    _attr_icon = "mdi:clock-outline"

    def update_values(
        self,
        statistics,
        last_trip,
        last_charge,
    ):
        seconds = (
            statistics.get("average_charge_duration")
            if statistics
            else None
        )

        self._value = format_duration(seconds)

class FordTriplogAverageChargeStartSocSensor(FordTriplogSensorBase):
    """Average SOC at the start of charging sessions."""

    _attr_name = "Average Charge Start SOC"
    _attr_unique_id = "ford_triplog_average_charge_start_soc"
    _attr_native_unit_of_measurement = "%"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = ICON_SOC

    def update_values(
        self,
        statistics,
        last_trip,
        last_charge,
    ):
        self._value = (
            statistics.get("average_start_soc")
            if statistics
            else None
        )

class FordTriplogAverageChargeEndSocSensor(FordTriplogSensorBase):
    """Average SOC at the end of charging sessions."""

    _attr_name = "Average Charge End SOC"
    _attr_unique_id = "ford_triplog_average_charge_end_soc"
    _attr_native_unit_of_measurement = "%"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = ICON_SOC

    def update_values(
        self,
        statistics,
        last_trip,
        last_charge,
    ):
        self._value = (
            statistics.get("average_end_soc")
            if statistics
            else None
        )

class FordTriplogAverageTripDistanceSensor(FordTriplogSensorBase):
    """Average trip distance."""

    _attr_name = "Average Trip Distance"
    _attr_unique_id = "ford_triplog_average_trip_distance"
    _attr_native_unit_of_measurement = "km"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:map-marker-distance"

    def update_values(
        self,
        statistics,
        last_trip,
        last_charge,
    ):
        self._value = (
            statistics.get("average_trip_distance_km")
            if statistics
            else None
        )

class FordTriplogAverageTripDurationSensor(FordTriplogSensorBase):
    """Average trip duration."""

    _attr_name = "Average Trip Duration"
    _attr_unique_id = "ford_triplog_average_trip_duration"
    _attr_icon = "mdi:clock-outline"

    def update_values(
        self,
        statistics,
        last_trip,
        last_charge,
    ):
        seconds = (
            statistics.get("average_trip_duration_seconds")
            if statistics
            else None
        )

        self._value = format_duration(seconds)

class FordTriplogAverageTripEnergySensor(FordTriplogSensorBase):
    """Average trip energy used."""

    _attr_name = "Average Trip Energy Used"
    _attr_unique_id = "ford_triplog_average_trip_energy_used"
    _attr_native_unit_of_measurement = "kWh"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:lightning-bolt"

    def update_values(
        self,
        statistics,
        last_trip,
        last_charge,
    ):
        self._value = (
            statistics.get("average_trip_energy_used_kwh")
            if statistics
            else None
        )

class FordTriplogAverageTripSocUsedSensor(FordTriplogSensorBase):
    """Average SOC used per trip."""

    _attr_name = "Average Trip SOC Used"
    _attr_unique_id = "ford_triplog_average_trip_soc_used"
    _attr_native_unit_of_measurement = "%"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:battery-minus"

    def update_values(
        self,
        statistics,
        last_trip,
        last_charge,
    ):
        self._value = (
            statistics.get("average_trip_soc_used")
            if statistics
            else None
        )

class FordTriplogAverageTripConsumptionSensor(FordTriplogSensorBase):
    """Average trip consumption."""

    _attr_name = "Average Trip Consumption"
    _attr_unique_id = "ford_triplog_average_trip_consumption"
    _attr_native_unit_of_measurement = "kWh/100 km"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:ev-station"

    def update_values(
        self,
        statistics,
        last_trip,
        last_charge,
    ):
        self._value = (
            statistics.get("average_trip_consumption")
            if statistics
            else None
        )