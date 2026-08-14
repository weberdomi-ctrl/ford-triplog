"""
Ford Triplog

Track your Ford.

Separate storage for daily journeys.

Version: 1.6.0
Release: 1.6b
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant

from .database import FordTriplogDatabase
from .const import (
    CURRENT_JOURNEY_FILE,
    JOURNEYS_DIR,
    LAST_JOURNEY_FILE,
    STORAGE_DIR,
)
from .journey import FordTriplogJourney, build_pause_id
from .metadata_storage import FordTriplogMetadataStorage

_LOGGER = logging.getLogger(__name__)


class FordTriplogJourneyStorage:
    """Store journeys independently from trips and charging sessions."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize journey storage."""

        self.hass = hass

        self._base_directory = Path(
            hass.config.path(
                ".storage",
                STORAGE_DIR,
            )
        )
        self._journeys_directory = (
            self._base_directory / JOURNEYS_DIR
        )
        self._current_journey_path = (
            self._base_directory / CURRENT_JOURNEY_FILE
        )
        self._last_journey_path = (
            self._base_directory / LAST_JOURNEY_FILE
        )
        self._metadata_storage = FordTriplogMetadataStorage(hass)
        self.database = FordTriplogDatabase(
            hass,
            self._base_directory,
        )
        self._archive_lock = asyncio.Lock()

    async def async_setup(self) -> None:
        """Create the journey storage directories."""

        await self.hass.async_add_executor_job(
            self._journeys_directory.mkdir,
            0o755,
            True,
            True,
        )
        await self._metadata_storage.async_setup()
        await self.database.async_setup()
        await self._migrate_pause_overrides_to_metadata()
        await self._mirror_existing_journeys()

    async def _mirror_existing_journeys(self) -> None:
        """Synchronize existing JSON journey data into SQLite."""

        await self.database.delete_all_journeys()

        for path in await self.list_journey_files():
            data = await self._async_load_json(path)
            if isinstance(data, dict):
                await self.database.save_journey(data)

        current = await self._async_load_json(self._current_journey_path)
        if isinstance(current, dict):
            await self.database.save_current_journey(current)
        else:
            await self.database.delete_current_journey()

        last = await self._async_load_json(self._last_journey_path)
        if isinstance(last, dict):
            await self.database.save_last_journey(last)
        else:
            await self.database.delete_last_journey()

    async def save_current_journey(
        self,
        journey: FordTriplogJourney | dict[str, Any],
    ) -> None:
        """Save the currently active journey."""

        data = self._normalize_journey_data(journey)

        await self._async_write_json(
            self._current_journey_path,
            data,
        )
        await self.database.save_current_journey(data)

    async def load_current_journey(
        self,
    ) -> FordTriplogJourney | None:
        """Load the currently active journey."""

        data = await self._async_load_json(
            self._current_journey_path
        )

        if data is None:
            return None

        try:
            return FordTriplogJourney.from_dict(data)
        except (TypeError, ValueError):
            _LOGGER.exception(
                "Unable to load current journey from %s",
                self._current_journey_path,
            )
            return None

    async def clear_current_journey(self) -> None:
        """Remove the active journey file."""

        await self.hass.async_add_executor_job(
            self._unlink_file,
            self._current_journey_path,
        )
        await self.database.delete_current_journey()

    async def save_completed_journey(
        self,
        journey: FordTriplogJourney | dict[str, Any],
        *,
        preserve_pause_overrides: bool = True,
    ) -> Path:
        """Archive a completed journey without creating duplicates."""

        async with self._archive_lock:
            data = self._normalize_journey_data(journey)

            if preserve_pause_overrides:
                data = await self._inherit_pause_overrides(data)

            matching_paths = await self._find_matching_journey_paths(data)

            if matching_paths:
                archive_path = matching_paths[0]
                existing_data = await self._async_load_json(archive_path)

                if isinstance(existing_data, dict):
                    existing_id = str(
                        existing_data.get("journey_id", "")
                    ).strip()
                    if existing_id:
                        data["journey_id"] = existing_id

                    if existing_data.get("created"):
                        data["created"] = existing_data["created"]
            else:
                journey_id = str(data["journey_id"]).strip()
                archive_path = (
                    self._journeys_directory
                    / f"{self._safe_filename(journey_id)}.json"
                )

            await self._async_write_json(archive_path, data)
            await self._async_write_json(self._last_journey_path, data)
            await self.database.save_journey(data)
            await self.database.save_last_journey(data)

            for duplicate_path in matching_paths[1:]:
                duplicate_data = await self._async_load_json(duplicate_path)
                await self.hass.async_add_executor_job(
                    self._unlink_file,
                    duplicate_path,
                )
                if isinstance(duplicate_data, dict):
                    duplicate_id = str(
                        duplicate_data.get("journey_id", "")
                    ).strip()
                    if duplicate_id:
                        await self.database.delete_journey(duplicate_id)
                _LOGGER.warning(
                    "Removed duplicate journey archive %s; canonical=%s",
                    duplicate_path.name,
                    archive_path.name,
                )

            return archive_path

    async def _find_matching_journey_paths(
        self,
        data: dict[str, Any],
    ) -> list[Path]:
        """Return archived journeys with identical source references."""

        signature = self._journey_signature(data)
        if signature is None:
            return []

        matching: list[Path] = []

        for path in await self.list_journey_files():
            existing = await self._async_load_json(path)
            if (
                isinstance(existing, dict)
                and self._journey_signature(existing) == signature
            ):
                matching.append(path)

        return sorted(matching)

    @staticmethod
    def _journey_signature(
        data: dict[str, Any],
    ) -> tuple[tuple[str, ...], tuple[str, ...]] | None:
        """Return a stable signature from ordered trip and charge IDs."""

        raw_trip_ids = data.get("trip_ids")
        raw_charge_ids = data.get("charge_ids")

        if not isinstance(raw_trip_ids, list):
            return None
        if not isinstance(raw_charge_ids, list):
            return None

        trip_ids = tuple(
            str(item_id).strip()
            for item_id in raw_trip_ids
            if str(item_id).strip()
        )
        charge_ids = tuple(
            str(item_id).strip()
            for item_id in raw_charge_ids
            if str(item_id).strip()
        )

        if not trip_ids:
            return None

        return trip_ids, charge_ids

    async def load_last_journey(
        self,
    ) -> FordTriplogJourney | None:
        """Load the last completed journey."""

        data = await self._async_load_json(
            self._last_journey_path
        )

        if data is None:
            return None

        try:
            return FordTriplogJourney.from_dict(data)
        except (TypeError, ValueError):
            _LOGGER.exception(
                "Unable to load last journey from %s",
                self._last_journey_path,
            )
            return None

    async def save_last_journey(
        self,
        journey: FordTriplogJourney | dict[str, Any],
    ) -> None:
        """Save the last completed journey cache."""

        data = self._normalize_journey_data(journey)

        await self._async_write_json(
            self._last_journey_path,
            data,
        )
        await self.database.save_last_journey(data)

    async def clear_last_journey(self) -> None:
        """Remove the last completed journey cache."""

        await self.hass.async_add_executor_job(
            self._unlink_file,
            self._last_journey_path,
        )
        await self.database.delete_last_journey()

    async def list_journey_files(self) -> list[Path]:
        """Return all archived journey files."""

        return await self.hass.async_add_executor_job(
            self._list_journey_files
        )

    async def load_journey_file(
        self,
        path: Path,
    ) -> FordTriplogJourney | None:
        """Load one archived journey file."""

        resolved_path = Path(path)

        try:
            resolved_path.relative_to(
                self._journeys_directory
            )
        except ValueError:
            _LOGGER.warning(
                "Rejected journey file outside journey directory: %s",
                resolved_path,
            )
            return None

        data = await self._async_load_json(
            resolved_path
        )

        if data is None:
            return None

        try:
            return FordTriplogJourney.from_dict(data)
        except (TypeError, ValueError):
            _LOGGER.exception(
                "Unable to load journey from %s",
                resolved_path,
            )
            return None

    async def get_all_journeys(
        self,
    ) -> list[FordTriplogJourney]:
        """Load all archived journeys in chronological order."""

        journeys: list[FordTriplogJourney] = []

        for path in await self.list_journey_files():
            journey = await self.load_journey_file(path)

            if journey is not None:
                journeys.append(journey)

        journeys.sort(
            key=lambda journey: (
                journey.start_time or "",
                journey.journey_id,
            )
        )

        return journeys

    async def load_journey_by_id(
        self,
        journey_id: str,
    ) -> FordTriplogJourney | None:
        """Load an archived journey by its identifier."""

        normalized_id = str(journey_id).strip()
        if not normalized_id:
            return None

        path = self._journeys_directory / f"{self._safe_filename(normalized_id)}.json"
        return await self.load_journey_file(path)

    async def save_archived_journey(
        self,
        journey: FordTriplogJourney | dict[str, Any],
    ) -> Path:
        """Replace one archived journey and synchronize manual pause data.

        Explicit editor changes must not be re-imported from an older duplicate
        journey. The selected journey is therefore saved as authoritative and
        its pause overrides are copied to other archived journeys of the same
        day that contain the same stable pause identifiers.
        """

        data = self._normalize_journey_data(journey)
        path = await self.save_completed_journey(
            data,
            preserve_pause_overrides=False,
        )
        await self._synchronize_pause_overrides(data)
        return path

    async def _inherit_pause_overrides(
        self,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        """Apply persistent pause metadata to a generated journey."""

        valid_pause_ids = self._pause_ids_from_data(data)
        persistent = await self._metadata_storage.get_pause_overrides()
        current = data.get("pause_overrides")
        merged: dict[str, dict[str, Any]] = {
            pause_id: dict(persistent[pause_id])
            for pause_id in valid_pause_ids
            if pause_id in persistent
        }
        if isinstance(current, dict):
            merged.update(
                {
                    str(pause_id): dict(override)
                    for pause_id, override in current.items()
                    if str(pause_id) in valid_pause_ids
                    and isinstance(override, dict)
                }
            )
        data["pause_overrides"] = merged
        return data

    async def _migrate_pause_overrides_to_metadata(self) -> None:
        """Import legacy journey-embedded overrides into metadata.json."""

        collected: dict[str, dict[str, Any]] = {}

        for path in await self.list_journey_files():
            journey = await self.load_journey_file(path)
            if journey is not None:
                collected.update(
                    {
                        pause_id: dict(value)
                        for pause_id, value in journey.pause_overrides.items()
                        if isinstance(value, dict)
                    }
                )

        for cache_path in (self._current_journey_path, self._last_journey_path):
            cache_data = await self._async_load_json(cache_path)
            if not isinstance(cache_data, dict):
                continue
            overrides = cache_data.get("pause_overrides")
            if isinstance(overrides, dict):
                collected.update(
                    {
                        str(pause_id): dict(value)
                        for pause_id, value in overrides.items()
                        if isinstance(value, dict)
                    }
                )

        if collected:
            changed = await self._metadata_storage.import_legacy_pause_overrides(collected)
            if changed:
                _LOGGER.info(
                    "Migrated %d pause override(s) to persistent metadata",
                    len(collected),
                )

    async def _synchronize_pause_overrides(
        self,
        authoritative_data: dict[str, Any],
    ) -> None:
        """Synchronize pause edits to duplicate journeys of the same day."""

        journey_date = str(authoritative_data.get("date", "")).strip()
        journey_id = str(authoritative_data.get("journey_id", "")).strip()
        authoritative_ids = self._pause_ids_from_data(authoritative_data)
        authoritative_overrides = authoritative_data.get("pause_overrides")
        if not isinstance(authoritative_overrides, dict):
            authoritative_overrides = {}

        if not authoritative_ids:
            return

        await self._metadata_storage.synchronize_pause_overrides(
            authoritative_ids,
            {
                str(pause_id): dict(value)
                for pause_id, value in authoritative_overrides.items()
                if isinstance(value, dict)
            },
        )

        if not journey_date:
            return

        for path in await self.list_journey_files():
            existing = await self.load_journey_file(path)
            if existing is None or existing.journey_id == journey_id:
                continue
            if str(existing.date or "").strip() != journey_date:
                continue

            existing_ids = {
                build_pause_id(current.item_id, following.item_id)
                for current, following in zip(
                    existing.items,
                    existing.items[1:],
                )
            }
            shared_ids = authoritative_ids & existing_ids
            if not shared_ids:
                continue

            changed = False
            for pause_id in shared_ids:
                authoritative = authoritative_overrides.get(pause_id)
                if isinstance(authoritative, dict):
                    normalized = dict(authoritative)
                    if existing.pause_overrides.get(pause_id) != normalized:
                        existing.pause_overrides[pause_id] = normalized
                        changed = True
                elif pause_id in existing.pause_overrides:
                    existing.pause_overrides.pop(pause_id, None)
                    changed = True

            if changed:
                synchronized_data = existing.to_dict()
                await self._async_write_json(path, synchronized_data)
                await self.database.save_journey(synchronized_data)

    @staticmethod
    def _pause_ids_from_data(data: dict[str, Any]) -> set[str]:
        """Return stable pause identifiers represented by journey items."""

        items = data.get("items")
        if not isinstance(items, list):
            return set()

        item_ids = [
            str(item.get("id", "")).strip()
            for item in items
            if isinstance(item, dict) and str(item.get("id", "")).strip()
        ]
        return {
            build_pause_id(current_id, following_id)
            for current_id, following_id in zip(item_ids, item_ids[1:])
        }

    async def delete_journey(
        self,
        journey_id: str,
    ) -> bool:
        """Delete one archived journey without touching trips or charges."""

        normalized_id = str(journey_id).strip()
        if not normalized_id:
            return False

        path = (
            self._journeys_directory
            / f"{self._safe_filename(normalized_id)}.json"
        )

        deleted = await self.hass.async_add_executor_job(
            self._unlink_file,
            path,
        )

        if deleted:
            await self.database.delete_journey(normalized_id)

        return deleted

    async def delete_all_journeys(
        self,
        *,
        clear_current: bool = True,
        clear_last: bool = True,
    ) -> int:
        """Delete all archived journeys and optional cache files.

        Trips and charging sessions are never changed.
        """

        deleted = await self.hass.async_add_executor_job(
            self._delete_all_journey_files
        )
        await self.database.delete_all_journeys()

        if clear_current:
            await self.clear_current_journey()

        if clear_last:
            await self.clear_last_journey()

        return deleted

    def _normalize_journey_data(
        self,
        journey: FordTriplogJourney | dict[str, Any],
    ) -> dict[str, Any]:
        """Return validated serializable journey data."""

        if isinstance(journey, FordTriplogJourney):
            return journey.to_dict()

        if isinstance(journey, dict):
            return FordTriplogJourney.from_dict(
                journey
            ).to_dict()

        raise TypeError(
            "Journey must be FordTriplogJourney or dictionary"
        )

    async def _async_write_json(
        self,
        path: Path,
        data: dict[str, Any],
    ) -> None:
        """Write JSON outside the Home Assistant event loop."""

        await self.hass.async_add_executor_job(
            self._write_json,
            path,
            data,
        )

    async def _async_load_json(
        self,
        path: Path,
    ) -> dict[str, Any] | None:
        """Load JSON outside the Home Assistant event loop."""

        return await self.hass.async_add_executor_job(
            self._load_json,
            path,
        )

    @staticmethod
    def _write_json(
        path: Path,
        data: dict[str, Any],
    ) -> None:
        """Write JSON atomically."""

        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        temporary_path = path.with_suffix(
            f"{path.suffix}.tmp"
        )

        try:
            with temporary_path.open(
                "w",
                encoding="utf-8",
            ) as file:
                json.dump(
                    data,
                    file,
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=False,
                )
                file.write("\n")

            os.replace(
                temporary_path,
                path,
            )
        except Exception:
            temporary_path.unlink(
                missing_ok=True
            )
            raise

    @staticmethod
    def _load_json(
        path: Path,
    ) -> dict[str, Any] | None:
        """Load one JSON object."""

        if not path.exists():
            return None

        try:
            with path.open(
                "r",
                encoding="utf-8",
            ) as file:
                data = json.load(file)
        except (
            OSError,
            json.JSONDecodeError,
        ):
            _LOGGER.exception(
                "Unable to read journey JSON file: %s",
                path,
            )
            return None

        if not isinstance(data, dict):
            _LOGGER.warning(
                "Journey JSON file does not contain an object: %s",
                path,
            )
            return None

        return data

    def _list_journey_files(self) -> list[Path]:
        """Return sorted archived journey files."""

        if not self._journeys_directory.exists():
            return []

        return sorted(
            path
            for path in self._journeys_directory.glob("*.json")
            if path.is_file()
        )

    def _delete_all_journey_files(self) -> int:
        """Delete all archived journey files."""

        deleted = 0

        for path in self._list_journey_files():
            if self._unlink_file(path):
                deleted += 1

        return deleted

    @staticmethod
    def _unlink_file(path: Path) -> bool:
        """Remove one file and report whether it existed."""

        try:
            path.unlink()
        except FileNotFoundError:
            return False

        return True

    @staticmethod
    def _safe_filename(value: str) -> str:
        """Return a filesystem-safe filename component."""

        safe = "".join(
            character
            if character.isalnum() or character in ("-", "_")
            else "_"
            for character in value
        ).strip("_")

        if not safe:
            raise ValueError(
                "Journey ID does not contain usable filename characters"
            )

        return safe
