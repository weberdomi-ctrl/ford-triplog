"""
Ford Triplog

Route Tracker storage

Version: 2.3.0
Phase: SQLite-only Route Storage
Build: 23006

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
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.util import dt as dt_util

from .const import (
    ROUTE_SCHEMA_VERSION,
    ROUTES_DIR,
    STORAGE_DIR,
)
from .database import FordTriplogDatabase

SIGNAL_LAST_ROUTE_UPDATED = "ford_triplog_last_route_updated"

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

        # 2.3: SQLite is the only runtime route backend.
        # Compatibility attribute used by sensors/debug output.
        self.read_backend = "sqlite"


    async def async_setup(self) -> None:
        """Ensure the route storage directory exists."""

        await self.hass.async_add_executor_job(
            lambda: self.base_path.mkdir(parents=True, exist_ok=True)
        )

        migration_id = "legacy_route_import_v23"
        if not await self.database.is_migration_completed(migration_id):
            completed = await self._import_legacy_routes()
            if completed:
                await self.database.mark_migration_completed(migration_id)
        else:
            _LOGGER.debug("Legacy Route JSON import already completed")

    async def _import_legacy_routes(self) -> None:
        """Import missing completed legacy JSON routes into SQLite once."""

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

        imported = 0
        unchanged = 0
        failed = 0

        sqlite_routes = await self.database.load_route_mirror_index()

        for route in routes:
            trip_id = str(route.get("trip_id", "")).strip()
            if not trip_id:
                failed += 1
                continue

            if trip_id in sqlite_routes:
                unchanged += 1
                continue

            if await self.database.save_route(route):
                imported += 1
                sqlite_routes[trip_id] = route
            else:
                failed += 1

        _LOGGER.info(
            "Legacy Route JSON import completed: "
            "routes=%d imported=%d unchanged=%d failed=%d",
            len(routes),
            imported,
            unchanged,
            failed,
        )
        return failed == 0

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

        if not await self.database.save_route(payload):
            raise OSError(f"Unable to save route to SQLite: {trip_id}")

        if str(status) == "completed":
            async_dispatcher_send(
                self.hass,
                SIGNAL_LAST_ROUTE_UPDATED,
                str(trip_id),
            )

    async def async_load_route(
        self,
        trip_id: str,
    ) -> dict[str, Any] | None:
        """Load one route by Trip ID from SQLite."""
        _LOGGER.debug("Route read backend: sqlite trip_id=%s", trip_id)
        return await self.database.load_route(str(trip_id))

    async def async_load_latest_route(self) -> dict[str, Any] | None:
        """Load the most recently written completed route from SQLite."""
        _LOGGER.debug("Latest Route read backend: sqlite")
        data = await self.database.load_last_route()
        if data is not None:
            _LOGGER.debug("SQLite last route loaded: trip_id=%s", data.get("trip_id", "unknown"))
        return data

    async def async_list_routes(self) -> list[dict[str, Any]]:
        """Load all completed historical routes from SQLite."""
        _LOGGER.debug("Route archive read backend: sqlite")
        routes = await self.database.load_all_routes()
        routes = [route for route in routes if self._is_completed_route(route)]
        routes.sort(
            key=lambda route: (
                self._route_timestamp(route)
                or datetime.min.replace(tzinfo=dt_util.UTC)
            )
        )
        _LOGGER.debug("SQLite routes loaded: %d", len(routes))
        return routes

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

        _LOGGER.debug(
            "Routes for date read backend: %s date=%s",
            self.read_backend,
            selected_date.isoformat(),
        )

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
        """Load completed routes for Trip IDs from SQLite, preserving order."""
        _LOGGER.debug("Routes for trip IDs read backend: sqlite count=%d", len(trip_ids))
        routes = await self.database.load_routes_for_trip_ids(trip_ids)
        return [route for route in routes if self._is_completed_route(route)]

