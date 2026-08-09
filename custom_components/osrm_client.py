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
  radius=15 m, gaps=ignore, tidy=true.
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
        """Map-match raw Ford Triplog points to the local OSM road network."""

        normalized = self._normalize_points(points)

        if len(normalized) < 2:
            raise FordTriplogOSRMResponseError(
                "At least two valid route points are required"
            )

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
            "&tidy=true"
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

        # Ford Triplog currently requests gaps=ignore and expects one route.
        # If OSRM nevertheless returns more than one matching, merge only
        # when all geometries are LineStrings.
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

        matched_count = sum(
            1 for point in tracepoints if isinstance(point, dict)
        )
        unmatched_count = sum(
            1 for point in tracepoints if point is None
        )

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
        )

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
