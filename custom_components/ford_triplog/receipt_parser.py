"""Rule-based parser profiles for OCR receipt text."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class ReceiptParseResult:
    """Result of parsing one OCR text."""

    status: str
    profile_id: str | None
    profile_name: str | None
    profile_version: str | None
    confidence: float
    fields: dict[str, Any]
    missing_fields: list[str]

    def as_dict(self) -> dict[str, Any]:
        """Return serializable parser result."""

        return {
            "status": self.status,
            "profile_id": self.profile_id,
            "profile_name": self.profile_name,
            "profile_version": self.profile_version,
            "confidence": self.confidence,
            "fields": self.fields,
            "missing_fields": self.missing_fields,
        }


class ReceiptParserEngine:
    """Load and apply bundled parser profiles."""

    def __init__(self, profile_directory: Path) -> None:
        self._profile_directory = profile_directory
        self._profiles: list[dict[str, Any]] = []

    @property
    def is_loaded(self) -> bool:
        """Return whether parser profiles have already been loaded."""

        return bool(self._profiles)

    def load(self) -> None:
        """Load bundled JSON profiles.

        This method performs file I/O and must be called through the
        Home Assistant executor.
        """

        profiles: list[dict[str, Any]] = []
        if self._profile_directory.is_dir():
            for path in sorted(self._profile_directory.glob("*.json")):
                with path.open("r", encoding="utf-8") as handle:
                    profile = json.load(handle)
                if isinstance(profile, dict) and profile.get("profile_id"):
                    profiles.append(profile)

        profiles.sort(
            key=lambda item: int(item.get("priority", 0)),
            reverse=True,
        )
        self._profiles = profiles

    def parse(self, raw_text: str) -> ReceiptParseResult:
        """Apply the best matching parser profile."""

        text = str(raw_text or "")
        if not text.strip():
            return ReceiptParseResult(
                status="no_text",
                profile_id=None,
                profile_name=None,
                profile_version=None,
                confidence=0.0,
                fields={},
                missing_fields=[],
            )

        if not self._profiles:
            return ReceiptParseResult(
                status="profiles_not_loaded",
                profile_id=None,
                profile_name=None,
                profile_version=None,
                confidence=0.0,
                fields={},
                missing_fields=[],
            )

        matches: list[tuple[float, dict[str, Any]]] = []
        for profile in self._profiles:
            score = self._match_score(profile, text)
            threshold = float(profile.get("match_threshold", 0.6))
            if score >= threshold:
                matches.append((score, profile))

        if not matches:
            return ReceiptParseResult(
                status="no_match",
                profile_id=None,
                profile_name=None,
                profile_version=None,
                confidence=0.0,
                fields={},
                missing_fields=[],
            )

        matches.sort(
            key=lambda item: (
                item[0],
                int(item[1].get("priority", 0)),
            ),
            reverse=True,
        )
        match_score, profile = matches[0]

        fields: dict[str, Any] = {}
        missing_fields: list[str] = []
        rules = profile.get("fields", {})

        for field_name, rule in rules.items():
            if not isinstance(rule, dict):
                continue
            value = self._extract_value(rule, text)
            if value is None or value == "":
                if bool(rule.get("required", False)):
                    missing_fields.append(str(field_name))
                continue
            fields[str(field_name)] = value

        field_count = max(1, len(rules))
        extracted_ratio = len(fields) / field_count
        confidence = round(
            min(1.0, (match_score * 0.55) + (extracted_ratio * 0.45)),
            4,
        )

        return ReceiptParseResult(
            status="parsed" if fields else "matched_empty",
            profile_id=str(profile.get("profile_id")),
            profile_name=str(profile.get("name") or profile.get("profile_id")),
            profile_version=str(profile.get("version") or "1.0"),
            confidence=confidence,
            fields=fields,
            missing_fields=missing_fields,
        )

    @staticmethod
    def _match_score(profile: dict[str, Any], text: str) -> float:
        match = profile.get("match", {})
        if not isinstance(match, dict):
            return 0.0

        case_sensitive = bool(match.get("case_sensitive", False))
        haystack = text if case_sensitive else text.casefold()

        required = [
            str(value)
            for value in match.get("required_contains", [])
            if str(value).strip()
        ]
        optional = [
            str(value)
            for value in match.get("optional_contains", [])
            if str(value).strip()
        ]

        normalized_required = (
            required
            if case_sensitive
            else [value.casefold() for value in required]
        )
        normalized_optional = (
            optional
            if case_sensitive
            else [value.casefold() for value in optional]
        )

        if normalized_required and not all(
            value in haystack for value in normalized_required
        ):
            return 0.0

        required_score = 1.0 if normalized_required else 0.5
        optional_hits = sum(
            1 for value in normalized_optional if value in haystack
        )
        optional_score = (
            optional_hits / len(normalized_optional)
            if normalized_optional
            else 1.0
        )

        return round((required_score * 0.75) + (optional_score * 0.25), 4)

    def _extract_value(
        self,
        rule: dict[str, Any],
        text: str,
    ) -> Any:
        method = str(rule.get("method") or "regex")

        if method == "fixed":
            return rule.get("value")

        patterns = rule.get("patterns")
        if isinstance(patterns, str):
            patterns = [patterns]
        if not isinstance(patterns, list):
            return None

        flags = re.IGNORECASE | re.MULTILINE
        if bool(rule.get("dotall", False)):
            flags |= re.DOTALL

        for pattern in patterns:
            try:
                match = re.search(str(pattern), text, flags)
            except re.error:
                continue
            if match is None:
                continue

            groups = match.groups()
            if not groups:
                value: Any = match.group(0)
            elif bool(rule.get("join_groups", False)):
                value = "".join(
                    str(group or "") for group in groups
                )
            else:
                group_index = int(rule.get("group", 1))
                value = match.group(group_index)

            return self._transform(value, rule.get("transform"))

        return None

    @staticmethod
    def _transform(value: Any, transform: Any) -> Any:
        if value is None:
            return None

        transforms = (
            transform
            if isinstance(transform, list)
            else [transform]
            if transform
            else []
        )

        result: Any = value
        for action in transforms:
            name = str(action)
            if name == "strip":
                result = str(result).strip()
            elif name == "collapse_whitespace":
                result = re.sub(r"\s+", " ", str(result)).strip()
            elif name == "remove_whitespace":
                result = re.sub(r"\s+", "", str(result))
            elif name == "decimal":
                normalized = str(result).strip().replace("'", "")
                if "," in normalized and "." in normalized:
                    if normalized.rfind(",") > normalized.rfind("."):
                        normalized = normalized.replace(".", "").replace(",", ".")
                    else:
                        normalized = normalized.replace(",", "")
                else:
                    normalized = normalized.replace(",", ".")
                result = float(normalized)
            elif name == "integer":
                result = int(re.sub(r"[^\d-]", "", str(result)))
            elif name == "date_dmy2":
                result = datetime.strptime(
                    str(result).strip(),
                    "%d.%m.%y",
                ).date().isoformat()
            elif name == "date_dmy4":
                result = datetime.strptime(
                    str(result).strip(),
                    "%d.%m.%Y",
                ).date().isoformat()
            elif name == "date_slash_dmy4":
                result = datetime.strptime(
                    str(result).strip(),
                    "%d/%m/%Y",
                ).date().isoformat()
            elif name == "datetime_dmy2_comma":
                result = datetime.strptime(
                    re.sub(r"\s+", "", str(result)),
                    "%d.%m.%y,%H:%M",
                ).isoformat()
            elif name == "datetime_dmy4_space":
                result = datetime.strptime(
                    re.sub(r"\s+", " ", str(result)).strip(),
                    "%d.%m.%Y %H:%M",
                ).isoformat()
            elif name == "datetime_iso":
                result = datetime.fromisoformat(
                    re.sub(r"\s+", " ", str(result)).strip()
                ).isoformat()
            elif name == "upper":
                result = str(result).upper()
        return result
