"""Conservative sanity checks for OSRM geometry, including cached routes.

Full-detail map-matching geometry must not silently bridge an unobserved
kilometre-scale GPS gap. Keep original GPS points unchanged and use the
existing observed-GPS fallback when a match fails these checks.
"""

from __future__ import annotations

from math import asin, cos, isfinite, radians, sin, sqrt
from typing import Any

# OSRM is requested with overview=full. A single 1 km+ straight hop between
# adjacent vertices is not credible as observed turn-by-turn road geometry.
MAX_OSRM_GEOMETRY_STEP_M = 1000.0


def _point_distance_m(first: Any, second: Any) -> float:
    """Distance between two GeoJSON [lon, lat] vertices (metres)."""
    try:
        lon1, lat1 = float(first[0]), float(first[1])
        lon2, lat2 = float(second[0]), float(second[1])
        if not all(isfinite(v) for v in (lon1, lat1, lon2, lat2)):
            return float("inf")
        if not all(-90 <= v <= 90 for v in (lat1, lat2)):
            return float("inf")
        if not all(-180 <= v <= 180 for v in (lon1, lon2)):
            return float("inf")
    except (IndexError, TypeError, ValueError, OverflowError):
        return float("inf")

    lat_a, lat_b = radians(lat1), radians(lat2)
    dlat = lat_b - lat_a
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(lat_a) * cos(lat_b) * sin(dlon / 2) ** 2
    return 12_742_000.0 * asin(min(1.0, sqrt(max(0.0, a))))


def largest_osrm_step_m(geometry: dict[str, Any] | None) -> float:
    """Largest adjacent-vertex step; do not bridge independent LineStrings."""
    if not isinstance(geometry, dict):
        return float("inf")

    coordinates = geometry.get("coordinates")
    if not isinstance(coordinates, list):
        return float("inf")

    geom_type = geometry.get("type")
    if geom_type == "LineString":
        segments = [coordinates]
    elif geom_type == "MultiLineString":
        segments = coordinates
    else:
        return float("inf")

    largest = 0.0
    for segment in segments:
        if not isinstance(segment, list):
            return float("inf")
        for previous, current in zip(segment, segment[1:]):
            largest = max(largest, _point_distance_m(previous, current))
    return largest


def oversized_osrm_step_m(geometry: dict[str, Any] | None) -> float | None:
    """Return the unacceptable step distance, if any."""
    largest = largest_osrm_step_m(geometry)
    return largest if largest > MAX_OSRM_GEOMETRY_STEP_M else None
