"""
Ford Triplog

Route Tracker storage

Version: 2.0.1-dev
Phase: Historical Route Index
Build: Phase 1 - Historical route loading

Changes:
- Keeps the Ford Triplog 2.0.0 route storage format unchanged.
- Adds loading of all completed historical routes.
- Adds loading of routes for a selected local calendar date.
- Adds loading of routes for a supplied list of Trip IDs.
- Legacy route files without a status field remain compatible.
- Active and paused recovery files are excluded from history queries.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .const import ROUTE_SCHEMA_VERSION, ROUTES_DIR, STORAGE_DIR
from .database import FordTriplogDatabase

_LOGGER = logging.getLogger(__name__)


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
        self.database = FordTriplogDatabase(
            hass,
            Path(hass.config.path(".storage", STORAGE_DIR)),
        )

    async def async_setup(self) -> None:
        """Ensure the route storage directory exists."""

        await self.hass.async_add_executor_job(
            lambda: self.base_path.mkdir(parents=True, exist_ok=True)
        )

        mirror_key = "ford_triplog_route_initial_sqlite_mirror_done"
        if not self.hass.data.get(mirror_key, False):
            self.hass.data[mirror_key] = True
            await self._mirror_existing_routes()

    async def _mirror_existing_routes(self) -> None:
        """Mirror all existing completed JSON routes into SQLite once."""

        def _list_and_read() -> list[dict[str, Any]]:
            if not self.base_path.is_dir():
                return []

            routes: list[dict[str, Any]] = []
            for path in self.base_path.glob("*.json"):
                if not path.is_file():
                    continue

                data = self._read_route_file(path)
                if data is None or not self._is_completed_route(data):
                    continue

                routes.append(data)

            return routes

        routes = await self.hass.async_add_executor_job(_list_and_read)

        mirrored = 0
        failed = 0

        for route in routes:
            if await self.database.save_route(route):
                mirrored += 1
            else:
                failed += 1

        _LOGGER.info(
            "Initial SQLite route mirror completed: routes=%d mirrored=%d failed=%d",
            len(routes),
            mirrored,
            failed,
        )

    def _path_for_trip(self, trip_id: str) -> Path:
        """Return a safe route file path for one Trip ID."""

        safe_trip_id = "".join(
            char
            for char in str(trip_id)
            if char.isalnum() or char in ("_", "-")
        )
        return self.base_path / f"{safe_trip_id}.json"

    @staticmethod
    def _read_route_file(path: Path) -> dict[str, Any] | None:
        """Read and validate one route JSON file."""

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

        return data if isinstance(data, dict) else None

    @staticmethod
    def _is_completed_route(route: dict[str, Any]) -> bool:
        """Return whether a route is suitable for historical display."""

        return route.get("status") in (None, "completed")

    @staticmethod
    def _route_timestamp(route: dict[str, Any]) -> datetime | None:
        """Return the best available timestamp for chronological sorting."""

        candidates: list[Any] = [
            route.get("created_at"),
        ]

        points = route.get("points")
        if isinstance(points, list):
            for point in points:
                if isinstance(point, dict) and point.get("timestamp"):
                    candidates.append(point.get("timestamp"))
                    break

        candidates.append(route.get("updated_at"))

        for value in candidates:
            if not value:
                continue

            try:
                parsed = dt_util.parse_datetime(str(value))
            except (TypeError, ValueError):
                parsed = None

            if parsed is not None:
                return parsed

        return None

    def _route_local_date(
        self,
        route: dict[str, Any],
    ) -> date | None:
        """Return the Home Assistant local calendar date for a route."""

        timestamp = self._route_timestamp(route)
        if timestamp is None:
            return None

        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=dt_util.UTC)

        return dt_util.as_local(timestamp).date()

    async def async_save_route(
        self,
        *,
        trip_id: str,
        source_type: str,
        points: list[dict[str, Any]],
        status: str = "completed",
        created_at: str | None = None,
        matched_route: dict[str, Any] | None = None,
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
            "matched_route": matched_route,
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

        # Phase 1: keep JSON as production storage and mirror the
        # identical route payload into SQLite.
        if not await self.database.save_route(payload):
            _LOGGER.error(
                "SQLite route mirror failed for trip_id=%s",
                trip_id,
            )

    async def async_load_route(
        self,
        trip_id: str,
    ) -> dict[str, Any] | None:
        """Load one stored route by Trip ID."""

        path = self._path_for_trip(trip_id)

        def _read() -> dict[str, Any] | None:
            if not path.is_file():
                return None
            return self._read_route_file(path)

        return await self.hass.async_add_executor_job(_read)

    async def async_load_latest_route(self) -> dict[str, Any] | None:
        """Load the most recently written completed route.

        Legacy route files without a status field are treated as completed.
        Active/paused recovery files are intentionally ignored so the
        Last Route sensor keeps representing the last finished route.
        """

        def _read_latest() -> dict[str, Any] | None:
            if not self.base_path.is_dir():
                return None

            candidates: list[tuple[int, dict[str, Any]]] = []

            for path in self.base_path.glob("*.json"):
                if not path.is_file():
                    continue

                data = self._read_route_file(path)
                if data is None or not self._is_completed_route(data):
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

    async def async_list_routes(self) -> list[dict[str, Any]]:
        """Load all completed historical routes in chronological order."""

        def _read_all() -> list[dict[str, Any]]:
            if not self.base_path.is_dir():
                return []

            routes: list[dict[str, Any]] = []

            for path in self.base_path.glob("*.json"):
                if not path.is_file():
                    continue

                data = self._read_route_file(path)
                if data is None or not self._is_completed_route(data):
                    continue

                routes.append(data)

            routes.sort(
                key=lambda route: (
                    self._route_timestamp(route)
                    or datetime.min.replace(tzinfo=dt_util.UTC)
                )
            )
            return routes

        return await self.hass.async_add_executor_job(_read_all)

    async def async_load_routes_for_date(
        self,
        route_date: date | str,
    ) -> list[dict[str, Any]]:
        """Load completed routes belonging to one HA-local calendar date."""

        if isinstance(route_date, str):
            try:
                selected_date = date.fromisoformat(route_date)
            except ValueError:
                return []
        elif isinstance(route_date, date):
            selected_date = route_date
        else:
            return []

        routes = await self.async_list_routes()

        return [
            route
            for route in routes
            if self._route_local_date(route) == selected_date
        ]

    async def async_load_routes_for_trip_ids(
        self,
        trip_ids: list[str],
    ) -> list[dict[str, Any]]:
        """Load completed routes for Trip IDs, preserving requested order."""

        routes: list[dict[str, Any]] = []

        for trip_id in trip_ids:
            normalized = str(trip_id).strip()
            if not normalized:
                continue

            route = await self.async_load_route(normalized)
            if route is None or not self._is_completed_route(route):
                continue

            routes.append(route)

        return routes
