"""Separate observed energy-transfer completion from physical unplugging.

A Ford can report COMPLETED hours before the plug is disconnected.  Keep
Charge.end_time as the physical-session boundary for Ford Last Charge matching,
but use a validated COMPLETED timestamp for displayed charging end/duration.
This also corrects already archived charges without changing SQLite records.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping


def _parse_timestamp(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo is not None else None


def charge_transfer_end_time(charge: Mapping[str, Any]) -> str | None:
    """Return a proven last COMPLETED time, else the physical session end."""
    unplug_time = charge.get("end_time")
    completion_time = charge.get("completion_time")
    if not unplug_time or not completion_time:
        return unplug_time

    start = _parse_timestamp(charge.get("start_time"))
    completion = _parse_timestamp(completion_time)
    unplug = _parse_timestamp(unplug_time)
    if start is None or completion is None or unplug is None:
        return unplug_time

    # Never let invalid, stale or mismatched timestamps change a charge.
    if start <= completion <= unplug:
        return completion_time
    return unplug_time


def charge_transfer_duration_seconds(charge: Mapping[str, Any]) -> int | None:
    """Elapsed time from charge start to actual completion (or unplug fallback).

    Physical plug-session time and preconditioning pause metadata are retained
    independently.  This is elapsed charging time, not summed active-power time.
    """
    start = _parse_timestamp(charge.get("start_time"))
    end = _parse_timestamp(charge_transfer_end_time(charge))
    if start is None or end is None or end < start:
        return None
    return int((end - start).total_seconds())

def charge_plug_disconnected_time(charge: Mapping[str, Any]) -> str | None:
    """Expose unplug separately only if a distinct COMPLETED time was proven."""
    physical = charge.get("end_time")
    transfer_end = charge_transfer_end_time(charge)
    physical_dt = _parse_timestamp(physical)
    transfer_dt = _parse_timestamp(transfer_end)
    if physical_dt is not None and transfer_dt is not None:
        if transfer_dt < physical_dt:
            return physical
    return None
