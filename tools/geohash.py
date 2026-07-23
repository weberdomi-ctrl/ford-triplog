"""Small dependency-free geohash encoder."""
from __future__ import annotations

_BASE32 = "0123456789bcdefghjkmnpqrstuvwxyz"

def encode(latitude: float, longitude: float, precision: int = 5) -> str:
    if not -90 <= latitude <= 90:
        raise ValueError("latitude must be between -90 and 90")
    if not -180 <= longitude <= 180:
        raise ValueError("longitude must be between -180 and 180")
    if precision < 1:
        raise ValueError("precision must be at least 1")

    lat_interval = [-90.0, 90.0]
    lon_interval = [-180.0, 180.0]
    bits = (16, 8, 4, 2, 1)
    result: list[str] = []
    bit_index = 0
    character = 0
    even = True

    while len(result) < precision:
        interval = lon_interval if even else lat_interval
        value = longitude if even else latitude
        midpoint = (interval[0] + interval[1]) / 2
        if value >= midpoint:
            character |= bits[bit_index]
            interval[0] = midpoint
        else:
            interval[1] = midpoint
        even = not even
        if bit_index < 4:
            bit_index += 1
        else:
            result.append(_BASE32[character])
            bit_index = 0
            character = 0
    return "".join(result)
