"""
Ford Triplog

Home Assistant sensor platform.

Version: 1.6.3
"""

from __future__ import annotations

from typing import Any

from datetime import datetime
import math

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    UnitOfEnergy,
    UnitOfLength,
    UnitOfSpeed,
    UnitOfTime,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.translation import async_get_translations
from homeassistant.helpers.dispatcher import async_dispatcher_connect
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

from .const import DOMAIN, VERSION, SIGNAL_LAST_JOURNEY_UPDATED
from .journey_storage import FordTriplogJourneyStorage

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities,
) -> None:
    """Set up sensors."""

    data = hass.data[DOMAIN][entry.entry_id]

    coordinator = data["coordinator"]
    history = data["history"]
    journey_storage = data.get("journey_storage")

    translations = await async_get_translations(
        hass,
        hass.config.language,
        "common",
        {DOMAIN},
    )

    common_translations = {
        "today": translations.get(
            f"component.{DOMAIN}.common.today",
            "Today",
        ),
        "yesterday": translations.get(
            f"component.{DOMAIN}.common.yesterday",
            "Yesterday",
        ),
        "unknown": translations.get(
            f"component.{DOMAIN}.common.unknown",
            "Unknown",
        ),
        "no_gps_data": translations.get(
            f"component.{DOMAIN}.common.no_gps_data",
            "No GPS data available",
        ),
    }

    async_add_entities(
        [
            # Last journey
            FordTriplogLastJourneySensor(
                journey_storage,
                common_translations,
            ),
            FordTriplogLastJourneyOverviewSensor(
                journey_storage,
                common_translations,
            ),

            # Last trip
            FordTriplogLastStartAddressSensor(coordinator, history, common_translations),
            FordTriplogLastEndAddressSensor(coordinator, history, common_translations),
            FordTriplogLastStartTimeSensor(coordinator, history, common_translations),
            FordTriplogLastEndTimeSensor(coordinator, history, common_translations),
            FordTriplogLastDistanceSensor(coordinator, history, common_translations),
            FordTriplogLastConsumptionSensor(coordinator, history, common_translations),
            FordTriplogLastEfficiencySensor(coordinator, history, common_translations),
            FordTriplogLastAverageSpeedSensor(coordinator, history, common_translations),
            FordTriplogLastDurationFormattedSensor(coordinator, history, common_translations),
            FordTriplogLastDurationSensor(coordinator, history, common_translations),
            FordTriplogLastChargeSensor(coordinator, history, common_translations),
            FordTriplogLastChargeStartTimeSensor(coordinator, history, common_translations),
            FordTriplogLastChargeEndTimeSensor(coordinator, history, common_translations),
            FordTriplogLastChargeStartSocSensor(coordinator, history, common_translations),
            FordTriplogLastChargeEndSocSensor(coordinator, history, common_translations),
            FordTriplogLastChargeSocAddedSensor(coordinator, history, common_translations),
            FordTriplogLastChargeDurationSensor(coordinator, history, common_translations),
            FordTriplogLastChargeEnergySensor(coordinator, history, common_translations),
            FordTriplogLastChargeEnergyFordPassSensor(coordinator, history, common_translations),
            FordTriplogLastChargeEnergyCalculatedSensor(coordinator, history, common_translations),
            FordTriplogLastChargeEnergySourceSensor(coordinator, history, common_translations),
            FordTriplogLastChargeStartAddressSensor(coordinator, history, common_translations),
            FordTriplogLastChargingSiteSensor(coordinator, history, common_translations),
            FordTriplogLastTripStartSocSensor(coordinator, history, common_translations),
            FordTriplogLastTripEndSocSensor(coordinator, history, common_translations),
            FordTriplogLastTripSocUsedSensor(coordinator, history, common_translations),

            # Statistics
            FordTriplogDistanceSensor(coordinator, history, common_translations),
            FordTriplogTotalEnergySensor(coordinator, history, common_translations),
            FordTriplogAverageConsumptionSensor(coordinator, history, common_translations),
            FordTriplogDurationFormattedSensor(coordinator, history, common_translations),
            FordTriplogDurationSensor(coordinator, history, common_translations),
            FordTriplogTripCountSensor(coordinator, history, common_translations),         
            FordTriplogChargeCountSensor(coordinator, history, common_translations),
            FordTriplogAverageChargeSocAddedSensor(coordinator, history, common_translations),
            FordTriplogAverageChargeDurationSensor(coordinator, history, common_translations),
            FordTriplogAverageChargeStartSocSensor(coordinator, history, common_translations),
            FordTriplogAverageChargeEndSocSensor(coordinator, history, common_translations),
            FordTriplogAverageTripDistanceSensor(coordinator, history, common_translations),
            FordTriplogAverageTripDurationSensor(coordinator, history, common_translations),
            FordTriplogAverageTripEnergySensor(coordinator, history, common_translations),
            FordTriplogAverageTripSocUsedSensor(coordinator, history, common_translations),
            FordTriplogAverageTripConsumptionSensor(coordinator, history, common_translations),
        ]


    )



class FordTriplogLastJourneySensor(SensorEntity):
    """Expose the last completed Journey."""

    _attr_has_entity_name = True
    _attr_translation_key = "last_journey"
    _attr_unique_id = "ford_triplog_last_journey"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:map-marker-path"

    def __init__(
        self,
        storage: FordTriplogJourneyStorage | None,
        translations: dict[str, str],
    ) -> None:
        self.storage = storage
        self.translations = translations
        self._journey = None
        self._attr_native_value = None

    async def async_added_to_hass(self) -> None:
        """Load state and subscribe to Journey updates."""

        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_LAST_JOURNEY_UPDATED,
                self._handle_journey_update,
            )
        )
        await self._async_refresh()

    def _handle_journey_update(self) -> None:
        """Schedule a refresh after a Journey update."""

        self.hass.async_create_task(
            self._async_refresh_and_write()
        )

    async def _async_refresh_and_write(self) -> None:
        """Refresh the sensor and write the new state."""

        await self._async_refresh()
        self.async_write_ha_state()

    async def _async_refresh(self) -> None:
        """Load the last completed Journey."""

        if self.storage is None:
            self._journey = None
            self._attr_native_value = None
            return

        self._journey = await self.storage.load_last_journey()

        if self._journey is None or not self._journey.end_time:
            self._attr_native_value = None
            return

        try:
            timestamp = datetime.fromisoformat(
                self._journey.end_time
            )
        except (TypeError, ValueError):
            self._attr_native_value = None
            return

        if timestamp.tzinfo is None:
            timestamp = timestamp.astimezone()

        self._attr_native_value = timestamp

    @property
    def available(self) -> bool:
        """Return whether Journey data is available."""

        return self._journey is not None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return details of the last completed Journey."""

        if self._journey is None:
            return {}

        journey = self._journey

        return {
            "journey_id": journey.journey_id,
            "date": journey.date,
            "start_time": journey.start_time,
            "end_time": journey.end_time,
            "start_address": journey.start_address,
            "end_address": journey.end_address,
            "start_latitude": journey.start_latitude,
            "start_longitude": journey.start_longitude,
            "end_latitude": journey.end_latitude,
            "end_longitude": journey.end_longitude,
            "trip_count": journey.trip_count,
            "charge_count": journey.charge_count,
            "trip_ids": list(journey.trip_ids),
            "charge_ids": list(journey.charge_ids),
            "distance_km": journey.distance_km,
            "driving_duration_seconds": (
                journey.driving_duration_seconds
            ),
            "charging_duration_seconds": (
                journey.charging_duration_seconds
            ),
            "total_duration_seconds": (
                journey.total_duration_seconds
            ),
            "energy_used_kwh": journey.energy_used_kwh,
            "energy_charged_kwh": journey.energy_charged_kwh,
            "average_consumption_kwh_100km": (
                journey.average_consumption_kwh_100km
            ),
            "items": [
                item.to_dict()
                for item in journey.items
            ],
        }

    @property
    def device_info(self):
        """Return device information."""

        return {
            "identifiers": {(DOMAIN, "ford_triplog")},
            "name": "Ford Triplog",
            "manufacturer": "Ford",
            "model": "Triplog",
            "sw_version": VERSION,
        }


class FordTriplogLastJourneyOverviewSensor(SensorEntity):
    """Expose a dashboard-ready overview of the last completed Journey."""

    _attr_has_entity_name = True
    _attr_name = "Letzte Tour Übersicht"
    _attr_unique_id = "ford_triplog_last_journey_overview"
    _attr_icon = "mdi:map-clock-outline"

    def __init__(
        self,
        storage: FordTriplogJourneyStorage | None,
        translations: dict[str, str],
    ) -> None:
        self.storage = storage
        self.translations = translations
        self._journey = None
        self._attr_native_value = None
        self._attributes: dict[str, Any] = {}

    async def async_added_to_hass(self) -> None:
        """Load state and subscribe to Journey updates."""

        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_LAST_JOURNEY_UPDATED,
                self._handle_journey_update,
            )
        )
        await self._async_refresh()

    def _handle_journey_update(self) -> None:
        """Schedule a refresh after a Journey update."""

        self.hass.async_create_task(
            self._async_refresh_and_write()
        )

    async def _async_refresh_and_write(self) -> None:
        """Refresh the sensor and write the new state."""

        await self._async_refresh()
        self.async_write_ha_state()

    @staticmethod
    def _parse_datetime(value: Any) -> datetime | None:
        """Parse one stored ISO timestamp."""

        if not value:
            return None

        try:
            return datetime.fromisoformat(str(value))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _seconds_between(start: Any, end: Any) -> int:
        """Return the non-negative duration between two timestamps."""

        start_dt = FordTriplogLastJourneyOverviewSensor._parse_datetime(
            start
        )
        end_dt = FordTriplogLastJourneyOverviewSensor._parse_datetime(
            end
        )

        if start_dt is None or end_dt is None:
            return 0

        return max(0, int((end_dt - start_dt).total_seconds()))

    @staticmethod
    def _format_clock(value: Any) -> str | None:
        """Return a compact local clock time."""

        timestamp = (
            FordTriplogLastJourneyOverviewSensor._parse_datetime(value)
        )
        if timestamp is None:
            return None

        return timestamp.astimezone().strftime("%H:%M")

    @staticmethod
    def _short_address(value: Any) -> str | None:
        """Return a compact address for dashboard output."""

        if value is None:
            return None

        formatted = format_address_short(value)
        return formatted or None

    def _build_timeline(self, journey) -> tuple[list[dict[str, Any]], int]:
        """Build start, trip, pause, charge and end timeline entries."""

        timeline: list[dict[str, Any]] = []
        total_pause_seconds = 0

        start_address = self._short_address(journey.start_address)
        end_address = self._short_address(journey.end_address)

        timeline.append(
            {
                "type": "start",
                "time": journey.start_time,
                "time_formatted": self._format_clock(journey.start_time),
                "location": start_address,
            }
        )

        items = list(journey.items)

        for index, item in enumerate(items):
            duration_seconds = self._seconds_between(
                item.start_time,
                item.end_time,
            )

            if item.item_type == "trip":
                entry = {
                    "type": "trip",
                    "id": item.item_id,
                    "start_time": item.start_time,
                    "end_time": item.end_time,
                    "start_time_formatted": self._format_clock(
                        item.start_time
                    ),
                    "end_time_formatted": self._format_clock(
                        item.end_time
                    ),
                    "duration_seconds": duration_seconds,
                    "duration": format_duration(duration_seconds),
                }
            else:
                entry = {
                    "type": "charge",
                    "id": item.item_id,
                    "start_time": item.start_time,
                    "end_time": item.end_time,
                    "start_time_formatted": self._format_clock(
                        item.start_time
                    ),
                    "end_time_formatted": self._format_clock(
                        item.end_time
                    ),
                    "duration_seconds": duration_seconds,
                    "duration": format_duration(duration_seconds),
                }

            timeline.append(entry)

            if index >= len(items) - 1:
                continue

            next_item = items[index + 1]
            pause_seconds = self._seconds_between(
                item.end_time,
                next_item.start_time,
            )

            if pause_seconds <= 0:
                continue

            total_pause_seconds += pause_seconds
            timeline.append(
                {
                    "type": "pause",
                    "start_time": item.end_time,
                    "end_time": next_item.start_time,
                    "start_time_formatted": self._format_clock(
                        item.end_time
                    ),
                    "end_time_formatted": self._format_clock(
                        next_item.start_time
                    ),
                    "duration_seconds": pause_seconds,
                    "duration": format_duration(pause_seconds),
                    "after": item.item_type,
                    "before": next_item.item_type,
                }
            )

        timeline.append(
            {
                "type": "end",
                "time": journey.end_time,
                "time_formatted": self._format_clock(journey.end_time),
                "location": end_address,
            }
        )

        return timeline, total_pause_seconds

    async def _async_refresh(self) -> None:
        """Load and prepare the last completed Journey."""

        if self.storage is None:
            self._journey = None
            self._attr_native_value = None
            self._attributes = {}
            return

        self._journey = await self.storage.load_last_journey()

        if self._journey is None:
            self._attr_native_value = None
            self._attributes = {}
            return

        journey = self._journey
        timeline, pause_seconds = self._build_timeline(journey)

        distance = round(float(journey.distance_km or 0), 1)
        total_duration = int(journey.total_duration_seconds or 0)

        self._attr_native_value = (
            f"{distance:g} km · {format_duration(total_duration)}"
        )

        self._attributes = {
            "journey_id": journey.journey_id,
            "date": journey.date,
            "start": {
                "time": journey.start_time,
                "time_formatted": self._format_clock(journey.start_time),
                "address": self._short_address(journey.start_address),
                "latitude": journey.start_latitude,
                "longitude": journey.start_longitude,
            },
            "end": {
                "time": journey.end_time,
                "time_formatted": self._format_clock(journey.end_time),
                "address": self._short_address(journey.end_address),
                "latitude": journey.end_latitude,
                "longitude": journey.end_longitude,
            },
            "distance_km": distance,
            "total_duration_seconds": total_duration,
            "total_duration": format_duration(total_duration),
            "driving_duration_seconds": (
                journey.driving_duration_seconds
            ),
            "driving_duration": format_duration(
                journey.driving_duration_seconds
            ),
            "pause_duration_seconds": pause_seconds,
            "pause_duration": format_duration(pause_seconds),
            "charging_duration_seconds": (
                journey.charging_duration_seconds
            ),
            "charging_duration": format_duration(
                journey.charging_duration_seconds
            ),
            "trip_count": journey.trip_count,
            "charge_count": journey.charge_count,
            "energy_used_kwh": journey.energy_used_kwh,
            "energy_charged_kwh": journey.energy_charged_kwh,
            "average_consumption_kwh_100km": (
                journey.average_consumption_kwh_100km
            ),
            "timeline": timeline,
        }

    @property
    def available(self) -> bool:
        """Return whether Journey data is available."""

        return self._journey is not None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return dashboard-ready Journey attributes."""

        return self._attributes

    @property
    def device_info(self):
        """Return device information."""

        return {
            "identifiers": {(DOMAIN, "ford_triplog")},
            "name": "Ford Triplog",
            "manufacturer": "Ford",
            "model": "Triplog",
            "sw_version": VERSION,
        }


class FordTriplogSensorBase(SensorEntity):
    """Base sensor."""

    _attr_has_entity_name = True

    def __init__(self, coordinator, history, translations) -> None:
        self.coordinator = coordinator
        self.history = history
        self.translations = translations
        self._value = None


    async def async_added_to_hass(self) -> None:
        """Entity added to Home Assistant."""

        self.async_on_remove(
            self.coordinator.async_add_listener(
                self._handle_update
            )
        )

        await self.async_update()

    async def async_update(self) -> None:
        """Update the sensor from the shared history snapshot."""
        statistics, last_trip, last_charge = (
            await self.history.get_sensor_data()
        )

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
            "sw_version": VERSION,
        }


class FordTriplogTripCountSensor(FordTriplogSensorBase):
    _attr_translation_key = "trip_count"
    _attr_unique_id = "ford_triplog_trip_count"
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_icon = ICON_TRIP_COUNT

    def update_values(self, statistics, last_trip,last_charge):
        self._value = statistics.get("trip_count", 0)


class FordTriplogDistanceSensor(FordTriplogSensorBase):
    _attr_translation_key = "total_distance"
    _attr_device_class = SensorDeviceClass.DISTANCE
    _attr_unique_id = "ford_triplog_total_distance"
    _attr_native_unit_of_measurement = UnitOfLength.KILOMETERS
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_suggested_display_precision = 1
    _attr_icon = ICON_DISTANCE

    def update_values(self, statistics, last_trip,last_charge):
        self._value = statistics.get("total_distance_km", 0)


class FordTriplogTotalEnergySensor(FordTriplogSensorBase):
    """Total energy used."""

    _attr_translation_key = "total_energy_used"
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_unique_id = "ford_triplog_total_energy"
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_suggested_display_precision = 2
    _attr_icon = "mdi:lightning-bolt"

    def update_values(self, statistics, last_trip,last_charge):
        self._value = statistics.get("total_energy_used_kwh", 0)


class FordTriplogAverageConsumptionSensor(FordTriplogSensorBase):
    """Average consumption over all trips."""

    _attr_translation_key = "average_consumption"
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
    _attr_translation_key = "total_duration"
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_unique_id = "ford_triplog_total_duration"
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_suggested_display_precision = 0
    _attr_icon = ICON_DURATION

    def update_values(self, statistics, last_trip,last_charge):
        self._value = statistics.get("total_duration_seconds", 0)
       
class FordTriplogDurationFormattedSensor(FordTriplogSensorBase):
    """Formatted total driving time."""

    _attr_translation_key = "total_driving_time"
    _attr_unique_id = "ford_triplog_total_duration_formatted"
    _attr_icon = ICON_DRIVING_TIME

    def update_values(self, statistics, last_trip,last_charge):
        self._value = format_duration(
            statistics.get("total_duration_seconds")
        )


class FordTriplogLastDistanceSensor(FordTriplogSensorBase):
    _attr_translation_key = "last_distance"
    _attr_device_class = SensorDeviceClass.DISTANCE
    _attr_unique_id = "ford_triplog_last_trip_distance"
    _attr_native_unit_of_measurement = UnitOfLength.KILOMETERS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1
    _attr_icon = "mdi:map-marker-distance"

    def update_values(self, statistics, last_trip,last_charge):
        self._value = last_trip.get("distance_km") if last_trip else None

class FordTriplogLastConsumptionSensor(FordTriplogSensorBase):
    """Energy used during the last trip."""
    _attr_translation_key = "last_energy_used"
    _attr_unique_id = "ford_triplog_last_trip_consumption"
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
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

    _attr_translation_key = "last_consumption"
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

    _attr_translation_key = "last_average_speed"
    _attr_device_class = SensorDeviceClass.SPEED
    _attr_unique_id = "ford_triplog_last_trip_average_speed"
    _attr_native_unit_of_measurement = UnitOfSpeed.KILOMETERS_PER_HOUR
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
    _attr_translation_key = "last_duration"
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_unique_id = "ford_triplog_last_trip_duration"
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    _attr_suggested_display_precision = 0
    _attr_icon = "mdi:clock-outline"

    def update_values(self, statistics, last_trip,last_charge):
        self._value = last_trip.get("duration_seconds") if last_trip else None

class FordTriplogLastDurationFormattedSensor(FordTriplogSensorBase):
    """Formatted duration of the last trip."""

    _attr_translation_key = "last_driving_time"
    _attr_unique_id = "ford_triplog_last_trip_duration_formatted"
    _attr_icon = "mdi:clock-time-eight-outline"

    def update_values(self, statistics, last_trip,last_charge):
        self._value = format_duration(
            last_trip.get("duration_seconds")
            if last_trip
            else None
        )

class FordTriplogLastStartAddressSensor(FordTriplogSensorBase):
    _attr_translation_key = "last_start_address"
    _attr_unique_id = "ford_triplog_last_trip_start_address"
    _attr_icon = ICON_START

    def update_values(self, statistics, last_trip,last_charge):
        self._value = format_address_short(
            last_trip.get("start_address")
            if last_trip
            else None
        )

class FordTriplogLastEndAddressSensor(FordTriplogSensorBase):
    _attr_translation_key = "last_destination"
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

    _attr_translation_key = "last_start_time"
    _attr_unique_id = "ford_triplog_last_trip_start_time"
    _attr_icon = ICON_START_TIME

    def update_values(self, statistics, last_trip,last_charge):
        self._value = format_datetime(
            last_trip.get("start_time")
            if last_trip
            else None,
            self.translations["today"],
            self.translations["yesterday"],
        )


class FordTriplogLastEndTimeSensor(FordTriplogSensorBase):
    """Formatted end time of the last trip."""

    _attr_translation_key = "last_end_time"
    _attr_unique_id = "ford_triplog_last_trip_end_time"
    _attr_icon = ICON_END_TIME

    def update_values(self, statistics, last_trip,last_charge):
        self._value = format_datetime(
            last_trip.get("end_time")
            if last_trip
            else None,
            self.translations["today"],
            self.translations["yesterday"],
        )
        
class FordTriplogLastChargeSensor(FordTriplogSensorBase):
    """Compact summary of the last completed charging session."""

    _attr_translation_key = "last_charge"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_unique_id = "ford_triplog_last_charge"
    _attr_icon = "mdi:ev-station"

    def __init__(self, coordinator, history, translations) -> None:
        super().__init__(coordinator, history, translations)
        self._attributes: dict[str, Any] = {}

    @staticmethod
    def _parse_timestamp(value: Any) -> datetime | None:
        """Parse a stored ISO timestamp for a timestamp sensor."""

        if not value:
            return None

        try:
            timestamp = datetime.fromisoformat(str(value))
        except (TypeError, ValueError):
            return None

        if timestamp.tzinfo is None:
            return timestamp.astimezone()

        return timestamp

    @staticmethod
    def _duration_seconds(last_charge: dict[str, Any]) -> int | None:
        """Return stored or calculated charging duration."""

        duration = last_charge.get("duration_seconds")
        if duration is not None:
            try:
                return int(duration)
            except (TypeError, ValueError):
                pass

        start = FordTriplogLastChargeSensor._parse_timestamp(
            last_charge.get("start_time")
        )
        end = FordTriplogLastChargeSensor._parse_timestamp(
            last_charge.get("end_time")
        )

        if not start or not end:
            return None

        return max(0, int((end - start).total_seconds()))

    @staticmethod
    def _soc_added(last_charge: dict[str, Any]) -> float | None:
        """Return stored or calculated SOC increase."""

        value = last_charge.get("soc_added")
        if value is not None:
            try:
                return round(float(value), 1)
            except (TypeError, ValueError):
                pass

        start_soc = last_charge.get("start_soc")
        end_soc = last_charge.get("end_soc")

        try:
            return round(float(end_soc) - float(start_soc), 1)
        except (TypeError, ValueError):
            return None

    def update_values(
        self,
        statistics,
        last_trip,
        last_charge,
    ):
        if not last_charge:
            self._value = None
            self._attributes = {}
            return

        self._value = self._parse_timestamp(
            last_charge.get("end_time")
            or last_charge.get("start_time")
        )

        duration_seconds = self._duration_seconds(last_charge)
        soc_added = self._soc_added(last_charge)

        address = format_address_short(last_charge.get("start_address"))
        charging_location = (
            last_charge.get("charging_site_name")
            or last_charge.get("charging_site_brand")
            or last_charge.get("charging_site_operator")
            or last_charge.get("charging_site_network")
            or address
        )

        attributes = {
            "start_time": last_charge.get("start_time"),
            "end_time": last_charge.get("end_time"),
            "duration_seconds": duration_seconds,
            "duration": (
                format_duration(duration_seconds)
                if duration_seconds is not None
                else None
            ),
            "start_soc": last_charge.get("start_soc"),
            "end_soc": last_charge.get("end_soc"),
            "soc_added": soc_added,
            "energy_added_kwh": last_charge.get("energy_added_kwh"),
            "energy_added_kwh_fordpass": last_charge.get(
                "energy_added_kwh_fordpass"
            ),
            "energy_added_kwh_calculated": last_charge.get(
                "energy_added_kwh_calculated"
            ),
            "energy_source": last_charge.get("energy_source"),
            "charging_location": charging_location,
            "address": address,
            "latitude": last_charge.get("start_latitude"),
            "longitude": last_charge.get("start_longitude"),
            "charging_site_id": last_charge.get("charging_site_id"),
            "charging_site_name": last_charge.get("charging_site_name"),
            "charging_site_brand": last_charge.get("charging_site_brand"),
            "charging_site_operator": last_charge.get(
                "charging_site_operator"
            ),
            "charging_site_network": last_charge.get(
                "charging_site_network"
            ),
            "charging_site_power_kw": last_charge.get(
                "charging_site_power_kw"
            ),
            "charging_site_connectors": last_charge.get(
                "charging_site_connectors"
            ),
            "charging_site_quality": last_charge.get(
                "charging_site_quality"
            ),
            "charging_site_distance_m": last_charge.get(
                "charging_site_distance_m"
            ),
            "trip_id": last_charge.get("trip_id"),
            "journey_id": last_charge.get("journey_id"),
        }

        self._attributes = {
            key: value
            for key, value in attributes.items()
            if value is not None
        }

    @property
    def extra_state_attributes(self):
        return self._attributes


class FordTriplogLastChargeStartTimeSensor(FordTriplogSensorBase):
    """Formatted start time of the last charging session."""

    _attr_translation_key = "last_charge_start_time"
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
            else None,
            self.translations["today"],
            self.translations["yesterday"],
        )

class FordTriplogLastChargeEndTimeSensor(FordTriplogSensorBase):
    """Formatted end time of the last charging session."""

    _attr_translation_key = "last_charge_end_time"
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
            else None,
            self.translations["today"],
            self.translations["yesterday"],
        )        
class FordTriplogLastChargeStartSocSensor(FordTriplogSensorBase):
    """SOC at the start of the last charging session."""

    _attr_translation_key = "last_charge_start_soc"
    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_unique_id = "ford_triplog_last_charge_start_soc"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1
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

    _attr_translation_key = "last_charge_end_soc"
    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_unique_id = "ford_triplog_last_charge_end_soc"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1
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

    _attr_translation_key = "last_charge_soc_added"
    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_unique_id = "ford_triplog_last_charge_soc_added"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1
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

    _attr_translation_key = "last_charge_duration"
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_unique_id = "ford_triplog_last_charge_duration"
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 0
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
class FordTriplogLastChargeEnergySensor(FordTriplogSensorBase):
    """Primary energy value of the last charging session."""

    _attr_translation_key = "last_charge_energy"
    _attr_unique_id = "ford_triplog_last_charge_energy"
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 2
    _attr_icon = "mdi:lightning-bolt"

    def update_values(
        self,
        statistics,
        last_trip,
        last_charge,
    ):
        self._value = (
            last_charge.get("energy_added_kwh")
            if last_charge
            else None
        )


class FordTriplogLastChargeEnergyFordPassSensor(
    FordTriplogSensorBase
):
    """FordPass energy value of the last charging session."""

    _attr_translation_key = "last_charge_energy_fordpass"
    _attr_unique_id = "ford_triplog_last_charge_energy_fordpass"
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 2
    _attr_icon = "mdi:car-connected"

    def update_values(
        self,
        statistics,
        last_trip,
        last_charge,
    ):
        self._value = (
            last_charge.get("energy_added_kwh_fordpass")
            if last_charge
            else None
        )


class FordTriplogLastChargeEnergyCalculatedSensor(
    FordTriplogSensorBase
):
    """Calculated energy value of the last charging session."""

    _attr_translation_key = "last_charge_energy_calculated"
    _attr_unique_id = "ford_triplog_last_charge_energy_calculated"
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 2
    _attr_icon = "mdi:calculator"

    def update_values(
        self,
        statistics,
        last_trip,
        last_charge,
    ):
        self._value = (
            last_charge.get("energy_added_kwh_calculated")
            if last_charge
            else None
        )


class FordTriplogLastChargeEnergySourceSensor(
    FordTriplogSensorBase
):
    """Source used for the primary charging energy value."""

    _attr_translation_key = "last_charge_energy_source"
    _attr_unique_id = "ford_triplog_last_charge_energy_source"
    _attr_icon = "mdi:source-branch"

    def update_values(
        self,
        statistics,
        last_trip,
        last_charge,
    ):
        self._value = (
            last_charge.get("energy_source")
            if last_charge
            else None
        )


class FordTriplogLastChargeStartAddressSensor(FordTriplogSensorBase):
    """Address of the last charging session."""

    _attr_translation_key = "last_charging_location"
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
            self._value = address.get("display_name")

            if not self._value:
                road = address.get("road", "")
                house = address.get("house_number", "")
                postcode = address.get("postcode", "")
                city = address.get("city", "")

                street = f"{road} {house}".strip()
                locality = f"{postcode} {city}".strip()

                self._value = (
                    f"{street}, {locality}".strip(", ")
                    if street or locality
                    else self.translations["no_gps_data"]
                )
        else:
            self._value = address or self.translations["no_gps_data"]
    
class FordTriplogLastChargingSiteSensor(FordTriplogSensorBase):
    """Resolved charging location of the last charging session."""

    _attr_translation_key = "last_charging_site"
    _attr_unique_id = "ford_triplog_last_charging_site"
    _attr_icon = "mdi:ev-station"

    def __init__(self, coordinator, history, translations) -> None:
        super().__init__(coordinator, history, translations)
        self._attributes: dict[str, Any] = {}

    @staticmethod
    def _distance_m(
        latitude_1: float,
        longitude_1: float,
        latitude_2: float,
        longitude_2: float,
    ) -> float:
        """Calculate distance between two coordinates in metres."""

        earth_radius_m = 6_371_000

        lat_1 = math.radians(latitude_1)
        lat_2 = math.radians(latitude_2)
        delta_lat = math.radians(latitude_2 - latitude_1)
        delta_lon = math.radians(longitude_2 - longitude_1)

        a = (
            math.sin(delta_lat / 2) ** 2
            + math.cos(lat_1)
            * math.cos(lat_2)
            * math.sin(delta_lon / 2) ** 2
        )

        return earth_radius_m * 2 * math.atan2(
            math.sqrt(a),
            math.sqrt(1 - a),
        )

    def _resolve_zone_name(
        self,
        latitude: Any,
        longitude: Any,
    ) -> str | None:
        """Resolve coordinates against configured Home Assistant zones."""

        try:
            charge_latitude = float(latitude)
            charge_longitude = float(longitude)
        except (TypeError, ValueError):
            return None

        matching_zone: tuple[float, str] | None = None

        for zone_state in self.hass.states.async_all("zone"):
            zone_latitude = zone_state.attributes.get("latitude")
            zone_longitude = zone_state.attributes.get("longitude")
            zone_radius = zone_state.attributes.get("radius", 100)

            try:
                distance = self._distance_m(
                    charge_latitude,
                    charge_longitude,
                    float(zone_latitude),
                    float(zone_longitude),
                )
                radius = float(zone_radius)
            except (TypeError, ValueError):
                continue

            if distance > radius:
                continue

            zone_name = zone_state.attributes.get(
                "friendly_name",
                zone_state.name,
            )

            # Prefer the closest matching zone when zones overlap.
            if (
                matching_zone is None
                or distance < matching_zone[0]
            ):
                matching_zone = (distance, zone_name)

        return matching_zone[1] if matching_zone else None

    @staticmethod
    def _fordpass_location(
        last_charge: dict[str, Any],
    ) -> dict[str, Any]:
        """Return the FordPass location dictionary when available."""

        snapshot = last_charge.get("fordpass_last_charge")

        if not isinstance(snapshot, dict):
            return {}

        attributes = snapshot.get("attributes")

        if not isinstance(attributes, dict):
            return {}

        location = attributes.get("location")
        return location if isinstance(location, dict) else {}

    @staticmethod
    def _address_fallback(
        last_charge: dict[str, Any],
        fordpass_location: dict[str, Any],
    ) -> str | None:
        """Build a readable address fallback."""

        fordpass_address = fordpass_location.get("address")

        if isinstance(fordpass_address, dict):
            address_1 = fordpass_address.get("address1")
            postcode = fordpass_address.get("postalCode")
            city = fordpass_address.get("city")

            locality = " ".join(
                part for part in (postcode, city) if part
            )

            if address_1 and locality:
                return f"{address_1}, {locality}"
            if address_1:
                return address_1
            if locality:
                return locality

        start_address = last_charge.get("start_address")

        if isinstance(start_address, dict):
            road = start_address.get("road")
            house_number = start_address.get("house_number")
            postcode = start_address.get("postcode")
            city = start_address.get("city")

            street = " ".join(
                str(part)
                for part in (road, house_number)
                if part
            )
            locality = " ".join(
                str(part)
                for part in (postcode, city)
                if part
            )

            if street and locality:
                return f"{street}, {locality}"
            return street or locality or start_address.get("display")

        return start_address if isinstance(start_address, str) else None

    def update_values(
        self,
        statistics,
        last_trip,
        last_charge,
    ):
        if not last_charge:
            self._value = None
            self._attributes = {}
            return

        fordpass_location = self._fordpass_location(last_charge)

        latitude = (
            fordpass_location.get("latitude")
            or last_charge.get("start_latitude")
        )
        longitude = (
            fordpass_location.get("longitude")
            or last_charge.get("start_longitude")
        )

        zone_name = self._resolve_zone_name(latitude, longitude)
        fordpass_name = fordpass_location.get("name")

        site_name = last_charge.get("charging_site_name")
        brand = last_charge.get("charging_site_brand")
        operator = last_charge.get("charging_site_operator")
        network = (
            last_charge.get("charging_site_network")
            or fordpass_location.get("network")
        )
        address = self._address_fallback(
            last_charge,
            fordpass_location,
        )

        stored_location = last_charge.get("start_address")
        stored_display_name = (
            stored_location.get("display_name")
            if isinstance(stored_location, dict)
            else None
        )

        self._value = (
            stored_display_name
            or zone_name
            or fordpass_name
            or site_name
            or brand
            or operator
            or network
            or address
            or self.translations["no_gps_data"]
        )

        self._attributes = {
            "resolved_from": (
                stored_location.get("source")
                if isinstance(stored_location, dict)
                and stored_location.get("source")
                else "zone"
                if zone_name
                else "fordpass_name"
                if fordpass_name
                else "osm"
                if any((site_name, brand, operator))
                else "fordpass_network"
                if network and network != "UNKNOWN"
                else "address"
                if address
                else None
            ),
            "zone": zone_name,
            "fordpass_name": fordpass_name,
            "address": address,
            "latitude": latitude,
            "longitude": longitude,
            "site_id": last_charge.get("charging_site_id"),
            "name": site_name,
            "brand": brand,
            "operator": operator,
            "network": network,
            "power_kw": last_charge.get("charging_site_power_kw", []),
            "capacity": last_charge.get("charging_site_capacity", []),
            "connectors": last_charge.get(
                "charging_site_connectors",
                [],
            ),
            "quality": last_charge.get("charging_site_quality"),
            "distance_m": last_charge.get(
                "charging_site_distance_m"
            ),
        }

    @property
    def extra_state_attributes(self):
        return self._attributes


class FordTriplogLastTripStartSocSensor(FordTriplogSensorBase):
    """SOC at the start of the last trip."""

    _attr_translation_key = "last_trip_start_soc"
    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_unique_id = "ford_triplog_last_trip_start_soc"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1
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

    _attr_translation_key = "last_trip_end_soc"
    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_unique_id = "ford_triplog_last_trip_end_soc"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1
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

    _attr_translation_key = "last_trip_soc_used"
    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_unique_id = "ford_triplog_last_trip_soc_used"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1
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

    _attr_translation_key = "charge_count"
    _attr_unique_id = "ford_triplog_charge_count"
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
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

    _attr_translation_key = "average_charge_soc_added"
    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_unique_id = "ford_triplog_average_charge_soc_added"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1
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

    _attr_translation_key = "average_charge_duration"
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

    _attr_translation_key = "average_charge_start_soc"
    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_unique_id = "ford_triplog_average_charge_start_soc"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1
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

    _attr_translation_key = "average_charge_end_soc"
    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_unique_id = "ford_triplog_average_charge_end_soc"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1
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

    _attr_translation_key = "average_trip_distance"
    _attr_device_class = SensorDeviceClass.DISTANCE
    _attr_unique_id = "ford_triplog_average_trip_distance"
    _attr_native_unit_of_measurement = UnitOfLength.KILOMETERS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1
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

    _attr_translation_key = "average_trip_duration"
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

    _attr_translation_key = "average_trip_energy"
    _attr_unique_id = "ford_triplog_average_trip_energy_used"
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 2
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

    _attr_translation_key = "average_trip_soc_used"
    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_unique_id = "ford_triplog_average_trip_soc_used"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1
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

    _attr_translation_key = "average_trip_consumption"
    _attr_unique_id = "ford_triplog_average_trip_consumption"
    _attr_native_unit_of_measurement = "kWh/100 km"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1
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