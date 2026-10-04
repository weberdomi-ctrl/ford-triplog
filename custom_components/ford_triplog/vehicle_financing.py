"""Vehicle financing storage and TCO calculations for Ford Triplog."""

from __future__ import annotations

import functools
import sqlite3
import time
from calendar import monthrange
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant

from .database import FordTriplogDatabase

SUPPORTED_FINANCING_TYPES = {"leasing", "purchase", "financing", "loan"}


@dataclass(frozen=True)
class FinancingCostSummary:
    """Real-payment and smoothed TCO summary for one financing contract."""

    total_contract_payments: float
    monthly_tco: float
    special_first_payment_share: float
    regular_payment: float
    residual_value: float | None


def calculate_leasing_summary(contract: dict[str, Any]) -> FinancingCostSummary:
    """Calculate leasing totals without treating residual value as a cost."""
    duration = int(contract["duration_months"])
    payment_count = int(contract["number_of_payments"])
    first = float(contract.get("first_payment") or 0.0)
    regular = float(contract.get("regular_payment") or 0.0)
    if duration <= 0 or payment_count <= 0:
        raise ValueError("duration_months and number_of_payments must be positive")
    if first < 0 or regular < 0:
        raise ValueError("payments must not be negative")

    # The first payment replaces one regular payment.  The difference is the
    # special first-payment component which is smoothed over the TCO period.
    special = max(0.0, first - regular)
    total = first + max(0, payment_count - 1) * regular
    monthly_tco = total / duration
    residual = contract.get("residual_value")
    return FinancingCostSummary(
        total_contract_payments=round(total, 2),
        monthly_tco=round(monthly_tco, 2),
        special_first_payment_share=round(special / duration, 2),
        regular_payment=round(regular, 2),
        residual_value=round(float(residual), 2) if residual is not None else None,
    )


def leasing_real_cost_for_month(contract: dict[str, Any], year: int, month: int) -> float:
    """Return the actual contractual leasing payment in a calendar month."""
    start = date.fromisoformat(str(contract["start_date"]))
    target = date(year, month, 1)
    start_month = date(start.year, start.month, 1)
    offset = (target.year - start_month.year) * 12 + target.month - start_month.month
    payment_count = int(contract["number_of_payments"])
    if offset < 0 or offset >= payment_count:
        return 0.0
    if offset == 0:
        return round(float(contract.get("first_payment") or 0.0), 2)
    return round(float(contract.get("regular_payment") or 0.0), 2)


def leasing_tco_for_month(contract: dict[str, Any], year: int, month: int) -> float:
    """Return smoothed leasing TCO for a calendar month within the term."""
    start = date.fromisoformat(str(contract["start_date"]))
    target = date(year, month, 1)
    start_month = date(start.year, start.month, 1)
    offset = (target.year - start_month.year) * 12 + target.month - start_month.month
    duration = int(contract["duration_months"])
    if offset < 0 or offset >= duration:
        return 0.0
    return calculate_leasing_summary(contract).monthly_tco


class FordTriplogVehicleFinancingStorage:
    """SQLite-backed financing contracts for one Ford Triplog vehicle."""

    def __init__(self, hass: HomeAssistant, base_path: Path, vehicle_id: int) -> None:
        self.hass = hass
        self.database = FordTriplogDatabase(hass, base_path, vehicle_id=vehicle_id)

    async def async_setup(self) -> None:
        await self.database.async_setup()

    async def async_load(self) -> list[dict[str, Any]]:
        await self.async_setup()
        vehicle_id = self.database.vehicle_id
        db_path = self.database.db_path

        def _read() -> list[dict[str, Any]]:
            with sqlite3.connect(db_path) as db:
                db.row_factory = sqlite3.Row
                rows = db.execute(
                    "SELECT * FROM vehicle_financing WHERE vehicle_id = ? ORDER BY start_date, financing_id",
                    (vehicle_id,),
                ).fetchall()
            return [dict(row) for row in rows]

        return await self.hass.async_add_executor_job(functools.partial(_read))

    async def async_save(self, contract: dict[str, Any]) -> dict[str, Any]:
        await self.async_setup()
        data = self._normalize(contract)
        vehicle_id = self.database.vehicle_id
        db_path = self.database.db_path

        def _write() -> dict[str, Any]:
            now = time.strftime("%Y-%m-%dT%H:%M:%S%z")
            financing_id = data.get("financing_id")
            values = (
                data["financing_type"], data.get("provider"), data.get("contract_number"),
                data["start_date"], data.get("end_date"), data["duration_months"],
                data.get("purchase_price"), data["first_payment"], data["regular_payment"],
                data["number_of_payments"], data.get("residual_value"), data.get("interest_rate"),
                data.get("annual_mileage"), data.get("excess_km_rate"), data["currency"],
                data.get("notes"), data.get("document_filename"),
                data.get("document_original_name"), now,
            )
            with sqlite3.connect(db_path) as db:
                db.row_factory = sqlite3.Row
                # Keep the original uploaded main contract when an existing
                # financing record is edited. The financing form does not
                # submit document fields, so older dev builds could otherwise
                # overwrite the linkage with NULL.
                if financing_id is not None and not data.get("document_filename"):
                    existing = db.execute(
                        "SELECT document_filename, document_original_name FROM vehicle_financing WHERE vehicle_id=? AND financing_id=?",
                        (vehicle_id, int(financing_id)),
                    ).fetchone()
                    if existing is not None and existing["document_filename"]:
                        data["document_filename"] = existing["document_filename"]
                        data["document_original_name"] = existing["document_original_name"]
                        values = (
                            data["financing_type"], data.get("provider"), data.get("contract_number"),
                            data["start_date"], data.get("end_date"), data["duration_months"],
                            data.get("purchase_price"), data["first_payment"], data["regular_payment"],
                            data["number_of_payments"], data.get("residual_value"), data.get("interest_rate"),
                            data.get("annual_mileage"), data.get("excess_km_rate"), data["currency"],
                            data.get("notes"), data.get("document_filename"),
                            data.get("document_original_name"), now,
                        )
                if financing_id is None:
                    cur = db.execute(
                        """INSERT INTO vehicle_financing (
                            vehicle_id, financing_type, provider, contract_number, start_date, end_date,
                            duration_months, purchase_price, first_payment, regular_payment,
                            number_of_payments, residual_value, interest_rate, annual_mileage,
                            excess_km_rate, currency, notes, document_filename,
                            document_original_name, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (vehicle_id, *values[:-1], now, now),
                    )
                    financing_id = int(cur.lastrowid)
                else:
                    db.execute(
                        """UPDATE vehicle_financing SET financing_type=?, provider=?, contract_number=?,
                            start_date=?, end_date=?, duration_months=?, purchase_price=?, first_payment=?,
                            regular_payment=?, number_of_payments=?, residual_value=?, interest_rate=?,
                            annual_mileage=?, excess_km_rate=?, currency=?, notes=?, document_filename=?,
                            document_original_name=?, updated_at=?
                            WHERE vehicle_id=? AND financing_id=?""",
                        (*values, vehicle_id, int(financing_id)),
                    )
                db.commit()
                row = db.execute(
                    "SELECT * FROM vehicle_financing WHERE vehicle_id=? AND financing_id=?",
                    (vehicle_id, financing_id),
                ).fetchone()
            if row is None:
                raise RuntimeError("Unable to reload saved financing contract")
            return dict(row)

        return await self.hass.async_add_executor_job(functools.partial(_write))

    @staticmethod
    def _normalize(contract: dict[str, Any]) -> dict[str, Any]:
        result = dict(contract)
        kind = str(result.get("financing_type") or "").strip().lower()
        if kind not in SUPPORTED_FINANCING_TYPES:
            raise ValueError(f"Unsupported financing type: {kind}")
        result["financing_type"] = kind
        result["start_date"] = date.fromisoformat(str(result["start_date"])).isoformat()
        if result.get("end_date"):
            result["end_date"] = date.fromisoformat(str(result["end_date"])).isoformat()
        result["duration_months"] = int(result["duration_months"])
        result["number_of_payments"] = int(result["number_of_payments"])
        result["first_payment"] = float(result.get("first_payment") or 0.0)
        result["regular_payment"] = float(result.get("regular_payment") or 0.0)
        result["currency"] = str(result.get("currency") or "CHF").strip().upper()
        for key in ("purchase_price", "residual_value", "interest_rate", "excess_km_rate"):
            if result.get(key) is not None:
                result[key] = float(result[key])
        if result.get("annual_mileage") is not None:
            result["annual_mileage"] = int(result["annual_mileage"])
        if kind == "leasing":
            calculate_leasing_summary(result)
        return result
