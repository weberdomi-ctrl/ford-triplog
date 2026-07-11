"""
Ford Triplog

Track your Ford.

Storage layer for trips, recovery data and cache.

Version: 1.0.0
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant

from .const import VERSION

_LOGGER = logging.getLogger(__name__)

STORAGE_SCHEMA = 1


class FordTriplogStorage:
    """Persistent storage manager for Ford Triplog."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self.base_path = Path(
            hass.config.path(".storage", "ford_triplog")
        )

        self.recovery_path = self.base_path / "recovery"
        self.trips_path = self.base_path / "trips"
        self.cache_path = self.base_path / "cache"

    async def async_setup(self) -> None:
        """Initialize storage directories."""

        for path in (
            self.recovery_path,
            self.trips_path,
            self.cache_path,
        ):
            path.mkdir(parents=True, exist_ok=True)

        _LOGGER.debug("Ford Triplog storage initialized")

    def _add_metadata(
        self,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        """Add storage metadata."""

        result = dict(data)

        result.setdefault("schema", STORAGE_SCHEMA)
        result.setdefault("generator", "Ford Triplog")
        result.setdefault("version", VERSION)
        result.setdefault(
            "created",
            datetime.utcnow().isoformat() + "Z",
        )

        return result

    async def _save_json(
        self,
        path: Path,
        data: dict[str, Any],
    ) -> bool:
        """Save JSON atomically."""

        try:
            path.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            temp = path.with_suffix(".tmp")

            with temp.open(
                "w",
                encoding="utf-8",
            ) as file:
                json.dump(
                    self._add_metadata(data),
                    file,
                    indent=2,
                    ensure_ascii=False,
                )

            os.replace(temp, path)

            return True

        except Exception:
            _LOGGER.exception(
                "Unable to save %s",
                path,
            )
            return False

    async def _load_json(
        self,
        path: Path,
    ) -> dict[str, Any] | None:
        """Load JSON."""

        if not path.exists():
            return None

        try:
            with path.open(
                "r",
                encoding="utf-8",
            ) as file:
                return json.load(file)

        except Exception:
            _LOGGER.exception(
                "Unable to load %s",
                path,
            )
            return None

    async def load_trip_file(
        self,
        path: Path,
    ) -> dict[str, Any] | None:
        """Load archived trip file."""

        return await self._load_json(path)

    async def _delete_file(
        self,
        path: Path,
    ) -> None:
        """Delete file."""

        if path.exists():
            path.unlink()

    def _current_trip_file(self) -> Path:
        return self.recovery_path / "current_trip.json"

    def _last_trip_file(self) -> Path:
        return self.cache_path / "last_trip.json"

    def _statistics_file(self) -> Path:
        return self.cache_path / "statistics.json"

    def _diagnostics_file(self) -> Path:
        return self.cache_path / "diagnostics.json"

    async def save_current_trip(self, data: dict[str, Any]) -> bool:
        return await self._save_json(
            self._current_trip_file(),
            data,
        )

    async def load_current_trip(self) -> dict[str, Any] | None:
        return await self._load_json(
            self._current_trip_file()
        )

    async def delete_current_trip(self) -> None:
        await self._delete_file(
            self._current_trip_file()
        )

    async def save_trip(self, data: dict[str, Any]) -> bool:
        """Archive completed trip."""

        start = data.get("start_time")

        if not start:
            _LOGGER.error("Trip without start_time")
            return False

        timestamp = datetime.fromisoformat(
            start.replace("Z", "+00:00")
        )

        folder = (
            self.trips_path
            / timestamp.strftime("%Y")
            / timestamp.strftime("%m")
        )

        filename = timestamp.strftime(
            "%Y-%m-%d_%H-%M-%S.json"
        )

        path = folder / filename
        counter = 1

        while path.exists():
            path = folder / (
                timestamp.strftime(
                    "%Y-%m-%d_%H-%M-%S"
                )
                + f"_{counter}.json"
            )
            counter += 1

        return await self._save_json(path, data)

    async def list_trips(self) -> list[Path]:
        """Return archived trips."""

        if not self.trips_path.exists():
            return []

        return sorted(
            self.trips_path.rglob("*.json")
        )

    async def save_last_trip(self, data: dict[str, Any]) -> bool:
        return await self._save_json(
            self._last_trip_file(),
            data,
        )

    async def load_last_trip(self) -> dict[str, Any] | None:
        return await self._load_json(
            self._last_trip_file()
        )

    async def save_statistics(self, data: dict[str, Any]) -> bool:
        return await self._save_json(
            self._statistics_file(),
            data,
        )

    async def load_statistics(self) -> dict[str, Any] | None:
        return await self._load_json(
            self._statistics_file()
        )

    async def save_diagnostics(self, data: dict[str, Any]) -> bool:
        return await self._save_json(
            self._diagnostics_file(),
            data,
        )

    async def load_diagnostics(self) -> dict[str, Any] | None:
        return await self._load_json(
            self._diagnostics_file()
        )

    async def validate_storage(self) -> bool:
        """Validate storage structure."""

        await self.async_setup()

        return all(
            path.exists()
            for path in (
                self.recovery_path,
                self.trips_path,
                self.cache_path,
            )
        )

    async def rebuild_cache(self) -> None:
        """Rebuild cache placeholder."""

        _LOGGER.info(
            "Cache rebuild requested"
        )
