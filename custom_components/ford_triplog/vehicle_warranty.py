"""Vehicle warranty storage and calculations for Ford Triplog."""
from __future__ import annotations
import sqlite3, time
from calendar import monthrange
from datetime import date
from pathlib import Path
from typing import Any
from .const import STORAGE_DIR

WARRANTY_TYPES = ("vehicle", "ev_components", "hv_battery")


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    raw = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d.%m.%y", "%d/%m/%Y"):
        try:
            from datetime import datetime
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            pass
    return None


def add_years(value: date, years: int) -> date:
    year = value.year + int(years)
    day = min(value.day, monthrange(year, value.month)[1])
    return value.replace(year=year, day=day)


def warranty_end_date(first_registration: str | None, years: int | None) -> str | None:
    start = _parse_date(first_registration)
    if not start or not years or int(years) <= 0:
        return None
    return add_years(start, int(years)).isoformat()


def warranty_remaining_time(valid_until: str | None, today: date | None = None) -> dict[str, int | None]:
    """Return calendar remaining time as years, months and days."""
    end = _parse_date(valid_until)
    current = today or date.today()
    if not end:
        return {"remaining_years": None, "remaining_months": None, "remaining_days": None}
    if end <= current:
        return {"remaining_years": 0, "remaining_months": 0, "remaining_days": 0}

    years = end.year - current.year
    months = end.month - current.month
    days = end.day - current.day
    if days < 0:
        months -= 1
        prev_month = end.month - 1 or 12
        prev_year = end.year if end.month > 1 else end.year - 1
        days += monthrange(prev_year, prev_month)[1]
    if months < 0:
        years -= 1
        months += 12
    return {"remaining_years": years, "remaining_months": months, "remaining_days": days}


class FordTriplogVehicleWarrantyStorage:
    def __init__(self, hass) -> None:
        self.hass = hass

    async def _db(self):
        from .database import FordTriplogDatabase
        db = FordTriplogDatabase(self.hass, Path(self.hass.config.path('.storage', STORAGE_DIR)))
        await db.async_setup()
        return db

    async def async_get(self, vehicle_id: int) -> dict[str, dict[str, Any]]:
        db = await self._db()
        def _r():
            with sqlite3.connect(db.db_path) as c:
                c.row_factory = sqlite3.Row
                rows = c.execute('SELECT * FROM vehicle_warranties WHERE vehicle_id=?', (int(vehicle_id),)).fetchall()
                return {str(r['warranty_type']): dict(r) for r in rows}
        return await self.hass.async_add_executor_job(_r)

    async def async_save_all(self, vehicle_id: int, data: dict[str, Any]) -> None:
        db = await self._db(); now = time.strftime('%Y-%m-%dT%H:%M:%S%z')
        def clean_int(v):
            try:
                s = str(v or '').strip()
                return int(float(s)) if s else None
            except (TypeError, ValueError):
                return None
        rows = []
        for kind in WARRANTY_TYPES:
            years = clean_int(data.get(f'{kind}_years'))
            km = clean_int(data.get(f'{kind}_km'))
            rows.append((kind, years, km))
        def _w():
            with sqlite3.connect(db.db_path) as c:
                for kind, years, km in rows:
                    if years is None and km is None:
                        c.execute('DELETE FROM vehicle_warranties WHERE vehicle_id=? AND warranty_type=?', (int(vehicle_id), kind))
                        continue
                    c.execute('''INSERT INTO vehicle_warranties (vehicle_id,warranty_type,duration_years,mileage_limit_km,created_at,updated_at)
                                 VALUES (?,?,?,?,?,?)
                                 ON CONFLICT(vehicle_id,warranty_type) DO UPDATE SET duration_years=excluded.duration_years,mileage_limit_km=excluded.mileage_limit_km,updated_at=excluded.updated_at''',
                              (int(vehicle_id), kind, years, km, now, now))
                c.commit()
        await self.hass.async_add_executor_job(_w)
