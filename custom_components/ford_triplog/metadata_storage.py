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

from .const import (
    CONF_STORAGE_READ_BACKEND,
    DEFAULT_STORAGE_READ_BACKEND,
    METADATA_FILE,
    METADATA_SCHEMA_VERSION,
    STORAGE_DIR,
    STORAGE_READ_BACKEND_SQLITE,
)
from .database import FordTriplogDatabase

_LOGGER = logging.getLogger(__name__)


class FordTriplogMetadataStorage:
    """Store persistent user-maintained metadata."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self._path = Path(hass.config.path(".storage", STORAGE_DIR, METADATA_FILE))
        self._base_directory = Path(
            hass.config.path(".storage", STORAGE_DIR)
        )
        self.database = FordTriplogDatabase(
            hass,
            self._base_directory,
        )
        self.read_backend = DEFAULT_STORAGE_READ_BACKEND
        entries = hass.config_entries.async_entries("ford_triplog")
        if len(entries) == 1:
            self.read_backend = str(
                entries[0].options.get(
                    CONF_STORAGE_READ_BACKEND,
                    DEFAULT_STORAGE_READ_BACKEND,
                )
            )

    async def async_setup(self) -> None:
        """Initialize metadata storage."""

        await self.database.async_setup()

        if self.read_backend == STORAGE_READ_BACKEND_SQLITE:
            await self._migrate_charge_metadata_to_table()
            return

        data = await self.async_load()
        if data is None:
            await self.async_save(self._empty_data())

    async def _migrate_charge_metadata_to_table(self) -> None:
        """Move legacy metadata['charges'] into the dedicated SQLite table."""

        data = await self.database.load_metadata()
        if not isinstance(data, dict):
            return

        migrations = data.setdefault("migrations", {})
        if not isinstance(migrations, dict):
            migrations = {}
            data["migrations"] = migrations

        legacy_charges = data.get("charges", {})
        if not isinstance(legacy_charges, dict):
            legacy_charges = {}

        existing = await self.database.load_all_charge_metadata()

        if (
            migrations.get("charge_metadata_table_v1") is True
            and not legacy_charges
        ):
            return

        merged: dict[str, dict[str, Any]] = {
            str(charge_id): dict(value)
            for charge_id, value in legacy_charges.items()
            if str(charge_id).strip() and isinstance(value, dict)
        }

        # Existing dedicated-table values are newer/authoritative.
        merged.update(existing)

        if merged:
            saved = await self.database.save_all_charge_metadata(merged)
            if not saved:
                raise OSError(
                    "Unable to migrate charge metadata to SQLite table"
                )

        data["charges"] = {}
        migrations["charge_metadata_table_v1"] = True

        saved = await self.database.save_metadata(
            self._normalize(data)
        )
        if not saved:
            raise OSError(
                "Unable to finalize charge metadata migration"
            )

        _LOGGER.info(
            "Charge metadata migration completed: %d records",
            len(merged),
        )

    async def async_load(self) -> dict[str, Any] | None:
        if self.read_backend == STORAGE_READ_BACKEND_SQLITE:
            data = await self.database.load_metadata()
            if data is None:
                return None

            normalized = self._normalize(data)
            normalized["charges"] = (
                await self.database.load_all_charge_metadata()
            )
            return normalized

        return await self.hass.async_add_executor_job(self._load_json)

    async def async_save(self, data: dict[str, Any]) -> None:
        normalized = self._normalize(data)

        if self.read_backend == STORAGE_READ_BACKEND_SQLITE:
            charge_metadata = normalized.get("charges", {})
            if not isinstance(charge_metadata, dict):
                charge_metadata = {}

            saved = await self.database.save_all_charge_metadata(
                charge_metadata
            )
            if not saved:
                raise OSError(
                    "Unable to save charge metadata to SQLite"
                )

            base_metadata = dict(normalized)
            base_metadata["charges"] = {}

            saved = await self.database.save_metadata(base_metadata)
            if not saved:
                raise OSError("Unable to save metadata to SQLite")
            return

        await self.hass.async_add_executor_job(self._write_json, normalized)

    async def get_pause_overrides(self) -> dict[str, dict[str, Any]]:
        """Return all persistent pause overrides."""

        data = await self.async_load() or self._empty_data()
        pauses = data.get("pauses", {})
        if not isinstance(pauses, dict):
            return {}
        return {
            str(pause_id): {
                key: item
                for key, item in value.items()
                if key != "receipts"
            }
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
            existing = pauses.get(normalized_id)
            existing_receipts = (
                existing.get("receipts")
                if isinstance(existing, dict)
                and isinstance(existing.get("receipts"), list)
                else None
            )
            normalized_value = dict(value)
            if existing_receipts:
                normalized_value["receipts"] = existing_receipts
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
                existing = pauses.get(pause_id)
                existing_receipts = (
                    existing.get("receipts")
                    if isinstance(existing, dict)
                    and isinstance(existing.get("receipts"), list)
                    else None
                )
                normalized_value = dict(value)
                if existing_receipts:
                    normalized_value["receipts"] = existing_receipts
                if pauses.get(pause_id) != normalized_value:
                    pauses[pause_id] = normalized_value
                    changed = True
            elif pause_id in pauses:
                existing = pauses.get(pause_id)
                if isinstance(existing, dict) and existing.get("receipts"):
                    receipts = existing.get("receipts")
                    pauses[pause_id] = {"receipts": receipts}
                    changed = True
                else:
                    pauses.pop(pause_id, None)
                    changed = True

        if changed:
            await self.async_save(data)


    async def add_receipt(
        self,
        target_type: str,
        target_id: str,
        receipt: dict[str, Any],
    ) -> None:
        """Attach one receipt to a pause or charging session."""

        section = self._receipt_section(target_type)
        normalized_target_id = str(target_id).strip()
        if not normalized_target_id:
            raise ValueError("Receipt target ID is required")

        data = await self.async_load() or self._empty_data()
        items = data.setdefault(section, {})
        if not isinstance(items, dict):
            items = {}
            data[section] = items
        metadata = items.setdefault(normalized_target_id, {})
        if not isinstance(metadata, dict):
            metadata = {}
            items[normalized_target_id] = metadata
        receipts = metadata.setdefault("receipts", [])
        if not isinstance(receipts, list):
            receipts = []
            metadata["receipts"] = receipts

        receipt_id = str(receipt.get("receipt_id") or "").strip()
        if not receipt_id:
            raise ValueError("Receipt ID is required")
        receipts[:] = [
            item for item in receipts
            if not isinstance(item, dict)
            or str(item.get("receipt_id") or "") != receipt_id
        ]
        receipts.append(dict(receipt))
        await self.async_save(data)

    async def get_all_receipts(self) -> list[dict[str, Any]]:
        """Return receipts from all supported metadata sections."""

        data = await self.async_load() or self._empty_data()
        result: list[dict[str, Any]] = []
        for section, target_type in (("pauses", "pause"), ("charges", "charge")):
            items = data.get(section, {})
            if not isinstance(items, dict):
                continue
            for target_id, metadata in items.items():
                if not isinstance(metadata, dict):
                    continue
                receipts = metadata.get("receipts", [])
                if not isinstance(receipts, list):
                    continue
                for receipt in receipts:
                    if isinstance(receipt, dict):
                        value = dict(receipt)
                        value["target_type"] = target_type
                        value["target_id"] = str(target_id)
                        result.append(value)
        result.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
        return result

    async def remove_receipt(self, receipt_id: str) -> dict[str, Any] | None:
        """Remove one receipt from metadata and return its record."""

        normalized_id = str(receipt_id).strip()
        if not normalized_id:
            return None
        data = await self.async_load() or self._empty_data()
        for section in ("pauses", "charges"):
            items = data.get(section, {})
            if not isinstance(items, dict):
                continue
            for metadata in items.values():
                if not isinstance(metadata, dict):
                    continue
                receipts = metadata.get("receipts", [])
                if not isinstance(receipts, list):
                    continue
                for index, receipt in enumerate(receipts):
                    if (
                        isinstance(receipt, dict)
                        and str(receipt.get("receipt_id") or "") == normalized_id
                    ):
                        removed = dict(receipt)
                        receipts.pop(index)
                        if not receipts:
                            metadata.pop("receipts", None)
                        await self.async_save(data)
                        return removed
        return None

    async def get_receipt(self, receipt_id: str) -> dict[str, Any] | None:
        """Return one receipt including its target metadata."""

        normalized_id = str(receipt_id).strip()
        if not normalized_id:
            return None
        data = await self.async_load() or self._empty_data()
        for section, target_type in (("pauses", "pause"), ("charges", "charge")):
            items = data.get(section, {})
            if not isinstance(items, dict):
                continue
            for target_id, metadata in items.items():
                if not isinstance(metadata, dict):
                    continue
                receipts = metadata.get("receipts", [])
                if not isinstance(receipts, list):
                    continue
                for receipt in receipts:
                    if (
                        isinstance(receipt, dict)
                        and str(receipt.get("receipt_id") or "") == normalized_id
                    ):
                        value = dict(receipt)
                        value["target_type"] = target_type
                        value["target_id"] = str(target_id)
                        return value
        return None

    async def update_receipt(
        self,
        receipt_id: str,
        updates: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Update one receipt in-place and return the resulting record."""

        normalized_id = str(receipt_id).strip()
        if not normalized_id:
            return None
        data = await self.async_load() or self._empty_data()
        for section, target_type in (("pauses", "pause"), ("charges", "charge")):
            items = data.get(section, {})
            if not isinstance(items, dict):
                continue
            for target_id, metadata in items.items():
                if not isinstance(metadata, dict):
                    continue
                receipts = metadata.get("receipts", [])
                if not isinstance(receipts, list):
                    continue
                for receipt in receipts:
                    if (
                        isinstance(receipt, dict)
                        and str(receipt.get("receipt_id") or "") == normalized_id
                    ):
                        for key, value in updates.items():
                            if value is None:
                                receipt.pop(str(key), None)
                            else:
                                receipt[str(key)] = value
                        await self.async_save(data)
                        result = dict(receipt)
                        result["target_type"] = target_type
                        result["target_id"] = str(target_id)
                        return result
        return None

    @staticmethod
    def _receipt_section(target_type: str) -> str:
        if target_type == "pause":
            return "pauses"
        if target_type == "charge":
            return "charges"
        raise ValueError("Unsupported receipt target type")

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
