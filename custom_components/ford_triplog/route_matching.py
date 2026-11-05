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
    geometry_coordinates,
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


def validate_osrm_coverage(
    points: list[dict[str, Any]],
    segment: list[dict[str, Any]],
    coordinates: list[list[float]],
) -> None:
    """Reject a good *partial* OSRM match masquerading as an entire Trip.

    The first/last original points are the stored vehicle/zone Trip bounds.
    The first/last quality-filtered points and OSRM geometry must represent
    those same ends, within conservative spatial/temporal tolerances.
    """
    try:
        geometry_start = {'latitude': float(coordinates[0][1]),
                          'longitude': float(coordinates[0][0])}
        geometry_end = {'latitude': float(coordinates[-1][1]),
                        'longitude': float(coordinates[-1][0])}
        start_gap = max(distance_m(points[0], segment[0]),
                        distance_m(points[0], geometry_start))
        end_gap = max(distance_m(points[-1], segment[-1]),
                      distance_m(points[-1], geometry_end))
    except (ValueError, TypeError, IndexError, KeyError, OverflowError) as err:
        raise RouteMatchRejected('invalid_route_endpoints') from err

    if not isfinite(start_gap) or not isfinite(end_gap):
        raise RouteMatchRejected('invalid_route_endpoint_distance')
    if start_gap > MAX_OSRM_ENDPOINT_GAP_M or end_gap > MAX_OSRM_ENDPOINT_GAP_M:
        raise RouteMatchRejected(
            f'incomplete_endpoint_coverage_start_{start_gap:.0f}m_end_{end_gap:.0f}m'
        )

    # Spatial proximity alone is insufficient for short or looping trips:
    # a middle section can return near the start/end while missing minutes.
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

    One unreliable segment rejects the complete OSRM overlay, allowing the
    caller's filtered-raw display fallback. Raw trip storage is untouched.
    """
    segments = osrm_segments(points)
    if not segments:
        raise RouteMatchRejected('no_usable_gps_segment')
    if len(segments) > MAX_OSRM_SEGMENTS:
        raise RouteMatchRejected('too_many_gps_gaps')
    # Several disjoint traces never establish a *complete* drive.  Do not
    # present MultiLineString fragments as a verified full journey.
    if len(segments) != 1:
        raise RouteMatchRejected(f'incomplete_gps_gaps_{len(segments)}_segments')

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
