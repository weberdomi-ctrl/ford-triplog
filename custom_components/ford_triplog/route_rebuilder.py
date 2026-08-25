"""
Ford Triplog

OSRM route maintenance / rebuild helper.

Version: 2.3.0
Build: 23026

Purpose:
- Re-run OSRM map matching for stored completed routes.
- Keep raw GPS points untouched at all times.
- Preserve an existing matched route if a rebuild fails.
- Support rebuilding the latest route, only raw/unmatched routes, or all routes.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
from math import asin, cos, radians, sin, sqrt
from typing import Any, Literal

from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .osrm_client import FordTriplogOSRMClient, FordTriplogOSRMError
from .route_storage import FordTriplogRouteStorage, SIGNAL_LAST_ROUTE_UPDATED

_LOGGER = logging.getLogger(__name__)

RouteRebuildMode = Literal["last", "raw", "all"]


@dataclass(slots=True)
class FordTriplogRouteRebuildResult:
    """Summary returned to the maintenance UI."""

    mode: str
    routes_total: int = 0
    routes_selected: int = 0
    routes_processed: int = 0
    routes_matched: int = 0
    routes_failed: int = 0
    routes_skipped: int = 0
    last_trip_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Return a serializable result."""

        return {
            "mode": self.mode,
            "routes_total": self.routes_total,
            "routes_selected": self.routes_selected,
            "routes_processed": self.routes_processed,
            "routes_matched": self.routes_matched,
            "routes_failed": self.routes_failed,
            "routes_skipped": self.routes_skipped,
            "last_trip_id": self.last_trip_id,
        }


class FordTriplogRouteRebuilder:
    """Re-run OSRM matching for archived routes."""

    def __init__(
        self,
        hass: HomeAssistant,
        route_storage: FordTriplogRouteStorage,
        *,
        osrm_url: str,
        radius_meters: float,
    ) -> None:
        self.hass = hass
        self.route_storage = route_storage
        self.osrm_url = str(osrm_url or "").strip().rstrip("/")
        self.radius_meters = float(radius_meters)

    async def async_rebuild(
        self,
        mode: RouteRebuildMode,
    ) -> FordTriplogRouteRebuildResult:
        """Rebuild routes for the requested maintenance scope."""

        if mode not in {"last", "raw", "all"}:
            raise ValueError(f"Unsupported route rebuild mode: {mode}")

        if not self.osrm_url:
            raise ValueError("OSRM is not configured")

        routes = await self.route_storage.async_list_routes()
        result = FordTriplogRouteRebuildResult(
            mode=mode,
            routes_total=len(routes),
        )

        if not routes:
            return result

        latest_route = routes[-1]
        result.last_trip_id = str(latest_route.get("trip_id") or "")

        if mode == "last":
            selected = [latest_route]
        elif mode == "raw":
            selected = [
                route
                for route in routes
                if not self._has_usable_osrm_match(route)
            ]
        else:
            selected = routes

        result.routes_selected = len(selected)

        client = FordTriplogOSRMClient(
            self.hass,
            self.osrm_url,
            radius_meters=self.radius_meters,
        )

        latest_route_changed = False

        for index, route in enumerate(selected, start=1):
            trip_id = str(route.get("trip_id") or "").strip()
            points = route.get("points")

            if not trip_id or not isinstance(points, list) or len(points) < 2:
                result.routes_skipped += 1
                _LOGGER.warning(
                    "OSRM route maintenance skipped route %s/%s: "
                    "trip_id=%s points=%s",
                    index,
                    len(selected),
                    trip_id or "unknown",
                    len(points) if isinstance(points, list) else 0,
                )
                continue

            result.routes_processed += 1

            _LOGGER.info(
                "OSRM route maintenance processing %s/%s: trip=%s "
                "raw_points=%s mode=%s",
                index,
                len(selected),
                trip_id,
                len(points),
                mode,
            )

            try:
                match_result = await client.async_match(points)
            except FordTriplogOSRMError as err:
                result.routes_failed += 1
                _LOGGER.warning(
                    "OSRM route maintenance failed for trip %s: %s; "
                    "stored route remains unchanged",
                    trip_id,
                    err,
                )
                continue
            except Exception:
                result.routes_failed += 1
                _LOGGER.exception(
                    "Unexpected OSRM route maintenance error for trip %s; "
                    "stored route remains unchanged",
                    trip_id,
                )
                continue

            plausible, reason = self._match_plausibility(
                points,
                match_result.distance_m,
                match_result.unmatched_tracepoints,
            )
            if not plausible:
                result.routes_failed += 1
                _LOGGER.warning(
                    "OSRM route maintenance rejected trip %s: reason=%s "
                    "raw_points=%s matched_points=%s unmatched=%s "
                    "distance=%.1fm; stored route remains unchanged",
                    trip_id,
                    reason,
                    len(points),
                    len(match_result.geometry.get("coordinates", [])),
                    match_result.unmatched_tracepoints,
                    match_result.distance_m,
                )
                continue

            matched_route = {
                "provider": "osrm",
                "url": self.osrm_url,
                "radius_m": self.radius_meters,
                "distance_m": match_result.distance_m,
                "duration_s": match_result.duration_s,
                "confidence": match_result.confidence,
                "matched_tracepoints": match_result.matched_tracepoints,
                "unmatched_tracepoints": match_result.unmatched_tracepoints,
                "geometry": match_result.geometry,
            }

            try:
                await self.route_storage.async_save_route(
                    trip_id=trip_id,
                    source_type=str(route.get("source_type") or "unknown"),
                    points=points,
                    status="completed",
                    created_at=(
                        str(route.get("created_at"))
                        if route.get("created_at") is not None
                        else None
                    ),
                    matched_route=matched_route,
                    notify=False,
                )
            except Exception:
                result.routes_failed += 1
                _LOGGER.exception(
                    "Unable to store rebuilt OSRM route for trip %s; "
                    "previous stored route remains available if SQLite "
                    "write failed atomically",
                    trip_id,
                )
                continue

            result.routes_matched += 1
            if trip_id == result.last_trip_id:
                latest_route_changed = True

            _LOGGER.info(
                "OSRM route maintenance updated trip %s: raw_points=%s "
                "matched_points=%s distance=%.1fm confidence=%s",
                trip_id,
                len(points),
                len(match_result.geometry.get("coordinates", [])),
                match_result.distance_m,
                match_result.confidence,
            )

        # Avoid dispatching one Last Route refresh for every historical route.
        if latest_route_changed and result.last_trip_id:
            async_dispatcher_send(
                self.hass,
                SIGNAL_LAST_ROUTE_UPDATED,
                result.last_trip_id,
            )

        _LOGGER.info(
            "OSRM route maintenance completed: mode=%s total=%s selected=%s "
            "processed=%s matched=%s failed=%s skipped=%s",
            result.mode,
            result.routes_total,
            result.routes_selected,
            result.routes_processed,
            result.routes_matched,
            result.routes_failed,
            result.routes_skipped,
        )

        return result

    @staticmethod
    def _has_usable_osrm_match(route: dict[str, Any]) -> bool:
        """Return True when a stored route already has usable OSRM geometry."""

        matched_route = route.get("matched_route")
        if not isinstance(matched_route, dict):
            return False

        if matched_route.get("provider") != "osrm":
            return False

        geometry = matched_route.get("geometry")
        return (
            isinstance(geometry, dict)
            and geometry.get("type") == "LineString"
            and isinstance(geometry.get("coordinates"), list)
            and len(geometry["coordinates"]) >= 2
        )

    @staticmethod
    def _match_plausibility(
        points: list[dict[str, Any]],
        matched_distance_m: float,
        unmatched_tracepoints: int,
    ) -> tuple[bool, str]:
        """Apply the same conservative acceptance rules as live recording."""

        if matched_distance_m <= 0:
            return False, "non_positive_distance"

        unmatched_limit = max(1, len(points) // 5)
        if unmatched_tracepoints > unmatched_limit:
            return False, "too_many_unmatched_tracepoints"

        try:
            lat1 = radians(float(points[0]["latitude"]))
            lon1 = radians(float(points[0]["longitude"]))
            lat2 = radians(float(points[-1]["latitude"]))
            lon2 = radians(float(points[-1]["longitude"]))

            dlat = lat2 - lat1
            dlon = lon2 - lon1
            value = (
                sin(dlat / 2) ** 2
                + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
            )
            direct_distance_m = 6371000.0 * 2 * asin(
                min(1.0, sqrt(value))
            )
        except (KeyError, TypeError, ValueError):
            return True, "endpoint_distance_unavailable"

        if direct_distance_m > 100:
            if matched_distance_m < direct_distance_m * 0.95:
                return False, "shorter_than_direct_distance"
            if matched_distance_m > direct_distance_m * 8.0:
                return False, "excessive_detour"

        return True, "ok"
