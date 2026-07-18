"""
Ford Triplog

Charge object.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any


class Charge:
    """Represents one charging session."""

    def __init__(self) -> None:
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

    def start(
        self,
        soc,
        latitude,
        longitude,
        address,
    ) -> None:
        self.start_time = datetime.now().isoformat()

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
        self.end_time = datetime.now().isoformat()

        self.end_soc = float(soc) if soc is not None else None

        self.end_latitude = latitude
        self.end_longitude = longitude

        self.end_address = address

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Charge":
        charge = cls()
        charge.__dict__.update(data)
        return charge