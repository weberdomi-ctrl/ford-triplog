"""Extract conservative editable expense suggestions from PDF/OCR text.

The receipt may contain multiple sums (net, VAT, subtotal). Only explicit
grand-total/payment labels or unambiguous currency-marked amounts are used.
No expenses are ever booked by this module.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Any


_AMOUNT = re.compile(
    r"(?<![\w])(?:\d{1,3}(?:[ .'’\u00a0]\d{3})+(?:[.,]\d{2}|[.,][-–—])?|\d{1,6}(?:[.,]\d{2}|[.,][-–—]))(?!\d)"
)
_CURRENCY = re.compile(r"\b(CHF|EUR|USD|GBP)\b|(?<!\w)(Fr\.|€|£|\$)", re.I)
_DATE = re.compile(r"(?<!\d)(?:(\d{1,2})[./-](\d{1,2})[./-](\d{4})|(\d{4})[-/.](\d{1,2})[-/.](\d{1,2}))(?!\d)")
_PAYMENT = re.compile(
    r"\b(?:zu\s+bezahlen|zahlbetrag|rechnungsbetrag|gesamtbetrag|totalbetrag|endbetrag|bruttobetrag|"
    r"total(?:\s+inkl\.?\s*(?:mwst|ust|vat))?|grand\s+total|amount\s+due|"
    r"total\s+due|balance\s+due|betrag\s+inkl\.?\s*(?:mwst|ust))\b",
    re.I,
)
_GENERAL_TOTAL = re.compile(r"\b(?:summe|gesamt|total|betrag)\b", re.I)
_EXCLUDED = re.compile(r"\b(?:zwischensumme|zwischentotal|subtotal|sub-total|netto|net\b|exkl\.?|"
                       r"rückgeld|wechselgeld|gegeben|mwst|ust|vat|tax\s+amount|rabatt|discount)\b", re.I)
_INVOICE_DATE = re.compile(r"\b(?:rechnungsdatum|belegdatum|invoice\s+date|date\s+of\s+issue|ausstellungsdatum)\b",re.I)
_OTHER_DATE = re.compile(r"\b(?:datum|date|bezahlt\s+am|paid\s+on)\b",re.I)
_DUE_DATE = re.compile(r"\b(?:fällig|faellig|due\s+date|zahlbar\s+bis|gültig\s+bis)\b",re.I)
_MERCHANT_SKIP = re.compile(
    r"\b(?:rechnung|invoice|quittung|receipt|beleg|datum|kundennummer|mwst|"
    r"steuer|total|zahlbetrag|rechnungsnummer|seite|page|telefon|fax|"
    r"www\.|https?://|iban|konto|adresse)\b", re.I
)


def _money(token: str) -> float | None:
    value = token.strip().replace("\u00a0", "").replace(" ", "").replace("’", "").replace("'", "")
    if value.endswith((".-", ".–", ".—", ",-", ",–", ",—")):
        value = value[:-2] + ".00"
    elif "," in value and "." in value:
        decimal = "," if value.rfind(",") > value.rfind(".") else "."
        thousands = "." if decimal == "," else ","
        value = value.replace(thousands, "").replace(decimal, ".")
    elif value.count(".") > 1 or value.count(",") > 1:
        return None
    elif "," in value:
        value = value.replace(",", ".")
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return None
    return round(amount, 2) if 0 < amount < 1_000_000 else None


def _line_amounts(line: str) -> list[float]:
    values = []
    for match in _AMOUNT.finditer(line):
        amount = _money(match.group(0))
        if amount is not None:
            values.append(amount)
    return values


def _guess_total(lines: list[str]) -> float | None:
    ranked: list[tuple[int, int, float]] = []
    for index, line in enumerate(lines):
        if _EXCLUDED.search(line) and not _PAYMENT.search(line):
            continue
        priority = 4 if _PAYMENT.search(line) else 2 if _GENERAL_TOTAL.search(line) else 0
        amounts = _line_amounts(line)
        if priority and not amounts and index + 1 < len(lines):
            # Common PDF: "Total" and "CHF 123.45" end up on separate lines.
            amounts = _line_amounts(lines[index + 1])
        if amounts and priority:
            ranked.append((priority, index, max(amounts)))
        elif amounts and _CURRENCY.search(line):
            ranked.append((1, index, max(amounts)))
    if not ranked:
        return None
    best = max(x[0] for x in ranked)
    candidates = [x for x in ranked if x[0] == best]
    # Multiple contradictory currency-only rows are not safe to guess from.
    if best == 1 and len({x[2] for x in candidates}) > 1:
        return None
    return candidates[-1][2]


def _date_from(line: str) -> str | None:
    for match in _DATE.finditer(line):
        groups = match.groups()
        try:
            if groups[0] is not None:
                result = date(int(groups[2]), int(groups[1]), int(groups[0]))
            else:
                result = date(int(groups[3]), int(groups[4]), int(groups[5]))
        except ValueError:
            continue
        if 2000 <= result.year <= 2100:
            return result.isoformat()
    return None


def _guess_date(lines: list[str]) -> str | None:
    matches: list[tuple[int, int, str]] = []
    for i, line in enumerate(lines):
        if _DUE_DATE.search(line):
            continue
        parsed = _date_from(line)
        if not parsed and (_INVOICE_DATE.search(line) or _OTHER_DATE.search(line)) and i + 1 < len(lines):
            parsed = _date_from(lines[i + 1])
        if parsed:
            score = 3 if _INVOICE_DATE.search(line) else 2 if _OTHER_DATE.search(line) else 1
            matches.append((score, -i, parsed))
    return max(matches)[2] if matches else None


def _guess_currency(lines: list[str]) -> str | None:
    for line in lines:
        match = _CURRENCY.search(line)
        if match:
            value = (match.group(1) or match.group(2) or "").upper()
            return {"FR.": "CHF", "€": "EUR", "£": "GBP", "$": "USD"}.get(value, value)
    return None


def _guess_merchant(lines: list[str]) -> str | None:
    for line in lines[:10]:
        name = line.strip(" \t-:|")
        if not 4 <= len(name) <= 100 or _MERCHANT_SKIP.search(name):
            continue
        if _AMOUNT.search(name) or _DATE.search(name) or "@" in name:
            continue
        if len(re.findall(r"[A-Za-zÀ-ÿ]", name)) < 4:
            continue
        if name.lower().startswith(("chf", "eur", "fr.")):
            continue
        return name
    return None


def _clean_provider(name: str) -> str:
    """Keep the invoicing company, not its address on the same PDF text line."""
    # Company header: "Garage Muster AG - Musterstrasse 5 - CH-8000 Zürich".
    name = re.split(r"\s+[-–—]\s+(?=[^-\n]{2,})", name, maxsplit=1)[0]
    # The comma-separated variant is only split at recognisable street names.
    name = re.split(
        r",\s+(?=[\wÀ-ÿ -]+(?:strasse|straße|street|road|avenue|rue|weg|gasse)\b)",
        name,
        maxsplit=1,
        flags=re.I,
    )[0]
    return name.strip(" ,;-")[:120]


def normalize_registration(value: str | None) -> str:
    """Comparable Swiss/German/etc. plate characters; ignore spacing/dashes."""
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())


def compare_receipt_registration(receipt_plate: str | None, vehicle_plate: str | None) -> str:
    """Return match/mismatch/unverified without guessing from country/currency."""
    receipt = normalize_registration(receipt_plate)
    vehicle = normalize_registration(vehicle_plate)
    if not receipt:
        return "not_found"
    if not vehicle:
        return "unverified"
    return "match" if receipt == vehicle else "mismatch"


_PLATE_LABEL = re.compile(
    r"\b(?:kontrollschild|kennzeichen|nummernschild|amtliches\s+kennzeichen|"
    r"license\s+plate|registration\s+(?:number|no\.?))"
    r"\s*[:#-]?\s*(?P<plate>[A-ZÄÖÜ]{1,3}(?:[ -][A-ZÄÖÜ]{1,3})?"
    r"[ -]?\d{1,6}(?:[ -]?[A-Z]{1,2})?)\b", re.I
)
_ODOMETER = re.compile(
    r"\b(?:km[\s-]*stand|kilometerstand|laufleistung|odometer|mileage)"
    r"\s*(?:\((?:km|kilometer)\)|in\s*km)?\s*[:\-]?\s*"
    r"(?P<value>\d{1,3}(?:[ ’'\u00a0.,]\d{3})+|\d{1,7})\s*(?:km)?\b",
    re.I,
)
_COUNTRY_POSTCODE = re.compile(
    r"\b(?P<country>CH|DE|AT|FR|IT|NL|PL|BE|LU)[ -]\d{4,5}\b", re.I
)
_COUNTRY_NAME = (
    (re.compile(r"\b(?:schweiz|switzerland|suisse|svizzera)\b", re.I), "CH"),
    (re.compile(r"\b(?:deutschland|germany|allemagne)\b", re.I), "DE"),
    (re.compile(r"\b(?:österreich|oesterreich|austria)\b", re.I), "AT"),
    (re.compile(r"\b(?:frankreich|france)\b", re.I), "FR"),
    (re.compile(r"\b(?:italien|italy|italia)\b", re.I), "IT"),
)
_MODEL = re.compile(r"\b(?:marke\s*/\s*modell|fahrzeugmodell|vehicle\s*model)\s*:\s*(.{3,80})",re.I)


def _guess_registration(lines: list[str]) -> str | None:
    for line in lines[:80]:
        match = _PLATE_LABEL.search(line)
        if match:
            plate = re.sub(r"\s+", " ", match.group("plate").strip()).upper()
            if 4 <= len(normalize_registration(plate)) <= 12:
                return plate
    return None


def _guess_odometer(lines: list[str]) -> str | None:
    for line in lines[:120]:
        match = _ODOMETER.search(line)
        if not match:
            continue
        digits = re.sub(r"\D", "", match.group("value"))
        if not digits:
            continue
        value = int(digits)
        if 0 <= value <= 2_000_000:
            return str(value)
    return None


def _guess_country(lines: list[str]) -> str | None:
    """Recognize merchant country from the invoice heading, not the vehicle plate."""
    for line in lines[:5]:
        postal = _COUNTRY_POSTCODE.search(line)
        if postal:
            return postal.group("country").upper()
    for line in lines[:5]:
        for pattern, code in _COUNTRY_NAME:
            if pattern.search(line):
                return code
    return None


def _guess_vehicle_model(lines: list[str]) -> str | None:
    for line in lines[:100]:
        match = _MODEL.search(line)
        if match:
            return match.group(1).strip(" -:;,")[:80]
    return None


def _guess_category(lines: list[str], expense_group: str | None) -> str | None:
    """Use only distinctive receipt wording; never infer category from currency."""
    if expense_group not in ("maintenance", "toll", "other"):
        return None
    body = "\n".join(lines)
    if expense_group == "maintenance":
        if re.search(r"\breifen\w*|\bradwechsel\b|\bpneus?\b|\btyres?\b|\btires?\b|\bauswucht\w*",body,re.I):
            return "tires"
        if re.search(r"\b(?:service|wartung|inspektion|inspection)\b",body,re.I):
            return "service"
        if re.search(r"\b(?:bremsbelag\w*|bremsklötze|verschleiss\w*|wear\s+parts)\b",body,re.I):
            return "wear"
        if re.search(r"\b(?:reparatur|instandsetzung|repair)\b",body,re.I):
            return "repair"
    elif expense_group == "toll":
        if re.search(r"\b(?:vignette|vignetta|vinieta)\b",body,re.I):
            return "vignette"
        if re.search(r"\b(?:tunnel|passgebühr|tunnelgebühr)\b",body,re.I):
            return "tunnel_pass"
        if re.search(r"\b(?:fähre|faehre|ferry)\b",body,re.I):
            return "ferry"
        if re.search(r"\b(?:brücke|bruecke|bridge)\b",body,re.I):
            return "bridge"
        if re.search(r"\b(?:maut|road\s+toll|péage)\b",body,re.I):
            return "road_toll"
    else:
        if re.search(r"\b(?:kontrollschilder\s+bestellt|nummernschildgebühr|license\s+plates\s+fee)\b",body,re.I):
            return "plates"
        if re.search(r"\b(?:fahrzeugausweisgebühr|zulassungsgebühr|registration\s+fee)\b",body,re.I):
            return "registration_document"
        if re.search(r"\b(?:pannenhilfe|roadside\s+assistance)\b",body,re.I):
            return "roadside_assistance"
    return None


def _readable_description(parts: list[str]) -> str | None:
    if not parts:
        return None
    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        return " und ".join(parts)
    return ", ".join(parts[:-1]) + " und " + parts[-1]


def _guess_description(lines: list[str], expense_group: str | None, category: str | None) -> str | None:
    """Only provide a description when recognizable line items exist."""
    body = "\n".join(lines)
    if category == "tires" and expense_group == "maintenance":
        parts: list[str] = []
        if re.search(r"\breifen\s+wechseln\b|\breifenwechsel\b|\bradwechsel\b|\breifenmontage\b",body,re.I):
            parts.append("Reifenwechsel")
        if re.search(r"\bauswucht\w*",body,re.I):
            parts.append("Auswuchten")
        if re.search(r"\breifen(?:ein)?lagerung\b|\breifen\s+einlagern\b",body,re.I):
            parts.append("Reifeneinlagerung")
        return _readable_description(parts) or "Reifen / Räder"
    if category == "vignette":
        return "Vignette"
    if category == "road_toll":
        return "Strassenmaut"
    if category == "tunnel_pass":
        return "Tunnel-/Passgebühr"
    if category == "service" and re.search(r"\b(?:service|wartung|inspektion)\b",body,re.I):
        return "Service / Wartung"
    if category == "repair":
        return "Reparatur"
    return None


def extract_expense_fields(text: str, expense_group: str | None = None) -> dict[str, Any]:
    """Return safely prefillable values for the existing expense form."""
    if not isinstance(text, str) or not text.strip():
        return {}
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines() if line.strip()]
    lines = lines[:250]
    result: dict[str, Any] = {}
    amount = _guess_total(lines)
    when = _guess_date(lines)
    currency = _guess_currency(lines)
    provider = _guess_merchant(lines)
    if provider:
        provider = _clean_provider(provider)
    category = _guess_category(lines, expense_group)
    description = _guess_description(lines, expense_group, category)
    if amount is not None:
        result["amount"] = f"{amount:.2f}"
    if when:
        result["expense_date"] = when
    if currency:
        result["currency"] = currency
    if provider:
        result["provider"] = provider
    country = _guess_country(lines)
    if country:
        result["country"] = country
    odometer = _guess_odometer(lines)
    if odometer:
        result["odometer_km"] = odometer
    if category:
        result["category"] = category
    if description:
        result["description"] = description
    # Metadata for vehicle-check UI only, not persisted as expense columns.
    plate = _guess_registration(lines)
    if plate:
        result["receipt_registration"] = plate
    vehicle_model = _guess_vehicle_model(lines)
    if vehicle_model:
        result["receipt_vehicle_model"] = vehicle_model
    return result
