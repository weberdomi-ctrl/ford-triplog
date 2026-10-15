"""Normalize user-entered calendar dates without modifying stored records."""
from __future__ import annotations

from datetime import date, datetime
import re
from typing import Any


def parse_user_date(value: Any) -> date:
    """Accept ISO, DD.MM.YYYY and DD.MM.YY (YY means 20YY)."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value or "").strip()
    match = re.fullmatch(r"(\d{1,2})\.(\d{1,2})\.(\d{2}|\d{4})\.?", text)
    if match:
        day, month, year = match.groups()
        full_year = 2000 + int(year) if len(year) == 2 else int(year)
        return date(full_year, int(month), int(day))
    return date.fromisoformat(text)


def normalize_user_date(value: Any) -> str:
    return parse_user_date(value).isoformat()
