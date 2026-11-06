"""Conservative OSRM route matching with gap-safe partial display (R20).

A good matched road *section* may be shown even when the original GPS trace
is incomplete. It must never be presented as a complete journey or stitched
across an unobserved GPS gap. Original recorded GPS points are unchanged.
"""
from __future__ import annotations

from math import isfinite
from typing import Any

from .route_quality import (
    MAX_OSRM_SEGMENTS, MIN_OSRM_SEGMENT_DISTANCE_M,
    MIN_OSRM_SEGMENT_POINTS, clean_segments, confidence_valid, distance_m,
    geometry_coordinates, matched_geometry_valid, segment_length_m, _time,
    display_geometry,
)

MAX_OSRM_ENDPOINT_GAP_M = 90.0
MAX_OSRM_ENDPOINT_TIME_GAP_S = 90.0


class RouteMatchRejected(ValueError):
    """An OSRM candidate was not credible enough to display."""


def validate_osrm_result(points: list[dict[str, Any]], result: Any) -> None:
    """Validate a match only against its own contiguous input segment."""
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
    raw_length = segment_length_m(points)
    if raw_length > 100 and distance > raw_length * 1.8 + 250:
        raise RouteMatchRejected('excessive_detour_relative_to_gps')


def validate_segment_geometry(
    section: list[dict[str, Any]], coordinates: list[list[float]],
) -> None:
    """OSRM must actually snap to this observed section, not a distant road."""
    try:
        first = {'latitude': float(coordinates[0][1]),
                 'longitude': float(coordinates[0][0])}
        last = {'latitude': float(coordinates[-1][1]),
                'longitude': float(coordinates[-1][0])}
        gaps = (distance_m(section[0], first), distance_m(section[-1], last))
    except (ValueError, TypeError, IndexError, KeyError, OverflowError) as err:
        raise RouteMatchRejected('invalid_segment_endpoints') from err
    if any(not isfinite(gap) or gap > MAX_OSRM_ENDPOINT_GAP_M for gap in gaps):
        raise RouteMatchRejected('osrm_segment_endpoint_mismatch')


def validate_osrm_coverage(
    points: list[dict[str, Any]],
    segment: list[dict[str, Any]],
    coordinates: list[list[float]],
) -> None:
    """Mark a match *complete* only if the trip bounds are actually covered."""
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



def choose_display_geometry(
    route: dict[str, Any],
) -> tuple[dict[str, Any] | None, str, str | None, str | None]:
    """Prefer verified OSRM sections; otherwise show observed GPS sections only.

    Never replace an incomplete GPS trace with the direct endpoint chord.
    Any absent GPS sections stay absent; archived raw points are untouched.
    """
    usable, status, reason = evaluate_stored_osrm_match(route)
    matched = route.get('matched_route')
    if usable and isinstance(matched, dict):
        return matched['geometry'], 'osrm', status, reason
    points = route.get('points')
    points = points if isinstance(points, list) else []
    geometry = display_geometry(points)
    return geometry, 'raw', status, reason


def evaluate_stored_osrm_match(
    route: dict[str, Any],
) -> tuple[bool, str | None, str | None]:
    """Accept only proven full matches or explicitly marked R20 partials.

    Legacy incomplete matches remain rejected until manually rebuilt. This
    is display-only and does not modify old SQLite records.
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
    if status in ('incomplete', 'rejected', 'error'):
        return False, status, reason

    coverage = matched.get('coverage_status')
    geom = matched.get('geometry', {})
    coords = geom.get('coordinates')
    if coverage == 'partial':
        sources = matched.get('geometry_segment_sources')
        pieces = (coords if geom.get('type') == 'MultiLineString'
                  else [coords] if geom.get('type') == 'LineString' else [])
        valid_pieces = (
            isinstance(sources, list) and len(sources) == len(pieces)
            and all(source in ('osrm', 'raw') for source in sources)
            and 'osrm' in sources and matched.get('matched_segments', 0) >= 1
            and all(isinstance(piece, list) and len(piece) >= 2
                    for piece in pieces)
        )
        if not valid_pieces or status not in (None, 'partial', 'complete'):
            return False, 'rejected', 'invalid_cached_partial_osrm'
        return True, 'partial', matched.get('coverage_reason') or reason

    # Old full-route records must still pass R18's coverage checks.
    if coverage not in (None, 'complete'):
        return False, 'rejected', 'invalid_cached_coverage_status'
    if geom.get('type') != 'LineString' or not isinstance(coords, list):
        return False, 'incomplete', 'incomplete_disconnected_geometry'
    try:
        segments = clean_segments(points)
        eligible = [s for s in segments if len(s) >= MIN_OSRM_SEGMENT_POINTS
                    and segment_length_m(s) >= MIN_OSRM_SEGMENT_DISTANCE_M]
        if len(segments) != 1 or len(eligible) != 1:
            return False, 'incomplete', f'incomplete_gps_gaps_{len(segments)}_segments'
        validate_osrm_coverage(points, eligible[0], coords)
    except RouteMatchRejected as err:
        return False, 'incomplete', str(err)
    except (ValueError, TypeError, IndexError, KeyError, OverflowError):
        return False, 'rejected', 'invalid_cached_route_points'
    return True, status or 'complete', reason


async def verified_osrm_match(client: Any, points: list[dict[str, Any]],
                              *, url: str, radius: float) -> dict[str, Any]:
    """Match credible contiguous sections; preserve breaks, never connect gaps.

    Incomplete endpoints or GPS gaps yield an explicitly PARTIAL route. Failed
    individual sections fall back to their already-filtered raw geometry.
    When every OSRM section fails, callers retain their regular raw fallback.
    """
    sections = clean_segments(points)
    if not sections:
        raise RouteMatchRejected('no_usable_gps_segment')
    if len(sections) > MAX_OSRM_SEGMENTS:
        raise RouteMatchRejected('too_many_gps_gaps')

    geometries: list[list[list[float]]] = []
    sources: list[str] = []
    matched = unmatched = 0
    distance = duration = weighted_confidence = 0.0
    confidence_weight = matched_segment_count = 0
    eligible_count = 0
    skipped_reasons: list[str] = []
    complete_coverage = False
    coverage_reason: str | None = None

    for section in sections:
        eligible = (len(section) >= MIN_OSRM_SEGMENT_POINTS
                    and segment_length_m(section) >= MIN_OSRM_SEGMENT_DISTANCE_M)
        if not eligible:
            if len(section) >= 2:
                geometries.append([[float(p['longitude']), float(p['latitude'])]
                                   for p in section])
                sources.append('raw')
            continue
        eligible_count += 1
        try:
            result = await client.async_match(section)
            validate_osrm_result(section, result)
            geometry = result.geometry
            if (not isinstance(geometry, dict)
                    or geometry.get('type') != 'LineString'
                    or not isinstance(geometry.get('coordinates'), list)
                    or len(geometry['coordinates']) < 2):
                raise RouteMatchRejected('invalid_osrm_geometry')
            coords = geometry['coordinates']
            validate_segment_geometry(section, coords)
            # Treat a single eligible source segment as complete only after
            # checking BOTH authoritative trip endpoints and timestamps.
            if len(sections) == 1:
                try:
                    validate_osrm_coverage(points, section, coords)
                    complete_coverage = True
                except RouteMatchRejected as err:
                    coverage_reason = str(err)
            geometries.append(coords)
            sources.append('osrm')
            distance += float(result.distance_m)
            duration += float(result.duration_s)
            matched += result.matched_tracepoints
            unmatched += result.unmatched_tracepoints
            weighted_confidence += float(result.confidence) * len(section)
            confidence_weight += len(section)
            matched_segment_count += 1
        except Exception as err:
            # Individual OSRM failures must not erase other valid sections.
            # Do not catch system cancellation/termination (BaseException).
            skipped_reasons.append(str(err))
            complete_coverage = False
            if len(section) >= 2:
                geometries.append([[float(p['longitude']), float(p['latitude'])]
                                   for p in section])
                sources.append('raw')

    if not matched_segment_count:
        if not eligible_count:
            raise RouteMatchRejected('no_usable_gps_segment')
        raise RouteMatchRejected('no_credible_osrm_segment')

    if not complete_coverage or len(sources) != 1 or sources[0] != 'osrm':
        status = 'partial'
        if coverage_reason is None:
            coverage_reason = (f'incomplete_gps_gaps_{len(sections)}_segments'
                               if len(sections) != 1 else
                               'incomplete_osrm_sections')
    else:
        status = 'complete'
        coverage_reason = None

    geometry = ({'type': 'LineString', 'coordinates': geometries[0]}
                if len(geometries) == 1 else
                {'type': 'MultiLineString', 'coordinates': geometries})
    return {
        'provider': 'osrm', 'url': url, 'radius_m': radius,
        'distance_m': distance, 'duration_s': duration,
        'confidence': weighted_confidence / confidence_weight,
        'matched_tracepoints': matched, 'unmatched_tracepoints': unmatched,
        'quality_filtered': True, 'matched_segments': matched_segment_count,
        'matched_input_points': confidence_weight,
        'geometry': geometry,
        'geometry_segment_sources': sources,
        'coverage_status': status,
        'coverage_reason': coverage_reason,
        'failed_osrm_segments': len(skipped_reasons),
    }
