"""
Ford Triplog

Home Assistant sensor platform.

Version: 2.1.0-dev
Build: 20
Phase: 3 - Top Locations SQL view integrated
Changes:
- Top Locations supports JSON and SQLite read backends.
- SQLite uses a dedicated SQL view and a single database read.
- Existing location resolution and ranking logic is unchanged.
- Diagnostic 01: expose the active read backend on the trip count sensor.
Changes:
- Language fix 01: use language-neutral internal Home/Unknown codes in Top Charging.
- Language fix 02: translate Home/Unknown only when values are exposed to Home Assistant.
- Language fix 03: detect the Home zone via entity_id zone.home instead of its visible name.
- Preserve all existing 2.0.2 Top Statistics behavior.
- Recorder fix 01: exclude large GeoJSON attributes from Recorder history while keeping them available on the live entities.
- Top Locations 01: add Top 5 departures and Top 5 destinations from archived trips.
- Top Locations 02: group Home language-neutrally via zone.home and translate only on output.
- Top Locations 03: cluster departures/destinations primarily by GPS proximity (50 m); use address grouping only when GPS is unavailable.
- Top Locations 04: keep the most complete address label found inside each GPS cluster.
- Top Locations Fix 01: add missing re import for address quality scoring.
- Top Locations Fix 02: keep Home in raw sensor attributes as stable English fallback.
- Top Routes 01: add Top 5 directed routes using the same 50 m GPS clustering as Top Locations.
- Top Routes 02: expose trip count, average distance and average consumption where available.
- Top Routes Fix 01: exclude routes where start and destination resolve to the same location.
- Top Routes Fix 02: include consumption in route averages only for trips of at least 10 km.
- Zone fix 01: resolve all Home Assistant zones before GPS/address clustering for Top Locations and Top Routes.
- Zone fix 02: keep zone.home as stable raw value Home; use user-defined names for all other zones.
- Charging location fix 01: resolve custom charging locations after HA zones and before GPS clustering.
- Charging location fix 02: resolve current OSM charging locations after custom sites using the coordinator lookup.
- Charging location fix 03: reuse custom-site radius and configured OSM lookup radius.

Previous changes:
- Keep Top Trip and Top Journey.
- Add one compact Top Charging sensor based on archived charging sessions.
- State is the most-used charging provider.
- Attributes expose Top 5 providers, Top 5 charging locations and the
  largest charging session with sessions, energy and cost aggregates.
- Fix 01: remove undefined SIGNAL_CHARGE_UPDATED dependency.
- Fix 02: use the real archived charging-site and address field names.
- Fix 03: resolve Home Assistant zones for historic charges, group home
  charging as Home, compact long OSM addresses and aggregate locations
  independently from provider.
- Fix 04: exclude Unknown from the Top Provider ranking while retaining
  unknown-provider session totals; format postal code and city together.
- Fix 05: re-match historic charging sessions against today's user-defined
  charging sites and current OSM charging-site database without modifying
  archived charge files. Matching uses end coordinates first, then start,
  the configured user-site radius, and the coordinator OSM radius.
- Phase 4: add one compact Top Day sensor.
- Top Day aggregates all completed Journeys per local calendar day and selects
  the day with the highest total Journey distance.
- Attributes include Journey/trip/charge counts, duration, energy, charging
  costs, start/end locations and compact route references.
- Route GeoJSON is intentionally not duplicated into Top Day to avoid large
  recorder attributes.
- Fix 01: compact Top Day start/end location strings to street/POI and
  postal code + city, matching the other Top Statistics sensors.
- Fix 02: use Home Assistant translation keys for Top Trip, Top Journey,
  Top Charging and Top Day instead of fixed English entity names.
- Fix 03: make Charging History translatable via charging_history key;
  Trip Active is handled by binary_sensor.py via trip_active key.
- Fix 04: remove redundant FordPass last-charge energy entity. The raw
  FordPass value remains stored internally and in last-charge attributes.
- Fix 05: make Journey History and Route History entity names translatable.
- Fix 09: aggregate Journey History across all Journeys on the selected
  calendar date, including timeline, duration, energy, SOC and costs.
"""

from __future__ import annotations

from typing import Any

from datetime import datetime, timedelta
import math
import re
import logging

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
from homeassistant.util import dt as dt_util
from homeassistant.components.http.auth import async_sign_path
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
from .const import SIGNAL_CHARGE_DATA_UPDATED
from .journey_storage import FordTriplogJourneyStorage
from .route_storage import FordTriplogRouteStorage
from .route_history import async_build_route_feature_collection
from .journey import build_pause_id

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities,
) -> None:
    """Set up sensors."""

    data = hass.data[DOMAIN][entry.entry_id]

    coordinator = data["coordinator"]
    history = data["history"]
    storage = data["storage"]
    database = storage.database
    read_backend = storage.read_backend
    journey_storage = data.get("journey_storage")
    route_storage = data.get("route_storage")
    charge_manager = data.get("charge_manager")
    receipt_storage = data.get("receipt_storage")

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
        "charging_site_home": translations.get(
            f"component.{DOMAIN}.common.charging_site_home",
            "Home",
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
            FordTriplogLastRouteSensor(
                coordinator,
                route_storage,
            ),
            FordTriplogRouteHistorySensor(
                coordinator,
                route_storage,
                entry.entry_id,
            ),
            FordTriplogJourneyHistorySensor(
                journey_storage,
                common_translations,
                entry.entry_id,
            ),
            FordTriplogChargingHistorySensor(
                charge_manager,
                receipt_storage,
                entry.entry_id,
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
            FordTriplogLastChargeEnergyCalculatedSensor(coordinator, history, common_translations),
            FordTriplogLastChargeEnergySourceSensor(coordinator, history, common_translations),
            FordTriplogLastChargeStartAddressSensor(coordinator, history, common_translations),
            FordTriplogLastChargingSiteSensor(coordinator, history, common_translations),
            FordTriplogLastTripStartSocSensor(coordinator, history, common_translations),
            FordTriplogLastTripEndSocSensor(coordinator, history, common_translations),
            FordTriplogLastTripSocUsedSensor(coordinator, history, common_translations),

            # Statistics
            FordTriplogTopTripSensor(
                coordinator,
                history,
                database,
                read_backend,
                common_translations,
            ),
            FordTriplogTopJourneySensor(
                journey_storage,
                database,
                read_backend,
                common_translations,
            ),
            FordTriplogTopChargingSensor(
                coordinator,
                history,
                database,
                read_backend,
                common_translations,
            ),
            FordTriplogTopDaySensor(
                journey_storage,
                route_storage,
                database,
                read_backend,
                common_translations,
            ),
            FordTriplogTopLocationsSensor(
                coordinator,
                history,
                database,
                read_backend,
                common_translations,
            ),
            FordTriplogTopRoutesSensor(
                coordinator,
                history,
                database,
                read_backend,
                common_translations,
            ),
            FordTriplogDistanceSensor(coordinator, history, common_translations),
            FordTriplogTotalEnergySensor(coordinator, history, common_translations),
            FordTriplogAverageConsumptionSensor(coordinator, history, common_translations),
            FordTriplogDurationFormattedSensor(coordinator, history, common_translations),
            FordTriplogDurationSensor(coordinator, history, common_translations),
            FordTriplogTripCountSensor(
                coordinator,
                history,
                common_translations,
                read_backend,
            ),
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

    def _handle_journey_update(self, *_args: Any) -> None:
        """Schedule a thread-safe refresh after a Journey update."""

        self.hass.add_job(self._async_refresh_and_write)

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
            "display_start_location": (
                journey.items[0].start_location
                if journey.items
                and journey.items[0].item_type == "trip"
                and journey.items[0].start_location
                else journey.start_address
            ),
            "display_end_location": (
                journey.items[-1].end_location
                if journey.items
                and journey.items[-1].item_type == "trip"
                and journey.items[-1].end_location
                else journey.items[-1].location
                if journey.items
                and journey.items[-1].item_type == "charge"
                and journey.items[-1].location
                else journey.end_address
            ),
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
            "start_soc": journey.start_soc,
            "end_soc": journey.end_soc,
            "soc_delta": journey.soc_delta,
            "soc_used": journey.soc_used,
            "soc_charged": journey.soc_charged,
            "soc_adjustment": journey.soc_adjustment,
            "battery_capacity_kwh": journey.battery_capacity_kwh,
            "battery_energy_delta_kwh": (
                journey.battery_energy_delta_kwh
            ),
            "soc_adjustment_kwh": journey.soc_adjustment_kwh,
            "battery_energy_balance_kwh": (
                journey.battery_energy_balance_kwh
            ),
            "total_energy_flow_kwh": journey.total_energy_flow_kwh,
            "average_consumption_kwh_100km": (
                journey.average_consumption_kwh_100km
            ),
            "charging_cost_total": journey.charging_cost_total,
            "charging_energy_cost": journey.charging_energy_cost,
            "charging_additional_cost": (
                journey.charging_additional_cost
            ),
            "average_charging_price_per_kwh": (
                journey.average_charging_price_per_kwh
            ),
            "currency": journey.currency,
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
    _attr_translation_key = "last_journey_overview"
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

    def _handle_journey_update(self, *_args: Any) -> None:
        """Schedule a thread-safe refresh after a Journey update."""

        self.hass.add_job(self._async_refresh_and_write)

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

        start_dt = FordTriplogLastJourneyOverviewSensor._parse_datetime(start)
        end_dt = FordTriplogLastJourneyOverviewSensor._parse_datetime(end)

        if start_dt is None or end_dt is None:
            return 0

        return max(0, int((end_dt - start_dt).total_seconds()))

    @staticmethod
    def _format_duration_compact(seconds: Any) -> str:
        """Return a compact human-readable duration for the sensor state."""

        try:
            total_seconds = max(0, int(seconds or 0))
        except (TypeError, ValueError):
            total_seconds = 0

        hours, remainder = divmod(total_seconds, 3600)
        minutes = remainder // 60

        if hours:
            return f"{hours} h {minutes} min"

        return f"{minutes} min"

    @staticmethod
    def _format_clock(value: Any) -> str | None:
        """Return a compact local clock time."""

        timestamp = FordTriplogLastJourneyOverviewSensor._parse_datetime(value)
        if timestamp is None:
            return None

        return dt_util.as_local(timestamp).strftime("%H:%M")

    @staticmethod
    def _short_address(value: Any) -> str | None:
        """Return a compact address for dashboard output."""

        if value is None:
            return None

        if isinstance(value, str):
            value = value.strip()
            if not value:
                return None

            parts = [part.strip() for part in value.split(",") if part.strip()]
            return ", ".join(parts[:3]) if parts else value

        if isinstance(value, dict):
            formatted = format_address_short(value)
            return formatted or None

        return str(value)

    @staticmethod
    def _optional_number(value: Any, digits: int = 1) -> float | None:
        """Return a rounded number while preserving missing values."""

        if value is None:
            return None

        try:
            return round(float(value), digits)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _soc_used(start_soc: Any, end_soc: Any) -> float | None:
        """Return used SOC for one trip."""

        try:
            return round(float(start_soc) - float(end_soc), 1)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _soc_added(start_soc: Any, end_soc: Any) -> float | None:
        """Return added SOC for one charging session."""

        try:
            return round(float(end_soc) - float(start_soc), 1)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _consumption(distance_km: Any, energy_kwh: Any) -> float | None:
        """Return consumption in kWh/100 km."""

        try:
            distance = float(distance_km)
            energy = float(energy_kwh)
        except (TypeError, ValueError):
            return None

        if distance <= 0:
            return None

        return round((energy / distance) * 100, 1)

    def _item_start_location(self, item: Any) -> str | None:
        """Return the resolved start location of an item."""

        if getattr(item, "item_type", None) == "trip":
            return (
                getattr(item, "start_location", None)
                or self._short_address(getattr(item, "start_address", None))
            )

        return (
            getattr(item, "location", None)
            or self._short_address(getattr(item, "address", None))
        )

    def _item_end_location(self, item: Any) -> str | None:
        """Return the resolved end location of an item."""

        if getattr(item, "item_type", None) == "trip":
            return (
                getattr(item, "end_location", None)
                or self._short_address(getattr(item, "end_address", None))
            )

        return (
            getattr(item, "location", None)
            or self._short_address(getattr(item, "address", None))
        )

    def _item_location_details(
        self,
        item: Any,
        *,
        endpoint: str | None = None,
    ) -> dict[str, Any]:
        """Return location details for one Journey item."""

        if getattr(item, "item_type", None) == "trip":
            prefix = endpoint or "end"
            return {
                "location": getattr(item, f"{prefix}_location", None)
                or self._short_address(
                    getattr(item, f"{prefix}_address", None)
                ),
                "address": self._short_address(
                    getattr(item, f"{prefix}_address", None)
                ),
                "latitude": getattr(item, f"{prefix}_latitude", None),
                "longitude": getattr(item, f"{prefix}_longitude", None),
                "location_source": getattr(
                    item,
                    f"{prefix}_location_source",
                    None,
                ),
            }

        return {
            "location": getattr(item, "location", None)
            or self._short_address(getattr(item, "address", None)),
            "address": self._short_address(getattr(item, "address", None)),
            "latitude": getattr(item, "latitude", None),
            "longitude": getattr(item, "longitude", None),
            "location_source": getattr(item, "location_source", None),
        }

    def _build_timeline(self, journey) -> tuple[list[dict[str, Any]], int]:
        """Build start, trip, pause, charge and end timeline entries."""

        timeline: list[dict[str, Any]] = []
        total_pause_seconds = 0
        items = list(journey.items)

        # Short gaps directly before or after a charging session are
        # operational buffers (parking, plugging in, unplugging, departure),
        # not separate Journey pauses. Keep the real charging duration
        # unchanged and expose the buffers on the charge timeline entry.
        charge_buffers: dict[int, dict[str, int]] = {}
        charging_buffer_limit_seconds = 180

        for gap_index in range(len(items) - 1):
            current_item = items[gap_index]
            following_item = items[gap_index + 1]
            gap_seconds = self._seconds_between(
                current_item.end_time,
                following_item.start_time,
            )

            if gap_seconds <= 0 or gap_seconds > charging_buffer_limit_seconds:
                continue

            if following_item.item_type == "charge":
                charge_buffers.setdefault(gap_index + 1, {})[
                    "arrival_buffer_seconds"
                ] = gap_seconds
            elif current_item.item_type == "charge":
                charge_buffers.setdefault(gap_index, {})[
                    "departure_buffer_seconds"
                ] = gap_seconds

        first_item = items[0] if items else None
        last_item = items[-1] if items else None

        start_location = (
            self._item_start_location(first_item)
            if first_item is not None
            else self._short_address(journey.start_address)
        )
        end_location = (
            self._item_end_location(last_item)
            if last_item is not None
            else self._short_address(journey.end_address)
        )

        timeline.append(
            {
                "type": "start",
                "time": journey.start_time,
                "time_formatted": self._format_clock(journey.start_time),
                "location": start_location,
                "display_location": start_location,
                "address": self._short_address(journey.start_address),
                "latitude": journey.start_latitude,
                "longitude": journey.start_longitude,
            }
        )

        for index, item in enumerate(items):
            duration_seconds = (
                getattr(item, "duration_seconds", None)
                or self._seconds_between(item.start_time, item.end_time)
            )

            if item.item_type == "trip":
                distance_km = self._optional_number(
                    getattr(item, "distance_km", None),
                    1,
                )
                energy_kwh = self._optional_number(
                    getattr(item, "energy_kwh", None),
                    2,
                )
                start_soc = self._optional_number(
                    getattr(item, "start_soc", None),
                    1,
                )
                end_soc = self._optional_number(
                    getattr(item, "end_soc", None),
                    1,
                )

                entry = {
                    "type": "trip",
                    "id": item.item_id,
                    "start_time": item.start_time,
                    "end_time": item.end_time,
                    "start_time_formatted": self._format_clock(item.start_time),
                    "end_time_formatted": self._format_clock(item.end_time),
                    "duration_seconds": duration_seconds,
                    "duration": format_duration(duration_seconds),
                    "start_location": self._item_start_location(item),
                    "end_location": self._item_end_location(item),
                    "display_start_location": (
                        self._item_start_location(item)
                    ),
                    "display_end_location": (
                        self._item_end_location(item)
                    ),
                    "start_address": self._short_address(
                        getattr(item, "start_address", None)
                    ),
                    "end_address": self._short_address(
                        getattr(item, "end_address", None)
                    ),
                    "start_latitude": getattr(
                        item,
                        "start_latitude",
                        None,
                    ),
                    "start_longitude": getattr(
                        item,
                        "start_longitude",
                        None,
                    ),
                    "end_latitude": getattr(item, "end_latitude", None),
                    "end_longitude": getattr(item, "end_longitude", None),
                    "start_location_source": getattr(
                        item,
                        "start_location_source",
                        None,
                    ),
                    "end_location_source": getattr(
                        item,
                        "end_location_source",
                        None,
                    ),
                    "distance_km": distance_km,
                    "energy_used_kwh": energy_kwh,
                    "start_soc": start_soc,
                    "end_soc": end_soc,
                    "soc_used": self._soc_used(start_soc, end_soc),
                    "consumption_kwh_100km": self._consumption(
                        distance_km,
                        energy_kwh,
                    ),
                }
            else:
                location_details = self._item_location_details(item)
                start_soc = self._optional_number(
                    getattr(item, "start_soc", None),
                    1,
                )
                end_soc = self._optional_number(
                    getattr(item, "end_soc", None),
                    1,
                )
                energy_kwh = self._optional_number(
                    getattr(item, "energy_kwh", None),
                    2,
                )

                buffers = charge_buffers.get(index, {})
                arrival_buffer_seconds = buffers.get(
                    "arrival_buffer_seconds", 0
                )
                departure_buffer_seconds = buffers.get(
                    "departure_buffer_seconds", 0
                )
                total_stop_duration_seconds = (
                    duration_seconds
                    + arrival_buffer_seconds
                    + departure_buffer_seconds
                )

                entry = {
                    "type": "charge",
                    "id": item.item_id,
                    "start_time": item.start_time,
                    "end_time": item.end_time,
                    "start_time_formatted": self._format_clock(item.start_time),
                    "end_time_formatted": self._format_clock(item.end_time),
                    "duration_seconds": duration_seconds,
                    "duration": format_duration(duration_seconds),
                    "arrival_buffer_seconds": arrival_buffer_seconds or None,
                    "arrival_buffer": (
                        format_duration(arrival_buffer_seconds)
                        if arrival_buffer_seconds
                        else None
                    ),
                    "departure_buffer_seconds": (
                        departure_buffer_seconds or None
                    ),
                    "departure_buffer": (
                        format_duration(departure_buffer_seconds)
                        if departure_buffer_seconds
                        else None
                    ),
                    "total_stop_duration_seconds": (
                        total_stop_duration_seconds
                    ),
                    "total_stop_duration": format_duration(
                        total_stop_duration_seconds
                    ),
                    **location_details,
                    "display_location": location_details.get("location"),
                    "start_soc": start_soc,
                    "end_soc": end_soc,
                    "soc_added": self._soc_added(start_soc, end_soc),
                    "energy_charged_kwh": energy_kwh,
                    "energy_billed_kwh": self._optional_number(
                        getattr(item, "energy_billed_kwh", None),
                        2,
                    ),
                    "cost_total": self._optional_number(
                        getattr(item, "cost_total", None),
                        2,
                    ),
                    "energy_cost": self._optional_number(
                        getattr(item, "energy_cost", None),
                        2,
                    ),
                    "energy_price_per_kwh": self._optional_number(
                        getattr(item, "energy_price_per_kwh", None),
                        4,
                    ),
                    "effective_price_per_kwh": self._optional_number(
                        getattr(item, "effective_price_per_kwh", None),
                        4,
                    ),
                    "currency": getattr(item, "currency", None),
                    "cost_source": getattr(item, "cost_source", None),
                }

            timeline.append(
                {
                    key: value
                    for key, value in entry.items()
                    if value is not None
                }
            )

            if index >= len(items) - 1:
                continue

            next_item = items[index + 1]
            pause_seconds = self._seconds_between(
                item.end_time,
                next_item.start_time,
            )

            if pause_seconds <= 0:
                continue

            # Gaps up to three minutes adjacent to a charge were already
            # assigned to that charging entry as arrival/departure buffers.
            if (
                pause_seconds <= charging_buffer_limit_seconds
                and (
                    item.item_type == "charge"
                    or next_item.item_type == "charge"
                )
            ):
                continue

            total_pause_seconds += pause_seconds
            pause_location = self._item_location_details(
                item,
                endpoint="end",
            )

            pause_id = build_pause_id(item.item_id, next_item.item_id)
            override = getattr(journey, "pause_overrides", {}).get(
                pause_id, {}
            )
            if not isinstance(override, dict):
                override = {}

            pause_soc_start = self._optional_number(
                getattr(item, "end_soc", None),
                1,
            )
            pause_soc_end = self._optional_number(
                getattr(next_item, "start_soc", None),
                1,
            )
            pause_soc_delta = None
            battery_energy_change_kwh = None

            if pause_soc_start is not None and pause_soc_end is not None:
                pause_soc_delta = round(
                    pause_soc_end - pause_soc_start,
                    1,
                )

                battery_capacity_kwh = self._optional_number(
                    getattr(journey, "battery_capacity_kwh", None),
                    2,
                )
                if battery_capacity_kwh is not None:
                    battery_energy_change_kwh = round(
                        pause_soc_delta
                        / 100.0
                        * battery_capacity_kwh,
                        2,
                    )

            pause_entry = {
                "type": "pause",
                "id": pause_id,
                "start_time": item.end_time,
                "end_time": next_item.start_time,
                "start_time_formatted": self._format_clock(item.end_time),
                "end_time_formatted": self._format_clock(
                    next_item.start_time
                ),
                "duration_seconds": pause_seconds,
                "duration": format_duration(pause_seconds),
                "after": item.item_type,
                "before": next_item.item_type,
                **pause_location,
                "soc_start": pause_soc_start,
                "soc_end": pause_soc_end,
                "soc_delta": pause_soc_delta,
                "battery_energy_change_kwh": (
                    battery_energy_change_kwh
                ),
                "category": override.get("category"),
                "title": override.get("title"),
                "note": override.get("note"),
                "cost_total": override.get("cost_total"),
                "currency": override.get("currency"),
                "edited": bool(override),
                "updated_at": override.get("updated_at"),
            }

            manual_location = override.get("location")
            if manual_location:
                pause_entry["location"] = manual_location
                pause_entry["display_location"] = manual_location
                pause_entry["location_source"] = "manual"

            timeline.append(
                {
                    key: value
                    for key, value in pause_entry.items()
                    if value is not None
                }
            )

        timeline.append(
            {
                "type": "end",
                "time": journey.end_time,
                "time_formatted": self._format_clock(journey.end_time),
                "location": end_location,
                "display_location": end_location,
                "address": self._short_address(journey.end_address),
                "latitude": journey.end_latitude,
                "longitude": journey.end_longitude,
            }
        )

        allowed_fields = {
            "start": {
                "type",
                "time_formatted",
                "location",
            },
            "trip": {
                "type",
                "start_time_formatted",
                "end_time_formatted",
                "duration",
                "distance_km",
                "start_soc",
                "end_soc",
                "soc_used",
                "energy_used_kwh",
                "consumption_kwh_100km",
                "start_location",
                "end_location",
            },
            "pause": {
                "type",
                "start_time_formatted",
                "duration",
                "title",
                "category",
                "location",
                "note",
                "soc_start",
                "soc_end",
                "soc_delta",
                "battery_energy_change_kwh",
                "cost_total",
                "currency",
                "edited",
            },
            "charge": {
                "type",
                "start_time_formatted",
                "end_time_formatted",
                "arrival_buffer_seconds",
                "arrival_buffer",
                "duration",
                "departure_buffer_seconds",
                "departure_buffer",
                "total_stop_duration_seconds",
                "total_stop_duration",
                "start_soc",
                "end_soc",
                "soc_added",
                "energy_charged_kwh",
                "energy_billed_kwh",
                "cost_total",
                "currency",
                "energy_price_per_kwh",
                "effective_price_per_kwh",
                "cost_source",
                "location",
            },
            "end": {
                "type",
                "time_formatted",
                "location",
            },
        }

        compact_timeline = [
            {
                key: value
                for key, value in entry.items()
                if key in allowed_fields.get(
                    str(entry.get("type") or ""),
                    {"type"},
                )
                and value is not None
            }
            for entry in timeline
        ]

        return compact_timeline, total_pause_seconds

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

        items = list(journey.items)
        first_item = items[0] if items else None
        last_item = items[-1] if items else None

        self._attr_native_value = (
            f"{distance:g} km · "
            f"{self._format_duration_compact(total_duration)}"
        )

        self._attributes = {
            "date": journey.date,
            "distance_km": distance,
            "total_duration": format_duration(total_duration),
            "driving_duration": format_duration(
                journey.driving_duration_seconds
            ),
            "pause_duration": format_duration(pause_seconds),
            "charging_duration": format_duration(
                journey.charging_duration_seconds
            ),
            "energy_used_kwh": journey.energy_used_kwh,
            "energy_charged_kwh": journey.energy_charged_kwh,
            "battery_energy_balance_kwh": (
                journey.battery_energy_balance_kwh
            ),
            "total_energy_flow_kwh": journey.total_energy_flow_kwh,
            "currency": journey.currency,
            "charging_cost_total": journey.charging_cost_total,
            "charging_energy_cost": journey.charging_energy_cost,
            "charging_additional_cost": (
                journey.charging_additional_cost
            ),
            "average_charging_price_per_kwh": (
                journey.average_charging_price_per_kwh
            ),
            "battery_capacity_kwh": journey.battery_capacity_kwh,
            "start_soc": journey.start_soc,
            "end_soc": journey.end_soc,
            "soc_delta": journey.soc_delta,
            "battery_energy_delta_kwh": (
                journey.battery_energy_delta_kwh
            ),
            "soc_used": journey.soc_used,
            "soc_charged": journey.soc_charged,
            "soc_adjustment": journey.soc_adjustment,
            "soc_adjustment_kwh": journey.soc_adjustment_kwh,
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


class FordTriplogJourneyHistorySensor(FordTriplogLastJourneyOverviewSensor):
    """Expose the archived Journey for the selected History date."""

    _attr_has_entity_name = True
    _attr_translation_key = "journey_history"
    _attr_unique_id = "ford_triplog_journey_history"
    _attr_icon = "mdi:map-clock-outline"

    def __init__(self, storage, translations, entry_id: str) -> None:
        super().__init__(storage, translations)
        self.entry_id = entry_id
        self._selected_date = None
        self._journeys = []

    @property
    def _selection_key(self) -> str:
        return f"route_history_selected_date_{self.entry_id}"

    async def async_added_to_hass(self) -> None:
        data = self.hass.data[DOMAIN][self.entry_id]
        data["journey_history_sensor"] = self
        self._selected_date = data.get(self._selection_key)
        await self._async_refresh()

    async def async_will_remove_from_hass(self) -> None:
        data = self.hass.data.get(DOMAIN, {}).get(self.entry_id, {})
        if data.get("journey_history_sensor") is self:
            data.pop("journey_history_sensor", None)

    async def async_set_selected_date(self, selected_date: str) -> None:
        self._selected_date = selected_date
        await self._async_refresh()
        self.async_write_ha_state()

    async def _async_refresh(self) -> None:
        """Load and aggregate all Journeys for the selected History date."""

        if self.storage is None or not self._selected_date:
            self._journey = None
            self._journeys = []
            self._attr_native_value = None
            self._attributes = {}
            return

        all_journeys = await self.storage.get_all_journeys()
        matches = [
            journey
            for journey in all_journeys
            if str(journey.date or "") == self._selected_date
        ]
        matches.sort(
            key=lambda journey: (
                str(journey.start_time or ""),
                str(journey.journey_id or ""),
            )
        )

        self._journeys = matches
        self._attr_native_value = self._selected_date

        if not matches:
            self._journey = None
            self._attributes = {
                "date": self._selected_date,
                "journey_count": 0,
                "journeys": [],
            }
            return

        # Keep the last Journey as the internal reference for compatibility,
        # but all exposed day-level values below are aggregated from matches.
        self._journey = matches[-1]

        def _number(value: Any) -> float:
            try:
                return float(value or 0)
            except (TypeError, ValueError):
                return 0.0

        def _first_non_null(attribute: str):
            for journey in matches:
                value = getattr(journey, attribute, None)
                if value is not None:
                    return value
            return None

        def _last_non_null(attribute: str):
            for journey in reversed(matches):
                value = getattr(journey, attribute, None)
                if value is not None:
                    return value
            return None

        timeline: list[dict[str, Any]] = []
        pause_seconds = 0

        for journey in matches:
            journey_timeline, journey_pause_seconds = self._build_timeline(
                journey
            )
            timeline.extend(journey_timeline)
            pause_seconds += int(journey_pause_seconds or 0)

        distance_km = sum(_number(journey.distance_km) for journey in matches)
        total_duration_seconds = sum(
            int(journey.total_duration_seconds or 0)
            for journey in matches
        )
        driving_duration_seconds = sum(
            int(journey.driving_duration_seconds or 0)
            for journey in matches
        )
        charging_duration_seconds = sum(
            int(journey.charging_duration_seconds or 0)
            for journey in matches
        )

        energy_used_kwh = sum(
            _number(journey.energy_used_kwh)
            for journey in matches
        )
        energy_charged_kwh = sum(
            _number(journey.energy_charged_kwh)
            for journey in matches
        )
        battery_energy_balance_kwh = sum(
            _number(journey.battery_energy_balance_kwh)
            for journey in matches
        )
        total_energy_flow_kwh = sum(
            _number(journey.total_energy_flow_kwh)
            for journey in matches
        )

        charging_cost_total = sum(
            _number(journey.charging_cost_total)
            for journey in matches
        )
        charging_energy_cost = sum(
            _number(journey.charging_energy_cost)
            for journey in matches
        )
        charging_additional_cost = sum(
            _number(journey.charging_additional_cost)
            for journey in matches
        )

        soc_used = sum(
            _number(journey.soc_used)
            for journey in matches
        )
        soc_charged = sum(
            _number(journey.soc_charged)
            for journey in matches
        )
        soc_adjustment = sum(
            _number(journey.soc_adjustment)
            for journey in matches
        )
        soc_adjustment_kwh = sum(
            _number(journey.soc_adjustment_kwh)
            for journey in matches
        )

        start_soc = _first_non_null("start_soc")
        end_soc = _last_non_null("end_soc")

        if start_soc is not None and end_soc is not None:
            try:
                soc_delta = round(float(end_soc) - float(start_soc), 1)
            except (TypeError, ValueError):
                soc_delta = round(
                    sum(_number(journey.soc_delta) for journey in matches),
                    1,
                )
        else:
            soc_delta = round(
                sum(_number(journey.soc_delta) for journey in matches),
                1,
            )

        battery_energy_delta_kwh = sum(
            _number(journey.battery_energy_delta_kwh)
            for journey in matches
        )

        average_consumption = (
            round((energy_used_kwh / distance_km) * 100, 1)
            if distance_km > 0
            else None
        )
        average_charging_price = (
            round(charging_cost_total / energy_charged_kwh, 4)
            if energy_charged_kwh > 0
            else None
        )

        currencies = {
            str(journey.currency).strip().upper()
            for journey in matches
            if getattr(journey, "currency", None)
            and str(journey.currency).strip()
        }
        currency = (
            next(iter(currencies))
            if len(currencies) == 1
            else None
        )

        battery_capacity_kwh = _first_non_null("battery_capacity_kwh")

        self._attributes = {
            "date": self._selected_date,
            "journey_count": len(matches),
            "journey_id": matches[-1].journey_id,
            "distance_km": round(distance_km, 1),
            "total_duration": format_duration(total_duration_seconds),
            "driving_duration": format_duration(driving_duration_seconds),
            "pause_duration": format_duration(pause_seconds),
            "charging_duration": format_duration(charging_duration_seconds),
            "energy_used_kwh": round(energy_used_kwh, 2),
            "energy_charged_kwh": round(energy_charged_kwh, 2),
            "battery_energy_balance_kwh": round(
                battery_energy_balance_kwh,
                2,
            ),
            "total_energy_flow_kwh": round(total_energy_flow_kwh, 2),
            "currency": currency,
            "charging_cost_total": round(charging_cost_total, 2),
            "charging_energy_cost": round(charging_energy_cost, 2),
            "charging_additional_cost": round(
                charging_additional_cost,
                2,
            ),
            "average_charging_price_per_kwh": average_charging_price,
            "battery_capacity_kwh": battery_capacity_kwh,
            "start_soc": start_soc,
            "end_soc": end_soc,
            "soc_delta": soc_delta,
            "battery_energy_delta_kwh": round(
                battery_energy_delta_kwh,
                2,
            ),
            "soc_used": round(soc_used, 1),
            "soc_charged": round(soc_charged, 1),
            "soc_adjustment": round(soc_adjustment, 1),
            "soc_adjustment_kwh": round(soc_adjustment_kwh, 2),
            "average_consumption_kwh_100km": average_consumption,
            "timeline": timeline,
            "journeys": [
                {
                    "journey_id": journey.journey_id,
                    "date": journey.date,
                    "start_time": journey.start_time,
                    "end_time": journey.end_time,
                    "distance_km": journey.distance_km,
                    "trip_count": journey.trip_count,
                    "charge_count": journey.charge_count,
                }
                for journey in matches
            ],
        }

    @property
    def available(self) -> bool:
        return bool(self._selected_date)


class FordTriplogChargingHistorySensor(SensorEntity):
    """Expose archived charging sessions for the selected History date."""

    _attr_has_entity_name = True
    _attr_translation_key = "charging_history"
    _attr_unique_id = "ford_triplog_charging_history"
    _attr_icon = "mdi:ev-station"

    def __init__(
        self,
        charge_manager,
        receipt_storage,
        entry_id: str,
    ) -> None:
        self.charge_manager = charge_manager
        self.receipt_storage = receipt_storage
        self.entry_id = entry_id
        self._selected_date: str | None = None
        self._attr_native_value = None
        self._attributes: dict[str, Any] = {}

    @property
    def _selection_key(self) -> str:
        return f"route_history_selected_date_{self.entry_id}"

    async def async_added_to_hass(self) -> None:
        """Register for direct updates from the shared History date select."""
        data = self.hass.data[DOMAIN][self.entry_id]
        data["charging_history_sensor"] = self
        self._selected_date = data.get(self._selection_key)
        await self._async_refresh()

    async def async_will_remove_from_hass(self) -> None:
        data = self.hass.data.get(DOMAIN, {}).get(self.entry_id, {})
        if data.get("charging_history_sensor") is self:
            data.pop("charging_history_sensor", None)

    async def async_set_selected_date(self, selected_date: str) -> None:
        self._selected_date = selected_date
        await self._async_refresh()
        self.async_write_ha_state()

    @staticmethod
    def _parse_datetime(value: Any) -> datetime | None:
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)
        return parsed

    @classmethod
    def _local_date(cls, value: Any) -> str | None:
        parsed = cls._parse_datetime(value)
        if parsed is None:
            return None
        return dt_util.as_local(parsed).date().isoformat()

    @classmethod
    def _duration_seconds(cls, start: Any, end: Any) -> int | None:
        start_dt = cls._parse_datetime(start)
        end_dt = cls._parse_datetime(end)
        if start_dt is None or end_dt is None:
            return None
        return max(0, int((end_dt - start_dt).total_seconds()))

    @staticmethod
    def _optional_float(value: Any, digits: int = 2) -> float | None:
        if value is None:
            return None
        try:
            return round(float(value), digits)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _display_location(data: dict[str, Any]) -> str | None:
        for key in (
            "charging_site_name",
            "charging_site_brand",
            "charging_site_operator",
            "charging_site_network",
        ):
            value = data.get(key)
            if value and str(value).strip().upper() != "UNKNOWN":
                return str(value).strip()

        address = data.get("start_address")
        if isinstance(address, dict):
            return format_address_short(address) or None
        if address:
            return str(address).strip() or None
        return None

    async def _async_refresh(self) -> None:
        if self.charge_manager is None or not self._selected_date:
            self._attr_native_value = None
            self._attributes = {}
            return

        charges = await self.charge_manager.async_get_charges(
            newest_first=False
        )

        receipts_by_charge: dict[str, list[dict[str, Any]]] = {}
        if self.receipt_storage is not None:
            all_receipts = await self.receipt_storage.async_list()
            for receipt in all_receipts:
                if str(receipt.get("target_type") or "") != "charge":
                    continue
                target_id = str(receipt.get("target_id") or "").strip()
                receipt_id = str(receipt.get("receipt_id") or "").strip()
                if not target_id or not receipt_id:
                    continue

                receipt_path = (
                    f"/api/ford_triplog/receipts/{receipt_id}"
                )
                signed_path = async_sign_path(
                    self.hass,
                    receipt_path,
                    timedelta(hours=24),
                    use_content_user=True,
                )
                receipt_url = signed_path

                receipt_entry = {
                    "receipt_id": receipt_id,
                    "filename": (
                        receipt.get("original_filename")
                        or receipt.get("filename")
                        or receipt_id
                    ),
                    "stored_filename": receipt.get("filename"),
                    "media_type": receipt.get("media_type"),
                    "size_bytes": receipt.get("size_bytes"),
                    "created_at": receipt.get("created_at"),
                    "note": receipt.get("note"),
                    "ocr_status": receipt.get("ocr_status"),
                    "receipt_url": receipt_url,
                }
                receipts_by_charge.setdefault(target_id, []).append(
                    {
                        key: value
                        for key, value in receipt_entry.items()
                        if value is not None
                    }
                )

        selected = []
        for charge in charges:
            data = charge.to_dict()
            charge_date = self._local_date(
                data.get("start_time") or data.get("created")
            )
            if charge_date == self._selected_date:
                selected.append(data)

        selected.sort(
            key=lambda item: (
                str(item.get("start_time") or ""),
                str(item.get("charge_id") or ""),
            )
        )

        charge_entries: list[dict[str, Any]] = []
        total_vehicle_energy = 0.0
        total_billed_energy = 0.0
        total_cost = 0.0
        total_duration_seconds = 0
        currencies: set[str] = set()

        for data in selected:
            duration_seconds = self._duration_seconds(
                data.get("start_time"),
                data.get("end_time"),
            )
            vehicle_energy = self._optional_float(data.get("energy_added_kwh"))
            billed_energy = self._optional_float(data.get("energy_billed_kwh"))
            cost_total = self._optional_float(data.get("cost_total"))
            currency = str(data.get("currency") or "").strip().upper()

            if vehicle_energy is not None:
                total_vehicle_energy += vehicle_energy
            if billed_energy is not None:
                total_billed_energy += billed_energy
            if cost_total is not None:
                total_cost += cost_total
            if duration_seconds is not None:
                total_duration_seconds += duration_seconds
            if currency:
                currencies.add(currency)

            entry = {
                "charge_id": data.get("charge_id"),
                "start_time": data.get("start_time"),
                "end_time": data.get("end_time"),
                "duration_seconds": duration_seconds,
                "duration": (
                    format_duration(duration_seconds)
                    if duration_seconds is not None
                    else None
                ),
                "location": self._display_location(data),
                "start_latitude": data.get("start_latitude"),
                "start_longitude": data.get("start_longitude"),
                "start_soc": data.get("start_soc"),
                "end_soc": data.get("end_soc"),
                "energy_added_kwh": data.get("energy_added_kwh"),
                "energy_billed_kwh": data.get("energy_billed_kwh"),
                "energy_source": data.get("energy_source"),
                "energy_billed_source": data.get("energy_billed_source"),
                "charging_loss_kwh": data.get("charging_loss_kwh"),
                "charging_loss_percent": data.get("charging_loss_percent"),
                "energy_cost": data.get("energy_cost"),
                "session_fee": data.get("session_fee"),
                "time_fee": data.get("time_fee"),
                "blocking_fee": data.get("blocking_fee"),
                "parking_fee": data.get("parking_fee"),
                "other_cost": data.get("other_cost"),
                "cost_total": data.get("cost_total"),
                "currency": data.get("currency"),
                "energy_price_per_kwh": data.get("energy_price_per_kwh"),
                "effective_price_per_kwh": data.get("effective_price_per_kwh"),
                "cost_source": data.get("cost_source"),
                "cost_verified": data.get("cost_verified"),
                "receipt_filename": data.get("receipt_filename"),
                "receipts": receipts_by_charge.get(
                    str(data.get("charge_id") or ""),
                    [],
                ),
                "charging_site_id": data.get("charging_site_id"),
                "charging_site_name": data.get("charging_site_name"),
                "charging_site_brand": data.get("charging_site_brand"),
                "charging_site_operator": data.get("charging_site_operator"),
                "charging_site_network": data.get("charging_site_network"),
                "trip_id": data.get("trip_id"),
                "previous_trip_id": data.get("previous_trip_id"),
                "notes": data.get("notes"),
                "tags": data.get("tags"),
            }
            charge_entries.append(
                {key: value for key, value in entry.items() if value is not None}
            )

        currency = next(iter(currencies)) if len(currencies) == 1 else None

        receipt_count = sum(
            len(entry.get("receipts", []))
            for entry in charge_entries
        )

        self._attr_native_value = self._selected_date
        self._attributes = {
            "date": self._selected_date,
            "charge_count": len(charge_entries),
            "receipt_count": receipt_count,
            "charging_duration_seconds": total_duration_seconds,
            "charging_duration": format_duration(total_duration_seconds),
            "energy_added_kwh": round(total_vehicle_energy, 2),
            "energy_billed_kwh": round(total_billed_energy, 2),
            "cost_total": round(total_cost, 2),
            "currency": currency,
            "charges": charge_entries,
        }

    @property
    def available(self) -> bool:
        return bool(self._selected_date)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return self._attributes

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, "ford_triplog")},
            "name": "Ford Triplog",
            "manufacturer": "Ford",
            "model": "Triplog",
            "sw_version": VERSION,
        }


class FordTriplogLastRouteSensor(SensorEntity):
    """Expose the last stored Route Tracker track as GeoJSON."""

    _attr_has_entity_name = True
    _unrecorded_attributes = frozenset({"geojson"})
    _attr_translation_key = "last_route"
    _attr_unique_id = "ford_triplog_last_route"
    _attr_icon = "mdi:map-marker-path"

    def __init__(
        self,
        coordinator,
        storage: FordTriplogRouteStorage | None,
    ) -> None:
        self.coordinator = coordinator
        self.storage = storage
        self._route: dict[str, Any] | None = None
        self._attr_native_value = None
        self._attributes: dict[str, Any] = {}

    async def async_added_to_hass(self) -> None:
        """Load the latest route and refresh after coordinator updates."""

        self.async_on_remove(
            self.coordinator.async_add_listener(self._handle_update)
        )
        await self._async_refresh()

    def _handle_update(self) -> None:
        """Refresh the route sensor after coordinator activity."""

        self.hass.async_create_task(self._async_refresh_and_write())

    async def _async_refresh_and_write(self) -> None:
        """Refresh and write the current route state."""

        await self._async_refresh()
        self.async_write_ha_state()

    async def _async_refresh(self) -> None:
        """Load the most recently stored route and build GeoJSON."""

        if self.storage is None:
            self._route = None
            self._attr_native_value = None
            self._attributes = {}
            return

        route = await self.storage.async_load_latest_route()
        if not route:
            self._route = None
            self._attr_native_value = None
            self._attributes = {}
            return

        valid_points: list[dict[str, Any]] = []
        coordinates: list[list[float]] = []

        for point in route.get("points", []):
            if not isinstance(point, dict):
                continue
            try:
                latitude = float(point.get("latitude"))
                longitude = float(point.get("longitude"))
            except (TypeError, ValueError):
                continue

            coordinates.append([longitude, latitude])
            valid_points.append(point)

        if not coordinates:
            self._route = route
            self._attr_native_value = None
            self._attributes = {}
            return

        trip_id = str(route.get("trip_id") or "")
        source_type = route.get("source_type")
        start_time = valid_points[0].get("timestamp")
        end_time = valid_points[-1].get("timestamp")

        # Prefer the optional OSRM geometry when a completed route contains
        # a valid match. Raw GPS coordinates always remain the fallback.
        display_coordinates = coordinates
        geometry_source = "raw"
        osrm_distance_km = None
        osrm_confidence = None
        osrm_matched_tracepoints = None
        osrm_unmatched_tracepoints = None

        matched_route = route.get("matched_route")
        if isinstance(matched_route, dict):
            matched_geometry = matched_route.get("geometry")
            matched_coordinates = (
                matched_geometry.get("coordinates")
                if isinstance(matched_geometry, dict)
                and matched_geometry.get("type") == "LineString"
                else None
            )

            if isinstance(matched_coordinates, list) and len(matched_coordinates) >= 2:
                valid_matched_coordinates: list[list[float]] = []

                for coordinate in matched_coordinates:
                    if (
                        not isinstance(coordinate, (list, tuple))
                        or len(coordinate) < 2
                    ):
                        continue

                    try:
                        longitude = float(coordinate[0])
                        latitude = float(coordinate[1])
                    except (TypeError, ValueError):
                        continue

                    valid_matched_coordinates.append(
                        [longitude, latitude]
                    )

                if len(valid_matched_coordinates) >= 2:
                    display_coordinates = valid_matched_coordinates
                    geometry_source = "osrm"

                    try:
                        osrm_distance_km = round(
                            float(matched_route.get("distance_m")) / 1000.0,
                            3,
                        )
                    except (TypeError, ValueError):
                        osrm_distance_km = None

                    osrm_confidence = matched_route.get("confidence")
                    osrm_matched_tracepoints = matched_route.get(
                        "matched_tracepoints"
                    )
                    osrm_unmatched_tracepoints = matched_route.get(
                        "unmatched_tracepoints"
                    )

        geojson = {
            "type": "Feature",
            "properties": {
                "trip_id": trip_id,
                "source_type": source_type,
                "geometry_source": geometry_source,
            },
            "geometry": {
                "type": "LineString",
                "coordinates": display_coordinates,
            },
        }

        self._route = route
        self._attr_native_value = trip_id or len(display_coordinates)

        # Geographic center of the geometry currently exposed to the map.
        center_latitude = (
            sum(coord[1] for coord in display_coordinates)
            / len(display_coordinates)
        )
        center_longitude = (
            sum(coord[0] for coord in display_coordinates)
            / len(display_coordinates)
        )

        self._attributes = {
            "trip_id": trip_id or None,
            "source_type": source_type,
            "geometry_source": geometry_source,
            "point_count": len(display_coordinates),
            "raw_point_count": len(coordinates),
            "start_time": start_time,
            "end_time": end_time,
            "latitude": center_latitude,
            "longitude": center_longitude,
            "osrm_distance_km": osrm_distance_km,
            "osrm_confidence": osrm_confidence,
            "osrm_matched_tracepoints": osrm_matched_tracepoints,
            "osrm_unmatched_tracepoints": osrm_unmatched_tracepoints,
            "geojson": geojson,
        }

    @property
    def available(self) -> bool:
        """Return whether a stored route is available."""

        return self._route is not None and bool(self._attributes)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return route metadata and the map-ready GeoJSON feature."""

        return {
            key: value
            for key, value in self._attributes.items()
            if value is not None
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


class FordTriplogRouteHistorySensor(SensorEntity):
    """Expose all stored routes for the selected historical date."""

    _attr_has_entity_name = True
    _unrecorded_attributes = frozenset({"geojson"})
    _attr_translation_key = "route_history"
    _attr_unique_id = "ford_triplog_route_history"
    _attr_icon = "mdi:map-clock-outline"

    def __init__(
        self,
        coordinator,
        storage: FordTriplogRouteStorage | None,
        entry_id: str,
    ) -> None:
        self.coordinator = coordinator
        self.storage = storage
        self.entry_id = entry_id
        self._selected_date: str | None = None
        self._attr_native_value = None
        self._attributes: dict[str, Any] = {}

    @property
    def _selection_key(self) -> str:
        return f"route_history_selected_date_{self.entry_id}"

    async def async_added_to_hass(self) -> None:
        """Register this sensor for direct updates from the date select."""

        data = self.hass.data[DOMAIN][self.entry_id]
        data["route_history_sensor"] = self

        self._selected_date = data.get(self._selection_key)
        _LOGGER.debug(
            "Route History initial date: %s",
            self._selected_date,
        )
        await self._async_refresh()

    async def async_will_remove_from_hass(self) -> None:
        """Remove the shared sensor reference on unload."""

        data = self.hass.data.get(DOMAIN, {}).get(self.entry_id, {})
        if data.get("route_history_sensor") is self:
            data.pop("route_history_sensor", None)

    async def async_set_selected_date(self, selected_date: str) -> None:
        """Set the selected date and refresh the history immediately."""

        self._selected_date = selected_date
        _LOGGER.debug(
            "Route History direct date update to %s",
            selected_date,
        )
        await self._async_refresh()
        self.async_write_ha_state()

    async def _async_refresh_and_write(self) -> None:
        await self._async_refresh()
        self.async_write_ha_state()

    async def _async_refresh(self) -> None:
        if self.storage is None:
            self._attr_native_value = None
            self._attributes = {}
            return

        selected_date = self._selected_date
        if not selected_date:
            self._attr_native_value = None
            self._attributes = {}
            return

        routes = await self.storage.async_load_routes_for_date(selected_date)
        trip_ids = [
            str(route.get("trip_id"))
            for route in routes
            if route.get("trip_id")
        ]

        collection = await async_build_route_feature_collection(
            self.storage,
            trip_ids,
            journey_date=selected_date,
        )
        properties = collection.get("properties", {})

        _LOGGER.debug(
            "Route History loaded date=%s routes=%s osrm=%s raw=%s missing=%s",
            selected_date,
            properties.get("route_count", 0),
            properties.get("osrm_route_count", 0),
            properties.get("raw_route_count", 0),
            properties.get("missing_route_count", 0),
        )

        coordinates: list[list[float]] = []
        for feature in collection.get("features", []):
            geometry = feature.get("geometry", {})
            if geometry.get("type") != "LineString":
                continue
            for coordinate in geometry.get("coordinates", []):
                if isinstance(coordinate, list) and len(coordinate) >= 2:
                    coordinates.append(coordinate)

        attrs = {
            "date": selected_date,
            "trip_ids": trip_ids,
            "route_count": properties.get("route_count", 0),
            "osrm_route_count": properties.get("osrm_route_count", 0),
            "raw_route_count": properties.get("raw_route_count", 0),
            "missing_route_count": properties.get("missing_route_count", 0),
            "missing_trip_ids": properties.get("missing_trip_ids", []),
            "geojson": collection,
        }

        if coordinates:
            attrs["latitude"] = (
                sum(float(c[1]) for c in coordinates) / len(coordinates)
            )
            attrs["longitude"] = (
                sum(float(c[0]) for c in coordinates) / len(coordinates)
            )

        self._attr_native_value = selected_date
        self._attributes = attrs

    @property
    def available(self) -> bool:
        return bool(self._attributes)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return self._attributes

    @property
    def device_info(self):
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


class FordTriplogTopDaySensor(SensorEntity):
    """Expose the calendar day with the highest total Journey distance."""

    _attr_has_entity_name = True
    _attr_translation_key = "top_day"
    _attr_unique_id = "ford_triplog_top_day"
    _attr_device_class = SensorDeviceClass.DISTANCE
    _attr_native_unit_of_measurement = UnitOfLength.KILOMETERS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1
    _attr_icon = "mdi:calendar-star"

    def __init__(
        self,
        journey_storage: FordTriplogJourneyStorage | None,
        route_storage: FordTriplogRouteStorage | None,
        database,
        read_backend,
        translations: dict[str, Any],
    ) -> None:
        self.journey_storage = journey_storage
        self.route_storage = route_storage
        self.database = database
        self.read_backend = read_backend
        self.translations = translations
        self._attr_native_value = None
        self._attributes: dict[str, Any] = {}
        self._top_date: str | None = None

    async def async_added_to_hass(self) -> None:
        """Load Top Day and refresh it after Journey changes."""

        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_LAST_JOURNEY_UPDATED,
                self._handle_journey_update,
            )
        )
        await self._async_refresh()

    def _handle_journey_update(self, *_args: Any) -> None:
        """Schedule a Top Day refresh after Journey maintenance."""

        self.hass.add_job(self._async_refresh_and_write)

    async def _async_refresh_and_write(self) -> None:
        """Refresh and write Top Day."""

        await self._async_refresh()
        self.async_write_ha_state()

    @staticmethod
    def _optional_number(value: Any, digits: int = 2) -> float:
        try:
            return round(float(value or 0), digits)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _get(item: Any, key: str, default: Any = None) -> Any:
        if isinstance(item, dict):
            return item.get(key, default)
        return getattr(item, key, default)

    @staticmethod
    def _items(journey: Any) -> list[Any]:
        value = FordTriplogTopDaySensor._get(journey, "items", [])
        return list(value or [])

    @staticmethod
    def _compact_location(value: Any) -> str | None:
        if value is None:
            return None

        if isinstance(value, dict):
            road = (
                value.get("road")
                or value.get("pedestrian")
                or value.get("path")
                or value.get("amenity")
                or value.get("name")
            )
            house = value.get("house_number")
            postcode = value.get("postcode")
            city = (
                value.get("city")
                or value.get("town")
                or value.get("village")
                or value.get("municipality")
            )

            street = " ".join(
                str(part).strip()
                for part in (road, house)
                if part
            ).strip()
            postal_city = " ".join(
                str(part).strip()
                for part in (postcode, city)
                if part
            ).strip()

            parts = [
                part
                for part in (street or None, postal_city or None)
                if part
            ]
            if parts:
                return ", ".join(parts)

            value = value.get("display_name") or value.get("display")

        text = str(value or "").strip()
        if not text:
            return None

        parts = [part.strip() for part in text.split(",") if part.strip()]
        if len(parts) <= 3:
            return text

        postcode_index = next(
            (
                index
                for index, part in enumerate(parts)
                if part.isdigit() and 4 <= len(part) <= 5
            ),
            None,
        )

        if postcode_index is not None:
            postcode = parts[postcode_index]
            if len(parts) >= 3 and parts[0].isdigit():
                street = f"{parts[1]} {parts[0]}".strip()
                city = parts[2]
            else:
                street = parts[0]
                city = parts[1] if len(parts) > 1 else None

            postal_city = " ".join(
                part for part in (postcode, city) if part
            )
            return ", ".join(
                part for part in (street, postal_city) if part
            )

        return ", ".join(parts[:3])

    def _journey_start_location(self, journey) -> str | None:
        items = self._items(journey)
        first_item = items[0] if items else None

        if (
            first_item is not None
            and self._get(first_item, "item_type") == "trip"
        ):
            location = self._get(first_item, "start_location")
            compact = self._compact_location(location)
            if compact:
                return compact

            compact = self._compact_location(
                self._get(first_item, "start_address")
            )
            if compact:
                return compact

        return self._compact_location(
            self._get(journey, "start_address")
        )

    def _journey_end_location(self, journey) -> str | None:
        items = self._items(journey)
        last_item = items[-1] if items else None

        if last_item is not None:
            if self._get(last_item, "item_type") == "trip":
                compact = self._compact_location(
                    self._get(last_item, "end_location")
                )
                if compact:
                    return compact

                compact = self._compact_location(
                    self._get(last_item, "end_address")
                )
                if compact:
                    return compact
            else:
                compact = self._compact_location(
                    self._get(last_item, "location")
                )
                if compact:
                    return compact

                compact = self._compact_location(
                    self._get(last_item, "address")
                )
                if compact:
                    return compact

        return self._compact_location(
            self._get(journey, "end_address")
        )

    async def _route_summary(self, date_value: str) -> dict[str, Any]:
        # Routes are not part of the current SQLite mirror yet, so retain
        # the existing route-storage path for this auxiliary dashboard data.
        if self.route_storage is None:
            return {
                "route_available": False,
                "route_count": 0,
                "route_trip_ids": [],
            }

        try:
            routes = await self.route_storage.async_load_routes_for_date(
                date_value
            )
        except (OSError, ValueError):
            routes = []

        trip_ids = [
            str(route.get("trip_id"))
            for route in routes
            if isinstance(route, dict) and route.get("trip_id")
        ]

        return {
            "route_available": bool(routes),
            "route_count": len(routes),
            "route_trip_ids": trip_ids,
        }

    async def _async_refresh(self) -> None:
        """Aggregate Journeys by day and expose the record day."""

        if self.read_backend == "sqlite":
            _LOGGER.debug("Top Day sensor read backend: sqlite")
            if self.database is None:
                _LOGGER.error(
                    "Top Day SQLite read requested but database is unavailable"
                )
                journeys = []
            else:
                journeys = await self.database.load_top_day_journeys()
                _LOGGER.debug(
                    "Top Day sensor SQLite journeys loaded: %d",
                    len(journeys),
                )
        else:
            _LOGGER.debug("Top Day sensor read backend: json")
            journeys = (
                await self.journey_storage.get_all_journeys()
                if self.journey_storage is not None
                else []
            )
            _LOGGER.debug(
                "Top Day sensor JSON journeys loaded: %d",
                len(journeys),
            )

        if not journeys:
            self._attr_native_value = None
            self._attributes = {}
            self._top_date = None
            return

        days: dict[str, dict[str, Any]] = {}

        for journey in journeys:
            date_value = str(
                self._get(journey, "date", "")
            ).strip()
            if not date_value:
                continue

            row = days.setdefault(
                date_value,
                {
                    "date": date_value,
                    "journeys": [],
                    "distance_km": 0.0,
                    "total_duration_seconds": 0,
                    "driving_duration_seconds": 0,
                    "charging_duration_seconds": 0,
                    "journey_count": 0,
                    "trip_count": 0,
                    "charge_count": 0,
                    "energy_used_kwh": 0.0,
                    "energy_charged_kwh": 0.0,
                    "charging_cost_total": 0.0,
                    "journey_ids": [],
                    "trip_ids": [],
                    "charge_ids": [],
                    "currencies": set(),
                },
            )

            row["journeys"].append(journey)
            row["journey_count"] += 1
            row["distance_km"] += self._optional_number(
                self._get(journey, "distance_km"),
                3,
            )
            row["total_duration_seconds"] += int(
                self._get(journey, "total_duration_seconds", 0) or 0
            )
            row["driving_duration_seconds"] += int(
                self._get(journey, "driving_duration_seconds", 0) or 0
            )
            row["charging_duration_seconds"] += int(
                self._get(journey, "charging_duration_seconds", 0) or 0
            )
            row["trip_count"] += int(
                self._get(journey, "trip_count", 0) or 0
            )
            row["charge_count"] += int(
                self._get(journey, "charge_count", 0) or 0
            )
            row["energy_used_kwh"] += self._optional_number(
                self._get(journey, "energy_used_kwh"),
                3,
            )
            row["energy_charged_kwh"] += self._optional_number(
                self._get(journey, "energy_charged_kwh"),
                3,
            )
            row["charging_cost_total"] += self._optional_number(
                self._get(journey, "charging_cost_total"),
                3,
            )

            journey_id = self._get(journey, "journey_id")
            if journey_id:
                row["journey_ids"].append(journey_id)

            row["trip_ids"].extend(
                list(self._get(journey, "trip_ids", []) or [])
            )
            row["charge_ids"].extend(
                list(self._get(journey, "charge_ids", []) or [])
            )

            currency = str(
                self._get(journey, "currency", "")
            ).strip().upper()
            if currency:
                row["currencies"].add(currency)

        if not days:
            self._attr_native_value = None
            self._attributes = {}
            self._top_date = None
            return

        top = max(
            days.values(),
            key=lambda row: (
                row["distance_km"],
                row["driving_duration_seconds"],
            ),
        )

        top_journeys = sorted(
            top["journeys"],
            key=lambda journey: (
                str(self._get(journey, "start_time", "") or ""),
                str(self._get(journey, "journey_id", "") or ""),
            ),
        )

        first_journey = top_journeys[0]
        last_journey = top_journeys[-1]

        distance_km = round(top["distance_km"], 1)
        energy_used_kwh = round(top["energy_used_kwh"], 2)
        energy_charged_kwh = round(top["energy_charged_kwh"], 2)
        charging_cost_total = round(top["charging_cost_total"], 2)

        average_consumption = (
            round((energy_used_kwh / distance_km) * 100, 1)
            if distance_km > 0
            else 0.0
        )

        route_summary = await self._route_summary(top["date"])

        currencies = sorted(top["currencies"])
        currency = currencies[0] if len(currencies) == 1 else None

        self._top_date = top["date"]
        self._attr_native_value = distance_km

        self._attributes = {
            "date": top["date"],
            "distance_km": distance_km,
            "start_time": self._get(first_journey, "start_time"),
            "end_time": self._get(last_journey, "end_time"),
            "start_location": self._journey_start_location(
                first_journey
            ),
            "end_location": self._journey_end_location(
                last_journey
            ),
            "total_duration_seconds": top["total_duration_seconds"],
            "total_duration": format_duration(
                top["total_duration_seconds"]
            ),
            "driving_duration_seconds": top[
                "driving_duration_seconds"
            ],
            "driving_duration": format_duration(
                top["driving_duration_seconds"]
            ),
            "charging_duration_seconds": top[
                "charging_duration_seconds"
            ],
            "charging_duration": format_duration(
                top["charging_duration_seconds"]
            ),
            "journey_count": top["journey_count"],
            "trip_count": top["trip_count"],
            "charge_count": top["charge_count"],
            "energy_used_kwh": energy_used_kwh,
            "energy_charged_kwh": energy_charged_kwh,
            "average_consumption_kwh_100km": average_consumption,
            "charging_cost_total": charging_cost_total,
            "currency": currency,
            "journey_ids": top["journey_ids"],
            "trip_ids": top["trip_ids"],
            "charge_ids": top["charge_ids"],
            **route_summary,
        }

    @property
    def available(self) -> bool:
        return self._top_date is not None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            key: value
            for key, value in self._attributes.items()
            if value is not None
        }

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, "ford_triplog")},
            "name": "Ford Triplog",
            "manufacturer": "Ford",
            "model": "Triplog",
            "sw_version": VERSION,
        }


class FordTriplogTopLocationsSensor(FordTriplogSensorBase):
    """Expose the most frequent trip departures and destinations."""

    _HOME_CODE = "__home__"
    _CLUSTER_RADIUS_M = 50.0

    _attr_translation_key = "top_locations"
    _attr_unique_id = "ford_triplog_top_locations"
    _attr_icon = "mdi:map-marker-multiple-outline"

    def __init__(
        self,
        coordinator,
        history,
        database,
        read_backend,
        translations,
    ) -> None:
        super().__init__(coordinator, history, translations)
        self.database = database
        self.read_backend = read_backend
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

        value = (
            math.sin(delta_lat / 2) ** 2
            + math.cos(lat_1)
            * math.cos(lat_2)
            * math.sin(delta_lon / 2) ** 2
        )

        return earth_radius_m * 2 * math.atan2(
            math.sqrt(value),
            math.sqrt(1 - value),
        )

    def _resolve_zone(
        self,
        latitude: Any,
        longitude: Any,
    ) -> tuple[str, str] | None:
        """Return stable zone key and display label for matching HA zone."""

        try:
            point_latitude = float(latitude)
            point_longitude = float(longitude)
        except (TypeError, ValueError):
            return None

        matching_zone = None
        matching_distance = None

        for state in self.hass.states.async_all("zone"):
            try:
                zone_latitude = float(state.attributes.get("latitude"))
                zone_longitude = float(state.attributes.get("longitude"))
                zone_radius = max(
                    0.0,
                    float(state.attributes.get("radius", 100)),
                )
            except (TypeError, ValueError):
                continue

            distance_m = self._distance_m(
                point_latitude,
                point_longitude,
                zone_latitude,
                zone_longitude,
            )

            if distance_m > zone_radius:
                continue

            if matching_distance is None or distance_m < matching_distance:
                matching_zone = state
                matching_distance = distance_m

        if matching_zone is None:
            return None

        if matching_zone.entity_id == "zone.home":
            return "zone:home", "Home"

        zone_name = str(
            matching_zone.attributes.get("friendly_name")
            or matching_zone.name
            or matching_zone.entity_id.split(".", 1)[-1]
        ).strip()

        if not zone_name:
            return None

        return f"zone:{matching_zone.entity_id}", zone_name

    def _is_home(
        self,
        latitude: Any,
        longitude: Any,
    ) -> bool:
        """Return whether coordinates resolve to zone.home."""

        zone = self._resolve_zone(latitude, longitude)
        return zone is not None and zone[0] == "zone:home"

    @staticmethod
    def _charging_site_label(site: dict[str, Any]) -> str | None:
        """Return the best human-readable charging-site label."""

        for key in ("name", "brand", "operator", "network"):
            value = site.get(key)
            if value is None:
                continue

            label = str(value).strip()
            if (
                label
                and label.casefold()
                not in {
                    "unknown",
                    "unsaved",
                    "none",
                    "null",
                    "n/a",
                    "not available",
                }
            ):
                return label

        return None

    async def _async_resolve_user_charging_site(
        self,
        latitude: Any,
        longitude: Any,
    ) -> tuple[str, str] | None:
        """Resolve the nearest matching custom charging location."""

        try:
            point_latitude = float(latitude)
            point_longitude = float(longitude)
        except (TypeError, ValueError):
            return None

        storage = getattr(
            self.coordinator,
            "user_charging_site_storage",
            None,
        )
        if storage is None:
            return None

        try:
            sites = await storage.async_load()
        except (OSError, ValueError):
            return None

        best_site: dict[str, Any] | None = None
        best_distance: float | None = None

        for site in sites:
            try:
                site_latitude = float(site["latitude"])
                site_longitude = float(site["longitude"])
                radius = float(site["radius"])
            except (KeyError, TypeError, ValueError):
                continue

            distance_m = self._distance_m(
                point_latitude,
                point_longitude,
                site_latitude,
                site_longitude,
            )

            if distance_m > radius:
                continue

            if best_distance is None or distance_m < best_distance:
                best_site = site
                best_distance = distance_m

        if best_site is None:
            return None

        label = self._charging_site_label(best_site)
        if not label:
            return None

        site_id = str(
            best_site.get("site_id")
            or f"{point_latitude:.6f},{point_longitude:.6f}"
        )
        return f"charging:user:{site_id}", label

    async def _async_resolve_osm_charging_site(
        self,
        latitude: Any,
        longitude: Any,
    ) -> tuple[str, str] | None:
        """Resolve the current OSM charging location using coordinator lookup."""

        try:
            point_latitude = float(latitude)
            point_longitude = float(longitude)
        except (TypeError, ValueError):
            return None

        lookup = getattr(
            self.coordinator,
            "charging_site_lookup",
            None,
        )
        if lookup is None:
            return None

        try:
            radius = float(
                getattr(
                    self.coordinator,
                    "charging_site_radius",
                    10,
                )
            )
        except (TypeError, ValueError):
            radius = 10.0

        try:
            site = await self.hass.async_add_executor_job(
                lookup.find,
                point_latitude,
                point_longitude,
                radius,
            )
        except (TypeError, ValueError):
            return None

        if not site:
            return None

        label = self._charging_site_label(site)
        if not label:
            return None

        site_id = str(
            site.get("site_id")
            or f"{point_latitude:.6f},{point_longitude:.6f}"
        )
        return f"charging:osm:{site_id}", label

    async def _async_resolve_known_location(
        self,
        latitude: Any,
        longitude: Any,
    ) -> tuple[str, str] | None:
        """Resolve zone or charging-site location by configured priority."""

        zone = self._resolve_zone(latitude, longitude)
        if zone is not None:
            zone_key, zone_label = zone
            return (
                zone_key,
                self._HOME_CODE
                if zone_key == "zone:home"
                else zone_label,
            )

        user_site = await self._async_resolve_user_charging_site(
            latitude,
            longitude,
        )
        if user_site is not None:
            return user_site

        return await self._async_resolve_osm_charging_site(
            latitude,
            longitude,
        )

    @staticmethod
    def _compact_location(value: Any) -> str | None:
        """Return a stable compact location label from stored address data."""

        if value is None:
            return None

        if isinstance(value, dict):
            road = (
                value.get("road")
                or value.get("pedestrian")
                or value.get("path")
                or value.get("amenity")
                or value.get("name")
            )
            house = value.get("house_number")
            postcode = value.get("postcode")
            city = (
                value.get("city")
                or value.get("town")
                or value.get("village")
                or value.get("municipality")
            )

            street = " ".join(
                str(part).strip()
                for part in (road, house)
                if part
            ).strip()
            postal_city = " ".join(
                str(part).strip()
                for part in (postcode, city)
                if part
            ).strip()

            parts = [
                part
                for part in (street or None, postal_city or None)
                if part
            ]
            if parts:
                return ", ".join(parts)

            value = value.get("display_name") or value.get("display")

        text = str(value or "").strip()
        if not text or text.upper() == "UNKNOWN":
            return None

        parts = [part.strip() for part in text.split(",") if part.strip()]
        if len(parts) <= 2:
            return text

        # Prefer street/POI plus postal code and city when possible.
        postcode_index = next(
            (
                index
                for index, part in enumerate(parts)
                if part.isdigit() and 4 <= len(part) <= 5
            ),
            None,
        )

        if postcode_index is not None:
            postcode = parts[postcode_index]

            if len(parts) >= 3 and parts[0].isdigit():
                street = f"{parts[1]} {parts[0]}".strip()
                city = parts[2]
            else:
                street = parts[0]
                city = parts[1] if len(parts) > 1 else None

            postal_city = " ".join(
                part for part in (postcode, city) if part
            )
            return ", ".join(
                part for part in (street, postal_city) if part
            )

        return ", ".join(parts[:2])

    @staticmethod
    def _label_score(label: str) -> tuple[int, int]:
        """Prefer richer labels, especially addresses containing a house number."""

        has_house_number = bool(re.search(r"\\b\\d+[A-Za-z]?\\b", label))
        return (1 if has_house_number else 0, len(label))

    async def _add_location(
        self,
        rows: dict[str, dict[str, Any]],
        *,
        latitude: Any,
        longitude: Any,
        address: Any,
        distance_km: float,
    ) -> bool:
        """Add one location, clustering primarily by GPS proximity."""

        known_location = await self._async_resolve_known_location(
            latitude,
            longitude,
        )
        if known_location is not None:
            location_key, location_label = known_location
            row = rows.setdefault(
                location_key,
                {
                    "label": location_label,
                    "trips": 0,
                    "distance_km": 0.0,
                    "latitude": None,
                    "longitude": None,
                },
            )
            row["trips"] += 1
            row["distance_km"] += distance_km
            return True

        label = self._compact_location(address)

        try:
            point_latitude = float(latitude)
            point_longitude = float(longitude)
            has_coordinates = True
        except (TypeError, ValueError):
            point_latitude = None
            point_longitude = None
            has_coordinates = False

        if has_coordinates:
            # Match the nearest existing GPS cluster within the configured radius.
            matching_key = None
            matching_distance = None

            for key, row in rows.items():
                if key in (self._HOME_CODE, "zone:home"):

                    continue

                row_latitude = row.get("latitude")
                row_longitude = row.get("longitude")
                if row_latitude is None or row_longitude is None:
                    continue

                distance_m = self._distance_m(
                    point_latitude,
                    point_longitude,
                    float(row_latitude),
                    float(row_longitude),
                )
                if (
                    distance_m <= self._CLUSTER_RADIUS_M
                    and (
                        matching_distance is None
                        or distance_m < matching_distance
                    )
                ):
                    matching_key = key
                    matching_distance = distance_m

            if matching_key is None:
                matching_key = (
                    f"gps:{point_latitude:.6f},{point_longitude:.6f}"
                )
                rows[matching_key] = {
                    "label": label,
                    "trips": 0,
                    "distance_km": 0.0,
                    "latitude": point_latitude,
                    "longitude": point_longitude,
                    "coordinate_count": 0,
                }

            row = rows[matching_key]

            # Keep a running centroid so repeated GPS samples define the cluster
            # better than whichever point happened to be seen first.
            coordinate_count = int(row.get("coordinate_count") or 0)
            if coordinate_count <= 0:
                row["latitude"] = point_latitude
                row["longitude"] = point_longitude
                row["coordinate_count"] = 1
            else:
                new_count = coordinate_count + 1
                row["latitude"] = (
                    float(row["latitude"]) * coordinate_count
                    + point_latitude
                ) / new_count
                row["longitude"] = (
                    float(row["longitude"]) * coordinate_count
                    + point_longitude
                ) / new_count
                row["coordinate_count"] = new_count

            if label:
                current_label = row.get("label")
                if (
                    not current_label
                    or self._label_score(label)
                    > self._label_score(str(current_label))
                ):
                    row["label"] = label

            row["trips"] += 1
            row["distance_km"] += distance_km
            return True

        # GPS unavailable: fall back to the normalized address string.
        if not label:
            return False

        key = f"address:{label.casefold()}"
        row = rows.setdefault(
            key,
            {
                "label": label,
                "trips": 0,
                "distance_km": 0.0,
                "latitude": None,
                "longitude": None,
            },
        )
        row["trips"] += 1
        row["distance_km"] += distance_km
        return True

    def _display_label(self, value: str) -> str:
        """Return stable language-neutral labels for sensor attributes."""

        if value == self._HOME_CODE:
            return "Home"
        return value

    @staticmethod
    def _rank_rows(
        rows: dict[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Return Top 5 rows ordered by trip count and then distance."""

        ranked = [
            row
            for row in rows.values()
            if row.get("label")
        ]
        ranked.sort(
            key=lambda row: (
                int(row.get("trips") or 0),
                float(row.get("distance_km") or 0),
                str(row.get("label") or ""),
            ),
            reverse=True,
        )
        return ranked[:5]

    async def async_update(self) -> None:
        """Aggregate departures and destinations from the selected backend."""

        if self.read_backend == "sqlite":
            if self.database is None:
                _LOGGER.error(
                    "Top Locations SQLite read requested but database is unavailable"
                )
                trips = []
            else:
                trips = await self.database.load_top_location_trips()
        else:
            trips = await self.history.get_all_trips()

        valid_trips = [
            trip
            for trip in trips
            if isinstance(trip, dict)
            and trip.get("include_in_statistics", True)
        ]

        if not valid_trips:
            self._value = None
            self._attributes = {}
            return

        departures: dict[str, dict[str, Any]] = {}
        destinations: dict[str, dict[str, Any]] = {}
        evaluated_departures = 0
        evaluated_destinations = 0

        for trip in valid_trips:
            try:
                distance_km = max(
                    0.0,
                    float(trip.get("distance_km") or 0),
                )
            except (TypeError, ValueError):
                distance_km = 0.0

            if await self._add_location(
                departures,
                latitude=trip.get("start_latitude"),
                longitude=trip.get("start_longitude"),
                address=trip.get("start_address"),
                distance_km=distance_km,
            ):
                evaluated_departures += 1

            if await self._add_location(
                destinations,
                latitude=trip.get("end_latitude"),
                longitude=trip.get("end_longitude"),
                address=trip.get("end_address"),
                distance_km=distance_km,
            ):
                evaluated_destinations += 1

        top_departures = self._rank_rows(departures)
        top_destinations = self._rank_rows(destinations)

        display_departures = [
            {
                "location": self._display_label(str(row["label"])),
                "trips": int(row["trips"]),
                "distance_km": round(float(row["distance_km"]), 1),
            }
            for row in top_departures
        ]
        display_destinations = [
            {
                "location": self._display_label(str(row["label"])),
                "trips": int(row["trips"]),
                "distance_km": round(float(row["distance_km"]), 1),
            }
            for row in top_destinations
        ]

        self._value = len(valid_trips)
        self._attributes = {
            "top_departures": display_departures,
            "top_destinations": display_destinations,
            "trip_count": len(valid_trips),
            "evaluated_departures": evaluated_departures,
            "evaluated_destinations": evaluated_destinations,
        }

    def update_values(
        self,
        statistics,
        last_trip,
        last_charge,
    ):
        """Top Locations is refreshed directly from the trip archive."""

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return self._attributes


class FordTriplogTopRoutesSensor(FordTriplogTopLocationsSensor):
    """Expose the most frequently driven directed routes."""

    _attr_translation_key = "top_routes"
    _attr_unique_id = "ford_triplog_top_routes"
    _attr_icon = "mdi:routes"

    def __init__(
        self,
        coordinator,
        history,
        database,
        read_backend,
        translations,
    ) -> None:
        super().__init__(
            coordinator,
            history,
            database,
            read_backend,
            translations,
        )
        self._attributes: dict[str, Any] = {}

    async def _cluster_endpoint(
        self,
        clusters: dict[str, dict[str, Any]],
        *,
        latitude: Any,
        longitude: Any,
        address: Any,
    ) -> tuple[str, str] | None:
        """Resolve one route endpoint using the Top Locations clustering rules."""

        known_location = await self._async_resolve_known_location(
            latitude,
            longitude,
        )
        if known_location is not None:
            location_key, location_label = known_location
            return (
                location_key,
                "Home"
                if location_key == "zone:home"
                else location_label,
            )

        label = self._compact_location(address)

        try:
            point_latitude = float(latitude)
            point_longitude = float(longitude)
            has_coordinates = True
        except (TypeError, ValueError):
            point_latitude = None
            point_longitude = None
            has_coordinates = False

        if has_coordinates:
            matching_key = None
            matching_distance = None

            for key, row in clusters.items():
                if key in (self._HOME_CODE, "zone:home"):

                    continue

                row_latitude = row.get("latitude")
                row_longitude = row.get("longitude")
                if row_latitude is None or row_longitude is None:
                    continue

                distance_m = self._distance_m(
                    point_latitude,
                    point_longitude,
                    float(row_latitude),
                    float(row_longitude),
                )

                if (
                    distance_m <= self._CLUSTER_RADIUS_M
                    and (
                        matching_distance is None
                        or distance_m < matching_distance
                    )
                ):
                    matching_key = key
                    matching_distance = distance_m

            if matching_key is None:
                matching_key = (
                    f"gps:{point_latitude:.6f},{point_longitude:.6f}"
                )
                clusters[matching_key] = {
                    "label": label,
                    "latitude": point_latitude,
                    "longitude": point_longitude,
                    "coordinate_count": 1,
                }
            else:
                row = clusters[matching_key]
                coordinate_count = int(row.get("coordinate_count") or 1)
                new_count = coordinate_count + 1
                row["latitude"] = (
                    float(row["latitude"]) * coordinate_count
                    + point_latitude
                ) / new_count
                row["longitude"] = (
                    float(row["longitude"]) * coordinate_count
                    + point_longitude
                ) / new_count
                row["coordinate_count"] = new_count

                if label:
                    current_label = row.get("label")
                    if (
                        not current_label
                        or self._label_score(label)
                        > self._label_score(str(current_label))
                    ):
                        row["label"] = label

            row = clusters[matching_key]
            if label:
                current_label = row.get("label")
                if (
                    not current_label
                    or self._label_score(label)
                    > self._label_score(str(current_label))
                ):
                    row["label"] = label

            display_label = row.get("label")
            if not display_label:
                return None

            return matching_key, str(display_label)

        if not label:
            return None

        key = f"address:{label.casefold()}"
        clusters.setdefault(
            key,
            {
                "label": label,
                "latitude": None,
                "longitude": None,
            },
        )
        return key, label

    async def async_update(self) -> None:
        """Aggregate the Top 5 directed routes from archived trips."""

        if self.read_backend == "sqlite":
            if self.database is None:
                _LOGGER.error(
                    "Top Routes SQLite read requested but database is unavailable"
                )
                trips = []
            else:
                trips = await self.database.load_top_route_trips()
        else:
            trips = await self.history.get_all_trips()

        valid_trips = [
            trip
            for trip in trips
            if isinstance(trip, dict)
            and trip.get("include_in_statistics", True)
        ]

        if not valid_trips:
            self._value = None
            self._attributes = {}
            return

        endpoint_clusters: dict[str, dict[str, Any]] = {}
        routes: dict[tuple[str, str], dict[str, Any]] = {}
        evaluated_routes = 0

        for trip in valid_trips:
            start = await self._cluster_endpoint(
                endpoint_clusters,
                latitude=trip.get("start_latitude"),
                longitude=trip.get("start_longitude"),
                address=trip.get("start_address"),
            )
            end = await self._cluster_endpoint(
                endpoint_clusters,
                latitude=trip.get("end_latitude"),
                longitude=trip.get("end_longitude"),
                address=trip.get("end_address"),
            )

            if start is None or end is None:
                continue

            start_key, start_label = start
            end_key, end_label = end

            # Same-location round trips/local loops do not add useful
            # information to the directed Top Routes ranking.
            if start_key == end_key:
                continue

            try:
                distance_km = float(trip.get("distance_km"))
            except (TypeError, ValueError):
                distance_km = None

            consumption = trip.get("consumption_kwh_100km")
            try:
                consumption = float(consumption)
                if consumption <= 0:
                    consumption = None
            except (TypeError, ValueError):
                consumption = None

            route_key = (start_key, end_key)
            row = routes.setdefault(
                route_key,
                {
                    "start": start_label,
                    "destination": end_label,
                    "trips": 0,
                    "distance_sum_km": 0.0,
                    "distance_count": 0,
                    "consumption_sum": 0.0,
                    "consumption_count": 0,
                },
            )

            # Endpoint labels can improve as richer addresses are encountered.
            row["start"] = (
                "Home"
                if start_key == "zone:home"
                else str(endpoint_clusters.get(start_key, {}).get("label") or start_label)
            )
            row["destination"] = (
                "Home"
                if end_key == "zone:home"
                else str(endpoint_clusters.get(end_key, {}).get("label") or end_label)
            )

            row["trips"] += 1

            if distance_km is not None and distance_km >= 0:
                row["distance_sum_km"] += distance_km
                row["distance_count"] += 1

            if (
                consumption is not None
                and distance_km is not None
                and distance_km >= 10.0
            ):
                row["consumption_sum"] += consumption
                row["consumption_count"] += 1

            evaluated_routes += 1

        ranked = sorted(
            routes.values(),
            key=lambda row: (
                int(row.get("trips") or 0),
                int(row.get("distance_count") or 0),
                float(row.get("distance_sum_km") or 0),
            ),
            reverse=True,
        )[:5]

        top_routes = []
        for row in ranked:
            distance_count = int(row["distance_count"])
            consumption_count = int(row["consumption_count"])

            average_distance = (
                round(float(row["distance_sum_km"]) / distance_count, 1)
                if distance_count
                else None
            )
            average_consumption = (
                round(float(row["consumption_sum"]) / consumption_count, 1)
                if consumption_count
                else None
            )

            top_routes.append(
                {
                    "start": row["start"],
                    "destination": row["destination"],
                    "trips": int(row["trips"]),
                    "average_distance_km": average_distance,
                    "average_consumption_kwh_100km": average_consumption,
                    "consumption_trip_count": consumption_count,
                }
            )

        self._value = len(valid_trips)
        self._attributes = {
            "top_routes": top_routes,
            "trip_count": len(valid_trips),
            "evaluated_routes": evaluated_routes,
        }

    def update_values(
        self,
        statistics,
        last_trip,
        last_charge,
    ):
        """Top Routes is refreshed directly from the trip archive."""

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return self._attributes


class FordTriplogTopChargingSensor(FordTriplogSensorBase):
    """Expose compact Top Charging statistics."""

    _HOME_CODE = "__home__"
    _UNKNOWN_CODE = "__unknown__"

    _attr_translation_key = "top_charging"
    _attr_unique_id = "ford_triplog_top_charging"
    _attr_icon = "mdi:ev-station"

    def __init__(
        self,
        coordinator,
        history,
        database,
        read_backend,
        translations,
    ) -> None:
        super().__init__(coordinator, history, translations)
        self.database = database
        self.read_backend = read_backend
        self._attributes: dict[str, Any] = {}

    @staticmethod
    def _number(value: Any, digits: int = 2) -> float:
        try:
            return round(float(value or 0), digits)
        except (TypeError, ValueError):
            return 0.0

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

        value = (
            math.sin(delta_lat / 2) ** 2
            + math.cos(lat_1)
            * math.cos(lat_2)
            * math.sin(delta_lon / 2) ** 2
        )

        return earth_radius_m * 2 * math.atan2(
            math.sqrt(value),
            math.sqrt(1 - value),
        )

    def _resolve_zone_name(
        self,
        charge: dict[str, Any],
    ) -> str | None:
        """Return the closest matching Home Assistant zone."""

        latitude = (
            charge.get("start_latitude")
            if charge.get("start_latitude") is not None
            else charge.get("end_latitude")
        )
        longitude = (
            charge.get("start_longitude")
            if charge.get("start_longitude") is not None
            else charge.get("end_longitude")
        )

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
                radius = max(0.0, float(zone_radius))
            except (TypeError, ValueError):
                continue

            if distance > radius:
                continue

            zone_name = str(
                zone_state.attributes.get(
                    "friendly_name",
                    zone_state.name,
                )
            ).strip()

            if not zone_name:
                continue

            if matching_zone is None or distance < matching_zone[0]:
                matching_zone = (distance, zone_name)

        return matching_zone[1] if matching_zone else None

    def _is_home_zone(
        self,
        charge: dict[str, Any],
    ) -> bool:
        """Return whether the charge coordinates are inside zone.home."""

        home_zone = self.hass.states.get("zone.home")
        if home_zone is None:
            return False

        coordinates = self._charge_coordinates(charge)
        if coordinates is None:
            return False

        try:
            distance = self._distance_m(
                coordinates[0],
                coordinates[1],
                float(home_zone.attributes.get("latitude")),
                float(home_zone.attributes.get("longitude")),
            )
            radius = max(
                0.0,
                float(home_zone.attributes.get("radius", 100)),
            )
        except (TypeError, ValueError):
            return False

        return distance <= radius

    def _display_special_label(self, value: str) -> str:
        """Translate language-neutral special Top Charging labels."""

        if value == self._HOME_CODE:
            return self.translations.get("charging_site_home", "Home")
        if value == self._UNKNOWN_CODE:
            return self.translations.get("unknown", "Unknown")
        return value

    @staticmethod
    def _compact_address(value: Any) -> str | None:
        """Return street/POI, postal code and city for dashboard output."""

        if value is None:
            return None

        if isinstance(value, dict):
            road = (
                value.get("road")
                or value.get("pedestrian")
                or value.get("path")
                or value.get("amenity")
                or value.get("name")
            )
            house = value.get("house_number")
            postcode = value.get("postcode")
            city = (
                value.get("city")
                or value.get("town")
                or value.get("village")
                or value.get("municipality")
            )

            street = " ".join(
                str(part).strip()
                for part in (road, house)
                if part
            ).strip()

            postal_city = " ".join(
                str(part).strip()
                for part in (postcode, city)
                if part
            ).strip()

            parts = [
                part
                for part in (
                    street or None,
                    postal_city or None,
                )
                if part
            ]
            if parts:
                return ", ".join(parts)

            value = (
                value.get("display_name")
                or value.get("display")
            )

        text = str(value or "").strip()
        if not text:
            return None

        parts = [part.strip() for part in text.split(",") if part.strip()]
        if len(parts) <= 3:
            return text

        postcode_index = next(
            (
                index
                for index, part in enumerate(parts)
                if part.isdigit() and 4 <= len(part) <= 5
            ),
            None,
        )

        if postcode_index is not None:
            postcode = parts[postcode_index]

            # OSM often returns "house number, street, city, ... postcode".
            if len(parts) >= 3 and parts[0].isdigit():
                street = f"{parts[1]} {parts[0]}".strip()
                city = parts[2]
            else:
                street = parts[0]
                city = parts[1] if len(parts) > 1 else None

            postal_city = " ".join(
                part for part in (postcode, city) if part
            )
            return ", ".join(
                part for part in (street, postal_city) if part
            )

        return ", ".join(parts[:3])

    @staticmethod
    def _charge_coordinates(
        charge: dict[str, Any],
    ) -> tuple[float, float] | None:
        """Return end coordinates first, then start coordinates."""

        for latitude_key, longitude_key in (
            ("end_latitude", "end_longitude"),
            ("start_latitude", "start_longitude"),
        ):
            latitude = charge.get(latitude_key)
            longitude = charge.get(longitude_key)

            if latitude is None or longitude is None:
                continue

            try:
                return float(latitude), float(longitude)
            except (TypeError, ValueError):
                continue

        return None

    async def _async_match_current_user_site(
        self,
        charge: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Re-match one historic charge against current user sites."""

        coordinates = self._charge_coordinates(charge)
        if coordinates is None:
            return None

        storage = getattr(
            self.coordinator,
            "user_charging_site_storage",
            None,
        )
        if storage is None:
            return None

        try:
            sites = await storage.async_load()
        except (OSError, ValueError):
            return None

        best_site: dict[str, Any] | None = None
        best_distance: float | None = None

        for site in sites:
            try:
                distance = self._distance_m(
                    coordinates[0],
                    coordinates[1],
                    float(site["latitude"]),
                    float(site["longitude"]),
                )
                radius = float(site["radius"])
            except (KeyError, TypeError, ValueError):
                continue

            if distance > radius:
                continue

            if best_distance is None or distance < best_distance:
                best_site = site
                best_distance = distance

        if best_site is None:
            return None

        return {
            "source": "user",
            "site_id": best_site.get("site_id"),
            "name": best_site.get("name"),
            "brand": best_site.get("brand"),
            "operator": best_site.get("operator"),
            "network": best_site.get("network"),
            "distance_m": (
                round(best_distance, 1)
                if best_distance is not None
                else None
            ),
        }

    async def _async_match_current_osm_site(
        self,
        charge: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Re-match one historic charge against the current OSM database."""

        coordinates = self._charge_coordinates(charge)
        if coordinates is None:
            return None

        lookup = getattr(
            self.coordinator,
            "charging_site_lookup",
            None,
        )
        if lookup is None:
            return None

        radius = float(
            getattr(
                self.coordinator,
                "charging_site_radius",
                10,
            )
        )

        try:
            site = await self.hass.async_add_executor_job(
                lookup.find,
                coordinates[0],
                coordinates[1],
                radius,
            )
        except (TypeError, ValueError):
            return None

        if not site:
            return None

        return {
            "source": "osm",
            "site_id": site.get("site_id"),
            "name": site.get("name"),
            "brand": site.get("brand"),
            "operator": site.get("operator"),
            "network": site.get("network"),
            "distance_m": site.get("distance_m"),
        }

    @staticmethod
    def _provider_from_site(
        site: dict[str, Any] | None,
    ) -> str | None:
        """Return the best provider label from a current site match."""

        if not site:
            return None

        for key in ("brand", "operator", "network"):
            value = site.get(key)
            if (
                value
                and str(value).strip()
                and str(value).strip().upper() != "UNKNOWN"
            ):
                return str(value).strip()

        return None

    @staticmethod
    def _location_from_site(
        site: dict[str, Any] | None,
    ) -> str | None:
        """Return the best location label from a current site match."""

        if not site:
            return None

        for key in ("name", "brand", "operator", "network"):
            value = site.get(key)
            if (
                value
                and str(value).strip()
                and str(value).strip().upper() != "UNKNOWN"
            ):
                return str(value).strip()

        return None

    def _charge_provider(self, charge: dict[str, Any]) -> str:
        """Return the best available charging provider label."""

        zone_name = self._resolve_zone_name(charge)
        cost_source = str(charge.get("cost_source") or "").strip().lower()

        # Classification stays language-neutral. Home tariff is definitive;
        # otherwise use the stable Home Assistant entity_id zone.home.
        if cost_source == "home_tariff" or self._is_home_zone(charge):
            return self._HOME_CODE

        for key in (
            "charging_site_brand",
            "charging_site_operator",
            "charging_site_network",
            "provider",
            "charging_provider",
            "operator",
            "network",
            "tariff_provider",
        ):
            value = charge.get(key)
            if (
                value
                and str(value).strip()
                and str(value).strip().upper() != "UNKNOWN"
            ):
                return str(value).strip()

        if zone_name:
            return zone_name

        return self._UNKNOWN_CODE

    def _charge_location(self, charge: dict[str, Any]) -> str:
        """Return the best available compact charging location."""

        zone_name = self._resolve_zone_name(charge)
        if zone_name:
            return zone_name

        for key in (
            "charging_site_name",
            "location",
            "charging_location",
            "site_name",
            "station_name",
            "display_location",
        ):
            value = charge.get(key)
            if (
                value
                and str(value).strip()
                and str(value).strip().upper() != "UNKNOWN"
            ):
                return str(value).strip()

        address = charge.get("start_address") or charge.get("address")
        compact = self._compact_address(address)
        if compact:
            return compact

        for key in (
            "charging_site_brand",
            "charging_site_operator",
            "charging_site_network",
        ):
            value = charge.get(key)
            if (
                value
                and str(value).strip()
                and str(value).strip().upper() != "UNKNOWN"
            ):
                return str(value).strip()

        return self._UNKNOWN_CODE

    @classmethod
    def _energy_kwh(cls, charge: dict[str, Any]) -> float:
        for key in (
            "energy_added_kwh",
            "energy_kwh",
            "charged_energy_kwh",
            "energy_charged_kwh",
        ):
            if charge.get(key) is not None:
                return cls._number(charge.get(key), 3)

        return 0.0

    @classmethod
    def _total_cost(cls, charge: dict[str, Any]) -> float:
        for key in (
            "total_cost",
            "cost_total",
            "charging_cost",
            "cost",
        ):
            if charge.get(key) is not None:
                return cls._number(charge.get(key), 2)

        return 0.0

    @classmethod
    def _price_per_kwh(cls, charge: dict[str, Any]) -> float:
        for key in (
            "energy_price_per_kwh",
            "effective_price_per_kwh",
            "price_per_kwh",
            "cost_per_kwh",
            "tariff_per_kwh",
        ):
            if charge.get(key) is not None:
                return cls._number(charge.get(key), 4)

        energy = cls._energy_kwh(charge)
        cost = cls._total_cost(charge)
        return round(cost / energy, 4) if energy > 0 else 0.0

    @staticmethod
    def _charge_id(charge: dict[str, Any]) -> Any:
        return (
            charge.get("charge_id")
            or charge.get("id")
            or charge.get("session_id")
        )

    async def async_added_to_hass(self) -> None:
        """Register the existing coordinator listener and load Top Charging."""

        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_CHARGE_DATA_UPDATED,
                self._handle_charge_data_updated,
            )
        )

    def _handle_charge_data_updated(self) -> None:
        """Schedule an immediate Top Charging archive refresh."""

        self.hass.async_create_task(
            self._async_handle_charge_data_updated()
        )

    async def _async_handle_charge_data_updated(self) -> None:
        """Reload charge archive and publish the new Top Charging state."""

        await self._async_refresh_top_charging()
        self.async_write_ha_state()

    async def async_update(self) -> None:
        """Refresh Top Charging directly from the charging archive."""

        await self._async_refresh_top_charging()

    async def _async_refresh_top_charging(self) -> None:
        """Aggregate archived charging sessions."""

        if self.read_backend == "sqlite":
            if self.database is None:
                _LOGGER.error(
                    "Top Charging SQLite read requested but database is unavailable"
                )
                charges = []
            else:
                charges = await self.database.load_top_charging_charges()
        else:
            charges = await self.history.get_all_charges()

        valid_charges = [
            charge
            for charge in charges
            if charge.get("include_in_statistics", True)
        ]

        if not valid_charges:
            self._value = None
            self._attributes = {}
            return

        providers: dict[str, dict[str, Any]] = {}
        locations: dict[str, dict[str, Any]] = {}
        largest: dict[str, Any] | None = None
        largest_energy = -1.0
        unknown_provider_sessions = 0
        unknown_provider_energy = 0.0
        unknown_provider_cost = 0.0

        for charge in valid_charges:
            zone_name = self._resolve_zone_name(charge)
            cost_source = str(
                charge.get("cost_source") or ""
            ).strip().lower()

            current_site = None

            # Home remains the highest-priority classification, but the
            # classification is independent of the configured UI language.
            is_home = (
                cost_source == "home_tariff"
                or self._is_home_zone(charge)
            )

            if is_home:
                provider = self._HOME_CODE
                location = self._HOME_CODE
            else:
                # Current user-defined sites have priority over current OSM,
                # matching ChargingLocationResolver semantics.
                current_site = await self._async_match_current_user_site(
                    charge
                )

                if current_site is None:
                    current_site = await self._async_match_current_osm_site(
                        charge
                    )

                provider = (
                    self._provider_from_site(current_site)
                    or self._charge_provider(charge)
                )
                location = (
                    self._location_from_site(current_site)
                    or self._charge_location(charge)
                )

            energy = self._energy_kwh(charge)
            cost = self._total_cost(charge)

            if provider == self._UNKNOWN_CODE:
                unknown_provider_sessions += 1
                unknown_provider_energy += energy
                unknown_provider_cost += cost

            provider_row = providers.setdefault(
                provider,
                {
                    "provider": provider,
                    "sessions": 0,
                    "energy_kwh": 0.0,
                    "total_cost": 0.0,
                },
            )
            provider_row["sessions"] += 1
            provider_row["energy_kwh"] += energy
            provider_row["total_cost"] += cost

            location_row = locations.setdefault(
                location,
                {
                    "location": location,
                    "provider": provider,
                    "sessions": 0,
                    "energy_kwh": 0.0,
                    "total_cost": 0.0,
                },
            )
            if (
                location_row.get("provider") == self._UNKNOWN_CODE
                and provider != self._UNKNOWN_CODE
            ):
                location_row["provider"] = provider

            location_row["sessions"] += 1
            location_row["energy_kwh"] += energy
            location_row["total_cost"] += cost

            if energy > largest_energy:
                largest_energy = energy
                largest = {
                    "charge_id": self._charge_id(charge),
                    "provider": provider,
                    "location": location,
                    "location_source": (
                        current_site.get("source")
                        if current_site is not None
                        else ("home" if is_home else "historic")
                    ),
                    "start_time": charge.get("start_time"),
                    "end_time": charge.get("end_time"),
                    "energy_kwh": round(energy, 2),
                    "price_per_kwh": self._price_per_kwh(charge),
                    "total_cost": round(cost, 2),
                    "currency": charge.get("currency"),
                }

        provider_rows = []
        for row in providers.values():
            energy = row["energy_kwh"]
            cost = row["total_cost"]
            provider_rows.append(
                {
                    "provider": row["provider"],
                    "sessions": row["sessions"],
                    "energy_kwh": round(energy, 2),
                    "total_cost": round(cost, 2),
                    "avg_price_per_kwh": (
                        round(cost / energy, 4)
                        if energy > 0
                        else 0.0
                    ),
                }
            )

        provider_rows = [
            row
            for row in provider_rows
            if row["provider"] != self._UNKNOWN_CODE
        ]

        provider_rows.sort(
            key=lambda row: (
                row["sessions"],
                row["energy_kwh"],
            ),
            reverse=True,
        )

        location_rows = []
        for row in locations.values():
            energy = row["energy_kwh"]
            cost = row["total_cost"]
            location_rows.append(
                {
                    "location": row["location"],
                    "provider": row["provider"],
                    "sessions": row["sessions"],
                    "energy_kwh": round(energy, 2),
                    "total_cost": round(cost, 2),
                }
            )

        location_rows.sort(
            key=lambda row: (
                row["sessions"],
                row["energy_kwh"],
            ),
            reverse=True,
        )

        top_providers = provider_rows[:5]
        top_locations = location_rows[:5]

        display_top_providers = [
            {
                **row,
                "provider": self._display_special_label(
                    str(row.get("provider") or "")
                ),
            }
            for row in top_providers
        ]
        display_top_locations = [
            {
                **row,
                "location": self._display_special_label(
                    str(row.get("location") or "")
                ),
                "provider": self._display_special_label(
                    str(row.get("provider") or "")
                ),
            }
            for row in top_locations
        ]
        display_largest = (
            {
                **largest,
                "provider": self._display_special_label(
                    str(largest.get("provider") or "")
                ),
                "location": self._display_special_label(
                    str(largest.get("location") or "")
                ),
            }
            if largest is not None
            else None
        )

        self._value = (
            display_top_providers[0]["provider"]
            if display_top_providers
            else None
        )
        self._attributes = {
            "top_providers": display_top_providers,
            "top_locations": display_top_locations,
            "largest_session": display_largest,
            "session_count": len(valid_charges),
            "unknown_provider_sessions": unknown_provider_sessions,
            "unknown_provider_energy_kwh": round(
                unknown_provider_energy,
                2,
            ),
            "unknown_provider_total_cost": round(
                unknown_provider_cost,
                2,
            ),
        }

    def update_values(
        self,
        statistics,
        last_trip,
        last_charge,
    ):
        """Top Charging is refreshed from the charging archive."""

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return self._attributes


class FordTriplogTopJourneySensor(SensorEntity):
    """Expose the longest archived completed Journey."""

    _attr_has_entity_name = True
    _attr_translation_key = "top_journey"
    _attr_unique_id = "ford_triplog_top_journey"
    _attr_device_class = SensorDeviceClass.DISTANCE
    _attr_native_unit_of_measurement = UnitOfLength.KILOMETERS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1
    _attr_icon = "mdi:trophy-variant-outline"

    def __init__(
        self,
        storage: FordTriplogJourneyStorage | None,
        database,
        read_backend,
        translations: dict[str, str],
    ) -> None:
        self.storage = storage
        self.database = database
        self.read_backend = read_backend
        self.translations = translations
        self._journey = None
        self._attr_native_value = None
        self._attributes: dict[str, Any] = {}

    async def async_added_to_hass(self) -> None:
        """Load the record and refresh it when Journey data changes."""

        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_LAST_JOURNEY_UPDATED,
                self._handle_journey_update,
            )
        )
        await self._async_refresh()

    def _handle_journey_update(self, *_args: Any) -> None:
        """Schedule a refresh after Journey data changes."""

        self.hass.add_job(self._async_refresh_and_write)

    async def _async_refresh_and_write(self) -> None:
        """Refresh Top Journey and write the entity state."""

        await self._async_refresh()
        self.async_write_ha_state()

    @staticmethod
    def _short_address(value: Any) -> str | None:
        """Return a compact display address."""

        if value is None:
            return None

        if isinstance(value, dict):
            return format_address_short(value) or None

        text = str(value).strip()
        if not text:
            return None

        parts = [part.strip() for part in text.split(",") if part.strip()]
        if len(parts) <= 3:
            return text

        postal_index = next(
            (
                index
                for index, part in enumerate(parts)
                if any(char.isdigit() for char in part)
                and 3 <= len(part) <= 12
            ),
            None,
        )

        if postal_index is not None and postal_index > 0:
            street_or_poi = parts[0]
            city = parts[1] if len(parts) > 1 else None
            postal = parts[postal_index]

            compact = [street_or_poi]
            if postal:
                compact.append(postal)
            if city and city != postal:
                compact.append(city)

            return ", ".join(compact)

        return ", ".join(parts[:3])

    @staticmethod
    def _optional_number(
        value: Any,
        digits: int = 1,
    ) -> float | None:
        """Return a rounded optional number."""

        if value is None:
            return None

        try:
            return round(float(value), digits)
        except (TypeError, ValueError):
            return None

    async def _async_refresh(self) -> None:
        """Find and expose the longest archived Journey."""

        if self.read_backend == "sqlite":
            if self.database is None:
                _LOGGER.error(
                    "Top Journey SQLite read requested but database is unavailable"
                )
                journey = None
            else:
                journey = await self.database.load_top_journey()
        else:
            if self.storage is None:
                journey = None
            else:
                journeys = await self.storage.get_all_journeys()

                def journey_distance(item) -> float:
                    try:
                        return float(item.distance_km or 0)
                    except (TypeError, ValueError):
                        return 0.0

                journey = (
                    max(journeys, key=journey_distance)
                    if journeys
                    else None
                )

        if journey is None:
            self._journey = None
            self._attr_native_value = None
            self._attributes = {}
            return

        if isinstance(journey, dict):
            def get_value(key: str, default: Any = None) -> Any:
                return journey.get(key, default)

            items = journey.get("items") or []
            distance_km = self._optional_number(
                get_value("distance_km"),
                1,
            ) or 0.0
            journey_id = get_value("journey_id")
            date = get_value("date")
            start_time = get_value("start_time")
            end_time = get_value("end_time")
            start_address = get_value("start_address")
            end_address = get_value("end_address")
            trip_count = get_value("trip_count")
            charge_count = get_value("charge_count")
            total_duration_seconds = int(
                get_value("total_duration_seconds", 0) or 0
            )
            driving_duration_seconds = int(
                get_value("driving_duration_seconds", 0) or 0
            )
            charging_duration_seconds = int(
                get_value("charging_duration_seconds", 0) or 0
            )
            energy_used_kwh = get_value("energy_used_kwh")
            energy_charged_kwh = get_value("energy_charged_kwh")
            average_consumption = get_value(
                "average_consumption_kwh_100km"
            )
            charging_cost_total = get_value("charging_cost_total")
            average_charging_price = get_value(
                "average_charging_price_per_kwh"
            )
            currency = get_value("currency")
        else:
            items = list(journey.items)
            distance_km = round(
                float(journey.distance_km or 0),
                1,
            )
            journey_id = journey.journey_id
            date = journey.date
            start_time = journey.start_time
            end_time = journey.end_time
            start_address = journey.start_address
            end_address = journey.end_address
            trip_count = journey.trip_count
            charge_count = journey.charge_count
            total_duration_seconds = int(
                journey.total_duration_seconds or 0
            )
            driving_duration_seconds = int(
                journey.driving_duration_seconds or 0
            )
            charging_duration_seconds = int(
                journey.charging_duration_seconds or 0
            )
            energy_used_kwh = journey.energy_used_kwh
            energy_charged_kwh = journey.energy_charged_kwh
            average_consumption = journey.average_consumption_kwh_100km
            charging_cost_total = journey.charging_cost_total
            average_charging_price = journey.average_charging_price_per_kwh
            currency = journey.currency

        if distance_km <= 0:
            self._journey = None
            self._attr_native_value = None
            self._attributes = {}
            return

        first_item = items[0] if items else None
        last_item = items[-1] if items else None

        def item_value(item: Any, key: str) -> Any:
            if isinstance(item, dict):
                return item.get(key)
            return getattr(item, key, None)

        start_location = (
            item_value(first_item, "start_location")
            if item_value(first_item, "type") == "trip"
            or item_value(first_item, "item_type") == "trip"
            else None
        ) or self._short_address(start_address)

        if (
            last_item is not None
            and (
                item_value(last_item, "type") == "trip"
                or item_value(last_item, "item_type") == "trip"
            )
        ):
            end_location = (
                item_value(last_item, "end_location")
                or self._short_address(
                    item_value(last_item, "end_address")
                )
                or self._short_address(end_address)
            )
        elif last_item is not None:
            end_location = (
                item_value(last_item, "location")
                or self._short_address(
                    item_value(last_item, "address")
                )
                or self._short_address(end_address)
            )
        else:
            end_location = self._short_address(end_address)

        self._journey = journey
        self._attr_native_value = distance_km

        attributes = {
            "journey_id": journey_id,
            "date": date,
            "distance_km": distance_km,
            "start_time": start_time,
            "end_time": end_time,
            "start_location": start_location,
            "end_location": end_location,
            "total_duration_seconds": total_duration_seconds,
            "total_duration": format_duration(
                total_duration_seconds
            ),
            "driving_duration_seconds": driving_duration_seconds,
            "driving_duration": format_duration(
                driving_duration_seconds
            ),
            "charging_duration_seconds": charging_duration_seconds,
            "charging_duration": format_duration(
                charging_duration_seconds
            ),
            "trip_count": trip_count,
            "charge_count": charge_count,
            "energy_used_kwh": self._optional_number(
                energy_used_kwh,
                2,
            ),
            "energy_charged_kwh": self._optional_number(
                energy_charged_kwh,
                2,
            ),
            "average_consumption_kwh_100km": self._optional_number(
                average_consumption,
                1,
            ),
            "charging_cost_total": self._optional_number(
                charging_cost_total,
                2,
            ),
            "average_charging_price_per_kwh": self._optional_number(
                average_charging_price,
                4,
            ),
            "currency": currency,
        }

        self._attributes = {
            key: value
            for key, value in attributes.items()
            if value is not None
        }

    @property
    def available(self) -> bool:
        """Return whether Top Journey data is available."""

        return self._journey is not None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return dashboard-ready Top Journey details."""

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


class FordTriplogTopTripSensor(FordTriplogSensorBase):
    """Expose the longest recorded trip as one compact statistics sensor."""

    _attr_translation_key = "top_trip"
    _attr_unique_id = "ford_triplog_top_trip"
    _attr_device_class = SensorDeviceClass.DISTANCE
    _attr_native_unit_of_measurement = UnitOfLength.KILOMETERS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1
    _attr_icon = "mdi:trophy-outline"

    def __init__(
        self,
        coordinator,
        history,
        database,
        read_backend,
        translations,
    ) -> None:
        super().__init__(coordinator, history, translations)
        self.database = database
        self.read_backend = read_backend
        self._top_trip: dict[str, Any] | None = None
        self._statistics_initialized = False

    async def async_update(self) -> None:
        """Load Top Trip from the selected backend."""

        if self.read_backend == "sqlite":
            if self.database is None:
                _LOGGER.error(
                    "Top Trip SQLite read requested but database is unavailable"
                )
                self._top_trip = None
            else:
                self._top_trip = await self.database.load_top_trip()
        else:
            statistics, _, _ = await self.history.get_sensor_data()
            top_trip = statistics.get("top_trip") if statistics else None
            self._top_trip = (
                top_trip if isinstance(top_trip, dict) else None
            )

        if not self._top_trip:
            self._value = None
            return

        try:
            self._value = round(float(self._top_trip.get("distance_km")), 1)
        except (TypeError, ValueError):
            self._value = None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return dashboard-ready details of the longest trip."""

        if not self._top_trip:
            return {}

        trip = self._top_trip
        duration_seconds = int(trip.get("duration_seconds") or 0)

        start_address = format_address_short(trip.get("start_address"))
        end_address = format_address_short(trip.get("end_address"))

        attributes = {
            "trip_id": trip.get("trip_id"),
            "distance_km": trip.get("distance_km"),
            "duration_seconds": duration_seconds,
            "duration": format_duration(duration_seconds),
            "start_time": trip.get("start_time"),
            "end_time": trip.get("end_time"),
            "start_location": start_address,
            "end_location": end_address,
            "energy_used_kwh": trip.get("energy_used_kwh"),
            "consumption_kwh_100km": trip.get(
                "consumption_kwh_100km"
            ),
        }

        return {
            key: value
            for key, value in attributes.items()
            if value is not None
        }


class FordTriplogTripCountSensor(FordTriplogSensorBase):
    _attr_translation_key = "trip_count"
    _attr_unique_id = "ford_triplog_trip_count"
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_icon = ICON_TRIP_COUNT

    def __init__(
        self,
        coordinator,
        history,
        translations,
        read_backend,
    ) -> None:
        super().__init__(coordinator, history, translations)
        self.read_backend = read_backend

    def update_values(self, statistics, last_trip, last_charge):
        self._value = statistics.get("trip_count", 0)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose the active read backend for diagnostics."""

        return {
            "read_backend": self.read_backend,
        }


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

        value = (
            math.sin(delta_lat / 2) ** 2
            + math.cos(lat_1)
            * math.cos(lat_2)
            * math.sin(delta_lon / 2) ** 2
        )

        return earth_radius_m * 2 * math.atan2(
            math.sqrt(value),
            math.sqrt(1 - value),
        )

    def _resolve_zone_name(
        self,
        latitude: Any,
        longitude: Any,
    ) -> str | None:
        """Return the closest matching Home Assistant zone."""

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
                radius = max(0.0, float(zone_radius))
            except (TypeError, ValueError):
                continue

            if distance > radius:
                continue

            zone_name = str(
                zone_state.attributes.get(
                    "friendly_name",
                    zone_state.name,
                )
            ).strip()

            if not zone_name:
                continue

            if matching_zone is None or distance < matching_zone[0]:
                matching_zone = (distance, zone_name)

        return matching_zone[1] if matching_zone else None

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
        latitude = last_charge.get("start_latitude")
        longitude = last_charge.get("start_longitude")
        zone_name = self._resolve_zone_name(latitude, longitude)

        charging_location = (
            last_charge.get("charging_site_name")
            or last_charge.get("charging_site_brand")
            or last_charge.get("charging_site_operator")
            or last_charge.get("charging_site_network")
            or address
        )

        display_location = (
            zone_name
            or charging_location
            or address
            or self.translations["unknown"]
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
            "energy_billed_kwh": last_charge.get(
                "energy_billed_kwh"
            ),
            "energy_billed_source": last_charge.get(
                "energy_billed_source"
            ),
            "charging_loss_kwh": last_charge.get(
                "charging_loss_kwh"
            ),
            "charging_loss_percent": last_charge.get(
                "charging_loss_percent"
            ),
            "energy_cost": last_charge.get("energy_cost"),
            "session_fee": last_charge.get("session_fee"),
            "time_fee": last_charge.get("time_fee"),
            "blocking_fee": last_charge.get("blocking_fee"),
            "parking_fee": last_charge.get("parking_fee"),
            "other_cost": last_charge.get("other_cost"),
            "cost_total": last_charge.get("cost_total"),
            "currency": last_charge.get("currency"),
            "energy_price_per_kwh": last_charge.get(
                "energy_price_per_kwh"
            ),
            "effective_price_per_kwh": last_charge.get(
                "effective_price_per_kwh"
            ),
            "cost_source": last_charge.get("cost_source"),
            "cost_verified": last_charge.get("cost_verified"),
            "receipt_filename": last_charge.get(
                "receipt_filename"
            ),
            "display_location": display_location,
            "zone_name": zone_name,
            "charging_location": charging_location,
            "address": address,
            "latitude": latitude,
            "longitude": longitude,
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