"""Conservative vehicle parking anchor and trip-origin selection helpers.

No Home Assistant imports: the validation rules can be regression-tested without
an HA runtime. GPS recency alone does not prove that a parked vehicle moved.
"""

from __future__ import annotations

from datetime import datetime, timezone
from math import asin, cos, radians, sin, sqrt
from typing import Any

PARK_GPS_MAX_AGE_SECONDS = 30 * 60
PARK_REUSE_MAX_AGE_SECONDS = 30 * 24 * 3600
PARK_REUSE_MISSING_GPS_MAX_AGE_SECONDS = 24 * 3600
PARK_REUSE_RADIUS_METERS = 125.0
PARK_REFRESH_RADIUS_METERS = 75.0
PARK_ODOMETER_TOLERANCE_KM = 1.0


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (ValueError, TypeError):
        return None
    from math import isfinite
    return result if isfinite(result) else None


def coordinates(data: dict[str, Any] | None) -> tuple[float, float] | None:
    if not isinstance(data, dict):
        return None
    lat, lon = _number(data.get('latitude')), _number(data.get('longitude'))
    if lat is None or lon is None or not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
        return None
    if lat == 0 and lon == 0:
        return None
    return (lat, lon)


def parsed_at(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        result = value
    elif isinstance(value, str):
        try:
            result = datetime.fromisoformat(value.replace('Z', '+00:00'))
        except ValueError:
            return None
    else:
        return None
    return result if result.tzinfo is not None else result.replace(tzinfo=timezone.utc)


def distance_meters(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1 = map(radians, a)
    lat2, lon2 = map(radians, b)
    c = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371000 * asin(min(1.0, sqrt(max(0.0, c))))


def parking_snapshot(state: dict[str, Any], at: datetime) -> dict[str, Any] | None:
    """Save the vehicle's last plausible GPS *at the ignition OFF edge*."""
    coord = coordinates(state)
    gps_at = parsed_at(state.get('gps_updated_at'))
    if coord is None or gps_at is None:
        return None
    age = (at - gps_at).total_seconds()
    if age < -60 or age > PARK_GPS_MAX_AGE_SECONDS:
        return None
    return {
        'latitude': coord[0], 'longitude': coord[1],
        'ignition_off_at': at.isoformat(),
        'gps_updated_at': gps_at.isoformat(),
        'odometer': _number(state.get('odometer')),
        'source': 'vehicle_tracker_ignition_off',
    }


def parking_anchor(
    state: dict[str, Any], parking: dict[str, Any] | None, at: datetime,
) -> tuple[dict[str, Any] | None, str]:
    """Use last OFF coordinates only if age, location and odometer agree."""
    park_coord = coordinates(parking)
    if park_coord is None or not isinstance(parking, dict):
        return None, 'missing_parking_snapshot'
    parked_at = parsed_at(parking.get('ignition_off_at'))
    if parked_at is None:
        return None, 'missing_off_time'
    elapsed = (at - parked_at).total_seconds()
    if elapsed < -60 or elapsed > PARK_REUSE_MAX_AGE_SECONDS:
        return None, 'parking_too_old'

    old_odo, new_odo = _number(parking.get('odometer')), _number(state.get('odometer'))
    if old_odo is not None and new_odo is not None:
        if abs(new_odo - old_odo) > PARK_ODOMETER_TOLERANCE_KM:
            return None, 'odometer_changed'
    elif elapsed > PARK_REUSE_MISSING_GPS_MAX_AGE_SECONDS:
        return None, 'odometer_unavailable'

    live_coord = coordinates(state)
    if live_coord is None:
        if elapsed > PARK_REUSE_MISSING_GPS_MAX_AGE_SECONDS:
            return None, 'gps_missing_too_long'
        return dict(parking), 'parking_fallback_no_live_gps'

    distance = distance_meters(live_coord, park_coord)
    if distance > PARK_REUSE_RADIUS_METERS:
        return None, f'position_mismatch_{distance:.0f}m'
    return dict(parking), f'parking_confirmed_{distance:.0f}m'


def refresh_parking_snapshot(
    parking: dict[str, Any] | None, state: dict[str, Any], at: datetime,
) -> dict[str, Any] | None:
    """Accept a newer vehicle fix while still OFF, only near the parked anchor."""
    if not isinstance(parking, dict):
        return None
    new = parking_snapshot(state, at)
    if new is None or coordinates(parking) is None:
        return None
    previous_gps = parsed_at(parking.get('gps_updated_at'))
    updated_gps = parsed_at(new.get('gps_updated_at'))
    if previous_gps is None or updated_gps is None or updated_gps <= previous_gps:
        return None
    if distance_meters(coordinates(parking), coordinates(new)) > PARK_REFRESH_RADIUS_METERS:
        return None
    last_odo, current_odo = _number(parking.get('odometer')), _number(new.get('odometer'))
    if last_odo is not None and current_odo is not None and abs(last_odo - current_odo) > PARK_ODOMETER_TOLERANCE_KM:
        return None
    new['ignition_off_at'] = parking['ignition_off_at']
    new['source'] = 'vehicle_tracker_parked_refresh'
    return new
