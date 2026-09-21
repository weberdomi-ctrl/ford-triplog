"""Ford Triplog Home Assistant select platform."""

from __future__ import annotations

from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    VERSION,
    SIGNAL_LAST_JOURNEY_UPDATED,
    SIGNAL_CHARGE_DATA_UPDATED,
    SIGNAL_VEHICLE_CONTEXT_UPDATED,
    SIGNAL_VEHICLE_LIST_UPDATED,
)
from .vehicle_context import (
    VehicleRuntimeProxy,
    get_selected_vehicle_id,
    set_selected_vehicle_id,
    vehicle_option_map,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities,
) -> None:
    """Set up shared Ford Triplog selectors."""

    data = hass.data[DOMAIN][entry.entry_id]
    try:
        vehicle_id = int(data.get("vehicle_id") or 1)
    except (TypeError, ValueError):
        vehicle_id = 1

    # One shared Ford Triplog device/dashboard entity set is owned by vehicle 1.
    # Additional ConfigEntries only provide vehicle runtimes/data sources.
    if vehicle_id != 1:
        return

    route_storage = VehicleRuntimeProxy(
        hass,
        "route_storage",
        entry.entry_id,
    )
    journey_storage = VehicleRuntimeProxy(
        hass,
        "journey_storage",
        entry.entry_id,
    )
    charge_manager = VehicleRuntimeProxy(
        hass,
        "charge_manager",
        entry.entry_id,
    )

    async_add_entities(
        [
            FordTriplogVehicleContextSelect(entry.entry_id),
            FordTriplogRouteHistoryDateSelect(
                route_storage,
                journey_storage,
                charge_manager,
                entry.entry_id,
            ),
        ]
    )


class FordTriplogVehicleContextSelect(SelectEntity):
    """Select the vehicle shown by the shared Ford Triplog dashboard entities."""

    _attr_has_entity_name = True
    _attr_translation_key = "vehicle_context"
    _attr_unique_id = "ford_triplog_vehicle_context"
    _attr_icon = "mdi:car-multiple"
    _attr_should_poll = False

    def __init__(self, entry_id: str) -> None:
        self.entry_id = entry_id

    def _options_map(self) -> dict[str, int]:
        return vehicle_option_map(self.hass)

    @property
    def options(self) -> list[str]:
        """Return loaded vehicles as selectable labels."""

        return list(self._options_map())

    @property
    def current_option(self) -> str | None:
        """Return the label of the current shared vehicle context."""

        selected = get_selected_vehicle_id(self.hass, fallback=1)
        if selected is None:
            return None

        for label, vehicle_id in self._options_map().items():
            if int(vehicle_id) == int(selected):
                return label
        return None

    async def async_added_to_hass(self) -> None:
        """Keep state synchronized with the options-flow vehicle context."""

        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_VEHICLE_CONTEXT_UPDATED,
                self._handle_context_update,
            )
        )
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_VEHICLE_LIST_UPDATED,
                self._handle_context_update,
            )
        )

    @callback
    def _handle_context_update(self, *_args: Any) -> None:
        self.async_write_ha_state()

    async def async_select_option(self, option: str) -> None:
        """Switch the shared dashboard/UI vehicle context."""

        options = self._options_map()
        if option not in options:
            raise ValueError(f"Invalid Ford Triplog vehicle: {option}")

        set_selected_vehicle_id(self.hass, int(options[option]))
        self.async_write_ha_state()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        selected = get_selected_vehicle_id(self.hass, fallback=1)
        return {
            "vehicle_id": selected,
            "vehicle_count": len(self._options_map()),
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


class FordTriplogRouteHistoryDateSelect(SelectEntity):
    """Select one local calendar date for the currently selected vehicle."""

    _attr_has_entity_name = True
    _attr_translation_key = "route_history_date"
    _attr_unique_id = "ford_triplog_route_history_date"
    _attr_icon = "mdi:calendar-search"
    _attr_should_poll = False

    def __init__(
        self,
        storage,
        journey_storage,
        charge_manager,
        entry_id: str,
    ) -> None:
        self.storage = storage
        self.journey_storage = journey_storage
        self.charge_manager = charge_manager
        self.entry_id = entry_id
        self._options: list[str] = []
        self._current_option: str | None = None

    @property
    def _selection_key(self) -> str:
        vehicle_id = get_selected_vehicle_id(self.hass, fallback=1) or 1
        return f"route_history_selected_date_vehicle_{int(vehicle_id)}"

    @property
    def options(self) -> list[str]:
        """Return available history dates for the selected vehicle."""
        return self._options

    @property
    def current_option(self) -> str | None:
        """Return the currently selected history date."""
        return self._current_option

    async def async_added_to_hass(self) -> None:
        """Load dates and keep them synchronized with history and vehicle context."""
        await super().async_added_to_hass()

        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_LAST_JOURNEY_UPDATED,
                self._handle_history_data_updated,
            )
        )
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_CHARGE_DATA_UPDATED,
                self._handle_history_data_updated,
            )
        )
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_VEHICLE_CONTEXT_UPDATED,
                self._handle_vehicle_context_updated,
            )
        )

        await self._async_refresh_options()
        self.async_write_ha_state()
        await self._async_apply_selection()

    @callback
    def _handle_history_data_updated(self, *_args: Any) -> None:
        """Refresh available History dates after Journey or Charge changes."""

        self.hass.create_task(self._async_refresh_options_and_write())

    @callback
    def _handle_vehicle_context_updated(self, *_args: Any) -> None:
        """Refresh date options and all History cards after a vehicle switch."""

        self.hass.create_task(self._async_refresh_context_and_apply())

    async def _async_refresh_context_and_apply(self) -> None:
        await self._async_refresh_options()
        self.async_write_ha_state()
        await self._async_apply_selection()

    async def _async_refresh_options_and_write(self) -> None:
        """Refresh date options and publish the select state."""

        previous_options = tuple(self._options)
        previous_option = self._current_option

        await self._async_refresh_options()

        if (
            tuple(self._options) != previous_options
            or self._current_option != previous_option
        ):
            self.async_write_ha_state()
            await self._async_apply_selection()

    async def _async_refresh_options(self) -> None:
        """Build one date list from Route, Journey and Charge archives."""

        dates: set[str] = set()

        routes = await self.storage.async_list_routes()
        for route in routes:
            timestamp = self.storage._route_timestamp(route)
            if timestamp is None:
                continue
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=dt_util.UTC)
            dates.add(dt_util.as_local(timestamp).date().isoformat())

        journeys = await self.journey_storage.get_all_journeys()
        for journey in journeys:
            item_date_found = False
            for item in list(getattr(journey, "items", []) or []):
                value = getattr(item, "start_time", None)
                if not value:
                    continue
                timestamp = dt_util.parse_datetime(str(value))
                if timestamp is None:
                    continue
                if timestamp.tzinfo is None:
                    timestamp = timestamp.replace(
                        tzinfo=dt_util.DEFAULT_TIME_ZONE
                    )
                dates.add(dt_util.as_local(timestamp).date().isoformat())
                item_date_found = True

            if item_date_found:
                continue

            if journey.date:
                dates.add(str(journey.date))
                continue
            if not journey.start_time:
                continue
            timestamp = dt_util.parse_datetime(str(journey.start_time))
            if timestamp is not None:
                if timestamp.tzinfo is None:
                    timestamp = timestamp.replace(
                        tzinfo=dt_util.DEFAULT_TIME_ZONE
                    )
                dates.add(dt_util.as_local(timestamp).date().isoformat())

        charges = await self.charge_manager.async_get_charges(
            newest_first=False
        )
        for charge in charges:
            value = charge.start_time or charge.created
            if not value:
                continue
            timestamp = dt_util.parse_datetime(str(value))
            if timestamp is None:
                continue
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(
                    tzinfo=dt_util.DEFAULT_TIME_ZONE
                )
            dates.add(dt_util.as_local(timestamp).date().isoformat())

        self._options = sorted(dates, reverse=True)

        data = self.hass.data[DOMAIN][self.entry_id]
        selected = data.get(self._selection_key)

        if selected not in self._options:
            selected = self._options[0] if self._options else None
            data[self._selection_key] = selected

        self._current_option = selected

    async def _async_apply_selection(self) -> None:
        """Apply the current date to all shared History sensors."""

        data = self.hass.data[DOMAIN][self.entry_id]
        for sensor_key in (
            "route_history_sensor",
            "journey_history_sensor",
            "charging_history_sensor",
        ):
            sensor = data.get(sensor_key)
            if sensor is not None:
                await sensor.async_set_selected_date(self._current_option)

    async def async_select_option(self, option: str) -> None:
        """Select a history date for the active vehicle."""
        if option not in self._options:
            raise ValueError(f"Invalid route history date: {option}")

        self._current_option = option
        self.hass.data[DOMAIN][self.entry_id][self._selection_key] = option

        self.async_write_ha_state()
        await self._async_apply_selection()

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, "ford_triplog")},
            "name": "Ford Triplog",
            "manufacturer": "Ford",
            "model": "Triplog",
            "sw_version": VERSION,
        }
