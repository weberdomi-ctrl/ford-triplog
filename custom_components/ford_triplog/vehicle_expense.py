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
        d=dict(item); group=str(d.get('expense_group') or '').strip()
        if group not in GROUPS: raise ValueError('invalid expense group')
        def dt(v,required=False):
            s=str(v or '').strip()
            if not s:
                if required: raise ValueError('missing date')
                return None
            for f in ('%Y-%m-%d','%d.%m.%Y','%d/%m/%Y'):
                try:return datetime.strptime(s,f).date().isoformat()
                except ValueError:pass
            raise ValueError('invalid date')
        def num(v):
            s=str(v or '').strip().replace('CHF','').replace('Fr.','').replace("'",'').replace('’','').replace(' ','').replace('.–','').replace('.-','')
            if ',' in s and '.' in s: s=s.replace('.','').replace(',','.') if s.rfind(',')>s.rfind('.') else s.replace(',','')
            else:s=s.replace(',','.')
            return float(s)
        d['expense_date']=dt(d.get('expense_date')); d['valid_from']=dt(d.get('valid_from')); d['valid_to']=dt(d.get('valid_to'))
        if bool(d['valid_from']) != bool(d['valid_to']): raise ValueError('both validity dates required')
        if d['valid_from'] and d['valid_to']<d['valid_from']: raise ValueError('invalid validity range')
        d['amount']=num(d.get('amount')); 
        if d['amount']<0: raise ValueError('negative amount')
        year_raw=str(d.get('expense_year') or '').strip()
        d['expense_year']=int(year_raw) if year_raw else None
        if d['expense_year'] is not None and not (1900 <= d['expense_year'] <= 2200): raise ValueError('invalid year')
        if d['expense_date']: d['expense_year']=int(d['expense_date'][:4])
        if group == 'toll' and not (d['expense_date'] or d['valid_from'] or d['expense_year']): raise ValueError('missing toll date or year')
        if group != 'toll' and not (d['expense_date'] or d['expense_year']): raise ValueError('missing date or year')
        d['odometer_km']=None if str(d.get('odometer_km') or '').strip()=='' else num(d.get('odometer_km'))
        for k in ('category','description','provider','country','notes'): d[k]=str(d.get(k) or '').strip() or None
        if not d['category']: raise ValueError('category required')
        d['currency']=str(d.get('currency') or 'CHF').strip().upper()
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
