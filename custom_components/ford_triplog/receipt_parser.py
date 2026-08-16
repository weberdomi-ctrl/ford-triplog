"""Rule-based parser profiles for OCR receipt text."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


_LOGGER = logging.getLogger(__name__)

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

    def __init__(
        self,
        profile_directory: Path,
        user_profile_directory: Path | None = None,
    ) -> None:
        self._profile_directory = profile_directory
        self._user_profile_directory = user_profile_directory
        self._user_profiles: list[dict[str, Any]] = []
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
        directories = [self._profile_directory]
        if self._user_profile_directory is not None:
            directories.append(self._user_profile_directory)

        for directory in directories:
            if not directory.is_dir():
                continue
            for path in sorted(directory.glob("*.json")):
                with path.open("r", encoding="utf-8") as handle:
                    profile = json.load(handle)
                if (
                    isinstance(profile, dict)
                    and profile.get("profile_id")
                    and isinstance(profile.get("match"), dict)
                ):
                    profiles.append(profile)

        # SQLite-backed user profiles are injected by receipt_storage.
        # They are deliberately kept separate from bundled program profiles.
        for profile in self._user_profiles:
            if (
                isinstance(profile, dict)
                and profile.get("profile_id")
                and isinstance(profile.get("match"), dict)
            ):
                profiles.append(dict(profile))

        # If a user profile has the same ID as a bundled profile, keep the
        # user version. This also prevents duplicate IDs after migration.
        by_id: dict[str, dict[str, Any]] = {}
        for profile in profiles:
            profile_id = str(profile.get("profile_id") or "").strip()
            if profile_id:
                by_id[profile_id] = profile

        profiles = list(by_id.values())
        profiles.sort(
            key=lambda item: int(item.get("priority", 0)),
            reverse=True,
        )
        self._profiles = profiles

    def set_user_profiles(
        self,
        profiles: list[dict[str, Any]],
    ) -> None:
        """Set user-created profiles loaded from persistent storage."""

        self._user_profiles = [
            dict(profile)
            for profile in profiles
            if (
                isinstance(profile, dict)
                and str(profile.get("profile_id") or "").strip()
                and isinstance(profile.get("match"), dict)
            )
        ]

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

            try:
                value = self._extract_value(rule, text)
            except (TypeError, ValueError) as err:
                _LOGGER.warning(
                    "Receipt parser field conversion failed: "
                    "profile_id=%s field=%s error=%s",
                    profile.get("profile_id"),
                    field_name,
                    err,
                )
                if bool(rule.get("required", False)):
                    missing_fields.append(str(field_name))
                continue

            if value is None or value == "":
                if bool(rule.get("required", False)):
                    missing_fields.append(str(field_name))
                continue
            fields[str(field_name)] = value

        derived_rules = profile.get("derived_fields", {})
        if isinstance(derived_rules, dict):
            for field_name, rule in derived_rules.items():
                if not isinstance(rule, dict):
                    continue
                try:
                    value = self._derive_value(rule, fields)
                except (TypeError, ValueError) as err:
                    _LOGGER.warning(
                        "Receipt parser derived field failed: "
                        "profile_id=%s field=%s error=%s",
                        profile.get("profile_id"),
                        field_name,
                        err,
                    )
                    continue
                if value is not None and value != "":
                    fields[str(field_name)] = value

        field_count = max(1, len(rules) + len(derived_rules))
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
                separator = str(rule.get("join_separator") or "")
                value = separator.join(
                    str(group or "") for group in groups
                )
            else:
                group_index = int(rule.get("group", 1))
                value = match.group(group_index)

            return self._transform(value, rule.get("transform"))

        return None

    @staticmethod
    def _derive_value(
        rule: dict[str, Any],
        fields: dict[str, Any],
    ) -> Any:
        """Calculate one field from already extracted values."""

        method = str(rule.get("method") or "")
        if method == "add_seconds":
            start_value = fields.get(str(rule.get("start_field") or ""))
            seconds_value = fields.get(str(rule.get("seconds_field") or ""))
            if start_value is None or seconds_value is None:
                return None
            start = datetime.fromisoformat(str(start_value))
            return (
                start + timedelta(seconds=int(seconds_value))
            ).isoformat()

        if method == "copy":
            return fields.get(str(rule.get("source_field") or ""))

        if method == "concat_fields":
            source_fields = rule.get("source_fields", [])
            if not isinstance(source_fields, list):
                return None
            separator = str(rule.get("separator") or ", ")
            values = [
                str(fields.get(str(field)) or "").strip()
                for field in source_fields
            ]
            values = [value for value in values if value]
            return separator.join(values) if values else None

        if method == "format_fields":
            template = str(rule.get("template") or "")
            if not template:
                return None
            values = {
                key: str(value or "").strip()
                for key, value in fields.items()
            }
            try:
                result = template.format(**values)
            except KeyError:
                return None
            result = re.sub(r"\s+,", ",", result)
            result = re.sub(r",\s*,+", ",", result)
            result = re.sub(r"\s+", " ", result).strip(" ,")
            return result or None

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
            elif name == "datetime_slash_dmy4_at":
                normalized = re.sub(
                    r"\s+",
                    " ",
                    str(result),
                ).strip()
                normalized = normalized.replace(" à ", " ")
                result = datetime.strptime(
                    normalized,
                    "%d/%m/%Y %H:%M",
                ).isoformat()
            elif name == "duration_mmss":
                normalized = str(result).strip()
                minutes, seconds = normalized.split(":", 1)
                result = (int(minutes) * 60) + int(seconds)
            elif name == "duration_hhmmss":
                normalized = str(result).strip()
                hours, minutes, seconds = normalized.split(":", 2)
                result = (
                    int(hours) * 3600
                    + int(minutes) * 60
                    + int(seconds)
                )
            elif name == "date_ordinal_month":
                normalized = re.sub(
                    r"(\d{1,2})(?:st|nd|rd|th)",
                    r"\1",
                    str(result).strip(),
                    flags=re.IGNORECASE,
                )
                month_map = {
                    "januar": 1,
                    "january": 1,
                    "februar": 2,
                    "february": 2,
                    "märz": 3,
                    "maerz": 3,
                    "march": 3,
                    "april": 4,
                    "mai": 5,
                    "may": 5,
                    "juni": 6,
                    "june": 6,
                    "juli": 7,
                    "july": 7,
                    "august": 8,
                    "september": 9,
                    "oktober": 10,
                    "october": 10,
                    "november": 11,
                    "dezember": 12,
                    "december": 12,
                }
                parts = normalized.split()
                if len(parts) != 3:
                    raise ValueError(
                        f"Unsupported ordinal date: {normalized}"
                    )
                day = int(parts[0])
                month = month_map.get(parts[1].casefold())
                if month is None:
                    raise ValueError(
                        f"Unsupported month: {parts[1]}"
                    )
                result = datetime(
                    int(parts[2]),
                    month,
                    day,
                ).date().isoformat()
            elif name == "datetime_ordinal_month":
                normalized = re.sub(
                    r"(\d{1,2})(?:st|nd|rd|th)",
                    r"\1",
                    str(result).strip(),
                    flags=re.IGNORECASE,
                )
                parts = normalized.split()
                if len(parts) != 4:
                    raise ValueError(
                        f"Unsupported ordinal datetime: {normalized}"
                    )
                month_map = {
                    "januar": 1, "january": 1,
                    "februar": 2, "february": 2,
                    "märz": 3, "maerz": 3, "march": 3,
                    "april": 4,
                    "mai": 5, "may": 5,
                    "juni": 6, "june": 6,
                    "juli": 7, "july": 7,
                    "august": 8,
                    "september": 9,
                    "oktober": 10, "october": 10,
                    "november": 11,
                    "dezember": 12, "december": 12,
                }
                month = month_map.get(parts[1].casefold())
                if month is None:
                    raise ValueError(
                        f"Unsupported month: {parts[1]}"
                    )
                hour, minute, second = (
                    int(value) for value in parts[3].split(":")
                )
                result = datetime(
                    int(parts[2]),
                    month,
                    int(parts[0]),
                    hour,
                    minute,
                    second,
                ).isoformat()
            elif name == "datetime_dmy2_comma":
                result = datetime.strptime(
                    re.sub(r"\s+", "", str(result)),
                    "%d.%m.%y,%H:%M",
                ).isoformat()
            elif name == "datetime_dmy4_space":
                normalized = re.sub(
                    r"\s+",
                    " ",
                    str(result),
                ).strip()
                normalized = re.sub(
                    r"^(\d{2}\.\d{2}\.\d{4})(\d{2}:\d{2})$",
                    r"\1 \2",
                    normalized,
                )
                result = datetime.strptime(
                    normalized,
                    "%d.%m.%Y %H:%M",
                ).isoformat()
            elif name == "datetime_iso":
                normalized = re.sub(
                    r"\s+",
                    " ",
                    str(result),
                ).strip()
                normalized = re.sub(
                    r"^(\d{4}-\d{2}-\d{2})(\d{2}:\d{2}:\d{2})$",
                    r"\1 \2",
                    normalized,
                )
                normalized = normalized.replace("T", " ")
                result = datetime.fromisoformat(normalized).isoformat()
            elif name == "upper":
                result = str(result).upper()
        return result
