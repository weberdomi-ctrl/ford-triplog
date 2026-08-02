"""
Ford Triplog

Track your Ford.

Separate storage for daily journeys.

Version: 1.6.0
Release: 1.6b
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant

from .const import (
    CURRENT_JOURNEY_FILE,
    JOURNEYS_DIR,
    LAST_JOURNEY_FILE,
    STORAGE_DIR,
)
from .journey import FordTriplogJourney

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

    async def async_setup(self) -> None:
        """Create the journey storage directories."""

        await self.hass.async_add_executor_job(
            self._journeys_directory.mkdir,
            0o755,
            True,
            True,
        )

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

    async def save_completed_journey(
        self,
        journey: FordTriplogJourney | dict[str, Any],
    ) -> Path:
        """Archive a completed journey and update last_journey.json."""

        data = self._normalize_journey_data(journey)
        journey_id = str(data["journey_id"]).strip()

        archive_path = (
            self._journeys_directory
            / f"{self._safe_filename(journey_id)}.json"
        )

        await self._async_write_json(
            archive_path,
            data,
        )
        await self._async_write_json(
            self._last_journey_path,
            data,
        )

        return archive_path

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

    async def clear_last_journey(self) -> None:
        """Remove the last completed journey cache."""

        await self.hass.async_add_executor_job(
            self._unlink_file,
            self._last_journey_path,
        )

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
        """Replace one archived journey and refresh the last-journey cache when needed."""

        path = await self.save_completed_journey(journey)
        return path

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

        return await self.hass.async_add_executor_job(
            self._unlink_file,
            path,
        )

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
