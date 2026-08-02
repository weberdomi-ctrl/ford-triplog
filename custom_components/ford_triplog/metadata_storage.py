"""Persistent user metadata for Ford Triplog.

Manual data is stored independently from generated trips, charges and journeys.
Deleting or rebuilding generated journey files therefore does not remove user
annotations. The schema is intentionally generic so later releases can add
charge metadata, journey metadata, receipts and OCR results without another
storage migration.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant

from .const import METADATA_FILE, METADATA_SCHEMA_VERSION, STORAGE_DIR

_LOGGER = logging.getLogger(__name__)


class FordTriplogMetadataStorage:
    """Store persistent user-maintained metadata."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self._path = Path(hass.config.path(".storage", STORAGE_DIR, METADATA_FILE))

    async def async_setup(self) -> None:
        """Create the metadata file when it does not yet exist."""

        data = await self.async_load()
        if data is None:
            await self.async_save(self._empty_data())

    async def async_load(self) -> dict[str, Any] | None:
        return await self.hass.async_add_executor_job(self._load_json)

    async def async_save(self, data: dict[str, Any]) -> None:
        normalized = self._normalize(data)
        await self.hass.async_add_executor_job(self._write_json, normalized)

    async def get_pause_overrides(self) -> dict[str, dict[str, Any]]:
        """Return all persistent pause overrides."""

        data = await self.async_load() or self._empty_data()
        pauses = data.get("pauses", {})
        if not isinstance(pauses, dict):
            return {}
        return {
            str(pause_id): dict(value)
            for pause_id, value in pauses.items()
            if isinstance(value, dict)
        }

    async def import_legacy_pause_overrides(
        self,
        overrides: dict[str, dict[str, Any]],
    ) -> bool:
        """Import journey-embedded pause data exactly once."""

        data = await self.async_load() or self._empty_data()
        migrations = data.setdefault("migrations", {})
        if not isinstance(migrations, dict):
            migrations = {}
            data["migrations"] = migrations
        if migrations.get("pause_overrides_v1") is True:
            return False
        pauses = data.setdefault("pauses", {})
        if not isinstance(pauses, dict):
            pauses = {}
            data["pauses"] = pauses

        changed = False
        for pause_id, value in overrides.items():
            normalized_id = str(pause_id).strip()
            if not normalized_id or not isinstance(value, dict):
                continue
            normalized_value = dict(value)
            if pauses.get(normalized_id) != normalized_value:
                pauses[normalized_id] = normalized_value
                changed = True

        migrations["pause_overrides_v1"] = True
        await self.async_save(data)
        return changed

    async def synchronize_pause_overrides(
        self,
        valid_pause_ids: set[str],
        authoritative_overrides: dict[str, dict[str, Any]],
    ) -> None:
        """Persist editor changes for the represented pauses.

        A missing override for a represented pause means the user explicitly
        cleared it. Metadata for unrelated pauses remains untouched.
        """

        if not valid_pause_ids:
            return

        data = await self.async_load() or self._empty_data()
        pauses = data.setdefault("pauses", {})
        if not isinstance(pauses, dict):
            pauses = {}
            data["pauses"] = pauses

        changed = False
        for pause_id in valid_pause_ids:
            value = authoritative_overrides.get(pause_id)
            if isinstance(value, dict) and value:
                normalized_value = dict(value)
                if pauses.get(pause_id) != normalized_value:
                    pauses[pause_id] = normalized_value
                    changed = True
            elif pause_id in pauses:
                pauses.pop(pause_id, None)
                changed = True

        if changed:
            await self.async_save(data)

    @staticmethod
    def _empty_data() -> dict[str, Any]:
        return {
            "schema": METADATA_SCHEMA_VERSION,
            "pauses": {},
            "charges": {},
            "journeys": {},
            "migrations": {},
        }

    @classmethod
    def _normalize(cls, data: dict[str, Any]) -> dict[str, Any]:
        normalized = cls._empty_data()
        if not isinstance(data, dict):
            return normalized

        for section in ("pauses", "charges", "journeys"):
            value = data.get(section)
            if isinstance(value, dict):
                normalized[section] = {
                    str(item_id): dict(metadata)
                    for item_id, metadata in value.items()
                    if str(item_id).strip() and isinstance(metadata, dict)
                }

        migrations = data.get("migrations")
        if isinstance(migrations, dict):
            normalized["migrations"] = {
                str(key): bool(value)
                for key, value in migrations.items()
            }
        return normalized

    def _load_json(self) -> dict[str, Any] | None:
        if not self._path.exists():
            return None
        try:
            with self._path.open("r", encoding="utf-8") as file:
                data = json.load(file)
        except (OSError, json.JSONDecodeError):
            _LOGGER.exception("Unable to read Ford Triplog metadata: %s", self._path)
            return None
        if not isinstance(data, dict):
            _LOGGER.warning("Ford Triplog metadata does not contain an object: %s", self._path)
            return None
        return self._normalize(data)

    def _write_json(self, data: dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self._path.with_suffix(f"{self._path.suffix}.tmp")
        try:
            with temporary_path.open("w", encoding="utf-8") as file:
                json.dump(data, file, ensure_ascii=False, indent=2, sort_keys=False)
                file.write("\n")
            os.replace(temporary_path, self._path)
        except Exception:
            temporary_path.unlink(missing_ok=True)
            raise
