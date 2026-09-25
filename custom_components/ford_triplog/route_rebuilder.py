"""
Ford Triplog

OSRM route maintenance / rebuild helper.

Version: 2.5.0
Build: 25017

Purpose:
- Re-run OSRM map matching for stored completed routes.
- Reconstruct very sparse routes with the normal OSRM route service.
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

from .osrm_client import (
    FordTriplogOSRMClient,
    FordTriplogOSRMError,
    osrm_confidence_is_acceptable,
)
from .route_storage import FordTriplogRouteStorage, SIGNAL_LAST_ROUTE_UPDATED

_LOGGER = logging.getLogger(__name__)

RouteRebuildMode = Literal["last", "raw", "all"]

# A trace with only a handful of points cannot produce a meaningful OSRM
# map-match confidence. For those traces use a normal start/end route and
# validate it against the vehicle's measured trip distance instead.
SPARSE_ROUTE_MAX_POINTS = 5
RECONSTRUCTION_DISTANCE_TOLERANCE = 0.20
RECONSTRUCTION_MIN_TOLERANCE_M = 500.0


@dataclass(slots=True)
class FordTriplogRouteRebuildResult:
    """Summary returned to the maintenance UI."""

    mode: str
    routes_total: int = 0
    routes_selected: int = 0
    routes_processed: int = 0
    routes_matched: int = 0
    routes_reconstructed: int = 0
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
            "routes_reconstructed": self.routes_reconstructed,
            "routes_failed": self.routes_failed,
            "routes_skipped": self.routes_skipped,
            "last_trip_id": self.last_trip_id,
        }


class FordTriplogRouteRebuilder:
    """Re-run OSRM matching/reconstruction for archived routes."""

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

        # Trip distance and authoritative start/end coordinates are needed for
        # sparse-route reconstruction. RouteStorage owns the same vehicle-bound
        # database object, so this lookup stays inside the selected vehicle.
        trips = await self.route_storage.database.load_all_trips()
        trip_by_id = {
            str(trip.get("trip_id") or ""): trip
            for trip in trips
            if isinstance(trip, dict) and trip.get("trip_id")
        }

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
            trip = trip_by_id.get(trip_id)

            if not trip_id or not isinstance(points, list):
                result.routes_skipped += 1
                _LOGGER.info(
                    "OSRM route maintenance skipped route %s/%s: "
                    "trip_id=%s points=%s",
                    index,
                    len(selected),
                    trip_id or "unknown",
                    len(points) if isinstance(points, list) else 0,
                )
                continue

            # Even a route record with zero/one raw GPS point can be rebuilt
            # when the archived Trip still has authoritative start/end
            # coordinates and a measured distance. That is exactly the GPS
            # outage case the reconstruction path is meant to cover.
            if len(points) < 2 and (
                self._trip_distance_m(trip) is None
                or self._authoritative_endpoints(points, trip) is None
            ):
                result.routes_skipped += 1
                _LOGGER.info(
                    "OSRM route maintenance skipped route %s/%s: "
                    "trip_id=%s points=%s reconstruction_data=unavailable",
                    index,
                    len(selected),
                    trip_id,
                    len(points),
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

            matched_route: dict[str, Any] | None = None
            reconstruction = False

            if len(points) <= SPARSE_ROUTE_MAX_POINTS:
                matched_route = await self._async_reconstruct_sparse_route(
                    client,
                    trip_id,
                    points,
                    trip,
                )
                reconstruction = matched_route is not None

                if matched_route is None:
                    result.routes_failed += 1
                    continue
            else:
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
                    match_result.confidence,
                )
                if not plausible:
                    result.routes_failed += 1
                    # A quality rejection is an expected maintenance outcome,
                    # not an integration error. Keep it visible at INFO level.
                    _LOGGER.info(
                        "OSRM route maintenance rejected trip %s: reason=%s "
                        "raw_points=%s matched_points=%s unmatched=%s "
                        "distance=%.1fm confidence=%s; stored route remains unchanged",
                        trip_id,
                        reason,
                        len(points),
                        len(match_result.geometry.get("coordinates", [])),
                        match_result.unmatched_tracepoints,
                        match_result.distance_m,
                        match_result.confidence,
                    )
                    continue

                matched_route = {
                    "provider": "osrm",
                    "match_type": "matched",
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

            if reconstruction:
                result.routes_reconstructed += 1
            else:
                result.routes_matched += 1

            if trip_id == result.last_trip_id:
                latest_route_changed = True

            _LOGGER.info(
                "OSRM route maintenance updated trip %s: type=%s "
                "raw_points=%s route_points=%s distance=%.1fm confidence=%s",
                trip_id,
                matched_route.get("match_type"),
                len(points),
                len(matched_route.get("geometry", {}).get("coordinates", [])),
                float(matched_route.get("distance_m") or 0.0),
                matched_route.get("confidence"),
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
            "processed=%s matched=%s reconstructed=%s failed=%s skipped=%s",
            result.mode,
            result.routes_total,
            result.routes_selected,
            result.routes_processed,
            result.routes_matched,
            result.routes_reconstructed,
            result.routes_failed,
            result.routes_skipped,
        )

        return result

    async def _async_reconstruct_sparse_route(
        self,
        client: FordTriplogOSRMClient,
        trip_id: str,
        points: list[dict[str, Any]],
        trip: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        """Build and validate a route for a trace that is too sparse to match."""

        trip_distance_m = self._trip_distance_m(trip)
        if trip_distance_m is None or trip_distance_m <= 0:
            _LOGGER.info(
                "OSRM sparse-route reconstruction skipped trip %s: "
                "raw_points=%s reason=trip_distance_unavailable; "
                "stored route remains unchanged",
                trip_id,
                len(points),
            )
            return None

        endpoints = self._authoritative_endpoints(points, trip)
        if endpoints is None:
            _LOGGER.info(
                "OSRM sparse-route reconstruction skipped trip %s: "
                "raw_points=%s reason=endpoints_unavailable; "
                "stored route remains unchanged",
                trip_id,
                len(points),
            )
            return None

        start_lat, start_lon, end_lat, end_lon = endpoints

        try:
            route_result = await client.async_route(
                start_lat,
                start_lon,
                end_lat,
                end_lon,
            )
        except FordTriplogOSRMError as err:
            _LOGGER.warning(
                "OSRM sparse-route reconstruction failed for trip %s: %s; "
                "stored route remains unchanged",
                trip_id,
                err,
            )
            return None
        except Exception:
            _LOGGER.exception(
                "Unexpected OSRM sparse-route reconstruction error for trip %s; "
                "stored route remains unchanged",
                trip_id,
            )
            return None

        plausible, reason, delta_m, delta_pct = self._reconstruction_plausibility(
            trip_distance_m,
            route_result.distance_m,
        )
        if not plausible:
            _LOGGER.info(
                "OSRM sparse-route reconstruction rejected trip %s: reason=%s "
                "raw_points=%s trip_distance=%.1fm route_distance=%.1fm "
                "delta=%.1fm delta_pct=%.1f%%; stored route remains unchanged",
                trip_id,
                reason,
                len(points),
                trip_distance_m,
                route_result.distance_m,
                delta_m,
                delta_pct,
            )
            return None

        _LOGGER.info(
            "OSRM sparse-route reconstruction accepted trip %s: raw_points=%s "
            "trip_distance=%.1fm route_distance=%.1fm delta=%.1fm "
            "delta_pct=%.1f%%",
            trip_id,
            len(points),
            trip_distance_m,
            route_result.distance_m,
            delta_m,
            delta_pct,
        )

        return {
            "provider": "osrm",
            "match_type": "reconstructed",
            "url": self.osrm_url,
            "radius_m": self.radius_meters,
            "distance_m": route_result.distance_m,
            "duration_s": route_result.duration_s,
            "confidence": None,
            "matched_tracepoints": 0,
            "unmatched_tracepoints": len(points),
            "reconstruction_trip_distance_m": trip_distance_m,
            "reconstruction_distance_delta_m": delta_m,
            "reconstruction_distance_delta_pct": delta_pct,
            "geometry": route_result.geometry,
        }

    @staticmethod
    def _trip_distance_m(trip: dict[str, Any] | None) -> float | None:
        """Return archived trip distance in metres when available."""

        if not isinstance(trip, dict):
            return None
        try:
            distance_km = float(trip.get("distance_km"))
        except (TypeError, ValueError):
            return None
        if distance_km <= 0:
            return None
        return distance_km * 1000.0

    @staticmethod
    def _authoritative_endpoints(
        points: list[dict[str, Any]],
        trip: dict[str, Any] | None,
    ) -> tuple[float, float, float, float] | None:
        """Prefer archived Trip endpoints, then fall back to raw endpoints."""

        candidates: list[tuple[Any, Any, Any, Any]] = []
        if isinstance(trip, dict):
            candidates.append(
                (
                    trip.get("start_latitude"),
                    trip.get("start_longitude"),
                    trip.get("end_latitude"),
                    trip.get("end_longitude"),
                )
            )

        if points:
            first = points[0] if isinstance(points[0], dict) else {}
            last = points[-1] if isinstance(points[-1], dict) else {}
            candidates.append(
                (
                    first.get("latitude"),
                    first.get("longitude"),
                    last.get("latitude"),
                    last.get("longitude"),
                )
            )

        for values in candidates:
            try:
                start_lat, start_lon, end_lat, end_lon = map(float, values)
            except (TypeError, ValueError):
                continue
            if (
                -90.0 <= start_lat <= 90.0
                and -180.0 <= start_lon <= 180.0
                and -90.0 <= end_lat <= 90.0
                and -180.0 <= end_lon <= 180.0
            ):
                return start_lat, start_lon, end_lat, end_lon

        return None

    @staticmethod
    def _reconstruction_plausibility(
        trip_distance_m: float,
        route_distance_m: float,
    ) -> tuple[bool, str, float, float]:
        """Validate a reconstructed route against measured trip distance."""

        if trip_distance_m <= 0 or route_distance_m <= 0:
            return False, "non_positive_distance", 0.0, 0.0

        delta_m = abs(route_distance_m - trip_distance_m)
        delta_pct = (delta_m / trip_distance_m) * 100.0
        allowed_delta_m = max(
            RECONSTRUCTION_MIN_TOLERANCE_M,
            trip_distance_m * RECONSTRUCTION_DISTANCE_TOLERANCE,
        )
        if delta_m > allowed_delta_m:
            return False, "distance_mismatch", delta_m, delta_pct

        return True, "ok", delta_m, delta_pct

    @staticmethod
    def _has_usable_osrm_match(route: dict[str, Any]) -> bool:
        """Return True when a stored route already has usable OSRM geometry."""

        matched_route = route.get("matched_route")
        if not isinstance(matched_route, dict):
            return False

        if matched_route.get("provider") != "osrm":
            return False

        geometry = matched_route.get("geometry")
        geometry_ok = (
            isinstance(geometry, dict)
            and geometry.get("type") == "LineString"
            and isinstance(geometry.get("coordinates"), list)
            and len(geometry["coordinates"]) >= 2
        )
        if not geometry_ok:
            return False

        if matched_route.get("match_type") == "reconstructed":
            try:
                return float(matched_route.get("distance_m") or 0.0) > 0
            except (TypeError, ValueError):
                return False

        return osrm_confidence_is_acceptable(matched_route.get("confidence"))

    @staticmethod
    def _match_plausibility(
        points: list[dict[str, Any]],
        matched_distance_m: float,
        unmatched_tracepoints: int,
        confidence: float | None,
    ) -> tuple[bool, str]:
        """Apply conservative acceptance rules to normal map matching."""

        if not osrm_confidence_is_acceptable(confidence):
            return False, "low_confidence"

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
