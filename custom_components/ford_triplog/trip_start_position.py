"""Conservative vehicle parking anchor and trip-origin selection helpers.

No Home Assistant imports: the validation rules can be regression-tested without
an HA runtime. GPS recency alone does not prove that a parked vehicle moved.
"""

from __future__ import annotations

from datetime import datetime, timezone
from math import asin, cos, radians, sin, sqrt
from typing import Any

PARK_GPS_MAX_AGE_SECONDS = 30 * 60
# Keep an old, *genuine OEM-dated* OFF fix only as an untrusted candidate
# while two independent pre-OFF route fixes can corroborate the actual park.
PARK_STALE_CANDIDATE_MAX_AGE_SECONDS = 24 * 3600
PARK_REUSE_MAX_AGE_SECONDS = 30 * 24 * 3600
PARK_REUSE_MISSING_GPS_MAX_AGE_SECONDS = 24 * 3600
PARK_REUSE_RADIUS_METERS = 125.0
PARK_REFRESH_RADIUS_METERS = 75.0
PARK_ODOMETER_TOLERANCE_KM = 1.0
# FordPass may report ignition ON up to two minutes after the vehicle moved.
# Only a bounded displacement supported by odometer movement can use the saved
# parking GPS when the live REST position is already along the route.
PARK_DELAYED_ON_MAX_MOVEMENT_KM = 5.0
PARK_DELAYED_ON_MAX_ELAPSED_SECONDS = 48 * 3600
PARK_DELAYED_ON_GPS_BUFFER_METERS = 250.0
# FordConnect is polled via REST. HA last_updated is an observation time, not
# reliable evidence that Ford sampled a *new* GPS fix at that instant.
PARK_REFRESH_MAX_AFTER_OFF_SECONDS = 10 * 60
# R8: an independently timestamped Ford GPS-module fix at ignition OFF may
# corroborate a delayed (but accurate, near-stationary) phone route fix.
# Never relax the 20s limit for normal trip-end or route-only parking.
PARK_OEM_PHONE_MAX_AGE_SECONDS = 60.0
PARK_OEM_PHONE_MAX_DISTANCE_METERS = 100.0
PARK_OEM_PHONE_MAX_SPEED_MPS = 2.0
PARK_OEM_PHONE_MAX_ACCURACY_METERS = 25.0
PARK_OEM_SAMPLE_MAX_OFF_DELTA_SECONDS = 15.0
# A refreshed HA device_tracker timestamp is not proof of a fresh OEM GPS fix.
# Permit a distant parked-route correction only with TWO independent, accurate,
# near-stationary PRE-OFF phone fixes from this same recorded trip.
PARK_ROUTE_CORROBORATION_MAX_GAP_SECONDS = 45
PARK_ROUTE_CORROBORATION_MAX_DISTANCE_METERS = 80.0
PARK_ROUTE_CORROBORATION_MAX_VEHICLE_MISMATCH_METERS = 10000.0
PARK_ROUTE_CORROBORATION_MAX_SPEED_MPS = 2.0
TRUSTED_PARK_SOURCES = frozenset({
    'parked_route_fix_at_ignition_off',
    'parked_route_fix_corrob_pre_off',
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


def parking_snapshot(
    state: dict[str, Any], at: datetime, *, allow_stale: bool = False,
) -> dict[str, Any] | None:
    """Save OFF coordinates; old OEM fixes are UNTRUSTED until corroborated.

    allow_stale is reserved for real GPS module timestamps, not HA
    last_updated values. Otherwise we would lose the recorded route tail before
    R1 can verify the true parking location.
    """
    coord = coordinates(state)
    gps_at = parsed_at(state.get('gps_updated_at'))
    if coord is None or gps_at is None:
        return None
    age = (at - gps_at).total_seconds()
    limit = (
        PARK_STALE_CANDIDATE_MAX_AGE_SECONDS
        if allow_stale else PARK_GPS_MAX_AGE_SECONDS
    )
    if age < -60 or age > limit:
        return None
    unverified = age > PARK_GPS_MAX_AGE_SECONDS
    return {
        'latitude': coord[0], 'longitude': coord[1],
        'ignition_off_at': at.isoformat(),
        'gps_updated_at': gps_at.isoformat(),
        'odometer': _number(state.get('odometer')),
        'source': (
            'vehicle_tracker_stale_ignition_off' if unverified
            else 'vehicle_tracker_ignition_off'
        ),
    }


def parking_anchor(
    state: dict[str, Any], parking: dict[str, Any] | None, at: datetime,
) -> tuple[dict[str, Any] | None, str]:
    """Use last OFF coordinates only if age, location and odometer agree."""
    park_coord = coordinates(parking)
    if park_coord is None or not isinstance(parking, dict):
        return None, 'missing_parking_snapshot'
    # A five-hour-old Ford location does not become a confirmed parking
    # origin just because the next REST poll repeats identical coordinates.
    if parking.get('source') in (
        'vehicle_tracker_stale_ignition_off',
        'vehicle_tracker_pending_ignition_off',
    ):
        return None, 'stale_ignition_off_unconfirmed'
    parked_at = parsed_at(parking.get('ignition_off_at'))
    if parked_at is None:
        return None, 'missing_off_time'
    elapsed = (at - parked_at).total_seconds()
    if elapsed < -60 or elapsed > PARK_REUSE_MAX_AGE_SECONDS:
        return None, 'parking_too_old'

    old_odo, new_odo = _number(parking.get('odometer')), _number(state.get('odometer'))
    odo_delta = (
        new_odo - old_odo
        if old_odo is not None and new_odo is not None else None
    )
    if odo_delta is None and elapsed > PARK_REUSE_MISSING_GPS_MAX_AGE_SECONDS:
        return None, 'odometer_unavailable'

    live_coord = coordinates(state)
    if live_coord is None:
        if elapsed > PARK_REUSE_MISSING_GPS_MAX_AGE_SECONDS:
            return None, 'gps_missing_too_long'
        if odo_delta is not None and abs(odo_delta) > PARK_ODOMETER_TOLERANCE_KM:
            return None, 'odometer_changed_without_live_gps'
        return dict(parking), 'parking_fallback_no_live_gps'

    distance = distance_meters(live_coord, park_coord)
    if (distance <= PARK_REUSE_RADIUS_METERS
            and (odo_delta is None or abs(odo_delta) <= PARK_ODOMETER_TOLERANCE_KM)):
        return dict(parking), f'parking_confirmed_{distance:.0f}m'

    # The delayed ignition-ON edge may already show the vehicle driving away.
    # Preserve the actual parked coordinate, but only if the odometer confirms
    # a short, physically plausible distance from the saved parking fix.
    if (
        odo_delta is not None
        and 0 <= odo_delta <= PARK_DELAYED_ON_MAX_MOVEMENT_KM
        and elapsed <= PARK_DELAYED_ON_MAX_ELAPSED_SECONDS
        and distance <= (
            odo_delta * 1000 + PARK_DELAYED_ON_GPS_BUFFER_METERS
        )
    ):
        return dict(parking), f'parking_delayed_rest_{distance:.0f}m'

    if odo_delta is not None and abs(odo_delta) > PARK_ODOMETER_TOLERANCE_KM:
        return None, 'odometer_changed'
    return None, f'position_mismatch_{distance:.0f}m'


def pending_ignition_off_parking_snapshot(
    state: dict[str, Any], at: datetime,
) -> dict[str, Any] | None:
    """Preserve the OFF edge even when tracker and Ford GPS disagree.

    A VIN-matched GPS sensor may refresh before its device_tracker (or vice
    versa), leaving gps_updated_at=None at precisely the ignition-OFF edge.
    This candidate is never eligible as the next Trip start without separate
    corroboration by the genuine OEM sample and recorded pre-OFF phone GPS.
    """
    coord = coordinates(state)
    odo = _number(state.get('odometer'))
    if coord is None and odo is None:
        return None
    gps_at = (
        parsed_at(state.get('gps_updated_at'))
        if state.get('gps_timestamp_source') in (
            'ford_gps_module', 'ford_update_time',
        ) else None
    )
    return {
        'latitude': coord[0] if coord else None,
        'longitude': coord[1] if coord else None,
        'ignition_off_at': at.isoformat(),
        'gps_updated_at': gps_at.isoformat() if gps_at else None,
        'odometer': odo,
        'source': 'vehicle_tracker_pending_ignition_off',
    }


def latest_pre_off_route_point(
    points: list[dict[str, Any]] | None,
    off_at: datetime | None,
    *,
    max_age_seconds: float = 20.0,
) -> dict[str, Any] | None:
    """Select a genuine pre-OFF route fix. Normal callers use 20 seconds.

    The last tracked point can be recorded a few seconds AFTER the ignition
    edge (while the Companion App keeps updating). Never use such a point to
    corroborate an earlier parking location.
    """
    if not isinstance(points, list) or not isinstance(off_at, datetime):
        return None
    best: dict[str, Any] | None = None
    best_time: datetime | None = None
    for point in points:
        if not isinstance(point, dict) or coordinates(point) is None:
            continue
        point_time = parsed_at(point.get('timestamp'))
        accuracy = _number(point.get('gps_accuracy'))
        speed = _number(point.get('speed'))
        age = (off_at - point_time).total_seconds() if point_time else None
        delayed = age is not None and age > 20
        # Do not let a newer but still moving/low-quality fix mask an older
        # stationary route point eligible for the strict OEM corroboration.
        accuracy_limit = PARK_OEM_PHONE_MAX_ACCURACY_METERS if delayed else 35.0
        speed_limit = PARK_OEM_PHONE_MAX_SPEED_MPS if delayed else 5.0
        if (
            age is None or not 0 <= age <= max_age_seconds
            or accuracy is None or not 0 < accuracy <= accuracy_limit
            or speed is None or not 0 <= speed <= speed_limit
        ):
            continue
        if best_time is None or point_time > best_time:
            best, best_time = point, point_time
    return dict(best) if best is not None else None


def confirmed_post_off_oem_parking_fix(
    parking: dict[str, Any] | None,
    state: dict[str, Any],
    at: datetime,
    *,
    route_point: dict[str, Any] | None,
    allow_delayed_phone: bool = False,
) -> dict[str, Any] | None:
    """Promote a stale OFF candidate only with matching fresh Ford and route GPS.

    FordPass may update its GPS JSON and device_tracker seconds *after* the
    ignition-OFF event. A 36 km-old coordinate must not become a permanent
    parking origin if the newly sampled Ford position and the recorded trip's
    last accurate route point independently agree on the real endpoint.

    This intentionally requires a genuine VIN-paired OEM timestamp, a
    near-OFF recorded route point, and a stable vehicle odometer. A phone
    location captured after ignition OFF or a newer HA last_updated alone is
    insufficient, and verified parking anchors are never replaced here.
    """
    if (
        not isinstance(parking, dict)
        or parking.get('source') not in (
            'vehicle_tracker_stale_ignition_off',
            'vehicle_tracker_pending_ignition_off',
        )
        or not isinstance(state, dict)
        or state.get('gps_timestamp_source') not in (
            'ford_gps_module', 'ford_update_time',
        )
        or not isinstance(route_point, dict)
    ):
        return None

    off_at = parsed_at(parking.get('ignition_off_at'))
    oem_at = parsed_at(state.get('gps_updated_at'))
    original_at = parsed_at(parking.get('gps_updated_at'))
    route_at = parsed_at(route_point.get('timestamp'))
    if None in (off_at, oem_at, route_at):
        return None

    phone_age = (off_at - route_at).total_seconds()
    extended_phone = phone_age > 20.0
    max_phone_age = (
        PARK_OEM_PHONE_MAX_AGE_SECONDS if allow_delayed_phone else 20.0
    )

    # The OEM fix is allowed to be delivered late, but its *measurement* must
    # belong to this ignition-OFF window, not to an earlier stop or a later trip.
    if not (
        0 <= (at - off_at).total_seconds() <= PARK_REFRESH_MAX_AFTER_OFF_SECONDS
        and -120 <= (oem_at - off_at).total_seconds() <= 120
        and (original_at is None or oem_at > original_at)
        # Ford may deliver an OFF-time sample several minutes after the edge.
        # Sampling near OFF + a matching independent route fix are the proof,
        # not the age of the Home Assistant update that delivered the sample.
        and -60 <= (at - oem_at).total_seconds() <= (
            PARK_REFRESH_MAX_AFTER_OFF_SECONDS + 120
        )
        and 0 <= phone_age <= max_phone_age
    ):
        return None
    # An older phone fix can corroborate only an actual Ford GPS-MODULE
    # measurement at the ignition edge. A Ford publication/updateTime or HA
    # observation timestamp is not enough to extend the normal 20s window.
    if extended_phone and not (
        allow_delayed_phone
        and state.get('gps_timestamp_source') == 'ford_gps_module'
        and abs((oem_at - off_at).total_seconds())
        <= PARK_OEM_SAMPLE_MAX_OFF_DELTA_SECONDS
    ):
        return None

    vehicle_coord = coordinates(state)
    route_coord = coordinates(route_point)
    if vehicle_coord is None or route_coord is None:
        return None
    # The phone is not permitted to override the vehicle by kilometres:
    # both sources must now confirm the same end location independently.
    distance_limit = (
        PARK_OEM_PHONE_MAX_DISTANCE_METERS
        if extended_phone else PARK_REUSE_RADIUS_METERS
    )
    if distance_meters(vehicle_coord, route_coord) > distance_limit:
        return None

    accuracy = _number(route_point.get('gps_accuracy'))
    speed = _number(route_point.get('speed'))
    accuracy_limit = (
        PARK_OEM_PHONE_MAX_ACCURACY_METERS if extended_phone else 35.0
    )
    speed_limit = (
        PARK_OEM_PHONE_MAX_SPEED_MPS if extended_phone else 5.0
    )
    if not (
        accuracy is not None and 0 < accuracy <= accuracy_limit
        and speed is not None and 0 <= speed <= speed_limit
    ):
        return None

    old_odo = _number(parking.get('odometer'))
    new_odo = _number(state.get('odometer'))
    if (
        old_odo is None or new_odo is None
        or abs(new_odo - old_odo) > PARK_ODOMETER_TOLERANCE_KM
    ):
        return None

    confirmed = dict(parking)
    confirmed.update({
        'latitude': vehicle_coord[0],
        'longitude': vehicle_coord[1],
        'gps_updated_at': oem_at.isoformat(),
        'odometer': new_odo,
        'source': 'vehicle_oem_route_confirmed_post_off',
    })
    return confirmed


def refresh_parking_snapshot(
    parking: dict[str, Any] | None, state: dict[str, Any], at: datetime,
) -> dict[str, Any] | None:
    """Accept a newer vehicle fix while still OFF, only near the parked anchor."""
    if not isinstance(parking, dict):
        return None
    # A pending OFF candidate must never become a trusted snapshot via the
    # ordinary proximity-only refresh path; it needs OEM + route proof.
    if parking.get('source') == 'vehicle_tracker_pending_ignition_off':
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


def corroborated_parked_route_fix(
    route_point: dict[str, Any] | None,
    route_points: list[dict[str, Any]] | None,
    off_at: datetime,
    off_coord: tuple[float, float] | None,
    parked_odometer: float | None,
    stable_odometer: float | None,
) -> bool:
    """Verify independent pre-OFF route fixes before overruling distant OEM GPS.

    A tracker updated in Home Assistant can report a NEW last_updated while
    still carrying the OLD vehicle coordinate. A single phone position is not
    enough to override it by kilometres: require two consecutive high-quality
    slow route fixes, both captured during the ending trip before ignition OFF,
    and a stable post-OFF odometer. Post-OFF phone travel is never accepted.
    """
    if (
        not isinstance(route_point, dict)
        or not isinstance(route_points, list)
        or len(route_points) < 2
        or off_coord is None
        or parked_odometer is None
        or stable_odometer is None
        or abs(stable_odometer - parked_odometer) > PARK_ODOMETER_TOLERANCE_KM
    ):
        return False

    prior, latest = route_points[-2:]
    if not isinstance(prior, dict) or not isinstance(latest, dict):
        return False
    latest_coord = coordinates(latest)
    candidate_coord = coordinates(route_point)
    prior_coord = coordinates(prior)
    if latest_coord is None or prior_coord is None or candidate_coord is None:
        return False
    # Never promote an older or different point if the route progressed.
    if distance_meters(candidate_coord, latest_coord) > 1.0:
        return False
    vehicle_mismatch = distance_meters(off_coord, latest_coord)
    if not (PARK_REUSE_RADIUS_METERS < vehicle_mismatch
            <= PARK_ROUTE_CORROBORATION_MAX_VEHICLE_MISMATCH_METERS):
        return False

    times = [parsed_at(point.get('timestamp')) for point in (prior, latest)]
    if any(stamp is None for stamp in times):
        return False
    earlier, later = times
    gaps = ((off_at - earlier).total_seconds(),
            (off_at - later).total_seconds(),
            (later - earlier).total_seconds())
    if not (
        0 <= gaps[1] <= 20
        and 0 <= gaps[0] <= 60
        and 1 <= gaps[2] <= PARK_ROUTE_CORROBORATION_MAX_GAP_SECONDS
    ):
        return False

    if distance_meters(prior_coord, latest_coord) > PARK_ROUTE_CORROBORATION_MAX_DISTANCE_METERS:
        return False
    for point in (prior, latest):
        accuracy = _number(point.get('gps_accuracy'))
        speed = _number(point.get('speed'))
        if not (
            accuracy is not None and 0 < accuracy <= 25
            and speed is not None and 0 <= speed <= PARK_ROUTE_CORROBORATION_MAX_SPEED_MPS
        ):
            return False
    return True


def stabilize_parking_snapshot(
    parking: dict[str, Any] | None,
    stable_state: dict[str, Any],
    at: datetime,
    *,
    route_point: dict[str, Any] | None = None,
    route_points: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """Reconcile the OFF anchor with the stable vehicle odometer/last GPS.

    The vehicle (not a phone after leaving the car) may report its final GPS
    late. No subsequent trip must be allowed to rewrite an older OFF anchor.
    Route GPS is a tightly bounded fallback captured BEFORE ignition OFF.
    """
    if not isinstance(parking, dict):
        return None
    off_at = parsed_at(parking.get('ignition_off_at'))
    if off_at is None or not (-10 <= (at - off_at).total_seconds() <= 15 * 60):
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
        # A delayed REST fix may still refer to a point travelled up to
        # two minutes before ignition OFF. Only an accurate, slow, recent
        # route point is eligible for this expanded fallback distance.
        radius = (
            150 if vehicle_age <= 30
            else min(4000.0, max(600.0, vehicle_age * 35.0))
        )
        corroborated = corroborated_parked_route_fix(
            route_point, route_points, off_at, off_coord, old_odo, stable_odo
        )
        # HA tracker.last_updated can be fresh even when its vehicle position
        # is 6 km old. Only a corroborated, stationary pre-OFF phone trace may
        # overrule that apparent freshness and the normal 150 m radius.
        normal_route_fix = (
            parking.get('source') not in (
                'vehicle_tracker_stale_ignition_off',
                'vehicle_tracker_pending_ignition_off',
            )
            and point_coord is not None
            and distance_meters(off_coord, point_coord) <= radius
            and (original_gps_at is None or point_time > original_gps_at)
        )
        if (point_coord is not None and 0 <= gap <= 20
                and accuracy is not None and 0 < accuracy <= 25
                and speed is not None and 0 <= speed <= 5
                and (normal_route_fix or corroborated)):
            result['latitude'], result['longitude'] = point_coord
            result['gps_updated_at'] = point_time.isoformat()
            result['source'] = (
                'parked_route_fix_corrob_pre_off'
                if corroborated and not normal_route_fix
                else 'parked_route_fix_at_ignition_off'
            )
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
    # Once an independent high-quality route trace corrected an obviously
    # stale vehicle position, do not immediately overwrite it with the same
    # stale OEM coordinate just because the HA entity timestamp moved on.
    corrected_route_coord = coordinates(result)
    vehicle_agrees_with_route = (
        result.get('source') not in (
            'parked_route_fix_at_ignition_off',
            'parked_route_fix_corrob_pre_off',
        )
        or (
            corrected_route_coord is not None
            and vehicle_coord is not None
            and distance_meters(corrected_route_coord, vehicle_coord)
            <= PARK_REUSE_RADIUS_METERS
        )
    )
    if (vehicle_coord is not None and vehicle_gps_at is not None
            and parking.get('source') != 'vehicle_tracker_pending_ignition_off'
            and vehicle_agrees_with_route
            and off_at.timestamp() - 120 <= vehicle_gps_at.timestamp()
            and vehicle_gps_at <= at
            and (at - vehicle_gps_at).total_seconds() <= 180
            and (newer_fix or odo_corroborated)
            # A new HA last_updated with identical GPS coordinates is NOT
            # independent evidence of a new OEM position.
            and vehicle_distance is not None
            and (vehicle_distance >= 5.0 or odo_corroborated)
            and (vehicle_distance <= 2000 or odo_corroborated)):
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
