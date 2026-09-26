"""
Ford Triplog

Local OSRM client.

Version: 2.0.0-dev
Phase: Route Matching
Step: 01 - Local OSRM client

Purpose:
- Optional local OSRM connection.
- Test OSRM availability.
- Match Ford Triplog raw route points to the OSM road network.
- Defaults agreed for Ford Triplog:
  radius=15 m, gaps=ignore, tidy=false.
- No cloud/API-key dependency.

This module does not replace raw route storage. It only produces an
additional matched geometry.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import logging
from typing import Any
from urllib.parse import quote

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util import dt as dt_util

_LOGGER = logging.getLogger(__name__)

DEFAULT_OSRM_RADIUS_METERS = 15.0
DEFAULT_OSRM_TIMEOUT_SECONDS = 15
DEFAULT_OSRM_PROFILE = "driving"

# Keep below the common OSRM --max-matching-size default of 100.
OSRM_MATCH_CHUNK_SIZE = 90
OSRM_MATCH_CHUNK_OVERLAP = 5


class FordTriplogOSRMError(Exception):
    """Base exception for local OSRM errors."""


class FordTriplogOSRMConnectionError(FordTriplogOSRMError):
    """Raised when the local OSRM server cannot be reached."""


class FordTriplogOSRMResponseError(FordTriplogOSRMError):
    """Raised when OSRM returns an invalid or unsuccessful response."""


@dataclass(slots=True)
class FordTriplogOSRMMatchResult:
    """Normalized OSRM map-matching result."""

    geometry: dict[str, Any]
    distance_m: float
    duration_s: float
    confidence: float | None
    matched_tracepoints: int
    unmatched_tracepoints: int
    tracepoint_matched: tuple[bool, ...] = ()
    tracepoint_locations: tuple[tuple[float, float] | None, ...] = ()

    @property
    def geojson_feature(self) -> dict[str, Any]:
        """Return a GeoJSON Feature suitable for route display/export."""
        return {
            "type": "Feature",
            "properties": {
                "source_type": "osrm",
                "distance_km": round(self.distance_m / 1000.0, 3),
                "duration_s": round(self.duration_s, 1),
                "confidence": self.confidence,
                "matched_tracepoints": self.matched_tracepoints,
                "unmatched_tracepoints": self.unmatched_tracepoints,
            },
            "geometry": self.geometry,
        }


class FordTriplogOSRMClient:
    """Small async client for a local OSRM server."""

    def __init__(
        self,
        hass: HomeAssistant,
        base_url: str,
        *,
        timeout_seconds: int = DEFAULT_OSRM_TIMEOUT_SECONDS,
        radius_meters: float = DEFAULT_OSRM_RADIUS_METERS,
        profile: str = DEFAULT_OSRM_PROFILE,
    ) -> None:
        self.hass = hass
        self.base_url = str(base_url or "").strip().rstrip("/")
        self.timeout_seconds = max(2, int(timeout_seconds))
        self.radius_meters = max(1.0, float(radius_meters))
        self.profile = str(profile or DEFAULT_OSRM_PROFILE).strip()

    async def async_test_connection(self) -> dict[str, Any]:
        """Test OSRM using a harmless nearest request.

        Uses a fixed coordinate only to verify that the server and routing
        dataset respond. It does not store or change any Ford Triplog data.
        """

        if not self.base_url:
            raise FordTriplogOSRMConnectionError(
                "OSRM server URL is empty"
            )

        # Switzerland test coordinate. Any loaded CH dataset should resolve it.
        url = (
            f"{self.base_url}/nearest/v1/{quote(self.profile)}/"
            "8.95138,47.175636"
        )

        payload = await self._async_get_json(url)

        if payload.get("code") != "Ok":
            raise FordTriplogOSRMResponseError(
                str(payload.get("message") or payload.get("code") or "OSRM test failed")
            )

        waypoints = payload.get("waypoints")
        waypoint = waypoints[0] if isinstance(waypoints, list) and waypoints else {}

        return {
            "ok": True,
            "name": waypoint.get("name"),
            "distance_m": waypoint.get("distance"),
            "location": waypoint.get("location"),
        }

    async def async_match(
        self,
        points: list[dict[str, Any]],
    ) -> FordTriplogOSRMMatchResult:
        """Map-match raw Ford Triplog points to the local OSM road network.

        Long traces are split into overlapping chunks so Ford Triplog works
        with the common OSRM default ``--max-matching-size=100``. Raw route
        storage remains untouched; this method only returns one merged matched
        geometry.
        """

        normalized = self._normalize_points(points)

        if len(normalized) < 2:
            raise FordTriplogOSRMResponseError(
                "At least two valid route points are required"
            )

        if len(normalized) <= OSRM_MATCH_CHUNK_SIZE:
            return await self._async_match_normalized(normalized)

        chunks = self._build_match_chunks(len(normalized))
        _LOGGER.info(
            "OSRM matching long trace in %s chunks: points=%s "
            "chunk_size=%s overlap=%s",
            len(chunks),
            len(normalized),
            OSRM_MATCH_CHUNK_SIZE,
            OSRM_MATCH_CHUNK_OVERLAP,
        )

        merged_coordinates: list[list[float]] = []
        matched_flags = [False] * len(normalized)
        weighted_confidence = 0.0
        confidence_weight = 0
        previous_end = 0

        for chunk_number, (chunk_start, chunk_end) in enumerate(chunks, 1):
            chunk_points = normalized[chunk_start:chunk_end]
            _LOGGER.info(
                "OSRM matching chunk %s/%s: points=%s range=%s-%s",
                chunk_number,
                len(chunks),
                len(chunk_points),
                chunk_start + 1,
                chunk_end,
            )

            result = await self._async_match_normalized(chunk_points)

            chunk_coordinates = result.geometry.get("coordinates", [])
            if not isinstance(chunk_coordinates, list) or len(chunk_coordinates) < 2:
                raise FordTriplogOSRMResponseError(
                    f"OSRM chunk {chunk_number}/{len(chunks)} "
                    "returned no usable geometry"
                )

            for local_index, is_matched in enumerate(result.tracepoint_matched):
                global_index = chunk_start + local_index
                if global_index < len(matched_flags) and is_matched:
                    matched_flags[global_index] = True

            overlap_count = max(0, previous_end - chunk_start)
            unique_weight = len(chunk_points) - overlap_count
            if result.confidence is not None and unique_weight > 0:
                weighted_confidence += result.confidence * unique_weight
                confidence_weight += unique_weight

            normalized_chunk_geometry = self._normalize_geometry_coordinates(
                chunk_coordinates
            )

            if not merged_coordinates:
                merged_coordinates.extend(normalized_chunk_geometry)
            else:
                stitch_location = None
                if overlap_count > 0:
                    boundary_index = min(
                        overlap_count - 1,
                        len(result.tracepoint_locations) - 1,
                    )
                    if boundary_index >= 0:
                        stitch_location = result.tracepoint_locations[boundary_index]

                stitch_index = self._find_stitch_index(
                    normalized_chunk_geometry,
                    stitch_location,
                    merged_coordinates[-1] if merged_coordinates else None,
                )

                # The previous chunk already contains the overlap through the
                # boundary point. Append only geometry after that point.
                append_from = min(stitch_index + 1, len(normalized_chunk_geometry))
                for coordinate in normalized_chunk_geometry[append_from:]:
                    if (
                        not merged_coordinates
                        or not self._coordinates_equal(
                            merged_coordinates[-1],
                            coordinate,
                        )
                    ):
                        merged_coordinates.append(coordinate)

            previous_end = chunk_end

            _LOGGER.info(
                "OSRM matched chunk %s/%s: geometry_points=%s "
                "matched_tracepoints=%s unmatched_tracepoints=%s "
                "distance=%.1fm confidence=%s",
                chunk_number,
                len(chunks),
                len(chunk_coordinates),
                result.matched_tracepoints,
                result.unmatched_tracepoints,
                result.distance_m,
                result.confidence,
            )

        if len(merged_coordinates) < 2:
            raise FordTriplogOSRMResponseError(
                "OSRM chunk merge returned no usable LineString geometry"
            )

        matched_count = sum(1 for value in matched_flags if value)
        unmatched_count = len(matched_flags) - matched_count
        confidence = (
            weighted_confidence / confidence_weight
            if confidence_weight > 0
            else None
        )

        distance_m = self._geometry_distance_m(merged_coordinates)
        duration_s = float(max(0, normalized[-1][2] - normalized[0][2]))

        _LOGGER.info(
            "OSRM chunk merge completed: input_points=%s geometry_points=%s "
            "matched_tracepoints=%s unmatched_tracepoints=%s "
            "distance=%.1fm confidence=%s",
            len(normalized),
            len(merged_coordinates),
            matched_count,
            unmatched_count,
            distance_m,
            confidence,
        )

        return FordTriplogOSRMMatchResult(
            geometry={
                "type": "LineString",
                "coordinates": merged_coordinates,
            },
            distance_m=distance_m,
            duration_s=duration_s,
            confidence=confidence,
            matched_tracepoints=matched_count,
            unmatched_tracepoints=unmatched_count,
            tracepoint_matched=tuple(matched_flags),
            tracepoint_locations=(),
        )

    async def _async_match_normalized(
        self,
        normalized: list[tuple[float, float, int]],
    ) -> FordTriplogOSRMMatchResult:
        """Perform one OSRM match request for an already normalized chunk."""

        coordinates = ";".join(
            f"{lon:.7f},{lat:.7f}"
            for lat, lon, _timestamp in normalized
        )

        timestamps = ";".join(
            str(timestamp)
            for _lat, _lon, timestamp in normalized
        )

        radius = self._format_radius(self.radius_meters)
        radiuses = ";".join(radius for _ in normalized)

        url = (
            f"{self.base_url}/match/v1/{quote(self.profile)}/{coordinates}"
            f"?timestamps={timestamps}"
            f"&radiuses={radiuses}"
            "&geometries=geojson"
            "&overview=full"
            "&gaps=ignore"
            "&tidy=false"
        )

        payload = await self._async_get_json(url)

        if payload.get("code") != "Ok":
            raise FordTriplogOSRMResponseError(
                str(
                    payload.get("message")
                    or payload.get("code")
                    or "OSRM map matching failed"
                )
            )

        matchings = payload.get("matchings")
        if not isinstance(matchings, list) or not matchings:
            raise FordTriplogOSRMResponseError(
                "OSRM returned no matching"
            )

        matching = matchings[0]
        geometry = matching.get("geometry")

        if (
            not isinstance(geometry, dict)
            or geometry.get("type") != "LineString"
            or not isinstance(geometry.get("coordinates"), list)
        ):
            raise FordTriplogOSRMResponseError(
                "OSRM returned no valid LineString geometry"
            )

        tracepoints = payload.get("tracepoints")
        if not isinstance(tracepoints, list):
            tracepoints = []

        tracepoint_matched: list[bool] = []
        tracepoint_locations: list[tuple[float, float] | None] = []

        for index in range(len(normalized)):
            point = tracepoints[index] if index < len(tracepoints) else None
            is_matched = isinstance(point, dict)
            tracepoint_matched.append(is_matched)

            location = point.get("location") if is_matched else None
            if (
                isinstance(location, (list, tuple))
                and len(location) >= 2
            ):
                try:
                    tracepoint_locations.append(
                        (float(location[0]), float(location[1]))
                    )
                except (TypeError, ValueError):
                    tracepoint_locations.append(None)
            else:
                tracepoint_locations.append(None)

        matched_count = sum(1 for value in tracepoint_matched if value)
        unmatched_count = len(tracepoint_matched) - matched_count

        return FordTriplogOSRMMatchResult(
            geometry=geometry,
            distance_m=float(matching.get("distance") or 0.0),
            duration_s=float(matching.get("duration") or 0.0),
            confidence=(
                float(matching["confidence"])
                if matching.get("confidence") is not None
                else None
            ),
            matched_tracepoints=matched_count,
            unmatched_tracepoints=unmatched_count,
            tracepoint_matched=tuple(tracepoint_matched),
            tracepoint_locations=tuple(tracepoint_locations),
        )

    @staticmethod
    def _build_match_chunks(point_count: int) -> list[tuple[int, int]]:
        """Return overlapping [start, end) slices for an OSRM trace."""

        if point_count <= OSRM_MATCH_CHUNK_SIZE:
            return [(0, point_count)]

        chunks: list[tuple[int, int]] = []
        start = 0

        while start < point_count:
            end = min(start + OSRM_MATCH_CHUNK_SIZE, point_count)
            chunks.append((start, end))
            if end >= point_count:
                break

            next_start = end - OSRM_MATCH_CHUNK_OVERLAP
            if next_start <= start:
                raise FordTriplogOSRMResponseError(
                    "Invalid OSRM chunk configuration"
                )
            start = next_start

        return chunks

    @staticmethod
    def _normalize_geometry_coordinates(
        coordinates: list[Any],
    ) -> list[list[float]]:
        """Normalize GeoJSON coordinates to mutable [lon, lat] pairs."""

        normalized: list[list[float]] = []
        for coordinate in coordinates:
            if not isinstance(coordinate, (list, tuple)) or len(coordinate) < 2:
                continue
            try:
                normalized.append(
                    [float(coordinate[0]), float(coordinate[1])]
                )
            except (TypeError, ValueError):
                continue
        return normalized

    @staticmethod
    def _coordinates_equal(
        first: list[float],
        second: list[float],
    ) -> bool:
        """Return True for effectively identical GeoJSON coordinates."""

        return (
            abs(first[0] - second[0]) <= 1e-7
            and abs(first[1] - second[1]) <= 1e-7
        )

    @staticmethod
    def _find_stitch_index(
        coordinates: list[list[float]],
        stitch_location: tuple[float, float] | None,
        fallback_location: list[float] | None,
    ) -> int:
        """Find the geometry point nearest the overlap boundary."""

        if not coordinates:
            return 0

        target: tuple[float, float] | None = stitch_location
        if target is None and fallback_location is not None:
            target = (fallback_location[0], fallback_location[1])

        if target is None:
            return 0

        target_lon, target_lat = target
        return min(
            range(len(coordinates)),
            key=lambda index: (
                (coordinates[index][0] - target_lon) ** 2
                + (coordinates[index][1] - target_lat) ** 2
            ),
        )

    @staticmethod
    def _geometry_distance_m(
        coordinates: list[list[float]],
    ) -> float:
        """Calculate the length of a merged GeoJSON LineString."""

        from math import asin, cos, radians, sin, sqrt

        total = 0.0
        for first, second in zip(coordinates, coordinates[1:]):
            lon1 = radians(first[0])
            lat1 = radians(first[1])
            lon2 = radians(second[0])
            lat2 = radians(second[1])

            dlat = lat2 - lat1
            dlon = lon2 - lon1
            value = (
                sin(dlat / 2) ** 2
                + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
            )
            total += 6371000.0 * 2 * asin(min(1.0, sqrt(value)))

        return total

    async def _async_get_json(self, url: str) -> dict[str, Any]:
        """Perform one local OSRM HTTP request."""

        session = async_get_clientsession(self.hass)

        try:
            async with session.get(
                url,
                timeout=self.timeout_seconds,
            ) as response:
                if response.status != 200:
                    text = await response.text()
                    raise FordTriplogOSRMResponseError(
                        f"OSRM HTTP {response.status}: {text[:300]}"
                    )

                payload = await response.json(content_type=None)

        except FordTriplogOSRMError:
            raise
        except Exception as err:
            raise FordTriplogOSRMConnectionError(
                f"Could not reach OSRM server: {err}"
            ) from err

        if not isinstance(payload, dict):
            raise FordTriplogOSRMResponseError(
                "OSRM returned an invalid response"
            )

        return payload

    @staticmethod
    def _format_radius(value: float) -> str:
        """Format radius compactly for the OSRM query string."""
        if float(value).is_integer():
            return str(int(value))
        return f"{value:.1f}"

    @staticmethod
    def _normalize_points(
        points: list[dict[str, Any]],
    ) -> list[tuple[float, float, int]]:
        """Validate coordinates and convert timestamps to Unix seconds."""

        normalized: list[tuple[float, float, int]] = []

        for point in points:
            if not isinstance(point, dict):
                continue

            try:
                latitude = float(point["latitude"])
                longitude = float(point["longitude"])
            except (KeyError, TypeError, ValueError):
                continue

            timestamp_value = point.get("timestamp")
            timestamp = FordTriplogOSRMClient._timestamp_to_unix(
                timestamp_value
            )
            if timestamp is None:
                continue

            normalized.append(
                (latitude, longitude, timestamp)
            )

        # OSRM expects monotonically increasing timestamps. Route files can
        # contain equivalent UTC/local ISO forms, so Unix seconds are used.
        normalized.sort(key=lambda item: item[2])

        # Avoid duplicate timestamps because OSRM matching is time ordered.
        deduplicated: list[tuple[float, float, int]] = []
        last_timestamp: int | None = None
        for item in normalized:
            if item[2] == last_timestamp:
                continue
            deduplicated.append(item)
            last_timestamp = item[2]

        return deduplicated

    @staticmethod
    def _timestamp_to_unix(value: Any) -> int | None:
        """Convert ISO/datetime route timestamp to Unix seconds."""

        if isinstance(value, datetime):
            parsed = value
        elif isinstance(value, str) and value.strip():
            parsed = dt_util.parse_datetime(value.strip())
            if parsed is None:
                return None
        else:
            return None

        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt_util.UTC)

        return int(parsed.timestamp())
