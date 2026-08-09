"""
Ford Triplog

Route Tracker storage

Version: 2.0.0-dev
Phase: Route Tracker Phase 1
Build: Fix 06 - Route persistence and recovery

Changes:
- Route files can be persisted while active or paused.
- Adds route status and updated_at metadata.
- Existing route files without status remain backward compatible.
- Last Route lookup prefers completed/legacy routes and ignores active
  recovery files.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .const import ROUTE_SCHEMA_VERSION, ROUTES_DIR, STORAGE_DIR


class FordTriplogRouteStorage:
    """Store route point files independently from Trip storage."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self.base_path = Path(
            hass.config.path(
                ".storage",
                STORAGE_DIR,
                ROUTES_DIR,
            )
        )

    async def async_setup(self) -> None:
        """Ensure the route storage directory exists."""

        await self.hass.async_add_executor_job(
            lambda: self.base_path.mkdir(parents=True, exist_ok=True)
        )

    def _path_for_trip(self, trip_id: str) -> Path:
        """Return a safe route file path for one Trip ID."""

        safe_trip_id = "".join(
            char
            for char in str(trip_id)
            if char.isalnum() or char in ("_", "-")
        )
        return self.base_path / f"{safe_trip_id}.json"

    async def async_save_route(
        self,
        *,
        trip_id: str,
        source_type: str,
        points: list[dict[str, Any]],
        status: str = "completed",
        created_at: str | None = None,
    ) -> None:
        """Atomically save one route file."""

        payload = {
            "schema": ROUTE_SCHEMA_VERSION,
            "trip_id": str(trip_id),
            "source_type": str(source_type),
            "status": str(status),
            "created_at": created_at,
            "updated_at": dt_util.now().isoformat(),
            "points": points,
        }

        payload = {
            key: value
            for key, value in payload.items()
            if value is not None
        }

        path = self._path_for_trip(trip_id)

        def _write() -> None:
            temp_path = path.with_suffix(".json.tmp")
            temp_path.write_text(
                json.dumps(
                    payload,
                    ensure_ascii=False,
                    indent=2,
                ) + "\n",
                encoding="utf-8",
            )
            temp_path.replace(path)

        await self.hass.async_add_executor_job(_write)

    async def async_load_route(
        self,
        trip_id: str,
    ) -> dict[str, Any] | None:
        """Load one stored route by Trip ID."""

        path = self._path_for_trip(trip_id)

        def _read() -> dict[str, Any] | None:
            if not path.is_file():
                return None

            try:
                data = json.loads(
                    path.read_text(encoding="utf-8")
                )
            except (OSError, json.JSONDecodeError):
                return None

            return data if isinstance(data, dict) else None

        return await self.hass.async_add_executor_job(_read)

    async def async_load_latest_route(self) -> dict[str, Any] | None:
        """Load the most recently written completed route.

        Legacy route files without a status field are treated as completed.
        Active/paused recovery files are intentionally ignored so the
        "Last route" sensor keeps representing the last finished route.
        """

        def _read_latest() -> dict[str, Any] | None:
            if not self.base_path.is_dir():
                return None

            candidates: list[tuple[int, dict[str, Any]]] = []

            for path in self.base_path.glob("*.json"):
                if not path.is_file():
                    continue

                try:
                    data = json.loads(
                        path.read_text(encoding="utf-8")
                    )
                except (OSError, json.JSONDecodeError):
                    continue

                if not isinstance(data, dict):
                    continue

                status = data.get("status")
                if status not in (None, "completed"):
                    continue

                try:
                    mtime = path.stat().st_mtime_ns
                except OSError:
                    continue

                candidates.append((mtime, data))

            if not candidates:
                return None

            return max(candidates, key=lambda item: item[0])[1]

        return await self.hass.async_add_executor_job(_read_latest)
