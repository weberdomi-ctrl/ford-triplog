"""Resolve FordPass OEM GPS timestamps without trusting HA observation time.

Keep the configured device_tracker as the coordinate source. Only pair its
position with the vehicle-specific FordPass GPS sensor if both coordinates
agree. Pure Python for regression testing without Home Assistant.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from math import asin, cos, isfinite, radians, sin, sqrt
import re
from typing import Any

GPS_PAIRING_MAX_DISTANCE_METERS = 5.0
GPS_FUTURE_TOLERANCE_SECONDS = 60


def gps_sensor_entity_id(tracker_entity_id: str | None) -> str | None:
    """Map only the exact FordPass VIN tracker pattern to its GPS sensor."""
    match = re.fullmatch(
        r"device_tracker\.(fordpass_[a-z0-9]+)_tracker",
        tracker_entity_id or "",
        flags=re.IGNORECASE,
    )
    return f"sensor.{match.group(1).lower()}_gps" if match else None


def _coordinates(lat: Any, lon: Any) -> tuple[float, float] | None:
    try:
        a, b = float(lat), float(lon)
    except (TypeError, ValueError):
        return None
    if not (isfinite(a) and isfinite(b) and -90 <= a <= 90 and -180 <= b <= 180):
        return None
    if (a, b) == (0.0, 0.0):
        return None
    return a, b


def _distance_meters(first: tuple[float, float], second: tuple[float, float]) -> float:
    lat1, lon1 = map(radians, first)
    lat2, lon2 = map(radians, second)
    x = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371000 * asin(min(1.0, sqrt(max(0.0, x))))


def _parse_utc(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    # Never invent a time zone for an OEM timestamp.
    return result.astimezone(timezone.utc) if result.tzinfo else None


def resolve_oem_gps_timestamp(
    tracker_lat: Any,
    tracker_lon: Any,
    sensor_attributes: dict[str, Any] | None,
    now: datetime,
) -> tuple[datetime | None, str]:
    """Return (OEM sample time, reason) only for matching GPS coordinates.

    Prefer gpsModuleTimestamp (when the position was sampled) over updateTime
    (when Ford published the record). No HA last_updated fallback when the
    GPS sensor exists but has mismatching, missing, or invalid data.
    """
    if not isinstance(sensor_attributes, dict):
        return None, "sensor_attributes_missing"
    tracker_pos = _coordinates(tracker_lat, tracker_lon)
    value = sensor_attributes.get("value")
    location = value.get("location") if isinstance(value, dict) else None
    sensor_pos = (
        _coordinates(location.get("lat"), location.get("lon"))
        if isinstance(location, dict) else None
    )
    if tracker_pos is None or sensor_pos is None:
        return None, "coordinates_unavailable"
    if _distance_meters(tracker_pos, sensor_pos) > GPS_PAIRING_MAX_DISTANCE_METERS:
        return None, "coordinates_mismatch"
    current = now if now.tzinfo else now.replace(tzinfo=timezone.utc)
    for field, source in (
        ("gpsModuleTimestamp", "ford_gps_module"),
        ("updateTime", "ford_update_time"),
    ):
        sampled = _parse_utc(sensor_attributes.get(field))
        if sampled is not None and sampled <= current + timedelta(
            seconds=GPS_FUTURE_TOLERANCE_SECONDS
        ):
            return sampled, source
    return None, "oem_timestamp_unavailable"


def read_independent_oem_gps_position(
    sensor_attributes: dict[str, Any] | None,
    now: datetime,
) -> dict[str, Any] | None:
    """Read a VIN-specific GPS JSON fix without using the device_tracker.

    Only use this result as *candidate evidence* for an ignition-OFF parking
    anchor. The usual tracker/GPS pairing requirement still applies to normal
    vehicle state and trip endpoints. Parking validation must independently
    corroborate this position with a recorded, accurate pre-OFF phone fix and
    the stable vehicle odometer before it becomes trusted.
    """
    if not isinstance(sensor_attributes, dict):
        return None
    value = sensor_attributes.get("value")
    location = value.get("location") if isinstance(value, dict) else None
    if not isinstance(location, dict):
        return None
    pos = _coordinates(location.get("lat"), location.get("lon"))
    if pos is None:
        return None

    sampled_at, source = resolve_oem_gps_timestamp(
        pos[0], pos[1], sensor_attributes, now,
    )
    if sampled_at is None or source not in (
        "ford_gps_module", "ford_update_time",
    ):
        return None
    return {
        "latitude": pos[0],
        "longitude": pos[1],
        "gps_updated_at": sampled_at.isoformat(),
        "gps_timestamp_source": source,
    }
