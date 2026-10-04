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

# --- Insurance policy / invoice import helpers (2.6 dev27) -----------------
def extract_insurance_fields(raw_text: str) -> dict[str, Any]:
    """Best-effort extraction from insurance policies and premium invoices.

    The importer only prefills values. It deliberately distinguishes the
    insurance premium for a period from invoice totals, credits and balances.
    """
    import re
    from datetime import datetime

    raw = (raw_text or "").replace("\r", "\n")
    # Keep line boundaries where possible, but normalize horizontal whitespace.
    lines = [re.sub(r"[ \t\f\v]+", " ", x).strip() for x in raw.split("\n") if x.strip()]
    text = "\n".join(lines)
    flat = re.sub(r"\s+", " ", raw).strip()
    out: dict[str, Any] = {}

    # Provider. Company names in headers/footers are more reliable than generic
    # occurrences of "Versicherung" in product descriptions.
    provider_patterns = (
        r"\b(AXA\s+Versicherungen\s+AG)\b",
        r"\b(Helvetia(?:\s+Schweizerische)?\s+Versicherung(?:en)?(?:\s+AG)?)\b",
        r"\b(Mobiliar(?:\s+Versicherung(?:en)?)?(?:\s+AG)?)\b",
        r"\b(Zurich(?:\s+Versicherung(?:s-Gesellschaft)?)?(?:\s+AG)?)\b",
        r"\b(Allianz(?:\s+Suisse)?(?:\s+Versicherung(?:en)?)?(?:\s+AG)?)\b",
        r"\b(Baloise(?:\s+Versicherung(?:en)?)?(?:\s+AG)?)\b",
        r"\b(Vaudoise(?:\s+Versicherung(?:en)?)?(?:\s+AG)?)\b",
        r"(?:Versicherer|Versicherungsgesellschaft|Gesellschaft)\s*[:\-]?\s*([^\n]{2,80})",
    )
    for pat in provider_patterns:
        m = re.search(pat, text, re.I)
        if m:
            out["provider"] = re.sub(r"\s+", " ", m.group(1)).strip(" :;,-")
            break

    # Policy number: stop before the next known label even if PDF extraction
    # concatenates table cells (e.g. "16.242.692Kontrollschild...").
    policy_patterns = (
        r"\bPolice\s*Nr\.?\s*[:#\-]?\s*([A-Z0-9][A-Z0-9./\-]{2,30})",
        r"\bPolicen(?:nummer|[- ]?Nr\.?)\s*[:#\-]?\s*([A-Z0-9][A-Z0-9./\-]{2,30})",
        r"\b(?:Vertragsnummer|Vertrags[- ]?Nr\.?)\s*[:#\-]?\s*([A-Z0-9][A-Z0-9./\-]{2,30})",
    )
    for pat in policy_patterns:
        m = re.search(pat, flat, re.I)
        if m:
            value = m.group(1).strip(" .:/-")
            # AXA-style numbers are often immediately followed by a label in
            # badly extracted PDFs. Keep the leading dotted numeric identifier.
            numeric = re.match(r"\d{1,4}(?:\.\d{1,4}){1,4}", value)
            out["policy_number"] = numeric.group(0) if numeric else value
            break

    def iso_date(value: str) -> str | None:
        value = value.strip()
        for fmt in ("%d.%m.%Y", "%d.%m.%y", "%d/%m/%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(value, fmt).date().isoformat()
            except ValueError:
                pass
        return None

    date_pat = r"(\d{1,2}[./]\d{1,2}[./]\d{2,4}|\d{4}-\d{2}-\d{2})"
    # Prefer premium-labelled periods. This also handles AXA change invoices:
    # "Ihre Prämie neu (Belastung) vom 07.10.2024 - 31.12.2024 308.21".
    period_patterns = (
        rf"(?:Prämie|Praemie)[^\n]{{0,80}}?(?:vom|von)\s*{date_pat}\s*(?:bis|[-–—])\s*{date_pat}",
        rf"(?:Versicherungsperiode|Versicherungsdauer|Prämienperiode|Praemienperiode|Abrechnungsperiode|Gültigkeit|Periode)[^\n]{{0,30}}?{date_pat}\s*(?:bis|[-–—])\s*{date_pat}",
        rf"(?:vom|von)\s*{date_pat}\s*(?:bis|[-–—])\s*{date_pat}",
    )
    for pat in period_patterns:
        m = re.search(pat, text, re.I) or re.search(pat, flat, re.I)
        if m:
            a, b = iso_date(m.group(1)), iso_date(m.group(2))
            if a and b:
                out["valid_from"], out["valid_to"] = a, b
                break

    def amount_value(value: str) -> float | None:
        v = value.strip().replace("'", "").replace("’", "").replace(" ", "")
        # Swiss/German documents use apostrophes for thousands and dot/comma decimals.
        if "," in v and "." in v:
            if v.rfind(",") > v.rfind("."):
                v = v.replace(".", "").replace(",", ".")
            else:
                v = v.replace(",", "")
        else:
            v = v.replace(",", ".")
        try:
            return float(v)
        except ValueError:
            return None

    money_pat = r"(?<![\d.])[-+]?\s*(\d{1,3}(?:['’ ]\d{3})*(?:[.,]\d{2})|\d+(?:[.,]\d{2}))"

    # Strongest signal: the amount on a labelled period-premium line. Prefer
    # "new / debit" over "previous / credit" on contract-change invoices.
    premium_candidates: list[tuple[int, float, str]] = []
    for line in lines:
        low = line.lower()
        if not any(k in low for k in ("prämie", "praemie", "premium")):
            continue
        if any(k in low for k in ("totalbetrag", "zu zahlen", "zahlbetrag", "saldo", "auszahlung")):
            continue
        values = re.findall(money_pat, line, re.I)
        for val in values:
            amount = amount_value(val)
            if amount is None or amount <= 0:
                continue
            score = 0
            if "prämie neu" in low or "praemie neu" in low or "belastung" in low: score += 100
            if "periodenprämie" in low or "prämie für" in low or "prämie total" in low or "totalprämie" in low: score += 80
            if "gutschrift" in low or "prämie bisher" in low or "praemie bisher" in low: score -= 100
            if "jahresprämie" in low: score += 10
            # A date range on the same line strongly indicates a period amount.
            if re.search(r"\d{1,2}[./]\d{1,2}[./]\d{2,4}\s*[-–—]\s*\d{1,2}[./]\d{1,2}[./]\d{2,4}", line): score += 50
            premium_candidates.append((score, amount, line))
    if premium_candidates:
        premium_candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)
        out["period_premium"] = f"{premium_candidates[0][1]:.2f}"

    if re.search(r"\bEUR\b|€", text, re.I):
        out["currency"] = "EUR"
    elif re.search(r"\bCHF\b", text, re.I):
        out["currency"] = "CHF"

    # Payment frequency: explicit payment wording wins over a column heading
    # such as "Jahresprämie". AXA example: "Zuschlag halbjährliche Zahlung".
    explicit_freq = (
        ("monthly", r"(?:monatliche|monatlicher|monatlichen|monatlich)\s+(?:Zahlung|Zahlweise|Rate)|Zuschlag\s+monatlich"),
        ("quarterly", r"(?:vierteljährliche|vierteljährlicher|vierteljährlichen|vierteljährlich|quartalsweise)\s+(?:Zahlung|Zahlweise|Rate)|Zuschlag\s+vierteljährlich"),
        ("semiannual", r"(?:halbjährliche|halbjährlicher|halbjährlichen|halbjährlich)\s+(?:Zahlung|Zahlweise|Rate)|Zuschlag\s+halbjährlich"),
        ("annual", r"(?:jährliche|jährlicher|jährlichen|jährlich)\s+(?:Zahlung|Zahlweise|Rate)|Zuschlag\s+jährlich"),
    )
    for freq, pat in explicit_freq:
        if re.search(pat, text, re.I):
            out["payment_frequency"] = freq
            break
    else:
        generic_freq = (
            ("monthly", r"\bMonatsprämie\b"),
            ("quarterly", r"\bQuartalsprämie\b"),
            ("semiannual", r"\bHalbjahresprämie\b"),
        )
        for freq, pat in generic_freq:
            if re.search(pat, text, re.I):
                out["payment_frequency"] = freq
                break
        else:
            out["payment_frequency"] = "annual"

    # Only prefill an instalment amount when the document explicitly labels a
    # payment/rate. Do not use a surcharge or a credit/change invoice total.
    pay_line_pat = r"(?:Rate|Teilzahlung|Zahlungsbetrag)\s*[:\-]?\s*(?:CHF|EUR|€)?\s*" + money_pat
    m = re.search(pay_line_pat, text, re.I)
    if m:
        amt = amount_value(m.group(1))
        if amt is not None and amt > 0:
            out["payment_amount"] = f"{amt:.2f}"

    m = re.search(rf"(?:fällig(?:keit)?|Zahlbar(?:keit)?|erste\s+(?:Rate|Zahlung))\s*(?:am|per|:)\s*{date_pat}", text, re.I)
    if m:
        d = iso_date(m.group(1))
        if d:
            out["first_payment_date"] = d
    return out
