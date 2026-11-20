"""Charging-transfer timing, separate from the physical plug session.

The archive's start_time/end_time remain the plug-session timestamps for
Ford Last Charge correlation and journey chronology. A confirmed COMPLETED
timestamp and persisted pause periods describe actual energy-transfer time.
Older SQLite records are computed on read without a schema migration.
"""

from __future__ import annotations

from datetime import datetime
from math import isfinite
from typing import Any, Mapping


def _timestamp(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _elapsed_seconds(start: datetime | None, end: datetime | None) -> float | None:
    if start is None or end is None:
        return None
    try:
        seconds = (end - start).total_seconds()
    except (TypeError, ValueError):
        return None
    return seconds if isfinite(seconds) and seconds >= 0 else None


def charging_end_time(charge: Mapping[str, Any]) -> str | None:
    """Prefer a valid energy-transfer COMPLETED time for display only."""
    start = _timestamp(charge.get("start_time"))
    end = _timestamp(charge.get("end_time"))
    completion = _timestamp(charge.get("completion_time"))
    if (
        _elapsed_seconds(start, completion) is not None
        and _elapsed_seconds(completion, end) is not None
    ):
        return str(charge["completion_time"])
    return charge.get("end_time")


def plug_duration_seconds(charge: Mapping[str, Any]) -> int | None:
    """Duration of the whole connection, including time after charging ends."""
    elapsed = _elapsed_seconds(
        _timestamp(charge.get("start_time")),
        _timestamp(charge.get("end_time")),
    )
    return int(elapsed) if elapsed is not None else None


def charging_duration_seconds(charge: Mapping[str, Any]) -> int | None:
    """Energy-transfer duration, excluding recorded idle/paused plug time.

    For plug-aware sessions, pause_duration_seconds includes time from the
    final COMPLETED event until unplugging, plus any earlier pauses. If no
    pauses were recorded, use a valid COMPLETED timestamp directly. Legacy
    sessions without either value retain the original start-to-end duration.
    """
    connected = _elapsed_seconds(
        _timestamp(charge.get("start_time")),
        _timestamp(charge.get("end_time")),
    )
    if connected is None:
        return None

    try:
        paused = float(charge.get("pause_duration_seconds") or 0)
    except (TypeError, ValueError):
        paused = 0.0
    if isfinite(paused) and 0 < paused <= connected:
        return max(0, int(connected - paused))

    transfer_end = _timestamp(charging_end_time(charge))
    elapsed = _elapsed_seconds(_timestamp(charge.get("start_time")), transfer_end)
    return int(elapsed) if elapsed is not None else int(connected)
