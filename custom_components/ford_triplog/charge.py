"""
Ford Triplog

Charge object.

Version: 1.5.0
"""

from __future__ import annotations

from typing import Any

from homeassistant.util import dt as dt_util


class Charge:
    """Represents one charging session."""

    def __init__(self) -> None:
        self.schema: int = 3
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

        self.charging_site_id: str | None = None
        self.charging_site_name: str | None = None
        self.charging_site_brand: str | None = None
        self.charging_site_operator: str | None = None
        self.charging_site_network: str | None = None
        self.charging_site_power_kw: list[float] = []
        self.charging_site_capacity: list[str] = []
        self.charging_site_connectors: list[str] = []
        self.charging_site_quality: str | None = None
        self.charging_site_distance_m: float | None = None

        # FordPass Last Charge data is initially retained as a complete raw
        # snapshot. Field-by-field normalization follows in the next phase.
        self.fordpass_last_charge: dict[str, Any] | None = None
        self.last_charge_baseline_signature: str | None = None
        self.fordpass_pending: bool = False
        self.data_source: str = "local"

        self.energy_added_kwh: float | None = None
        self.energy_added_kwh_fordpass: float | None = None
        self.energy_added_kwh_calculated: float | None = None
        self.energy_source: str = "calculated"

        self.include_in_statistics: bool = True
        self.exclusion_reason: str | None = None


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
            "charging_site_id": self.charging_site_id,
            "charging_site_name": self.charging_site_name,
            "charging_site_brand": self.charging_site_brand,
            "charging_site_operator": self.charging_site_operator,
            "charging_site_network": self.charging_site_network,
            "charging_site_power_kw": self.charging_site_power_kw,
            "charging_site_capacity": self.charging_site_capacity,
            "charging_site_connectors": self.charging_site_connectors,
            "charging_site_quality": self.charging_site_quality,
            "charging_site_distance_m": self.charging_site_distance_m,
            "fordpass_last_charge": self.fordpass_last_charge,
            "last_charge_baseline_signature": (
                self.last_charge_baseline_signature
            ),
            "fordpass_pending": self.fordpass_pending,
            "data_source": self.data_source,
            "energy_added_kwh": self.energy_added_kwh,
            "energy_added_kwh_fordpass": self.energy_added_kwh_fordpass,
            "energy_added_kwh_calculated": (
                self.energy_added_kwh_calculated
            ),
            "energy_source": self.energy_source,
            "include_in_statistics": self.include_in_statistics,
            "exclusion_reason": self.exclusion_reason,
            "generator": "Ford Triplog",
            "version": "1.5.0",
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

        charge.charging_site_id = data.get("charging_site_id")
        charge.charging_site_name = data.get("charging_site_name")
        charge.charging_site_brand = data.get("charging_site_brand")
        charge.charging_site_operator = data.get("charging_site_operator")
        charge.charging_site_network = data.get("charging_site_network")
        charge.charging_site_power_kw = data.get("charging_site_power_kw", [])
        charge.charging_site_capacity = data.get("charging_site_capacity", [])
        charge.charging_site_connectors = data.get("charging_site_connectors", [])
        charge.charging_site_quality = data.get("charging_site_quality")
        charge.charging_site_distance_m = data.get("charging_site_distance_m")

        charge.fordpass_last_charge = data.get("fordpass_last_charge")
        charge.last_charge_baseline_signature = data.get(
            "last_charge_baseline_signature"
        )
        charge.fordpass_pending = bool(
            data.get("fordpass_pending", False)
        )
        charge.data_source = data.get("data_source", "local")

        charge.energy_added_kwh = data.get("energy_added_kwh")
        charge.energy_added_kwh_fordpass = data.get(
            "energy_added_kwh_fordpass"
        )
        charge.energy_added_kwh_calculated = data.get(
            "energy_added_kwh_calculated"
        )
        charge.energy_source = data.get(
            "energy_source",
            (
                "fordpass"
                if charge.energy_added_kwh_fordpass is not None
                else "calculated"
            ),
        )

        charge.include_in_statistics = bool(
            data.get("include_in_statistics", True)
        )
        charge.exclusion_reason = data.get("exclusion_reason")

        return charge
