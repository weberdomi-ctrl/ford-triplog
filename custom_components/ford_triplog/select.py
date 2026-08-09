"""
Ford Triplog

Home Assistant select platform.

Version: 2.0.1-dev
Phase: 3 - Historical route date selection (Fix 05)

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
from homeassistant.util import dt as dt_util

from .const import DOMAIN, VERSION
from .route_storage import FordTriplogRouteStorage


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities,
) -> None:
    """Set up Route History date selection."""

    data = hass.data[DOMAIN][entry.entry_id]
    route_storage = data.get("route_storage")

    async_add_entities(
        [
            FordTriplogRouteHistoryDateSelect(
                route_storage,
                entry.entry_id,
            )
        ]
    )


class FordTriplogRouteHistoryDateSelect(SelectEntity):
    """Select one local calendar date from stored routes."""

    _attr_has_entity_name = True
    _attr_name = "Route History Date"
    _attr_unique_id = "ford_triplog_route_history_date"
    _attr_icon = "mdi:calendar-search"
    _attr_should_poll = False

    def __init__(
        self,
        storage: FordTriplogRouteStorage | None,
        entry_id: str,
    ) -> None:
        self.storage = storage
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
        """Load available dates and initialize the shared History sensor."""
        await super().async_added_to_hass()
        await self._async_refresh_options()
        self.async_write_ha_state()

        if self._current_option:
            sensor = self.hass.data[DOMAIN][self.entry_id].get(
                "route_history_sensor"
            )
            if sensor is not None:
                await sensor.async_set_selected_date(self._current_option)

    async def _async_refresh_options(self) -> None:
        if self.storage is None:
            self._options = []
            self._current_option = None
            return

        routes = await self.storage.async_list_routes()
        dates: set[str] = set()

        for route in routes:
            timestamp = self.storage._route_timestamp(route)
            if timestamp is None:
                continue
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=dt_util.UTC)
            dates.add(dt_util.as_local(timestamp).date().isoformat())

        self._options = sorted(dates, reverse=True)

        data = self.hass.data[DOMAIN][self.entry_id]
        selected = data.get(self._selection_key)

        # Only choose the newest date when there is no valid selection yet.
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

        sensor = self.hass.data[DOMAIN][self.entry_id].get(
            "route_history_sensor"
        )
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
