"""Presentation-only helpers for vehicle expense dialogs (Beta 6 R3).

Never modifies expense amounts, dates, storage or receipt recognition.
"""
from __future__ import annotations

from datetime import date
from typing import Any

_CATEGORIES = {
    "maintenance": {
        "service": ("Service", "Service", "Serwis"),
        "repair": ("Reparatur", "Repair", "Naprawa"),
        "tires": ("Reifen / Räder", "Tyres / wheels", "Opony / koła"),
        "wear": ("Verschleissteile", "Wear parts", "Części eksploatacyjne"),
        "care": ("Fahrzeugpflege", "Vehicle care", "Pielęgnacja pojazdu"),
        "accessories": ("Zubehör", "Accessories", "Akcesoria"),
        "other": ("Sonstiges", "Other", "Inne"),
    },
    "toll": {
        "vignette": ("Vignette", "Vignette", "Winieta"),
        "road_toll": ("Strassenmaut", "Road toll", "Opłata drogowa"),
        "tunnel_pass": ("Tunnel / Pass", "Tunnel / mountain pass", "Tunel / przełęcz"),
        "bridge": ("Brücke", "Bridge", "Most"),
        "ferry": ("Fähre", "Ferry", "Prom"),
        "other": ("Sonstiges", "Other", "Inne"),
    },
    "other": {
        "registration_document": ("Fahrzeugausweis / Zulassung", "Registration document", "Dowód rejestracyjny"),
        "plates": ("Kontrollschilder", "Licence plates", "Tablice rejestracyjne"),
        "mutation": ("Mutation", "Registration change", "Zmiana rejestracyjna"),
        "admin_fee": ("Administrative Gebühr", "Administrative fee", "Opłata administracyjna"),
        "roadside_assistance": ("Pannenhilfe", "Roadside assistance", "Pomoc drogowa"),
        "other": ("Sonstiges", "Other", "Inne"),
    },
}

_LANGUAGE_INDEX = {"de": 0, "en": 1, "pl": 2}


def expense_sort_key(expense: dict[str, Any]) -> tuple[str, int]:
    """Newest dated entries first, with expense ID as deterministic tie-breaker."""
    raw = str(expense.get("expense_date") or expense.get("valid_from") or "").strip()
    try:
        stamp = date.fromisoformat(raw).isoformat()
    except (TypeError, ValueError):
        try:
            year = int(expense.get("expense_year") or 0)
        except (TypeError, ValueError):
            year = 0
        stamp = f"{year:04d}-01-01" if 1 <= year <= 9999 else "0000-01-01"
    try:
        expense_id = int(expense.get("expense_id") or 0)
    except (ValueError, TypeError):
        expense_id = 0
    return stamp, expense_id


def format_expense_choice(expense: dict[str, Any], group: str, language: str) -> str:
    """Readable HA select label using local date, currency and translated category."""
    lang = language.lower().split("-")[0]
    lang_i = _LANGUAGE_INDEX.get(lang, 1)
    raw_date = str(
        expense.get("expense_date") or expense.get("valid_from") or ""
    ).strip()
    try:
        display_date = date.fromisoformat(raw_date).strftime("%d.%m.%Y")
    except (ValueError, TypeError):
        display_date = str(expense.get("expense_year") or "—")
    raw_category = str(expense.get("category") or "other")
    category = _CATEGORIES.get(group, {}).get(raw_category)
    category_label = category[lang_i] if category else raw_category
    try:
        amount = f"{float(expense.get('amount') or 0):,.2f}".replace(",", "'")
    except (TypeError, ValueError):
        amount = "—"
    currency = str(expense.get("currency") or "CHF").strip()
    label = f"{display_date} · {currency} {amount} · {category_label}"
    provider = " ".join(str(expense.get("provider") or "").split())
    if provider:
        label += f" · {provider[:42]}"
    return label[:160]


def vehicle_check_label(
    result: str,
    receipt_plate: str,
    vehicle_plate: str,
    receipt_model: str,
    language: str,
) -> str:
    """Conspicuous single-choice display label for HA's native form selector."""
    de = language.lower().startswith("de")
    if result == "match":
        msg = (
            f"✓ Kontrollschild {receipt_plate} stimmt überein"
            if de else f"✓ Plate {receipt_plate} matches vehicle"
        )
    elif result == "mismatch":
        msg = (
            f"⚠ Beleg {receipt_plate} ≠ Fahrzeug {vehicle_plate} – Bestätigung nötig"
            if de else f"⚠ Receipt {receipt_plate} ≠ vehicle {vehicle_plate} – confirm"
        )
    elif result == "unverified":
        msg = (
            f"⚠ Beleg {receipt_plate}: kein Kennzeichen beim Fahrzeug gespeichert"
            if de else f"⚠ Receipt {receipt_plate}: no vehicle plate stored"
        )
    else:
        msg = (
            "⚠ Kein Kontrollschild auf dem Beleg erkannt – Zuordnung prüfen"
            if de else "⚠ No plate detected on receipt – verify vehicle"
        )
    if receipt_model:
        msg += f" · {receipt_model[:45]}"
    return msg
