# Ford Triplog 2.0
# Route Tracker – Phase 1 GeoJSON 01
# Add latest-route lookup for the Home Assistant GeoJSON route sensor.

"""Ford Triplog Route Tracker storage."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant

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
        safe_trip_id = "".join(
            char for char in str(trip_id)
            if char.isalnum() or char in ("_", "-")
        )
        return self.base_path / f"{safe_trip_id}.json"

    async def async_save_route(
        self,
        *,
        trip_id: str,
        source_type: str,
        points: list[dict[str, Any]],
    ) -> None:
        """Save one route file for a trip."""

        payload = {
            "schema": ROUTE_SCHEMA_VERSION,
            "trip_id": trip_id,
            "source_type": source_type,
            "points": points,
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
        """Load one stored route by trip ID."""

        path = self._path_for_trip(trip_id)

        def _read() -> dict[str, Any] | None:
            if not path.is_file():
                return None
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else None

        return await self.hass.async_add_executor_job(_read)

    async def async_load_latest_route(self) -> dict[str, Any] | None:
        """Load the most recently written stored route."""

        def _read_latest() -> dict[str, Any] | None:
            if not self.base_path.is_dir():
                return None

            route_files = [
                path
                for path in self.base_path.glob("*.json")
                if path.is_file()
            ]
            if not route_files:
                return None

            latest_path = max(
                route_files,
                key=lambda path: path.stat().st_mtime_ns,
            )

            try:
                data = json.loads(
                    latest_path.read_text(encoding="utf-8")
                )
            except (OSError, json.JSONDecodeError):
                return None

            return data if isinstance(data, dict) else None

        return await self.hass.async_add_executor_job(_read_latest)

