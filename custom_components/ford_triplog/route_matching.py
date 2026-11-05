"""Shared, conservative OSRM acceptance for live trips and maintenance."""
from __future__ import annotations

from typing import Any
from math import isfinite

# Only a near-complete, continuous journey is a valid OSRM *full-route* overlay.
# Larger missing sections remain visible only through the quality-filtered raw
# fallback; no invented road links are drawn across GPS outages.
MAX_OSRM_ENDPOINT_GAP_M = 90.0
MAX_OSRM_ENDPOINT_TIME_GAP_S = 90.0

from .route_quality import (
    MAX_OSRM_SEGMENTS, confidence_valid, distance_m, has_quality,
    osrm_segments, segment_length_m, _time, matched_geometry_valid,
    geometry_coordinates, display_geometry, _valid_coordinate,
)


class RouteMatchRejected(ValueError):
    """The candidate would invent an unreliable road geometry."""


def validate_osrm_result(points: list[dict[str, Any]], result: Any) -> None:
    """Check segment confidence, unmatched points and plausible distance."""
    if not confidence_valid(result.confidence):
        raise RouteMatchRejected(f'low_confidence_{result.confidence}')
    distance = float(result.distance_m)
    if not isfinite(distance) or distance <= 0:
        raise RouteMatchRejected('non_positive_distance')
    if result.unmatched_tracepoints > max(1, len(points) // 5):
        raise RouteMatchRejected('too_many_unmatched_tracepoints')
    direct = distance_m(points[0], points[-1])
    if direct > 100 and (distance < direct * 0.95 or distance > direct * 8.0):
        raise RouteMatchRejected('implausible_endpoint_distance')
    # With good-speed samples, OSRM must not add implausible loops.
    raw_length = segment_length_m(points)
    if raw_length > 100 and distance > raw_length * 1.8 + 250:
        raise RouteMatchRejected('excessive_detour_relative_to_gps')


def validate_osrm_input(points: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Preflight *before* any OSRM network request.

    A quality-filtered section must cover both authoritative vehicle Trip
    endpoints spatially and temporally. Incomplete GPS is never sent to OSRM.
    """
    if not isinstance(points, list) or len(points) < 2:
        raise RouteMatchRejected('incomplete_missing_raw_endpoints')
    try:
        segments = osrm_segments(points)
    except (ValueError, TypeError, KeyError, OverflowError) as err:
        raise RouteMatchRejected('invalid_route_points') from err
    if not segments:
        raise RouteMatchRejected('incomplete_no_usable_gps_segment')
    if len(segments) > MAX_OSRM_SEGMENTS:
        raise RouteMatchRejected('incomplete_too_many_gps_gaps')
    if len(segments) != 1:
        raise RouteMatchRejected(f'incomplete_gps_gaps_{len(segments)}_segments')
    segment = segments[0]
    try:
        start_gap = distance_m(points[0], segment[0])
        end_gap = distance_m(points[-1], segment[-1])
    except (ValueError, TypeError, KeyError, OverflowError) as err:
        raise RouteMatchRejected('invalid_route_endpoints') from err
    if not isfinite(start_gap) or not isfinite(end_gap):
        raise RouteMatchRejected('invalid_route_endpoint_distance')
    if start_gap > MAX_OSRM_ENDPOINT_GAP_M or end_gap > MAX_OSRM_ENDPOINT_GAP_M:
        raise RouteMatchRejected(
            f'incomplete_endpoint_coverage_start_{start_gap:.0f}m_end_{end_gap:.0f}m'
        )
    start_at, segment_start_at = _time(points[0]), _time(segment[0])
    end_at, segment_end_at = _time(points[-1]), _time(segment[-1])
    if start_at is not None and segment_start_at is not None:
        gap_s = (segment_start_at - start_at).total_seconds()
        if gap_s < -5 or gap_s > MAX_OSRM_ENDPOINT_TIME_GAP_S:
            raise RouteMatchRejected(f'incomplete_start_time_{gap_s:.0f}s')
    if end_at is not None and segment_end_at is not None:
        gap_s = (end_at - segment_end_at).total_seconds()
        if gap_s < -5 or gap_s > MAX_OSRM_ENDPOINT_TIME_GAP_S:
            raise RouteMatchRejected(f'incomplete_end_time_{gap_s:.0f}s')
    return segment


def validate_osrm_coverage(
    points: list[dict[str, Any]],
    segment: list[dict[str, Any]],
    coordinates: list[list[float]],
) -> None:
    """Verify the OSRM geometry also covers the actual recorded endpoints."""
    validate_osrm_input(points)
    try:
        geometry_start = {'latitude': float(coordinates[0][1]),
                          'longitude': float(coordinates[0][0])}
        geometry_end = {'latitude': float(coordinates[-1][1]),
                        'longitude': float(coordinates[-1][0])}
        start_gap = distance_m(points[0], geometry_start)
        end_gap = distance_m(points[-1], geometry_end)
    except (ValueError, TypeError, IndexError, KeyError, OverflowError) as err:
        raise RouteMatchRejected('invalid_route_endpoints') from err
    if not isfinite(start_gap) or not isfinite(end_gap):
        raise RouteMatchRejected('invalid_route_endpoint_distance')
    if start_gap > MAX_OSRM_ENDPOINT_GAP_M or end_gap > MAX_OSRM_ENDPOINT_GAP_M:
        raise RouteMatchRejected(
            f'incomplete_geometry_coverage_start_{start_gap:.0f}m_end_{end_gap:.0f}m'
        )


def direct_endpoint_geometry(points: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Honest straight-line display from stored Trip boundaries, not a road."""
    if not isinstance(points, list) or len(points) < 2:
        return None
    first, last = points[0], points[-1]
    if not (isinstance(first, dict) and isinstance(last, dict)
            and _valid_coordinate(first) and _valid_coordinate(last)):
        return None
    return {'type': 'LineString', 'coordinates': [
        [float(first['longitude']), float(first['latitude'])],
        [float(last['longitude']), float(last['latitude'])],
    ]}


def choose_display_geometry(
    route: dict[str, Any],
) -> tuple[dict[str, Any] | None, str, str | None, str | None]:
    """One shared decision for the latest-route sensor and Journey maps.

    Complete verified OSRM => road geometry. If quality GPS lacks full coverage
    => direct start/end line (explicitly not a driven path). Otherwise, retain
    the normal quality-filtered raw geometry, e.g. on an OSRM server failure.
    """
    usable, status, reason = evaluate_stored_osrm_match(route)
    matched = route.get('matched_route')
    if usable and isinstance(matched, dict):
        return matched['geometry'], 'osrm', status, reason
    points = route.get('points')
    points = points if isinstance(points, list) else []
    try:
        validate_osrm_input(points)
    except RouteMatchRejected as err:
        straight = direct_endpoint_geometry(points)
        if straight is not None:
            return straight, 'direct', 'incomplete', str(err)
    return display_geometry(points), 'raw', status, reason


def evaluate_stored_osrm_match(
    route: dict[str, Any],
) -> tuple[bool, str | None, str | None]:
    """Recheck R17/legacy matches when displaying, without modifying SQLite.

    Returns (usable, status, reason). This prevents already-cached partial
    OSRM results from continuing to replace the raw display after R18.
    """
    status = route.get('osrm_match_status')
    reason = route.get('osrm_match_reason')
    matched = route.get('matched_route')
    if not isinstance(matched, dict):
        return False, status, reason
    if not matched_geometry_valid(matched):
        return False, 'rejected', 'invalid_cached_osrm_geometry'
    points = route.get('points')
    if not isinstance(points, list) or len(points) < 2:
        return False, 'incomplete', 'incomplete_missing_raw_endpoints'
    try:
        segments = osrm_segments(points)
        if len(segments) != 1:
            return False, 'incomplete', f'incomplete_gps_gaps_{len(segments)}_segments'
        coords = matched.get('geometry', {}).get('coordinates', [])
        if not isinstance(coords, list) or matched['geometry'].get('type') != 'LineString':
            return False, 'incomplete', 'incomplete_disconnected_geometry'
        validate_osrm_coverage(points, segments[0], coords)
    except RouteMatchRejected as err:
        return False, 'incomplete', str(err)
    except (ValueError, TypeError, IndexError, KeyError, OverflowError):
        return False, 'rejected', 'invalid_cached_route_points'
    if status in ('incomplete', 'rejected', 'error'):
        return False, status, reason
    return True, status or 'complete', reason


async def verified_osrm_match(client: Any, points: list[dict[str, Any]],
                              *, url: str, radius: float) -> dict[str, Any]:
    """Match only credible, contiguous sections, never bridges over outages.

    The preflight rejects incomplete traces without contacting OSRM. The
    map can then show a labelled endpoint line. Raw storage is untouched.
    """
    # The preflight rejects missing or poor-quality GPS *before* async_match.
    # No HTTP call is made for a partial track, even if its middle is good.
    segments = [validate_osrm_input(points)]

    geometries = []
    matched = unmatched = 0
    total_distance = total_duration = 0.0
    weighted_confidence = 0.0
    total_weight = 0
    for segment in segments:
        result = await client.async_match(segment)
        validate_osrm_result(segment, result)
        geometry = result.geometry
        if not isinstance(geometry, dict) or geometry.get('type') != 'LineString' or len(geometry.get('coordinates', [])) < 2:
            raise RouteMatchRejected('invalid_osrm_geometry')
        validate_osrm_coverage(points, segment, geometry['coordinates'])
        geometries.append(geometry['coordinates'])
        total_distance += float(result.distance_m)
        total_duration += float(result.duration_s)
        matched += result.matched_tracepoints
        unmatched += result.unmatched_tracepoints
        weighted_confidence += float(result.confidence) * len(segment)
        total_weight += len(segment)

    geometry = ({'type': 'LineString', 'coordinates': geometries[0]}
                if len(geometries) == 1 else
                {'type': 'MultiLineString', 'coordinates': geometries})
    return {
        'provider': 'osrm', 'url': url, 'radius_m': radius,
        'distance_m': total_distance, 'duration_s': total_duration,
        'confidence': weighted_confidence / total_weight,
        'matched_tracepoints': matched, 'unmatched_tracepoints': unmatched,
        'quality_filtered': has_quality(points),
        'matched_segments': len(segments),
        'matched_input_points': total_weight,
        'geometry': geometry,
    }
