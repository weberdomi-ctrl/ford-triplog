"""OSRM trip distance gate without Home Assistant dependencies."""
from __future__ import annotations

import math
from typing import Any


def skip_osrm_for_short_trip(trip_distance_km: Any, minimum_distance_km: Any = 3.0) -> bool:
    """Skip only when a known odometer distance is below a positive limit.

    Zero disables the distance gate. Unknown mileage retains existing matching.
    """
    try:
        distance = float(trip_distance_km)
        minimum = float(minimum_distance_km)
    except (TypeError, ValueError, OverflowError):
        return False
    return (
        math.isfinite(distance)
        and math.isfinite(minimum)
        and distance >= 0.0
        and minimum > 0.0
        and distance < minimum
    )
