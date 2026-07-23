"""
Ford Triplog

Utility functions.

Version: 1.3.2
"""
from __future__ import annotations

from datetime import datetime
from homeassistant.util import dt as dt_util

from typing import Any

def format_address(address: dict[str, Any] | None) -> str | None:
    """Format an address for display."""

    if not address:
        return None

    street = " ".join(
        filter(
            None,
            [
                address.get("road"),
                address.get("house_number"),
            ],
        )
    )

    city = " ".join(
        filter(
            None,
            [
                address.get("postcode"),
                address.get("city"),
            ],
        )
    )

    return "\n".join(
        filter(
            None,
            [
            street,
            city,
            ],
        )
    )


def format_address_short(address: dict[str, Any] | None) -> str | None:
    """Format a compact address."""

    if not address:
        return None

    street = " ".join(
        filter(
            None,
            [
                address.get("road"),
                address.get("house_number"),
            ],
        )
    )

    city = " ".join(
        filter(
            None,
            [
                address.get("postcode"),
                address.get("city"),
            ],
        )
    )

    return ", ".join(
        filter(
            None,
            [
                street,
                city,
            ],
        )
    )


def format_duration(seconds: int | float | None) -> str | None:
    """Convert seconds to HH:MM:SS."""

    if seconds is None:
        return None

    total_seconds = int(seconds)

    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    secs = total_seconds % 60

    return f"{hours:02}:{minutes:02}:{secs:02}"

def format_datetime(value: str | None) -> str | None:
    """Format ISO datetime for display."""

    if not value:
        return None

    try:
        dt = datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )

        dt = dt_util.as_local(dt)
        now = dt_util.now()

        if dt.date() == now.date():
            return f"Heute {dt:%H:%M}"

        if (now.date() - dt.date()).days == 1:
            return f"Gestern {dt:%H:%M}"

        return dt.strftime("%d.%m.%Y %H:%M")

    except Exception:
        return value



def format_distance(distance: float | None) -> str | None:
    """Format distance."""

    if distance is None:
        return None

    return f"{distance:.1f} km"


def safe_get(
    data: dict[str, Any] | None,
    key: str,
    default: Any = None,
) -> Any:
    """Safely read a value from a dictionary."""

    if not data:
        return default

    return data.get(key, default)