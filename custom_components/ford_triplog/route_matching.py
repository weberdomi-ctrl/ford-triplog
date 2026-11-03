"""Shared, conservative OSRM acceptance for live trips and maintenance."""
from __future__ import annotations

from typing import Any
from math import isfinite

from .route_quality import (
    MAX_OSRM_SEGMENTS, confidence_valid, distance_m, has_quality,
    osrm_segments, segment_length_m,
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
