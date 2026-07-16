"""
Ford Triplog

Utility functions.

Version: 1.1.0-dev
"""

from __future__ import annotations

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