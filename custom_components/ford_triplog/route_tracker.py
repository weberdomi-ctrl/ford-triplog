"""
Ford Triplog

Route Tracker

Version: 2.0.0-dev
Phase: Route Tracker Phase 1
Build: Fix 05 - Trip GPS endpoints

Changes:
- Debounces separate ABRP latitude/longitude entity updates.
- Reads both ABRP coordinates only after the update pair has settled.
- Rejects ABRP coordinate pairs whose timestamps differ by more than 2 seconds.
- Rejects stale initial/final coordinates older than 120 seconds.
- Keeps the Home Assistant Companion Geocoded Location source unchanged.
- Uses the normal Trip tracker GPS as authoritative route start/end points.
- Pauses capture during Smart Trip without discarding collected ABRP points.
- Keeps ABRP debounce/synchronization from Fix 04 unchanged.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any

from homeassistant.core import Event, HomeAssistant, State
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.util import dt as dt_util

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

ABRP_DEBOUNCE_SECONDS = 0.75
ABRP_MAX_PAIR_DELTA_SECONDS = 2.0
ROUTE_MAX_EDGE_POINT_AGE_SECONDS = 120.0


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

        self.enabled = bool(config.get(CONF_ROUTE_TRACKER_ENABLED, False))
        self.source_type = str(
            config.get(CONF_ROUTE_SOURCE_TYPE, ROUTE_SOURCE_ABRP)
            or ROUTE_SOURCE_ABRP
        )

        self.latitude_entity = config.get(CONF_ROUTE_LATITUDE_ENTITY)
        self.longitude_entity = config.get(CONF_ROUTE_LONGITUDE_ENTITY)
        self.geocoded_entity = config.get(CONF_ROUTE_GEOCODED_ENTITY)

        self.active_trip_id: str | None = None
        self.paused_trip_id: str | None = None
        self.points: list[dict[str, Any]] = []
        self._remove_listener = None
        self._last_coordinate: tuple[float, float] | None = None
        self._debounce_task: asyncio.Task | None = None

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

        self._cancel_debounce()

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

    async def async_start(
        self,
        trip_id: str,
        *,
        start_latitude: Any = None,
        start_longitude: Any = None,
        start_timestamp: Any = None,
    ) -> None:
        """Start or resume recording points for one Trip ID."""

        if not self.enabled:
            return

        trip_id = str(trip_id)

        if self.paused_trip_id == trip_id:
            self.paused_trip_id = None
            self.active_trip_id = trip_id
            _LOGGER.info(
                "Route Tracker resumed for trip %s with %s GPS points",
                trip_id,
                len(self.points),
            )
            return

        if self.active_trip_id is not None:
            if self.active_trip_id == trip_id:
                return
            await self.async_finalize()

        self._cancel_debounce()
        self.active_trip_id = trip_id
        self.paused_trip_id = None
        self.points = []
        self._last_coordinate = None

        self._append_external_point(
            start_latitude,
            start_longitude,
            start_timestamp,
        )

        _LOGGER.info("Route Tracker started for trip %s", trip_id)

    async def async_pause(self) -> None:
        """Pause capture for Smart Trip without saving/resetting points."""

        if self.active_trip_id is None:
            return

        self._cancel_debounce()
        self.paused_trip_id = self.active_trip_id
        self.active_trip_id = None

        _LOGGER.info(
            "Route Tracker paused for Smart Trip %s with %s GPS points",
            self.paused_trip_id,
            len(self.points),
        )

    async def async_finalize(
        self,
        *,
        end_latitude: Any = None,
        end_longitude: Any = None,
        end_timestamp: Any = None,
    ) -> None:
        """Append authoritative Trip end GPS and save the route."""

        trip_id = self.active_trip_id or self.paused_trip_id
        if trip_id is None:
            return

        pending_task = self._debounce_task
        if pending_task is not None:
            try:
                await pending_task
            except asyncio.CancelledError:
                pass

        self._append_external_point(
            end_latitude,
            end_longitude,
            end_timestamp,
        )

        points = list(self.points)

        self._cancel_debounce()
        self.active_trip_id = None
        self.paused_trip_id = None
        self.points = []
        self._last_coordinate = None

        if not points:
            _LOGGER.warning(
                "Route Tracker finalized trip %s without GPS points",
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

    async def async_stop(self) -> None:
        """Compatibility wrapper."""
        await self.async_finalize()

    async def _source_changed(self, event: Event) -> None:
        """Capture one normalized point when the source updates."""

        if self.active_trip_id is None:
            return

        if self.source_type == ROUTE_SOURCE_ABRP:
            self._schedule_abrp_capture()
            return

        await self._capture_current_point(
            event.data.get("new_state")
        )

    def _schedule_abrp_capture(self) -> None:
        """Debounce split ABRP latitude/longitude state updates."""

        self._cancel_debounce()
        self._debounce_task = self.hass.async_create_task(
            self._debounced_abrp_capture()
        )

    async def _debounced_abrp_capture(self) -> None:
        """Wait briefly for both ABRP coordinate entities to settle."""

        try:
            await asyncio.sleep(ABRP_DEBOUNCE_SECONDS)

            if self.active_trip_id is None:
                return

            await self._capture_current_point()
        except asyncio.CancelledError:
            return
        finally:
            current_task = asyncio.current_task()
            if self._debounce_task is current_task:
                self._debounce_task = None

    def _cancel_debounce(self) -> None:
        """Cancel a pending ABRP coordinate capture."""

        if self._debounce_task is not None:
            if not self._debounce_task.done():
                self._debounce_task.cancel()
            self._debounce_task = None

    def _append_external_point(
        self,
        latitude_value: Any,
        longitude_value: Any,
        timestamp_value: Any,
    ) -> None:
        """Append a Trip start/end point if valid and not duplicated."""

        if latitude_value is None or longitude_value is None:
            return

        try:
            latitude = float(latitude_value)
            longitude = float(longitude_value)
        except (TypeError, ValueError):
            return

        coordinate_key = (latitude, longitude)
        if coordinate_key == self._last_coordinate:
            return

        if isinstance(timestamp_value, datetime):
            timestamp = timestamp_value.isoformat()
        elif timestamp_value:
            timestamp = str(timestamp_value)
        else:
            timestamp = dt_util.utcnow().isoformat()

        self.points.append(
            {
                "timestamp": timestamp,
                "latitude": latitude,
                "longitude": longitude,
            }
        )
        self._last_coordinate = coordinate_key

    async def _capture_current_point(
        self,
        changed_state: State | None = None,
        *,
        max_age_seconds: float | None = None,
    ) -> None:
        """Capture one point if valid and different from the previous one."""

        coordinates = self._read_coordinates(changed_state)
        if coordinates is None:
            return

        latitude, longitude, timestamp, source_updated_at = coordinates

        if max_age_seconds is not None:
            age_seconds = (
                dt_util.utcnow() - source_updated_at
            ).total_seconds()

            if age_seconds > max_age_seconds:
                _LOGGER.debug(
                    "Route Tracker ignored stale edge point: age=%.1fs",
                    age_seconds,
                )
                return

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

        _LOGGER.debug(
            "Route Tracker point: trip=%s lat=%.7f lon=%.7f",
            self.active_trip_id,
            latitude,
            longitude,
        )

    def _read_coordinates(
        self,
        changed_state: State | None = None,
    ) -> tuple[float, float, str, datetime] | None:
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
                state.last_updated,
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

        pair_delta_seconds = abs(
            (
                latitude_state.last_updated
                - longitude_state.last_updated
            ).total_seconds()
        )

        if pair_delta_seconds > ABRP_MAX_PAIR_DELTA_SECONDS:
            _LOGGER.debug(
                "Route Tracker waiting for synchronized ABRP pair: "
                "delta=%.3fs",
                pair_delta_seconds,
            )
            return None

        source_updated_at = max(
            latitude_state.last_updated,
            longitude_state.last_updated,
        )

        return (
            latitude,
            longitude,
            source_updated_at.isoformat(),
            source_updated_at,
        )
