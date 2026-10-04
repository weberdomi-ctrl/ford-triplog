"""Financing document storage and OCR field extraction for Ford Triplog."""

from __future__ import annotations

import functools
import mimetypes
import re
import shutil
import sqlite3
import time
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

    async def async_attach(self, financing_id: int, filename: str, original_filename: str, media_type: str | None, note: str | None = None) -> int:
        """Link an already imported file as an additional financing document."""
        from .database import FordTriplogDatabase
        base_path = Path(self.hass.config.path(".storage", STORAGE_DIR))
        db = FordTriplogDatabase(self.hass, base_path)
        await db.async_setup()
        def _write() -> int:
            with sqlite3.connect(db.db_path) as conn:
                cur = conn.execute("INSERT INTO vehicle_financing_documents (financing_id, filename, original_filename, media_type, note, created_at) VALUES (?, ?, ?, ?, ?, ?)", (int(financing_id), filename, original_filename, media_type, note, time.strftime("%Y-%m-%dT%H:%M:%S%z")))
                conn.commit()
                return int(cur.lastrowid)
        return await self.hass.async_add_executor_job(_write)

    async def async_list_for_financing(self, financing_id: int) -> list[dict[str, Any]]:
        """List additional documents linked to a financing contract."""
        from .database import FordTriplogDatabase
        base_path = Path(self.hass.config.path(".storage", STORAGE_DIR))
        db = FordTriplogDatabase(self.hass, base_path)
        await db.async_setup()
        def _read() -> list[dict[str, Any]]:
            with sqlite3.connect(db.db_path) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute("SELECT * FROM vehicle_financing_documents WHERE financing_id=? ORDER BY created_at, document_id", (int(financing_id),)).fetchall()
                return [dict(x) for x in rows]
        return await self.hass.async_add_executor_job(_read)

    async def async_delete_attachment(self, document_id: int, financing_id: int) -> None:
        """Delete one additional attachment and its persisted file."""
        from .database import FordTriplogDatabase
        base_path = Path(self.hass.config.path(".storage", STORAGE_DIR))
        db = FordTriplogDatabase(self.hass, base_path)
        await db.async_setup()
        def _delete() -> str | None:
            with sqlite3.connect(db.db_path) as conn:
                row = conn.execute("SELECT filename FROM vehicle_financing_documents WHERE document_id=? AND financing_id=?", (int(document_id), int(financing_id))).fetchone()
                if row is None:
                    return None
                conn.execute("DELETE FROM vehicle_financing_documents WHERE document_id=? AND financing_id=?", (int(document_id), int(financing_id)))
                conn.commit()
                return str(row[0])
        filename = await self.hass.async_add_executor_job(_delete)
        if filename:
            path = self.directory / filename
            await self.hass.async_add_executor_job(path.unlink, True)


def extract_pdf_text(content: bytes, max_pages: int = 5) -> str:
    """Extract embedded text from a PDF without OCR.

    Returns an empty string for image-only/scanned PDFs.
    """
    if not content:
        return ""
    try:
        from io import BytesIO
        from pypdf import PdfReader

        reader = PdfReader(BytesIO(content))
        parts: list[str] = []
        for page in reader.pages[:max_pages]:
            value = page.extract_text() or ""
            if value.strip():
                parts.append(value)
        return "\n".join(parts).strip()
    except Exception:
        return ""


def render_pdf_page_png(content: bytes, page_number: int = 0) -> bytes:
    """Render a PDF page to PNG for OCR fallback."""
    import fitz

    document = fitz.open(stream=content, filetype="pdf")
    try:
        if document.page_count <= page_number:
            return b""
        page = document.load_page(page_number)
        pixmap = page.get_pixmap(matrix=fitz.Matrix(2.0, 2.0), alpha=False)
        return pixmap.tobytes("png")
    finally:
        document.close()


def _money(value: str) -> float | None:
    text = value.replace("’", "'").replace(" ", "").replace("CHF", "").strip()
    text = text.replace("'", "")
    if "," in text and "." not in text:
        text = text.replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def _amounts_in_window(text: str) -> list[float]:
    """Return plausible monetary values from a short OCR/text window."""
    values: list[float] = []
    for token in re.findall(r"(?<!\d)(\d{1,3}(?:['’ .]\d{3})*(?:[.,]\d{2})|\d{1,6}[.,]\d{2})(?!\d)", text):
        value = _money(token)
        if value is not None:
            values.append(value)
    return values


def _payment_total_after_label(text: str, label_pattern: str, window: int = 180) -> float | None:
    """Find the gross/total payment near a leasing-rate label.

    Leasing contracts commonly print net amount, VAT and gross amount on the
    same row.  The gross amount is normally the largest monetary value in that
    row/window, so prefer it over the first number following the label.
    """
    match = re.search(label_pattern, text, re.IGNORECASE)
    if not match:
        return None
    tail = text[match.end():match.end() + window]
    # Stop before the next well-known field so unrelated amounts do not win.
    stop = re.search(
        r"(?:Restwert|Barkaufpreis|Kaufpreis|Jahresfahrleistung|Mehrkilometer|Nominal|Effektiv|2\.?\s*[-–]\s*\d+\.?\s*Leasingrate)",
        tail,
        re.IGNORECASE,
    )
    if stop:
        tail = tail[:stop.start()]
    amounts = _amounts_in_window(tail)
    return max(amounts) if amounts else None


def extract_financing_fields(raw_text: str) -> dict[str, Any]:
    """Extract conservative financing suggestions from PDF/OCR text."""
    text = str(raw_text or "")
    compact = " ".join(text.split())
    result: dict[str, Any] = {"financing_type": "leasing"}

    patterns: list[tuple[str, str, Any]] = [
        ("contract_number", r"(?:Leasing[- ]?(?:Nr\.?|Nummer)|Vertrags(?:nummer|nr\.?)?)\s*[:#]?\s*([A-Z0-9./-]{4,})", str),
        ("duration_months", r"(?:Leasingdauer|Vertragsdauer|Laufzeit)\s*[:]?\s*(\d{1,3})\s*(?:Monate|Mt\.?|months)?", int),
        ("purchase_price", r"(?:Barkaufpreis|Kaufpreis|Fahrzeugpreis)\s*[:]?\s*(?:CHF\s*)?([0-9'’ .]+(?:[.,]\d{2})?)", _money),
        ("interest_rate", r"(?:Nominal(?:zins|er Jahreszins)|Jahreszinssatz(?:\s+nominal)?|Jahreszins[^0-9]{0,20})\s*[:]?\s*([0-9]+(?:[.,]\d+)?)\s*%", lambda x: float(x.replace(",", "."))),
        ("annual_mileage", r"(?:Jährliche\s+Fahrleistung|Jahresfahrleistung|Kilometerleistung pro Jahr|km/Jahr)\s*[:]?\s*([0-9'’ .]+)", lambda x: int(re.sub(r"\D", "", x))),
        ("excess_km_rate", r"(?:Mehrkilometer(?:kosten)?|Mehr-km)[^0-9]{0,60}(?:CHF\s*)?([0-9]+(?:[.,]\d+)?)", lambda x: float(x.replace(",", "."))),
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

    # Contract/start date: only explicit start/commencement/takeover labels are
    # accepted.  Never use an unlabeled signature or document date.
    date_match = re.search(
        r"(?:Vertragsbeginn|Leasingbeginn|Mietbeginn|Übernahme(?:datum)?|Fahrzeugübernahme)\s*[:]?\s*"
        r"(\d{1,2}[./-]\d{1,2}[./-]\d{4})",
        compact,
        re.IGNORECASE,
    )
    if date_match:
        raw_date = date_match.group(1).replace("/", ".").replace("-", ".")
        try:
            result["start_date"] = datetime.strptime(raw_date, "%d.%m.%Y").date().isoformat()
        except ValueError:
            pass

    # Rest values can also be printed as net + VAT + gross. Prefer the
    # largest monetary amount close to the Restwert label, just like rates.
    residual_value = _payment_total_after_label(
        compact, r"Restwert(?:\s+(?:inkl\.?|exkl\.?)\s*(?:MWST|MwSt\.?))?", window=140
    )
    if residual_value is not None:
        result["residual_value"] = residual_value

    # Prefer the gross/total amounts. On Ford Credit/BANK-now contracts the
    # row contains net + VAT + gross, e.g. 4625.35 + 374.65 = 5000.00 and
    # 690.96 + 55.99 = 746.95. Choosing the largest row amount avoids taking
    # the net amount by accident.
    first_payment = _payment_total_after_label(compact, r"1\.?\s*Leasingrate")
    if first_payment is not None:
        result["first_payment"] = first_payment

    regular_label = re.search(r"2\.?\s*[-–]\s*(\d{1,3})\.?\s*Leasingrate", compact, re.IGNORECASE)
    if regular_label:
        result["number_of_payments"] = int(regular_label.group(1))
        regular_payment = _payment_total_after_label(
            compact, r"2\.?\s*[-–]\s*\d{1,3}\.?\s*Leasingrate"
        )
        if regular_payment is not None:
            result["regular_payment"] = regular_payment

    if "number_of_payments" not in result and result.get("duration_months"):
        result["number_of_payments"] = int(result["duration_months"])

    provider = re.search(r"\b(BANK-now AG|Ford Credit|Cembra Money Bank AG|AMAG Leasing AG)\b", compact, re.IGNORECASE)
    if provider:
        result["provider"] = provider.group(1)

    result["currency"] = "CHF"
    return result

