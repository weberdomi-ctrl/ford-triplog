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


def extract_expense_fields(text: str) -> dict[str, Any]:
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
    if amount is not None:
        result["amount"] = f"{amount:.2f}"
    if when:
        result["expense_date"] = when
    if currency:
        result["currency"] = currency
    if provider:
        result["provider"] = provider
    return result
