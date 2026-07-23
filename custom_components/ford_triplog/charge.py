"""
Ford Triplog

Charge object.

Version: 1.3.2
"""

from __future__ import annotations

from typing import Any

from homeassistant.util import dt as dt_util


class Charge:
    """Represents one charging session."""

    def __init__(self) -> None:
        self.schema: int = 1
        self.charge_id: str | None = None
        self.created: str | None = None

        self.start_time: str | None = None
        self.end_time: str | None = None

        self.start_soc: float | None = None
        self.end_soc: float | None = None

        self.start_latitude: float | None = None
        self.start_longitude: float | None = None

        self.end_latitude: float | None = None
        self.end_longitude: float | None = None

        self.start_address: dict[str, Any] | None = None
        self.end_address: dict[str, Any] | None = None

        self.notes: str | None = None
        self.tags: list[str] = []

        self.trip_id: str | None = None
        self.previous_trip_id: str | None = None

    def start(
        self,
        soc,
        latitude,
        longitude,
        address,
    ) -> None:
        now = dt_util.now()

        self.charge_id = now.strftime("%Y%m%dT%H%M%S")
        self.created = now.isoformat()
        self.start_time = now.isoformat()

        self.start_soc = float(soc) if soc is not None else None

        self.start_latitude = latitude
        self.start_longitude = longitude

        self.start_address = address

    def finish(
        self,
        soc,
        latitude,
        longitude,
        address,
    ) -> None:
        self.end_time = dt_util.now().isoformat()

        self.end_soc = float(soc) if soc is not None else None

        self.end_latitude = latitude
        self.end_longitude = longitude

        self.end_address = address

    def to_dict(self) -> dict[str, Any]:
        """Return the charging session as a serializable dictionary."""
        return {
            "schema": self.schema,
            "charge_id": self.charge_id,
            "created": self.created,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "start_soc": self.start_soc,
            "end_soc": self.end_soc,
            "start_latitude": self.start_latitude,
            "start_longitude": self.start_longitude,
            "end_latitude": self.end_latitude,
            "end_longitude": self.end_longitude,
            "start_address": self.start_address,
            "end_address": self.end_address,
            "notes": self.notes,
            "tags": self.tags,
            "trip_id": self.trip_id,
            "previous_trip_id": self.previous_trip_id,
            "generator": "Ford Triplog",
            "version": "1.3.0",
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Charge":
        """Create a charging session from stored data."""
        charge = cls()

        charge.schema = data.get("schema", 1)
        charge.charge_id = data.get("charge_id")
        charge.created = data.get("created")

        charge.start_time = data.get("start_time")
        charge.end_time = data.get("end_time")

        charge.start_soc = data.get("start_soc")
        charge.end_soc = data.get("end_soc")

        charge.start_latitude = data.get("start_latitude")
        charge.start_longitude = data.get("start_longitude")

        charge.end_latitude = data.get("end_latitude")
        charge.end_longitude = data.get("end_longitude")

        charge.start_address = data.get("start_address")
        charge.end_address = data.get("end_address")

        charge.notes = data.get("notes")
        charge.tags = data.get("tags", [])

        charge.trip_id = data.get("trip_id")
        charge.previous_trip_id = data.get("previous_trip_id")

        return charge
