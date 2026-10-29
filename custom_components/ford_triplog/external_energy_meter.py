"""Safe snapshots and deltas from optional HA charging energy meters.

Never substitute the grid/meter value for the vehicle's FordPass energy.
"""
from __future__ import annotations

from math import isfinite


# Explicit test/session counters reset at the beginning of a new charge.
_SESSION_KINDS = {"session_counter", "session", "session_total"}


def read_energy_kwh(state, *, mode="auto"):
    """Return (kWh, kind) or None for invalid/unavailable sensor readings.

    Explicit 'session'/'total' overrides the HA meter_type attribute.
    Automatic mode recognises declared session counters; otherwise a meter
    is treated as cumulative. A single reading cannot reliably distinguish
    a session meter from a lifetime counter. Units must be known.
    """
    if mode not in ("auto", "session", "total"):
        return None
    if state is None or str(state.state).strip().lower() in {
        "", "unknown", "unavailable", "none", "null",
    }:
        return None
    unit = str(state.attributes.get("unit_of_measurement") or "").strip().lower()
    if unit not in ("kwh", "wh"):
        return None
    try:
        value = float(state.state)
    except (ValueError, TypeError, OverflowError):
        return None
    if not isfinite(value) or value < 0:
        return None
    if unit == "wh":
        value /= 1000
    raw_kind = str(state.attributes.get("meter_type") or "").strip().lower()
    if mode == "session":
        kind = "session_counter"
    elif mode == "total":
        kind = "total_counter"
    else:
        kind = "session_counter" if raw_kind in _SESSION_KINDS else "total_counter"
    return round(value, 6), kind


def charging_energy_kwh(start, end, kind, *, reset_seen=False):
    """Calculate this charge's grid energy; return None when unsafe to use.

    For session counters a monitored reset means the end reading is the
    session total. A normal (nonreset) counter uses end-start. For a
    cumulative counter, any reset invalidates the delta.
    """
    if end is None or start is None:
        return None
    try:
        a, b = float(start), float(end)
    except (ValueError, TypeError, OverflowError):
        return None
    if not all(isfinite(v) and v >= 0 for v in (a, b)):
        return None
    if reset_seen:
        if kind != "session_counter":
            return None
        result = b
    elif b < a - 0.000001:
        if kind != "session_counter":
            return None
        result = b
    else:
        result = max(0, b-a)
    if not result > 0:
        return None
    return round(result, 4)
