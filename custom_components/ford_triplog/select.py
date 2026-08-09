"""
Ford Triplog

Home Assistant select platform.

Version: 2.0.1-dev
Phase: 3 - Historical route date selection

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
from homeassistant.helpers.dispatcher import async_dispatcher_send
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

    def __init__(
        self,
        storage: FordTriplogRouteStorage | None,
        entry_id: str,
    ) -> None:
        self.storage = storage
        self.entry_id = entry_id
        self._attr_options = []
        self._attr_current_option = None

    @property
    def _selection_key(self) -> str:
        return f"route_history_selected_date_{self.entry_id}"

    async def async_added_to_hass(self) -> None:
        await self._async_refresh_options()

    async def _async_refresh_options(self) -> None:
        if self.storage is None:
            self._attr_options = []
            self._attr_current_option = None
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

        options = sorted(dates, reverse=True)
        self._attr_options = options

        data = self.hass.data[DOMAIN][self.entry_id]
        selected = data.get(self._selection_key)

        if selected not in options:
            selected = options[0] if options else None
            data[self._selection_key] = selected

        self._attr_current_option = selected

    async def async_select_option(self, option: str) -> None:
        if option not in self._attr_options:
            raise ValueError(f"Invalid route history date: {option}")

        self._attr_current_option = option
        self.hass.data[DOMAIN][self.entry_id][self._selection_key] = option
        self.async_write_ha_state()

        async_dispatcher_send(
            self.hass,
            f"{DOMAIN}_route_history_date_changed_{self.entry_id}",
        )

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, "ford_triplog")},
            "name": "Ford Triplog",
            "manufacturer": "Ford",
            "model": "Triplog",
            "sw_version": VERSION,
        }
