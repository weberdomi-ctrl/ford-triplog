"""
Ford Triplog

Charge object.

Version: 1.8.4
Release: 1.8.4 - Detailed charging costs and losses
"""

from __future__ import annotations

from typing import Any

from homeassistant.util import dt as dt_util

from .const import CHARGE_SCHEMA_VERSION, GENERATOR, VERSION


class Charge:
    """Represents one charging session."""

    def __init__(self) -> None:
        self.schema: int = CHARGE_SCHEMA_VERSION
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

        # Billed energy and charging losses
        self.energy_billed_kwh: float | None = None
        self.energy_billed_source: str = "none"
        self.charging_loss_kwh: float | None = None
        self.charging_loss_percent: float | None = None

        # Charging costs
        self.energy_cost: float | None = None
        self.session_fee: float | None = None
        self.time_fee: float | None = None
        self.blocking_fee: float | None = None
        self.parking_fee: float | None = None
        self.other_cost: float | None = None

        self.cost_total: float | None = None
        self.currency: str | None = None
        self.energy_price_per_kwh: float | None = None
        self.effective_price_per_kwh: float | None = None

        # Backward-compatible alias for effective_price_per_kwh.
        self.price_per_kwh: float | None = None

        self.cost_source: str = "none"
        self.cost_verified: bool = False
        self.receipt_filename: str | None = None

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

    def recalculate_costs(self) -> None:
        """Recalculate billed energy, charging losses and cost values."""

        self.energy_billed_kwh = self._optional_non_negative_float(
            self.energy_billed_kwh
        )
        self.energy_billed_source = str(
            self.energy_billed_source or "none"
        ).strip().lower()
        if self.energy_billed_source not in {
            "none",
            "manual",
            "receipt",
            "ocr",
            "meter",
            "estimated",
        }:
            self.energy_billed_source = "none"

        self.energy_cost = self._optional_non_negative_float(
            self.energy_cost
        )
        self.session_fee = self._optional_non_negative_float(
            self.session_fee
        )
        self.time_fee = self._optional_non_negative_float(
            self.time_fee
        )
        self.blocking_fee = self._optional_non_negative_float(
            self.blocking_fee
        )
        self.parking_fee = self._optional_non_negative_float(
            self.parking_fee
        )
        self.other_cost = self._optional_non_negative_float(
            self.other_cost
        )
        self.cost_total = self._optional_non_negative_float(
            self.cost_total
        )

        if self.currency is not None:
            normalized_currency = str(self.currency).strip().upper()
            self.currency = normalized_currency or None

        self.cost_source = str(self.cost_source or "none").strip().lower()
        if self.cost_source not in {
            "none",
            "manual",
            "ocr",
            "home_tariff",
            "work_tariff",
        }:
            self.cost_source = "none"

        self.cost_verified = bool(self.cost_verified)

        if self.receipt_filename is not None:
            normalized_filename = str(self.receipt_filename).strip()
            self.receipt_filename = normalized_filename or None

        cost_components = (
            self.energy_cost,
            self.session_fee,
            self.time_fee,
            self.blocking_fee,
            self.parking_fee,
            self.other_cost,
        )

        if any(value is not None for value in cost_components):
            self.cost_total = round(
                sum(value or 0.0 for value in cost_components),
                4,
            )

        added_energy = self._optional_non_negative_float(
            self.energy_added_kwh
        )

        self.charging_loss_kwh = None
        self.charging_loss_percent = None

        if (
            self.energy_billed_kwh is not None
            and added_energy is not None
            and self.energy_billed_kwh > 0
        ):
            self.charging_loss_kwh = round(
                self.energy_billed_kwh - added_energy,
                4,
            )
            self.charging_loss_percent = round(
                self.charging_loss_kwh
                / self.energy_billed_kwh
                * 100,
                2,
            )

        pricing_energy = (
            self.energy_billed_kwh
            if self.energy_billed_kwh is not None
            and self.energy_billed_kwh > 0
            else added_energy
        )

        self.energy_price_per_kwh = None
        self.effective_price_per_kwh = None
        self.price_per_kwh = None

        if pricing_energy is not None and pricing_energy > 0:
            if self.energy_cost is not None:
                self.energy_price_per_kwh = round(
                    self.energy_cost / pricing_energy,
                    4,
                )

            if self.cost_total is not None:
                self.effective_price_per_kwh = round(
                    self.cost_total / pricing_energy,
                    4,
                )
                self.price_per_kwh = self.effective_price_per_kwh

    @staticmethod
    def _optional_non_negative_float(
        value: Any,
    ) -> float | None:
        """Return one optional non-negative float."""

        if value is None or isinstance(value, bool):
            return None

        try:
            normalized = float(value)
        except (TypeError, ValueError):
            return None

        return max(0.0, normalized)

    def to_dict(self) -> dict[str, Any]:
        """Return the charging session as a serializable dictionary."""

        self.recalculate_costs()

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
            "energy_billed_kwh": self.energy_billed_kwh,
            "energy_billed_source": self.energy_billed_source,
            "charging_loss_kwh": self.charging_loss_kwh,
            "charging_loss_percent": self.charging_loss_percent,
            "energy_cost": self.energy_cost,
            "session_fee": self.session_fee,
            "time_fee": self.time_fee,
            "blocking_fee": self.blocking_fee,
            "parking_fee": self.parking_fee,
            "other_cost": self.other_cost,
            "cost_total": self.cost_total,
            "currency": self.currency,
            "energy_price_per_kwh": self.energy_price_per_kwh,
            "effective_price_per_kwh": self.effective_price_per_kwh,
            "price_per_kwh": self.price_per_kwh,
            "cost_source": self.cost_source,
            "cost_verified": self.cost_verified,
            "receipt_filename": self.receipt_filename,
            "include_in_statistics": self.include_in_statistics,
            "exclusion_reason": self.exclusion_reason,
            "generator": GENERATOR,
            "version": VERSION,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Charge":
        """Create a charging session from stored data."""
        charge = cls()

        charge.schema = data.get("schema", CHARGE_SCHEMA_VERSION)
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

        charge.energy_billed_kwh = data.get("energy_billed_kwh")
        charge.energy_billed_source = data.get(
            "energy_billed_source",
            "none",
        )
        charge.charging_loss_kwh = data.get("charging_loss_kwh")
        charge.charging_loss_percent = data.get(
            "charging_loss_percent"
        )

        charge.energy_cost = data.get("energy_cost")
        charge.session_fee = data.get("session_fee")
        charge.time_fee = data.get("time_fee")
        charge.blocking_fee = data.get("blocking_fee")
        charge.parking_fee = data.get("parking_fee")
        charge.other_cost = data.get("other_cost")

        charge.cost_total = data.get("cost_total")
        charge.currency = data.get("currency")
        charge.energy_price_per_kwh = data.get(
            "energy_price_per_kwh"
        )
        charge.effective_price_per_kwh = data.get(
            "effective_price_per_kwh",
            data.get("price_per_kwh"),
        )
        charge.price_per_kwh = data.get("price_per_kwh")
        charge.cost_source = data.get("cost_source", "none")
        charge.cost_verified = bool(
            data.get("cost_verified", False)
        )
        charge.receipt_filename = data.get("receipt_filename")
        charge.recalculate_costs()

        charge.include_in_statistics = bool(
            data.get("include_in_statistics", True)
        )
        charge.exclusion_reason = data.get("exclusion_reason")

        return charge
