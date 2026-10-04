"""Financing document storage and OCR field extraction for Ford Triplog."""

from __future__ import annotations

import functools
import mimetypes
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from homeassistant.core import HomeAssistant

from .const import STORAGE_DIR

_ALLOWED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".webp"}


class FordTriplogFinancingDocumentStorage:
    """Persist uploaded financing documents independently of HA upload temp files."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self.directory = Path(hass.config.path(".storage", STORAGE_DIR, "financing_documents"))

    async def async_setup(self) -> None:
        await self.hass.async_add_executor_job(self.directory.mkdir, 0o755, True, True)

    async def async_import(self, source_path: str | Path, original_name: str | None = None) -> dict[str, Any]:
        await self.async_setup()
        source = Path(source_path)
        supplied_name = Path(original_name or source.name).name
        suffix = Path(supplied_name).suffix.lower() or source.suffix.lower()
        if suffix not in _ALLOWED_EXTENSIONS:
            raise ValueError("Unsupported financing document type")
        content = await self.hass.async_add_executor_job(source.read_bytes)
        if not content:
            raise ValueError("Financing document is empty")
        name = f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}_{uuid4().hex[:12]}{suffix}"
        destination = self.directory / name
        await self.hass.async_add_executor_job(functools.partial(shutil.copyfile, source, destination))
        return {
            "filename": name,
            "original_filename": supplied_name,
            "media_type": mimetypes.guess_type(supplied_name)[0] or "application/octet-stream",
            "content": content,
        }


def _money(value: str) -> float | None:
    text = value.replace("’", "'").replace(" ", "").replace("CHF", "").strip()
    text = text.replace("'", "")
    if "," in text and "." not in text:
        text = text.replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def extract_financing_fields(raw_text: str) -> dict[str, Any]:
    """Extract conservative financing suggestions from OCR text.

    Values are suggestions only and are always reviewed in the HA form.
    """
    text = str(raw_text or "")
    compact = " ".join(text.split())
    result: dict[str, Any] = {"financing_type": "leasing"}

    patterns: list[tuple[str, str, Any]] = [
        ("contract_number", r"(?:Leasing[- ]?(?:Nr\.?|Nummer)|Vertrags(?:nummer|nr\.?)?)\s*[:#]?\s*([A-Z0-9./-]{4,})", str),
        ("duration_months", r"(?:Vertragsdauer|Laufzeit)\s*[:]?\s*(\d{1,3})\s*(?:Monate|Mt\.?|months)", int),
        ("purchase_price", r"(?:Barkaufpreis|Kaufpreis|Fahrzeugpreis)\s*[:]?\s*(?:CHF\s*)?([0-9'’ .]+(?:[.,]\d{2})?)", _money),
        ("residual_value", r"(?:Restwert)\s*[:]?\s*(?:CHF\s*)?([0-9'’ .]+(?:[.,]\d{2})?)", _money),
        ("interest_rate", r"(?:Nominal(?:zins|er Jahreszins)|Jahreszins[^0-9]{0,20})\s*[:]?\s*([0-9]+(?:[.,]\d+)?)\s*%", lambda x: float(x.replace(",", "."))),
        ("annual_mileage", r"(?:Jahresfahrleistung|Kilometerleistung pro Jahr|km/Jahr)\s*[:]?\s*([0-9'’ .]+)", lambda x: int(re.sub(r"\D", "", x))),
        ("excess_km_rate", r"(?:Mehrkilometer|Mehr-km)[^0-9]{0,40}(?:CHF\s*)?([0-9]+(?:[.,]\d+)?)", lambda x: float(x.replace(",", "."))),
    ]
    for key, pattern, convert in patterns:
        match = re.search(pattern, compact, re.IGNORECASE)
        if match:
            try:
                value = convert(match.group(1))
            except (TypeError, ValueError):
                value = None
            if value not in (None, ""):
                result[key] = value

    # First and regular leasing payments. Support forms such as
    # "1. Leasingrate CHF 5'000.00" and "2.-48. Leasingrate CHF 746.95".
    first = re.search(r"1\.?\s*Leasingrate[^0-9]{0,25}(?:CHF\s*)?([0-9'’ .]+(?:[.,]\d{2})?)", compact, re.IGNORECASE)
    if first:
        value = _money(first.group(1))
        if value is not None:
            result["first_payment"] = value

    regular = re.search(r"2\.?\s*[-–]\s*(\d{1,3})\.?\s*Leasingrate[^0-9]{0,25}(?:CHF\s*)?([0-9'’ .]+(?:[.,]\d{2})?)", compact, re.IGNORECASE)
    if regular:
        result["number_of_payments"] = int(regular.group(1))
        value = _money(regular.group(2))
        if value is not None:
            result["regular_payment"] = value

    # Fallback count from duration for conventional monthly leasing.
    if "number_of_payments" not in result and result.get("duration_months"):
        result["number_of_payments"] = int(result["duration_months"])

    # Provider hints: deliberately conservative.
    provider = re.search(r"\b(BANK-now AG|Ford Credit|Cembra Money Bank AG|AMAG Leasing AG)\b", compact, re.IGNORECASE)
    if provider:
        result["provider"] = provider.group(1)

    result["currency"] = "CHF" if "CHF" in text.upper() else "CHF"
    return result
