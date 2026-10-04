"""Vehicle insurance storage and TCO/cashflow helpers for Ford Triplog."""
from __future__ import annotations
import functools, sqlite3, time
from datetime import date
from pathlib import Path
from typing import Any
from homeassistant.core import HomeAssistant
from .database import FordTriplogDatabase

PAYMENT_FREQUENCIES = {"monthly", "quarterly", "semiannual", "annual", "single", "individual"}

class FordTriplogVehicleInsuranceStorage:
    def __init__(self, hass: HomeAssistant, base_path: Path, vehicle_id: int) -> None:
        self.hass=hass; self.database=FordTriplogDatabase(hass, base_path, vehicle_id=vehicle_id)
    async def async_setup(self): await self.database.async_setup()
    async def async_load(self) -> list[dict[str, Any]]:
        await self.async_setup(); vid=self.database.vehicle_id; path=self.database.db_path
        def _r():
            with sqlite3.connect(path) as db:
                db.row_factory=sqlite3.Row
                return [dict(x) for x in db.execute("SELECT * FROM vehicle_insurance WHERE vehicle_id=? ORDER BY valid_from,insurance_id",(vid,)).fetchall()]
        return await self.hass.async_add_executor_job(functools.partial(_r))
    async def async_save(self, item: dict[str, Any]) -> dict[str, Any]:
        await self.async_setup(); d=self._normalize(item); vid=self.database.vehicle_id; path=self.database.db_path
        def _w():
            now=time.strftime('%Y-%m-%dT%H:%M:%S%z'); iid=d.get('insurance_id')
            vals=(d.get('provider'),d.get('policy_number'),d['valid_from'],d['valid_to'],d['period_premium'],d['currency'],d['payment_frequency'],d.get('payment_amount'),d.get('first_payment_date'),d.get('notes'))
            with sqlite3.connect(path) as db:
                db.row_factory=sqlite3.Row
                if iid is None:
                    cur=db.execute("INSERT INTO vehicle_insurance (vehicle_id,provider,policy_number,valid_from,valid_to,period_premium,currency,payment_frequency,payment_amount,first_payment_date,notes,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",(vid,*vals,now,now)); iid=int(cur.lastrowid)
                else:
                    db.execute("UPDATE vehicle_insurance SET provider=?,policy_number=?,valid_from=?,valid_to=?,period_premium=?,currency=?,payment_frequency=?,payment_amount=?,first_payment_date=?,notes=?,updated_at=? WHERE vehicle_id=? AND insurance_id=?",(*vals,now,vid,int(iid)))
                db.commit(); row=db.execute("SELECT * FROM vehicle_insurance WHERE vehicle_id=? AND insurance_id=?",(vid,iid)).fetchone(); return dict(row)
        return await self.hass.async_add_executor_job(functools.partial(_w))
    async def async_delete(self, insurance_id:int)->None:
        await self.async_setup(); vid=self.database.vehicle_id; path=self.database.db_path
        def _d():
            with sqlite3.connect(path) as db: db.execute("DELETE FROM vehicle_insurance WHERE vehicle_id=? AND insurance_id=?",(vid,int(insurance_id))); db.commit()
        await self.hass.async_add_executor_job(functools.partial(_d))
    @staticmethod
    def _normalize(item):
        d=dict(item); start=date.fromisoformat(str(d['valid_from']).strip()); end=date.fromisoformat(str(d['valid_to']).strip())
        if end < start: raise ValueError('valid_to before valid_from')
        d['valid_from']=start.isoformat(); d['valid_to']=end.isoformat(); d['period_premium']=float(str(d['period_premium']).replace("'",'').replace(',','.'))
        if d['period_premium'] < 0: raise ValueError('negative premium')
        d['currency']=str(d.get('currency') or 'CHF').strip().upper(); freq=str(d.get('payment_frequency') or 'annual').strip().lower()
        if freq not in PAYMENT_FREQUENCIES: raise ValueError('bad frequency')
        d['payment_frequency']=freq
        raw=str(d.get('payment_amount') or '').strip(); d['payment_amount']=float(raw.replace("'",'').replace(',','.')) if raw else None
        rawdate=str(d.get('first_payment_date') or '').strip(); d['first_payment_date']=date.fromisoformat(rawdate).isoformat() if rawdate else None
        d['provider']=str(d.get('provider') or '').strip() or None; d['policy_number']=str(d.get('policy_number') or '').strip() or None; d['notes']=str(d.get('notes') or '').strip() or None
        return d

# --- Insurance policy import helpers (2.6 dev30) -------------------------
def extract_insurance_fields(raw_text: str, document_type: str = "insurance_policy") -> dict[str, Any]:
    """Extract insurance data, with a dedicated policy parser.

    For TCO a policy is authoritative: annual premium is the TCO basis while
    payment frequency/amount describe cash flow. Invoice parsing deliberately
    keeps the dev27 best-effort behaviour for later refinement.
    """
    import re
    from datetime import datetime

    raw = (raw_text or "").replace("\r", "\n")
    lines = [re.sub(r"[ \t\f\v]+", " ", x).strip() for x in raw.split("\n") if x.strip()]
    text = "\n".join(lines)
    flat = re.sub(r"\s+", " ", raw).strip()
    out: dict[str, Any] = {}

    def iso_date(value: str) -> str | None:
        for fmt in ("%d.%m.%Y", "%d.%m.%y", "%d/%m/%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(value.strip(), fmt).date().isoformat()
            except ValueError:
                pass
        return None

    def amount_value(value: str) -> float | None:
        v = value.strip().replace("'", "").replace("’", "").replace(" ", "")
        if "," in v and "." in v:
            v = v.replace(".", "").replace(",", ".") if v.rfind(",") > v.rfind(".") else v.replace(",", "")
        else:
            v = v.replace(",", ".")
        try: return float(v)
        except ValueError: return None

    # Shared identity fields.
    providers = (
        r"(AXA\s*Versicherungen\s*AG)\b",
        r"\b(Helvetia(?:\s+Schweizerische)?\s+Versicherung(?:en)?(?:\s+AG)?)\b",
        r"\b(Mobiliar(?:\s+Versicherung(?:en)?)?(?:\s+AG)?)\b",
        r"\b(Zurich(?:\s+Versicherung(?:s-Gesellschaft)?)?(?:\s+AG)?)\b",
        r"\b(Allianz(?:\s+Suisse)?(?:\s+Versicherung(?:en)?)?(?:\s+AG)?)\b",
        r"\b(Baloise(?:\s+Versicherung(?:en)?)?(?:\s+AG)?)\b",
        r"\b(Vaudoise(?:\s+Versicherung(?:en)?)?(?:\s+AG)?)\b",
    )
    for pat in providers:
        m=re.search(pat,text,re.I)
        if m: out["provider"]=m.group(1).strip(); break

    m=re.search(r"Police\s*Nr\.?\s*[:#\-]?\s*(\d{1,4}(?:\.\d{1,4}){1,4}|[A-Z0-9][A-Z0-9./\-]{2,30})", flat, re.I)
    if m: out["policy_number"]=m.group(1).strip(" .:/-")

    if re.search(r"\bEUR\b|€", text, re.I): out["currency"]="EUR"
    elif re.search(r"\bCHF\b", text, re.I): out["currency"]="CHF"

    date_pat=r"(\d{1,2}[./]\d{1,2}[./]\d{2,4}|\d{4}-\d{2}-\d{2})"
    money=r"(\d{1,3}(?:['’ ]\d{3})*(?:[.,]\d{2})|\d+(?:[.,]\d{2}))"

    if document_type == "insurance_policy":
        # Contract dates. AXA policy: "Vertragsdaten Beginn: ... Ende: ...".
        m=re.search(rf"(?:Vertragsdaten\s*)?Beginn\s*:\s*{date_pat}.*?Ende\s*:\s*{date_pat}", flat, re.I)
        if not m:
            m=re.search(rf"(?:Vertragsbeginn|Beginn)\s*[:\-]?\s*{date_pat}.*?(?:Vertragsende|Ende)\s*[:\-]?\s*{date_pat}", flat, re.I)
        if m:
            a,b=iso_date(m.group(1)),iso_date(m.group(2))
            if a and b: out["valid_from"],out["valid_to"]=a,b

        # TCO basis is explicitly the annual premium, never an individual cover.
        m=re.search(rf"Total\s*Jahrespr[aä]mie\s*(?:in\s*[A-Z]{{3}}\s*)?(?:CHF|EUR|€)?\s*{money}", flat, re.I)
        if not m:
            m=re.search(rf"\bJahrespr[aä]mie\b\s*(?:in\s+[A-Z]{{3}}\s*)?(?:CHF|EUR|€)?\s*{money}", flat, re.I)
        if m:
            a=amount_value(m.group(1))
            if a is not None: out["period_premium"]=f"{a:.2f}"

        # Payment frequency from explicit policy wording, including Swiss "1/2-jährlich".
        freq=None
        if re.search(r"Zahlbar\s*:\s*(?:1/12|monatlich)|\bmonatlich\b", flat, re.I): freq="monthly"
        elif re.search(r"Zahlbar\s*:\s*(?:1/4|viertelj[aä]hrlich)|\bviertelj[aä]hrlich\b", flat, re.I): freq="quarterly"
        elif re.search(r"Zahlbar\s*:\s*(?:1/2|halbj[aä]hrlich)|\bhalbj[aä]hrlich\b", flat, re.I): freq="semiannual"
        elif re.search(r"Zahlbar\s*:\s*(?:1/1|j[aä]hrlich)|\bj[aä]hrlich\b", flat, re.I): freq="annual"
        out["payment_frequency"]=freq or "annual"

        # Prefer the premium matching the selected payment cadence.
        labels={"monthly":"Monatspr[aä]mie","quarterly":"(?:Quartals|Vierteljahres)pr[aä]mie","semiannual":"Halbjahrespr[aä]mie","annual":"Jahrespr[aä]mie"}
        label=labels[out["payment_frequency"]]
        m=re.search(rf"Total\s*{label}\s*(?:CHF|EUR|€)?\s*{money}", flat, re.I)
        if m:
            a=amount_value(m.group(1))
            if a is not None: out["payment_amount"]=f"{a:.2f}"

        # Main due date: day/month may be recurring and has no meaningful year.
        m=re.search(r"Pr[aä]mie\s+f[aä]llig\s+am\s*:\s*(\d{1,2})\.(\d{1,2})\.", flat, re.I)
        if m:
            out["notes"]=(f"Hauptfälligkeit: {int(m.group(1)):02d}.{int(m.group(2)):02d}.; "
                          + ("danach alle 6 Monate" if out["payment_frequency"]=="semiannual" else "gemäss Police"))
        return out

    # Invoice/other: retain a conservative dev27-style prefill. TCO will not use it.
    m=re.search(rf"(?:Pr[aä]mie\s+neu|Belastung)[^\n]{{0,80}}?(?:vom|von)\s*{date_pat}\s*(?:bis|[-–—])\s*{date_pat}[^\n]{{0,30}}?{money}", text, re.I)
    if m:
        a,b=iso_date(m.group(1)),iso_date(m.group(2)); amt=amount_value(m.group(3))
        if a and b: out["valid_from"],out["valid_to"]=a,b
        if amt is not None: out["period_premium"]=f"{amt:.2f}"
    out.setdefault("payment_frequency", "annual")
    return out
