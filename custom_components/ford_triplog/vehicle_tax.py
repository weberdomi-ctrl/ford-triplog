"""Vehicle road-tax storage for Ford Triplog."""
from __future__ import annotations

import functools
import sqlite3
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant

from .database import FordTriplogDatabase


class FordTriplogVehicleTaxStorage:
    """Store annual vehicle-road-tax bases per vehicle and validity period."""

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
                    "SELECT * FROM vehicle_tax WHERE vehicle_id=? "
                    "ORDER BY valid_from, tax_id",
                    (vehicle_id,),
                ).fetchall()
                return [dict(row) for row in rows]

        return await self.hass.async_add_executor_job(functools.partial(_read))

    async def async_save(self, item: dict[str, Any]) -> dict[str, Any]:
        await self.async_setup()
        data = self._normalize(item)
        vehicle_id = self.database.vehicle_id
        db_path = self.database.db_path

        def _write() -> dict[str, Any]:
            now = time.strftime("%Y-%m-%dT%H:%M:%S%z")
            tax_id = data.get("tax_id")
            values = (
                data["valid_from"], data["valid_to"], data["annual_tax"],
                data["currency"], data.get("authority"), data.get("notes"),
            )
            with sqlite3.connect(db_path) as db:
                db.row_factory = sqlite3.Row
                if tax_id is None:
                    cur = db.execute(
                        "INSERT INTO vehicle_tax "
                        "(vehicle_id,valid_from,valid_to,annual_tax,currency,authority,notes,created_at,updated_at) "
                        "VALUES (?,?,?,?,?,?,?,?,?)",
                        (vehicle_id, *values, now, now),
                    )
                    tax_id = int(cur.lastrowid)
                else:
                    db.execute(
                        "UPDATE vehicle_tax SET valid_from=?,valid_to=?,annual_tax=?,currency=?,authority=?,notes=?,updated_at=? "
                        "WHERE vehicle_id=? AND tax_id=?",
                        (*values, now, vehicle_id, int(tax_id)),
                    )
                db.commit()
                row = db.execute(
                    "SELECT * FROM vehicle_tax WHERE vehicle_id=? AND tax_id=?",
                    (vehicle_id, tax_id),
                ).fetchone()
                return dict(row)

        return await self.hass.async_add_executor_job(functools.partial(_write))

    async def async_delete(self, tax_id: int) -> None:
        await self.async_setup()
        vehicle_id = self.database.vehicle_id
        db_path = self.database.db_path

        def _delete() -> None:
            with sqlite3.connect(db_path) as db:
                db.execute(
                    "DELETE FROM vehicle_tax WHERE vehicle_id=? AND tax_id=?",
                    (vehicle_id, int(tax_id)),
                )
                db.commit()

        await self.hass.async_add_executor_job(functools.partial(_delete))

    @staticmethod
    def _normalize(item: dict[str, Any]) -> dict[str, Any]:
        data = dict(item)
        def _parse_date(value: Any) -> date:
            if isinstance(value, datetime):
                return value.date()
            if isinstance(value, date):
                return value
            text = str(value or "").strip()
            for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y"):
                try:
                    return datetime.strptime(text, fmt).date()
                except ValueError:
                    pass
            raise ValueError(f"invalid tax date: {text!r}")

        def _parse_amount(value: Any) -> float:
            text = str(value or "").strip().replace("CHF", "").replace("Fr.", "")
            text = text.replace("'", "").replace("’", "").replace(" ", "")
            text = text.replace(".–", "").replace(".-", "").replace("—", "")
            if "," in text and "." in text:
                if text.rfind(",") > text.rfind("."):
                    text = text.replace(".", "").replace(",", ".")
                else:
                    text = text.replace(",", "")
            else:
                text = text.replace(",", ".")
            return float(text)

        start = _parse_date(data["valid_from"])
        end = _parse_date(data["valid_to"])
        if end < start:
            raise ValueError("valid_to before valid_from")
        annual = _parse_amount(data["annual_tax"])
        if annual < 0:
            raise ValueError("negative annual tax")
        data["valid_from"] = start.isoformat()
        data["valid_to"] = end.isoformat()
        data["annual_tax"] = annual
        data["currency"] = str(data.get("currency") or "CHF").strip().upper()
        data["authority"] = str(data.get("authority") or "").strip() or None
        data["notes"] = str(data.get("notes") or "").strip() or None
        return data
