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
# FordConnect is polled via REST. HA last_updated is an observation time, not
# reliable evidence that Ford sampled a *new* GPS fix at that instant.
PARK_REFRESH_MAX_AFTER_OFF_SECONDS = 10 * 60
TRUSTED_PARK_SOURCES = frozenset({
    'parked_route_fix_at_ignition_off',
    'vehicle_tracker_odometer_confirmed_parked_fix',
})
ZONE_ANCHOR_MAX_RADIUS_METERS = 150.0
CHARGE_START_MAX_AGE_SECONDS = 3 * 3600
CHARGE_SITE_MAX_MATCH_METERS = 30.0
CHARGE_SITE_MAX_VEHICLE_DISTANCE_METERS = 180.0


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
    off_time = parsed_at(parking.get('ignition_off_at'))
    if off_time is None or not (0 <= (at - off_time).total_seconds() <= PARK_REFRESH_MAX_AFTER_OFF_SECONDS):
        return None
    if previous_gps is None or updated_gps is None or updated_gps <= previous_gps:
        return None
    shift_m = distance_meters(coordinates(parking), coordinates(new))
    # Do not turn each identical 60s REST response into a 'fresh' GPS fix.
    if shift_m < 5.0 or shift_m > PARK_REFRESH_RADIUS_METERS:
        return None
    last_odo, current_odo = _number(parking.get('odometer')), _number(new.get('odometer'))
    if last_odo is not None and current_odo is not None and abs(last_odo - current_odo) > PARK_ODOMETER_TOLERANCE_KM:
        return None
    new['ignition_off_at'] = parking['ignition_off_at']
    new['source'] = 'vehicle_tracker_parked_refresh'
    return new


def stabilize_parking_snapshot(
    parking: dict[str, Any] | None,
    stable_state: dict[str, Any],
    at: datetime,
    *,
    route_point: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Reconcile the OFF anchor with the stable vehicle odometer/last GPS.

    The vehicle (not a phone after leaving the car) may report its final GPS
    late. No subsequent trip must be allowed to rewrite an older OFF anchor.
    Route GPS is a tightly bounded fallback captured BEFORE ignition OFF.
    """
    if not isinstance(parking, dict):
        return None
    off_at = parsed_at(parking.get('ignition_off_at'))
    if off_at is None or not (-10 <= (at - off_at).total_seconds() <= 7 * 60):
        return None
    result = dict(parking)
    changed = False

    stable_odo = _number(stable_state.get('odometer'))
    old_odo = _number(parking.get('odometer'))
    if (stable_odo is not None and
            (old_odo is None or stable_odo >= old_odo - 0.5) and
            stable_odo != old_odo):
        result['odometer'] = stable_odo
        changed = True

    off_coord = coordinates(parking)
    original_gps_at = parsed_at(parking.get('gps_updated_at'))

    # A pre-OFF phone fix may be a better parking position than a vehicle fix
    # 60s old. Require a close, accurate and nearly stationary phone fix;
    # never read live post-OFF phone positions as parking coordinates.
    if isinstance(route_point, dict) and off_coord is not None:
        point_coord = coordinates(route_point)
        point_time = parsed_at(route_point.get('timestamp'))
        accuracy = _number(route_point.get('gps_accuracy'))
        speed = _number(route_point.get('speed'))
        gap = (off_at - point_time).total_seconds() if point_time else 9999
        vehicle_age = ((off_at - original_gps_at).total_seconds()
                       if original_gps_at else 9999)
        radius = 150 if vehicle_age <= 30 else 600
        if (point_coord is not None and 0 <= gap <= 20
                and accuracy is not None and 0 < accuracy <= 25
                and speed is not None and 0 <= speed <= 5
                and distance_meters(off_coord, point_coord) <= radius
                and (original_gps_at is None or point_time > original_gps_at)):
            result['latitude'], result['longitude'] = point_coord
            result['gps_updated_at'] = point_time.isoformat()
            result['source'] = 'parked_route_fix_at_ignition_off'
            changed = True

    # Only the VEHICLE tracker is trusted to correct parking after OFF.
    # FordConnect can deliver a newer coordinate AND an advanced odometer while
    # still exposing the exact same (up to 60s stale) GPS timestamp.  In that
    # case the timestamp alone must not freeze a several-kilometre-old OFF
    # snapshot.  The odometer delta can corroborate the position change.
    vehicle_coord = coordinates(stable_state)
    vehicle_gps_at = parsed_at(stable_state.get('gps_updated_at'))
    previous_at = parsed_at(result.get('gps_updated_at'))
    vehicle_distance = (distance_meters(off_coord, vehicle_coord)
                        if off_coord is not None and vehicle_coord is not None
                        else None)
    odo_progress_km = (stable_odo - old_odo
                       if stable_odo is not None and old_odo is not None
                       else None)
    odo_corroborated = (
        vehicle_distance is not None
        and odo_progress_km is not None and odo_progress_km >= 1.0
        # Direct displacement must fit the odometer advance, with some
        # margin for GPS error. Never equate any odometer change with consent
        # to accept an unbounded GPS jump.
        and vehicle_distance <= (odo_progress_km * 1000 + 750)
        and vehicle_distance <= 10000
        and vehicle_gps_at is not None
        and previous_at is not None
        and vehicle_gps_at >= previous_at
        and (at - vehicle_gps_at).total_seconds() <= 120
    )
    newer_fix = previous_at is None or (
        vehicle_gps_at is not None and vehicle_gps_at > previous_at
    )
    if (vehicle_coord is not None and vehicle_gps_at is not None
            and off_at.timestamp() - 120 <= vehicle_gps_at.timestamp()
            and vehicle_gps_at <= at
            and (at - vehicle_gps_at).total_seconds() <= 180
            and (newer_fix or odo_corroborated)
            and (vehicle_distance is None or vehicle_distance <= 2000
                 or odo_corroborated)):
        result['latitude'], result['longitude'] = vehicle_coord
        result['gps_updated_at'] = vehicle_gps_at.isoformat()
        result['source'] = ('vehicle_tracker_odometer_confirmed_parked_fix'
                            if odo_corroborated and not newer_fix
                            else 'vehicle_tracker_stable_parked_fix')
        changed = True

    return result if changed else None


def parked_zone_origin(
    state: dict[str, Any], parking: dict[str, Any] | None,
    center: tuple[float, float], radius: float, at: datetime,
) -> dict[str, Any] | None:
    """Use a user-configured Home/Work center only for a consistent parked car.

    The zone is an independent, user-set location. Both the *current* vehicle
    reading and the preceding OFF position must agree that this is the same
    parking area, with no odometer movement. Merely being in a zone is not
    enough to move a start to the center.
    """
    coord = coordinates(state)
    parked = coordinates(parking)
    off_at = parsed_at(parking.get('ignition_off_at')) if isinstance(parking, dict) else None
    if coord is None or parked is None or off_at is None:
        return None
    if not (0 <= (at - off_at).total_seconds() <= 36 * 3600):
        return None
    if not (0 < radius <= ZONE_ANCHOR_MAX_RADIUS_METERS):
        return None
    tolerance = min(165.0, radius + 25.0)
    if distance_meters(coord, center) > tolerance or distance_meters(parked, center) > tolerance:
        return None
    odo_a = _number(state.get('odometer'))
    odo_b = _number(parking.get('odometer'))
    if odo_a is None or odo_b is None or abs(odo_a - odo_b) > PARK_ODOMETER_TOLERANCE_KM:
        return None
    return {
        'latitude': center[0], 'longitude': center[1],
        'gps_updated_at': state.get('gps_updated_at'),
        'source': 'configured_zone_center',
    }


def verified_charging_origin(
    state: dict[str, Any], charge: dict[str, Any] | None, at: datetime,
) -> dict[str, Any] | None:
    """Use a physically detected charger to locate a recently parked car.

    A named charging site with a <=30m detection match is independent support
    for the parking location, unlike identical consecutive Ford REST polls.
    """
    if not isinstance(charge, dict) or not charge.get('charging_site_id'):
        return None
    matched = _number(charge.get('charging_site_distance_m'))
    started = parsed_at(charge.get('detected_start_time') or charge.get('start_time'))
    if matched is None or matched < 0 or matched > CHARGE_SITE_MAX_MATCH_METERS or started is None:
        return None
    if not (0 <= (at - started).total_seconds() <= CHARGE_START_MAX_AGE_SECONDS):
        return None
    charge_coord = coordinates({
        'latitude': charge.get('start_latitude'),
        'longitude': charge.get('start_longitude'),
    })
    vehicle_coord = coordinates(state)
    if charge_coord is None or vehicle_coord is None:
        return None
    if distance_meters(charge_coord, vehicle_coord) > CHARGE_SITE_MAX_VEHICLE_DISTANCE_METERS:
        return None
    return {
        'latitude': charge_coord[0], 'longitude': charge_coord[1],
        'gps_updated_at': state.get('gps_updated_at'),
        'source': 'verified_charging_site',
    }
