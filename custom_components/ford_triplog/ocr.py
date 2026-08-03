"""Local OCR support for Ford Triplog receipt files."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any

from homeassistant.core import HomeAssistant


_DATE_PATTERNS = (
    re.compile(r"\b(?P<day>\d{1,2})[.\-/](?P<month>\d{1,2})[.\-/](?P<year>\d{2,4})\b"),
    re.compile(r"\b(?P<year>\d{4})[.\-/](?P<month>\d{1,2})[.\-/](?P<day>\d{1,2})\b"),
)
_TIME_PATTERN = re.compile(r"\b([01]?\d|2[0-3])[:.]([0-5]\d)\b")
_AMOUNT_PATTERN = re.compile(
    r"(?<!\d)(?P<amount>\d{1,6}(?:[ '\u00a0]\d{3})*(?:[.,]\d{2}))(?!\d)"
)
_CURRENCY_PATTERN = re.compile(r"\b(CHF|EUR|USD|GBP|PLN)\b|(?<!\w)(Fr\.?|€|\$|£)(?!\w)", re.I)
_TOTAL_HINTS = (
    "total",
    "gesamt",
    "summe",
    "betrag",
    "zu zahlen",
    "zahlbetrag",
    "totalbetrag",
    "suma",
    "razem",
)


@dataclass(slots=True)
class OCRLine:
    text: str
    confidence: float | None = None


class FordTriplogReceiptOCR:
    """Run local OCR and derive conservative receipt suggestions."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass

    async def async_analyze(self, path: Path) -> dict[str, Any]:
        """Analyze one image or PDF receipt."""

        return await self.hass.async_add_executor_job(self._analyze_sync, path)

    def _analyze_sync(self, path: Path) -> dict[str, Any]:
        if not path.is_file():
            raise ValueError("Receipt file does not exist")

        input_value: Any = str(path)
        suffix = path.suffix.lower()
        if suffix == ".pdf":
            input_value = self._render_pdf_first_page(path)

        try:
            from rapidocr import RapidOCR
        except ImportError as err:
            raise RuntimeError("RapidOCR is not installed") from err

        engine = RapidOCR()
        result = engine(input_value)
        lines = self._extract_lines(result)
        if not lines:
            raise ValueError("No text was recognized")

        raw_text = "\n".join(line.text for line in lines)
        confidences = [
            line.confidence
            for line in lines
            if isinstance(line.confidence, (int, float))
        ]
        suggestions = self._extract_suggestions(lines)
        return {
            "engine": "rapidocr",
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "raw_text": raw_text,
            "lines": [
                {"text": line.text, "confidence": line.confidence}
                for line in lines
            ],
            "confidence": round(mean(confidences), 4) if confidences else None,
            "suggestions": suggestions,
        }

    @staticmethod
    def _render_pdf_first_page(path: Path) -> bytes:
        """Render the first PDF page to PNG bytes for OCR."""

        try:
            import fitz
        except ImportError as err:
            raise RuntimeError("PyMuPDF is not installed") from err

        document = fitz.open(path)
        try:
            if document.page_count < 1:
                raise ValueError("PDF contains no pages")
            page = document.load_page(0)
            matrix = fitz.Matrix(2.0, 2.0)
            pixmap = page.get_pixmap(matrix=matrix, alpha=False)
            return pixmap.tobytes("png")
        finally:
            document.close()

    @classmethod
    def _extract_lines(cls, result: Any) -> list[OCRLine]:
        """Support current and legacy RapidOCR result structures."""

        if result is None:
            return []

        texts = getattr(result, "txts", None)
        scores = getattr(result, "scores", None)
        if texts is not None:
            return cls._lines_from_texts_scores(texts, scores)

        if isinstance(result, tuple) and result:
            payload = result[0]
            if isinstance(payload, list):
                return cls._lines_from_legacy_payload(payload)

        if isinstance(result, list):
            return cls._lines_from_legacy_payload(result)

        to_json = getattr(result, "to_json", None)
        if callable(to_json):
            payload = to_json()
            if isinstance(payload, dict):
                texts = payload.get("txts") or payload.get("texts")
                scores = payload.get("scores")
                if texts:
                    return cls._lines_from_texts_scores(texts, scores)
        return []

    @staticmethod
    def _lines_from_texts_scores(texts: Any, scores: Any) -> list[OCRLine]:
        result: list[OCRLine] = []
        score_list = list(scores) if scores is not None else []
        for index, text in enumerate(list(texts)):
            normalized = str(text or "").strip()
            if not normalized:
                continue
            confidence = None
            if index < len(score_list):
                try:
                    confidence = float(score_list[index])
                except (TypeError, ValueError):
                    confidence = None
            result.append(OCRLine(normalized, confidence))
        return result

    @staticmethod
    def _lines_from_legacy_payload(payload: list[Any]) -> list[OCRLine]:
        result: list[OCRLine] = []
        for item in payload:
            text: str | None = None
            confidence: float | None = None
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                second = item[1]
                if isinstance(second, (list, tuple)) and second:
                    text = str(second[0] or "").strip()
                    if len(second) > 1:
                        try:
                            confidence = float(second[1])
                        except (TypeError, ValueError):
                            confidence = None
                elif isinstance(second, str):
                    text = second.strip()
            if text:
                result.append(OCRLine(text, confidence))
        return result

    @classmethod
    def _extract_suggestions(cls, lines: list[OCRLine]) -> dict[str, Any]:
        texts = [line.text.strip() for line in lines if line.text.strip()]
        suggestions: dict[str, Any] = {
            "merchant": cls._guess_merchant(texts),
            "date": cls._guess_date(texts),
            "time": cls._guess_time(texts),
            "amount": cls._guess_amount(texts),
            "currency": cls._guess_currency(texts),
        }
        return {key: value for key, value in suggestions.items() if value not in (None, "")}

    @staticmethod
    def _guess_merchant(lines: list[str]) -> str | None:
        for line in lines[:8]:
            value = line.strip(" -:|")
            if len(value) < 3 or not any(char.isalpha() for char in value):
                continue
            lower = value.lower()
            if any(hint in lower for hint in ("kasse", "receipt", "beleg", "rechnung", "datum")):
                continue
            if _AMOUNT_PATTERN.search(value):
                continue
            return value[:120]
        return None

    @staticmethod
    def _guess_date(lines: list[str]) -> str | None:
        for line in lines:
            for pattern in _DATE_PATTERNS:
                match = pattern.search(line)
                if not match:
                    continue
                year = int(match.group("year"))
                if year < 100:
                    year += 2000
                try:
                    value = datetime(
                        year,
                        int(match.group("month")),
                        int(match.group("day")),
                    )
                except ValueError:
                    continue
                return value.date().isoformat()
        return None

    @staticmethod
    def _guess_time(lines: list[str]) -> str | None:
        for line in lines:
            match = _TIME_PATTERN.search(line)
            if match:
                return f"{int(match.group(1)):02d}:{int(match.group(2)):02d}"
        return None

    @classmethod
    def _guess_amount(cls, lines: list[str]) -> float | None:
        candidates: list[tuple[int, float]] = []
        for index, line in enumerate(lines):
            lower = line.lower()
            priority = 2 if any(hint in lower for hint in _TOTAL_HINTS) else 1
            for match in _AMOUNT_PATTERN.finditer(line):
                normalized = match.group("amount").replace(" ", "").replace("\u00a0", "")
                normalized = normalized.replace("'", "").replace(",", ".")
                try:
                    value = float(normalized)
                except ValueError:
                    continue
                if 0 < value < 1_000_000:
                    candidates.append((priority * 10_000 + index, value))
        if not candidates:
            return None
        hinted = [item for item in candidates if item[0] >= 20_000]
        selected = hinted[-1] if hinted else max(candidates, key=lambda item: item[1])
        return round(selected[1], 2)

    @staticmethod
    def _guess_currency(lines: list[str]) -> str | None:
        for line in lines:
            match = _CURRENCY_PATTERN.search(line)
            if not match:
                continue
            token = (match.group(1) or match.group(2) or "").upper().replace(".", "")
            return {
                "FR": "CHF",
                "€": "EUR",
                "$": "USD",
                "£": "GBP",
            }.get(token, token)
        return None
