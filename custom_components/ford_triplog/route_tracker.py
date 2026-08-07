"""Ford Triplog independent Route Tracker."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import Event, HomeAssistant, State
from homeassistant.helpers.event import async_track_state_change_event

from .const import (
    CONF_ROUTE_GEOCODED_ENTITY,
    CONF_ROUTE_LATITUDE_ENTITY,
    CONF_ROUTE_LONGITUDE_ENTITY,
    CONF_ROUTE_SOURCE_TYPE,
    CONF_ROUTE_TRACKER_ENABLED,
    ROUTE_SOURCE_ABRP,
    ROUTE_SOURCE_HA_GEOCODED,
)
from .route_storage import FordTriplogRouteStorage

_LOGGER = logging.getLogger(__name__)


class FordTriplogRouteTracker:
    """Record normalized GPS points for the current Trip ID."""

    def __init__(
        self,
        hass: HomeAssistant,
        storage: FordTriplogRouteStorage,
        config: dict[str, Any],
    ) -> None:
        self.hass = hass
        self.storage = storage
        self.config = config

        self.enabled = bool(
            config.get(CONF_ROUTE_TRACKER_ENABLED, False)
        )
        self.source_type = str(
            config.get(
                CONF_ROUTE_SOURCE_TYPE,
                ROUTE_SOURCE_ABRP,
            )
            or ROUTE_SOURCE_ABRP
        )

        self.latitude_entity = config.get(CONF_ROUTE_LATITUDE_ENTITY)
        self.longitude_entity = config.get(CONF_ROUTE_LONGITUDE_ENTITY)
        self.geocoded_entity = config.get(CONF_ROUTE_GEOCODED_ENTITY)

        self.active_trip_id: str | None = None
        self.points: list[dict[str, Any]] = []
        self._remove_listener = None
        self._last_coordinate: tuple[float, float] | None = None

    async def async_setup(self) -> None:
        """Set up route storage and source listeners."""

        await self.storage.async_setup()

        if not self.enabled:
            _LOGGER.info("Route Tracker disabled")
            return

        entities = self._source_entities()
        if not entities:
            _LOGGER.warning(
                "Route Tracker enabled but no source entities are configured"
            )
            return

        self._remove_listener = async_track_state_change_event(
            self.hass,
            entities,
            self._source_changed,
        )

        _LOGGER.info(
            "Route Tracker ready: source=%s entities=%s",
            self.source_type,
            ", ".join(entities),
        )

    async def async_shutdown(self) -> None:
        """Remove Route Tracker listeners."""

        if self._remove_listener is not None:
            self._remove_listener()
            self._remove_listener = None

    def _source_entities(self) -> list[str]:
        """Return configured source entities."""

        if self.source_type == ROUTE_SOURCE_HA_GEOCODED:
            return [
                entity_id
                for entity_id in (self.geocoded_entity,)
                if entity_id
            ]

        return [
            entity_id
            for entity_id in (
                self.latitude_entity,
                self.longitude_entity,
            )
            if entity_id
        ]

    async def async_start(self, trip_id: str) -> None:
        """Start recording points for one Trip ID."""

        if not self.enabled:
            return

        if self.active_trip_id is not None:
            if self.active_trip_id == trip_id:
                return
            await self.async_stop()

        self.active_trip_id = str(trip_id)
        self.points = []
        self._last_coordinate = None

        await self._capture_current_point()

        _LOGGER.info(
            "Route Tracker started for trip %s",
            self.active_trip_id,
        )

    async def async_stop(self) -> None:
        """Save and close the active route."""

        trip_id = self.active_trip_id
        if trip_id is None:
            return

        await self._capture_current_point()

        points = list(self.points)
        self.active_trip_id = None
        self.points = []
        self._last_coordinate = None

        if not points:
            _LOGGER.warning(
                "Route Tracker stopped for trip %s without GPS points",
                trip_id,
            )
            return

        await self.storage.async_save_route(
            trip_id=trip_id,
            source_type=self.source_type,
            points=points,
        )

        _LOGGER.info(
            "Route Tracker saved %s GPS points for trip %s",
            len(points),
            trip_id,
        )

    async def _source_changed(self, event: Event) -> None:
        """Capture one normalized point when the source updates."""

        if self.active_trip_id is None:
            return

        await self._capture_current_point(
            event.data.get("new_state")
        )

    async def _capture_current_point(
        self,
        changed_state: State | None = None,
    ) -> None:
        """Capture one point if valid and different from the previous one."""

        coordinates = self._read_coordinates(changed_state)
        if coordinates is None:
            return

        latitude, longitude, timestamp = coordinates
        coordinate_key = (latitude, longitude)

        if coordinate_key == self._last_coordinate:
            return

        self.points.append(
            {
                "timestamp": timestamp,
                "latitude": latitude,
                "longitude": longitude,
            }
        )
        self._last_coordinate = coordinate_key

    def _read_coordinates(
        self,
        changed_state: State | None = None,
    ) -> tuple[float, float, str] | None:
        """Return normalized coordinates from the configured source."""

        if self.source_type == ROUTE_SOURCE_HA_GEOCODED:
            state = (
                changed_state
                if changed_state is not None
                and changed_state.entity_id == self.geocoded_entity
                else self.hass.states.get(self.geocoded_entity)
                if self.geocoded_entity
                else None
            )

            if state is None:
                return None

            location = state.attributes.get("location")
            if (
                not isinstance(location, (list, tuple))
                or len(location) < 2
            ):
                return None

            try:
                latitude = float(location[0])
                longitude = float(location[1])
            except (TypeError, ValueError):
                return None

            return (
                latitude,
                longitude,
                state.last_updated.isoformat(),
            )

        latitude_state = (
            self.hass.states.get(self.latitude_entity)
            if self.latitude_entity
            else None
        )
        longitude_state = (
            self.hass.states.get(self.longitude_entity)
            if self.longitude_entity
            else None
        )

        if latitude_state is None or longitude_state is None:
            return None

        try:
            latitude = float(latitude_state.state)
            longitude = float(longitude_state.state)
        except (TypeError, ValueError):
            return None

        timestamp = max(
            latitude_state.last_updated,
            longitude_state.last_updated,
        ).isoformat()

        return latitude, longitude, timestamp
