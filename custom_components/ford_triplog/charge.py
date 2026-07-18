from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass
class Charge:
    charge_id: str
    created: str

    start_time: str
    end_time: str | None = None

    start_soc: float | None = None
    end_soc: float | None = None

    energy_kwh: float = 0.0
    duration_minutes: float = 0.0

    start_latitude: float | None = None
    start_longitude: float | None = None

    end_latitude: float | None = None
    end_longitude: float | None = None

    start_address: str | None = None
    end_address: str | None = None

    average_power_kw: float | None = None
    charging_type: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Charge":
        return cls(**data)