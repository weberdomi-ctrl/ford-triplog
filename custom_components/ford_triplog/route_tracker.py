"""
Ford Triplog

Route Tracker

Version: 2.2.0
Phase: Route Tracker Phase 1
Build: 03 - Trip-end GPS validation

Changes:
- Persists the route JSON immediately when a Trip starts.
- Persists every accepted GPS point while driving.
- Persists Smart Trip pause/resume state.
- Restores active or paused route points after HA/integration reload.
- Keeps Trip start/end GPS endpoint logic from Fix 05.
- Keeps ABRP coordinate debounce/synchronization from Fix 04.
- Raw route points remain independent from Trip/Journey storage.
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
    CONF_OSRM_ENABLED,
    CONF_OSRM_URL,
    CONF_OSRM_MATCH_RADIUS,
    DEFAULT_OSRM_ENABLED,
    DEFAULT_OSRM_URL,
    DEFAULT_OSRM_MATCH_RADIUS,
    ROUTE_SOURCE_ABRP,
    ROUTE_SOURCE_HA_GEOCODED,
)
from .route_storage import FordTriplogRouteStorage
from .osrm_client import (
    FordTriplogOSRMClient,
    FordTriplogOSRMError,
)

_LOGGER = logging.getLogger(__name__)

ABRP_DEBOUNCE_SECONDS = 0.75
ABRP_MAX_PAIR_DELTA_SECONDS = 2.0


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
        self.route_source_type = self.source_type

        self.latitude_entity = config.get(
            CONF_ROUTE_LATITUDE_ENTITY
        )
        self.longitude_entity = config.get(
            CONF_ROUTE_LONGITUDE_ENTITY
        )
        self.geocoded_entity = config.get(
            CONF_ROUTE_GEOCODED_ENTITY
        )

        self.osrm_enabled = bool(
            config.get(CONF_OSRM_ENABLED, DEFAULT_OSRM_ENABLED)
        )
        self.osrm_url = str(
            config.get(CONF_OSRM_URL, DEFAULT_OSRM_URL) or ""
        ).strip().rstrip("/")
        self.osrm_match_radius = float(
            config.get(
                CONF_OSRM_MATCH_RADIUS,
                DEFAULT_OSRM_MATCH_RADIUS,
            )
        )

        self.active_trip_id: str | None = None
        self.paused_trip_id: str | None = None
        self.points: list[dict[str, Any]] = []

        self._remove_listener = None
        self._last_coordinate: tuple[float, float] | None = None
        self._debounce_task: asyncio.Task | None = None
        self._persist_lock = asyncio.Lock()
        self._route_created_at: str | None = None

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
        """Persist current state and remove Route Tracker listeners."""

        if self.active_trip_id is not None:
            await self._persist_current_route("active")
        elif self.paused_trip_id is not None:
            await self._persist_current_route("paused")

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

    async def async_recover(
        self,
        trip_id: str,
        *,
        paused: bool,
        start_latitude: Any = None,
        start_longitude: Any = None,
        start_timestamp: Any = None,
    ) -> None:
        """Restore one active/paused route after integration reload."""

        if not self.enabled:
            return

        trip_id = str(trip_id)
        stored = await self.storage.async_load_route(trip_id)

        if isinstance(stored, dict):
            stored_status = str(
                stored.get("status") or "completed"
            )

            if stored_status in ("active", "paused"):
                raw_points = stored.get("points", [])
                self.points = [
                    dict(point)
                    for point in raw_points
                    if isinstance(point, dict)
                ]

                stored_source = str(
                    stored.get("source_type")
                    or self.source_type
                )
                self.route_source_type = (
                    stored_source
                    if stored_source == self.source_type
                    else "mixed"
                )
                self._route_created_at = (
                    stored.get("created_at")
                    or dt_util.now().isoformat()
                )

                self._last_coordinate = (
                    self._coordinate_from_point(
                        self.points[-1]
                    )
                    if self.points
                    else None
                )

                if paused:
                    self.paused_trip_id = trip_id
                    self.active_trip_id = None
                    status = "paused"
                else:
                    self.active_trip_id = trip_id
                    self.paused_trip_id = None
                    status = "active"

                await self._persist_current_route(status)

                _LOGGER.info(
                    "Route Tracker recovered %s route for trip %s "
                    "with %s GPS points",
                    status,
                    trip_id,
                    len(self.points),
                )
                return

        # No recoverable route exists yet. Create one from the authoritative
        # Trip start GPS so a reload can no longer lose the entire route.
        self.active_trip_id = None if paused else trip_id
        self.paused_trip_id = trip_id if paused else None
        self.points = []
        self._last_coordinate = None
        self.route_source_type = self.source_type
        self._route_created_at = dt_util.now().isoformat()

        self._append_external_point(
            start_latitude,
            start_longitude,
            start_timestamp,
        )

        await self._persist_current_route(
            "paused" if paused else "active"
        )

        _LOGGER.info(
            "Route Tracker recovery created %s route for trip %s "
            "with %s GPS points",
            "paused" if paused else "active",
            trip_id,
            len(self.points),
        )

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
            await self._persist_current_route("active")

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

        # Also recover automatically if the route file already exists.
        stored = await self.storage.async_load_route(trip_id)
        if (
            isinstance(stored, dict)
            and stored.get("status") in ("active", "paused")
        ):
            await self.async_recover(
                trip_id,
                paused=False,
                start_latitude=start_latitude,
                start_longitude=start_longitude,
                start_timestamp=start_timestamp,
            )
            return

        self._cancel_debounce()

        self.active_trip_id = trip_id
        self.paused_trip_id = None
        self.points = []
        self._last_coordinate = None
        self.route_source_type = self.source_type
        self._route_created_at = dt_util.now().isoformat()

        self._append_external_point(
            start_latitude,
            start_longitude,
            start_timestamp,
        )

        # Fix 06: create the recovery file immediately.
        await self._persist_current_route("active")

        _LOGGER.info(
            "Route Tracker started for trip %s",
            trip_id,
        )

    async def async_pause(self) -> None:
        """Pause capture for Smart Trip without discarding points."""

        if self.active_trip_id is None:
            return

        self._cancel_debounce()
        self.paused_trip_id = self.active_trip_id
        self.active_trip_id = None

        await self._persist_current_route("paused")

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
        """Append authoritative Trip end GPS and complete the route."""

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
        source_type = self.route_source_type
        created_at = self._route_created_at

        # Optional OSRM matching is deliberately performed only after the
        # authoritative Trip end point has been appended. Raw points always
        # remain the primary stored source and therefore the safe fallback.
        matched_route: dict[str, Any] | None = None

        if self.osrm_enabled and self.osrm_url and len(points) >= 2:
            try:
                osrm_client = FordTriplogOSRMClient(
                    self.hass,
                    self.osrm_url,
                    radius_meters=self.osrm_match_radius,
                )
                match_result = await osrm_client.async_match(points)

                if self._osrm_match_is_plausible(
                    points,
                    match_result.distance_m,
                    match_result.unmatched_tracepoints,
                ):
                    matched_route = {
                        "provider": "osrm",
                        "url": self.osrm_url,
                        "radius_m": self.osrm_match_radius,
                        "distance_m": match_result.distance_m,
                        "duration_s": match_result.duration_s,
                        "confidence": match_result.confidence,
                        "matched_tracepoints": match_result.matched_tracepoints,
                        "unmatched_tracepoints": match_result.unmatched_tracepoints,
                        "geometry": match_result.geometry,
                    }
                    _LOGGER.info(
                        "OSRM matched route for trip %s: raw_points=%s "
                        "matched_points=%s distance=%.1fm confidence=%s",
                        trip_id,
                        len(points),
                        len(match_result.geometry.get("coordinates", [])),
                        match_result.distance_m,
                        match_result.confidence,
                    )
                else:
                    _LOGGER.warning(
                        "OSRM result rejected as implausible for trip %s; "
                        "raw route will be used",
                        trip_id,
                    )

            except FordTriplogOSRMError as err:
                _LOGGER.warning(
                    "OSRM matching failed for trip %s: %s; "
                    "raw route will be used",
                    trip_id,
                    err,
                )
            except Exception:
                _LOGGER.exception(
                    "Unexpected OSRM matching error for trip %s; "
                    "raw route will be used",
                    trip_id,
                )

        # Persist completed state before clearing in-memory recovery data.
        async with self._persist_lock:
            await self.storage.async_save_route(
                trip_id=trip_id,
                source_type=source_type,
                points=points,
                status="completed",
                created_at=created_at,
                matched_route=matched_route,
            )

        self._cancel_debounce()
        self.active_trip_id = None
        self.paused_trip_id = None
        self.points = []
        self._last_coordinate = None
        self._route_created_at = None
        self.route_source_type = self.source_type

        _LOGGER.info(
            "Route Tracker saved %s GPS points for trip %s",
            len(points),
            trip_id,
        )

    @staticmethod
    def _osrm_match_is_plausible(
        points: list[dict[str, Any]],
        matched_distance_m: float,
        unmatched_tracepoints: int,
    ) -> bool:
        """Apply conservative sanity checks before accepting OSRM geometry."""

        if matched_distance_m <= 0:
            return False

        if unmatched_tracepoints > max(1, len(points) // 5):
            return False

        # Compare against straight-line distance between the authoritative
        # route endpoints. A road route must not be shorter than this, while
        # an extreme detour usually indicates a bad match.
        try:
            from math import asin, cos, radians, sin, sqrt

            lat1 = radians(float(points[0]["latitude"]))
            lon1 = radians(float(points[0]["longitude"]))
            lat2 = radians(float(points[-1]["latitude"]))
            lon2 = radians(float(points[-1]["longitude"]))

            dlat = lat2 - lat1
            dlon = lon2 - lon1
            a = (
                sin(dlat / 2) ** 2
                + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
            )
            direct_distance_m = 6371000.0 * 2 * asin(sqrt(a))
        except (KeyError, TypeError, ValueError):
            return True

        if direct_distance_m > 100:
            if matched_distance_m < direct_distance_m * 0.95:
                return False
            if matched_distance_m > direct_distance_m * 8.0:
                return False

        return True

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

    def get_last_point(self) -> dict[str, Any] | None:
        """Return the latest recorded raw route point."""

        if not self.points:
            return None

        return dict(self.points[-1])

    @staticmethod
    def _coordinate_from_point(
        point: dict[str, Any],
    ) -> tuple[float, float] | None:
        """Return coordinate tuple from one stored route point."""

        try:
            return (
                float(point["latitude"]),
                float(point["longitude"]),
            )
        except (KeyError, TypeError, ValueError):
            return None

    def _append_external_point(
        self,
        latitude_value: Any,
        longitude_value: Any,
        timestamp_value: Any,
    ) -> bool:
        """Append a Trip start/end point if valid and not duplicated."""

        if latitude_value is None or longitude_value is None:
            return False

        try:
            latitude = float(latitude_value)
            longitude = float(longitude_value)
        except (TypeError, ValueError):
            return False

        coordinate_key = (latitude, longitude)
        if coordinate_key == self._last_coordinate:
            return False

        if isinstance(timestamp_value, datetime):
            timestamp = timestamp_value.isoformat()
        elif timestamp_value:
            timestamp = str(timestamp_value)
        else:
            timestamp = dt_util.now().isoformat()

        self.points.append(
            {
                "timestamp": timestamp,
                "latitude": latitude,
                "longitude": longitude,
            }
        )
        self._last_coordinate = coordinate_key
        return True

    async def _capture_current_point(
        self,
        changed_state: State | None = None,
    ) -> None:
        """Capture and immediately persist one new GPS point."""

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

        # Fix 06: one ~60 s ABRP point means one small atomic JSON write.
        # This is intentionally simple and makes crash/reload recovery robust.
        await self._persist_current_route("active")

        _LOGGER.debug(
            "Route Tracker point persisted: trip=%s points=%s",
            self.active_trip_id,
            len(self.points),
        )

    async def _persist_current_route(
        self,
        status: str,
    ) -> None:
        """Persist the current route snapshot atomically."""

        trip_id = self.active_trip_id or self.paused_trip_id
        if trip_id is None:
            return

        async with self._persist_lock:
            await self.storage.async_save_route(
                trip_id=trip_id,
                source_type=self.route_source_type,
                points=list(self.points),
                status=status,
                created_at=self._route_created_at,
            )

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

        timestamp = max(
            latitude_state.last_updated,
            longitude_state.last_updated,
        ).isoformat()

        return latitude, longitude, timestamp
