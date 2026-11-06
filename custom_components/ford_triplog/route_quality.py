"""GPS quality and stationary-drift filtering for *display/matching only*.

The original recorded route is never modified. Missing quality attributes on
legacy/ABRP routes retain the old behavior. Bad reception can create real gaps:
we preserve these rather than constructing roads between unrelated fixes.
"""
from __future__ import annotations

from datetime import datetime, timezone
from math import asin, cos, isfinite, radians, sin, sqrt
from typing import Any

MAX_MATCH_ACCURACY_M = 35.0
MAX_GAP_SECONDS = 45.0
MIN_OSRM_SEGMENT_POINTS = 3
MIN_OSRM_SEGMENT_DISTANCE_M = 35.0
MAX_OSRM_SEGMENTS = 12
MIN_OSRM_CONFIDENCE = 0.20


def numeric(value: Any) -> float | None:
    try:
        if isinstance(value, bool):
            return None
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) else None


def distance_m(a: dict[str, Any], b: dict[str, Any]) -> float:
    lat1 = radians(float(a['latitude']))
    lat2 = radians(float(b['latitude']))
    dlat = lat2 - lat1
    dlon = radians(float(b['longitude']) - float(a['longitude']))
    t = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 12742000.0 * asin(min(1.0, sqrt(max(0.0, t))))


def _time(point: dict[str, Any]) -> datetime | None:
    value = point.get('timestamp')
    try:
        if isinstance(value, datetime):
            result = value
        else:
            result = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except (ValueError, TypeError):
        return None
    return result if result.tzinfo else result.replace(tzinfo=timezone.utc)


def _valid_coordinate(point: dict[str, Any]) -> bool:
    lat, lon = numeric(point.get('latitude')), numeric(point.get('longitude'))
    return (lat is not None and lon is not None and -90 <= lat <= 90
            and -180 <= lon <= 180 and (lat != 0 or lon != 0))


def normalize_tracker_attributes(attributes: dict[str, Any]) -> dict[str, float]:
    """Copy optional Companion App metadata; m/s, metres, degrees."""
    result: dict[str, float] = {}
    accuracy = numeric(attributes.get('gps_accuracy'))
    # Zero is frequently an unavailable fix, NOT zero-metre precision.
    if accuracy is not None and accuracy > 0:
        result['gps_accuracy'] = accuracy
    elif attributes.get('gps_accuracy') is not None:
        result['gps_accuracy'] = 0.0
    speed = numeric(attributes.get('speed'))
    if speed is not None and speed >= 0:
        result['speed'] = speed
    course = numeric(attributes.get('course'))
    if course is not None and 0 <= course <= 360:
        result['course'] = course
    return result


def has_quality(points: list[dict[str, Any]]) -> bool:
    # Speed without accuracy is not enough for reliable filtering. Preserve
    # legacy behaviour for trackers that expose only speed or no metadata.
    return any(isinstance(p, dict) and 'gps_accuracy' in p for p in points)


def clean_segments(points: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Remove poor fixes and split unobserved/implausible connections.

    Synthetic vehicle endpoints have no phone quality information and are not
    connected blindly to the good phone trace. They remain in the raw storage.
    """
    available = [p for p in points if isinstance(p, dict) and _valid_coordinate(p)]
    if not available:
        return []
    if not has_quality(available):
        return [available]  # Legacy and non-Companion sources: unchanged.

    segments: list[list[dict[str, Any]]] = []
    segment: list[dict[str, Any]] = []
    previous: dict[str, Any] | None = None
    previous_time: datetime | None = None
    for point in available:
        accuracy = numeric(point.get('gps_accuracy'))
        # GPS accuracy absent/0/beyond 35m must not drive OSRM.
        if accuracy is None or accuracy <= 0 or accuracy > MAX_MATCH_ACCURACY_M:
            continue
        point_time = _time(point)
        if point_time is None:
            continue
        if previous is not None and previous_time is not None:
            elapsed = (point_time - previous_time).total_seconds()
            separation = distance_m(previous, point)
            prev_accuracy = numeric(previous.get('gps_accuracy')) or accuracy
            speed = max(numeric(point.get('speed')) or 0,
                        numeric(previous.get('speed')) or 0)
            # Repeated Recorder updates can carry the exact same fix/time.
            # They must not split an otherwise continuous route.
            if elapsed == 0 and separation < 0.8:
                continue
            # Movement over a long GPS outage must not become a straight line.
            discontinuity = (
                elapsed <= 0 or elapsed > MAX_GAP_SECONDS
                or separation > max(55.0, speed * elapsed * 2.2
                                  + 0.7 * (accuracy + prev_accuracy) + 15.0)
            )
            if discontinuity:
                if segment:
                    segments.append(segment)
                segment = []
            elif separation < 0.8:
                continue
            elif speed <= 0.75 and separation <= max(30.0, accuracy + prev_accuracy):
                # Typical stationary jitter. Advance observation time without
                # adding an artificial route movement or splitting the stop.
                previous_time = point_time
                continue
        segment.append(point)
        previous = point
        previous_time = point_time
    if segment:
        segments.append(segment)
    return segments


def segment_length_m(segment: list[dict[str, Any]]) -> float:
    return sum(distance_m(a, b) for a, b in zip(segment, segment[1:]))


def osrm_segments(points: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Return coherent sections of sufficient length for OSRM."""
    return [segment for segment in clean_segments(points)
            if len(segment) >= MIN_OSRM_SEGMENT_POINTS
            and segment_length_m(segment) >= MIN_OSRM_SEGMENT_DISTANCE_M]


def display_geometry(points: list[dict[str, Any]]) -> dict[str, Any] | None:
    """GeoJSON LineString/MultiLineString; never draw across bad GPS gaps."""
    segments = clean_segments(points)
    kept = [s for s in segments if len(s) >= 2]
    if not kept:
        return None
    coordinates = [
        [[float(p['longitude']), float(p['latitude'])] for p in segment]
        for segment in kept
    ]
    if len(coordinates) == 1:
        return {'type': 'LineString', 'coordinates': coordinates[0]}
    return {'type': 'MultiLineString', 'coordinates': coordinates}


def geometry_coordinates(geometry: dict[str, Any] | None) -> list[list[float]]:
    """Flatten valid GeoJSON for existing centre/start/end sensor attributes."""
    if not isinstance(geometry, dict):
        return []
    coordinates = geometry.get('coordinates')
    if not isinstance(coordinates, list):
        return []
    if geometry.get('type') == 'MultiLineString':
        return [point for segment in coordinates if isinstance(segment, list)
                for point in segment if isinstance(point, list) and len(point) >= 2]
    if geometry.get('type') == 'LineString':
        return [point for point in coordinates if isinstance(point, list) and len(point) >= 2]
    return []


def confidence_valid(value: Any) -> bool:
    val = numeric(value)
    return val is not None and val >= MIN_OSRM_CONFIDENCE and val <= 1.0


def matched_geometry_valid(matched: dict[str, Any] | None) -> bool:
    if not isinstance(matched, dict) or matched.get('provider') != 'osrm':
        return False
    geometry = matched.get('geometry')
    return (confidence_valid(matched.get('confidence'))
            and len(geometry_coordinates(geometry)) >= 2)
