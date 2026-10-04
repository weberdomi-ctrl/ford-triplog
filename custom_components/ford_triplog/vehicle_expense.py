"""Variable vehicle expenses (maintenance, tolls/vignettes and other costs)."""
from __future__ import annotations
import functools, sqlite3, time
from datetime import date, datetime
from pathlib import Path
from typing import Any
from homeassistant.core import HomeAssistant
from .database import FordTriplogDatabase

GROUPS={"maintenance","toll","other"}
class FordTriplogVehicleExpenseStorage:
    def __init__(self,hass:HomeAssistant,base_path:Path,vehicle_id:int)->None:
        self.hass=hass; self.database=FordTriplogDatabase(hass,base_path,vehicle_id=vehicle_id)
    async def async_setup(self): await self.database.async_setup()
    async def async_load(self,group:str|None=None):
        await self.async_setup(); vid=self.database.vehicle_id; p=self.database.db_path
        def _r():
            with sqlite3.connect(p) as db:
                db.row_factory=sqlite3.Row
                if group: rows=db.execute("SELECT * FROM vehicle_expenses WHERE vehicle_id=? AND expense_group=? ORDER BY expense_date,expense_id",(vid,group)).fetchall()
                else: rows=db.execute("SELECT * FROM vehicle_expenses WHERE vehicle_id=? ORDER BY expense_date,expense_id",(vid,)).fetchall()
                return [dict(x) for x in rows]
        return await self.hass.async_add_executor_job(_r)
    async def async_save(self,item:dict[str,Any]):
        await self.async_setup(); d=self._normalize(item); vid=self.database.vehicle_id; p=self.database.db_path
        def _w():
            now=time.strftime('%Y-%m-%dT%H:%M:%S%z'); eid=d.get('expense_id')
            vals=(d['expense_group'],d['category'],d['description'],d['amount'],d['currency'],d.get('expense_date'),d.get('expense_year'),d.get('valid_from'),d.get('valid_to'),d.get('odometer_km'),d.get('provider'),d.get('country'),d.get('notes'))
            with sqlite3.connect(p) as db:
                db.row_factory=sqlite3.Row
                if eid is None:
                    cur=db.execute("INSERT INTO vehicle_expenses (vehicle_id,expense_group,category,description,amount,currency,expense_date,expense_year,valid_from,valid_to,odometer_km,provider,country,notes,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(vid,*vals,now,now)); eid=int(cur.lastrowid)
                else:
                    db.execute("UPDATE vehicle_expenses SET expense_group=?,category=?,description=?,amount=?,currency=?,expense_date=?,expense_year=?,valid_from=?,valid_to=?,odometer_km=?,provider=?,country=?,notes=?,updated_at=? WHERE vehicle_id=? AND expense_id=?",(*vals,now,vid,int(eid)))
                db.commit(); return dict(db.execute("SELECT * FROM vehicle_expenses WHERE vehicle_id=? AND expense_id=?",(vid,eid)).fetchone())
        return await self.hass.async_add_executor_job(_w)
    async def async_delete(self,eid:int):
        await self.async_setup(); vid=self.database.vehicle_id; p=self.database.db_path
        def _d():
            with sqlite3.connect(p) as db: db.execute("DELETE FROM vehicle_expenses WHERE vehicle_id=? AND expense_id=?",(vid,int(eid))); db.commit()
        await self.hass.async_add_executor_job(_d)
    @staticmethod
    def _normalize(item):
        d = dict(item)
        group = str(d.get("expense_group") or "").strip()
        if group not in GROUPS:
            raise ValueError("invalid_expense_group")

        categories = {
            "maintenance": {"service","repair","tires","wear","care","accessories","other"},
            "toll": {"vignette","road_toll","tunnel_pass","bridge","ferry","other"},
            "other": {"registration_document","plates","mutation","admin_fee","roadside_assistance","other"},
        }
        category = str(d.get("category") or "").strip()
        if not category:
            raise ValueError("category_required")
        if category not in categories[group]:
            raise ValueError("invalid_category")
        d["category"] = category

        def dt(value, code):
            text = str(value or "").strip()
            if not text:
                return None
            for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y"):
                try:
                    return datetime.strptime(text, fmt).date().isoformat()
                except ValueError:
                    pass
            raise ValueError(code)

        def num(value, empty_code, invalid_code):
            text = str(value or "").strip()
            if not text:
                raise ValueError(empty_code)
            text = text.replace("CHF", "").replace("Fr.", "").replace("'", "").replace("’", "").replace(" ", "").replace(".–", "").replace(".-", "")
            if "," in text and "." in text:
                text = text.replace(".", "").replace(",", ".") if text.rfind(",") > text.rfind(".") else text.replace(",", "")
            else:
                text = text.replace(",", ".")
            try:
                return float(text)
            except (TypeError, ValueError):
                raise ValueError(invalid_code) from None

        d["expense_date"] = dt(d.get("expense_date"), "invalid_expense_date")
        d["valid_from"] = dt(d.get("valid_from"), "invalid_valid_from")
        d["valid_to"] = dt(d.get("valid_to"), "invalid_valid_to")
        if bool(d["valid_from"]) != bool(d["valid_to"]):
            raise ValueError("both_validity_dates_required")
        if d["valid_from"] and d["valid_to"] < d["valid_from"]:
            raise ValueError("invalid_validity_range")

        d["amount"] = num(d.get("amount"), "amount_required", "invalid_amount")
        if d["amount"] < 0:
            raise ValueError("negative_amount")

        year_raw = str(d.get("expense_year") or "").strip()
        if year_raw:
            try:
                d["expense_year"] = int(year_raw)
            except ValueError:
                raise ValueError("invalid_year") from None
            if not 1900 <= d["expense_year"] <= 2200:
                raise ValueError("invalid_year")
        else:
            d["expense_year"] = None
        if d["expense_date"]:
            d["expense_year"] = int(d["expense_date"][:4])

        if group == "toll" and not (d["expense_date"] or d["valid_from"] or d["expense_year"]):
            raise ValueError("missing_toll_date_or_year")
        if group != "toll" and not (d["expense_date"] or d["expense_year"]):
            raise ValueError("missing_date_or_year")

        odo_raw = str(d.get("odometer_km") or "").strip()
        d["odometer_km"] = None if not odo_raw else num(odo_raw, "invalid_odometer", "invalid_odometer")
        for key in ("description", "provider", "country", "notes"):
            d[key] = str(d.get(key) or "").strip() or None
        d["currency"] = str(d.get("currency") or "CHF").strip().upper() or "CHF"
        return d



def allocated_amount_for_period(item: dict[str, Any], period_start: date, period_end: date) -> float:
    """Return the expense amount allocated to an inclusive reporting period.

    Validity-based expenses (e.g. vignettes) are distributed day-exactly.
    Other expenses are assigned to their booking date or, if only a year is
    known, proportionally to that calendar year.
    """
    amount=float(item.get("amount") or 0.0)
    vf=item.get("valid_from"); vt=item.get("valid_to")
    if vf and vt:
        start=date.fromisoformat(str(vf)); end=date.fromisoformat(str(vt))
        total=(end-start).days+1
        overlap=max(0,(min(end,period_end)-max(start,period_start)).days+1)
        return amount*overlap/total if total > 0 else 0.0
    ed=item.get("expense_date")
    if ed:
        booked=date.fromisoformat(str(ed)); return amount if period_start <= booked <= period_end else 0.0
    year=item.get("expense_year")
    if year:
        start=date(int(year),1,1); end=date(int(year),12,31); total=(end-start).days+1
        overlap=max(0,(min(end,period_end)-max(start,period_start)).days+1)
        return amount*overlap/total
    return 0.0
