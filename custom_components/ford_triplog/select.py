"""
Ford Triplog

Home Assistant select platform.

Version: 2.0.2
Phase: 5 - Unified Route/Journey/Charging History date selection / Translation Fix

Changes:
- Adds a Route History Date select entity.
- Lists only local calendar dates that contain completed stored routes.
- Selects the newest available route date by default.
- Keeps the selected date in the integration runtime data.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    VERSION,
    SIGNAL_LAST_JOURNEY_UPDATED,
    SIGNAL_CHARGE_DATA_UPDATED,
)
from .route_storage import FordTriplogRouteStorage


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities,
) -> None:
    """Set up Route History date selection."""

    data = hass.data[DOMAIN][entry.entry_id]
    route_storage = data.get("route_storage")
    journey_storage = data.get("journey_storage")
    charge_manager = data.get("charge_manager")

    async_add_entities(
        [
            FordTriplogRouteHistoryDateSelect(
                route_storage,
                journey_storage,
                charge_manager,
                entry.entry_id,
            )
        ]
    )


class FordTriplogRouteHistoryDateSelect(SelectEntity):
    """Select one local calendar date from stored routes."""

    _attr_has_entity_name = True
    _attr_translation_key = "route_history_date"
    _attr_unique_id = "ford_triplog_route_history_date"
    _attr_icon = "mdi:calendar-search"
    _attr_should_poll = False

    def __init__(
        self,
        storage: FordTriplogRouteStorage | None,
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
        return f"route_history_selected_date_{self.entry_id}"

    @property
    def options(self) -> list[str]:
        """Return available route-history dates."""
        return self._options

    @property
    def current_option(self) -> str | None:
        """Return the currently selected route-history date."""
        return self._current_option

    async def async_added_to_hass(self) -> None:
        """Load available dates and keep them synchronized with History data."""
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

        await self._async_refresh_options()
        self.async_write_ha_state()

        if self._current_option:
            data = self.hass.data[DOMAIN][self.entry_id]
            for sensor_key in (
                "route_history_sensor",
                "journey_history_sensor",
                "charging_history_sensor",
            ):
                sensor = data.get(sensor_key)
                if sensor is not None:
                    await sensor.async_set_selected_date(
                        self._current_option
                    )

    def _handle_history_data_updated(self, *_args: Any) -> None:
        """Refresh available History dates after Journey or Charge changes."""

        self.hass.async_create_task(
            self._async_refresh_options_and_write()
        )

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

    async def _async_refresh_options(self) -> None:
        """Build one date list from Route, Journey and Charge archives."""

        dates: set[str] = set()

        if self.storage is not None:
            routes = await self.storage.async_list_routes()
            for route in routes:
                timestamp = self.storage._route_timestamp(route)
                if timestamp is None:
                    continue
                if timestamp.tzinfo is None:
                    timestamp = timestamp.replace(tzinfo=dt_util.UTC)
                dates.add(dt_util.as_local(timestamp).date().isoformat())

        if self.journey_storage is not None:
            journeys = await self.journey_storage.get_all_journeys()
            for journey in journeys:
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

        if self.charge_manager is not None:
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

    async def async_select_option(self, option: str) -> None:
        """Select a route-history date."""
        if option not in self._options:
            raise ValueError(f"Invalid route history date: {option}")

        self._current_option = option
        self.hass.data[DOMAIN][self.entry_id][self._selection_key] = option

        self.async_write_ha_state()

        data = self.hass.data[DOMAIN][self.entry_id]
        for sensor_key in (
            "route_history_sensor",
            "journey_history_sensor",
            "charging_history_sensor",
        ):
            sensor = data.get(sensor_key)
            if sensor is not None:
                await sensor.async_set_selected_date(option)

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, "ford_triplog")},
            "name": "Ford Triplog",
            "manufacturer": "Ford",
            "model": "Triplog",
            "sw_version": VERSION,
        }
