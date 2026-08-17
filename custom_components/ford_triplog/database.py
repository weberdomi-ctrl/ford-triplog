"""
Ford Triplog

SQLite storage mirror.

Version: 2.1.0
Build: 16
Changes: Add Top Locations SQL view read support
"""

from __future__ import annotations

import asyncio
import functools
import json
import logging
import sqlite3
import time
from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


class FordTriplogDatabase:
    """SQLite mirror storage for Ford Triplog."""

    def __init__(
        self,
        hass: HomeAssistant,
        base_path: Path,
    ) -> None:
        self.hass = hass
        self.db_path = base_path / "ford_triplog.db"

    def _log_read(self, resource: str) -> None:
        """Log a SQLite read at DEBUG level for development diagnostics."""
        _LOGGER.debug("SQLite READ: %s", resource)

    async def validate_json_identity(
        self,
        json_records: dict[str, dict[str, Any] | None],
        json_collections: dict[str, dict[str, dict[str, Any]]],
    ) -> dict[str, Any]:
        """Compare JSON storage records with their SQLite mirror.

        This is a development-only validation helper. It never changes
        either backend and returns a structured comparison report.
        """

        def _normalize(value: Any) -> Any:
            if isinstance(value, dict):
                return {
                    str(key): _normalize(item)
                    for key, item in value.items()
                }
            if isinstance(value, list):
                return [_normalize(item) for item in value]
            return value

        def _read() -> dict[str, Any]:
            report: dict[str, Any] = {
                "single": {},
                "collections": {},
                "pass": True,
            }

            with sqlite3.connect(self.db_path) as db:
                for name, expected in json_records.items():
                    row = None
                    if name == "current_trip":
                        row = db.execute(
                            "SELECT data FROM current_trip LIMIT 1"
                        ).fetchone()
                    elif name == "current_charge":
                        row = db.execute(
                            "SELECT data FROM current_charge LIMIT 1"
                        ).fetchone()
                    elif name == "last_trip":
                        row = db.execute(
                            "SELECT data FROM last_trip LIMIT 1"
                        ).fetchone()
                    elif name == "last_charge":
                        row = db.execute(
                            "SELECT data FROM last_charge LIMIT 1"
                        ).fetchone()
                    elif name == "statistics":
                        row = db.execute(
                            "SELECT data FROM statistics WHERE id = 1"
                        ).fetchone()
                    elif name == "diagnostics":
                        row = db.execute(
                            "SELECT data FROM diagnostics WHERE id = 1"
                        ).fetchone()

                    actual = json.loads(row[0]) if row else None
                    identical = _normalize(expected) == _normalize(actual)

                    report["single"][name] = {
                        "identical": identical,
                        "json_present": expected is not None,
                        "sqlite_present": actual is not None,
                    }

                    if not identical:
                        report["pass"] = False

                table_map = {
                    "trips": "trips",
                    "charges": "charges",
                }

                for name, expected_records in json_collections.items():
                    table = table_map[name]
                    rows = db.execute(
                        f"SELECT {('trip_id' if name == 'trips' else 'charge_id')}, data "
                        f"FROM {table}"
                    ).fetchall()

                    actual_records = {
                        str(row[0]): json.loads(row[1])
                        for row in rows
                    }

                    expected_ids = set(expected_records)
                    actual_ids = set(actual_records)
                    missing = sorted(expected_ids - actual_ids)
                    extra = sorted(actual_ids - expected_ids)
                    different = sorted(
                        record_id
                        for record_id in expected_ids & actual_ids
                        if _normalize(expected_records[record_id])
                        != _normalize(actual_records[record_id])
                    )

                    identical = not missing and not extra and not different

                    report["collections"][name] = {
                        "json_count": len(expected_records),
                        "sqlite_count": len(actual_records),
                        "missing_in_sqlite": missing,
                        "extra_in_sqlite": extra,
                        "different": different,
                        "identical": identical,
                    }

                    if not identical:
                        report["pass"] = False

            return report

        try:
            return await self.hass.async_add_executor_job(
                functools.partial(
                    _read
                )
            )
        except Exception:
            _LOGGER.exception(
                "SQLite identity validation failed"
            )
            return {
                "single": {},
                "collections": {},
                "pass": False,
                "error": True,
            }

    async def async_setup(self) -> None:
        """Initialize SQLite database once per Home Assistant runtime."""

        runtime_key = f"ford_triplog_database_setup:{self.db_path}"
        lock_key = f"{runtime_key}:lock"

        lock = self.hass.data.get(lock_key)
        if not isinstance(lock, asyncio.Lock):
            lock = asyncio.Lock()
            self.hass.data[lock_key] = lock

        if self.hass.data.get(runtime_key, False):
            _LOGGER.debug(
                "Ford Triplog SQLite database already initialized in this HA runtime: %s",
                self.db_path,
            )
            return

        async with lock:
            if self.hass.data.get(runtime_key, False):
                _LOGGER.debug(
                    "Ford Triplog SQLite database already initialized in this HA runtime: %s",
                    self.db_path,
                )
                return

            def _setup() -> None:
                self.db_path.parent.mkdir(
                    parents=True,
                    exist_ok=True,
                )

                with sqlite3.connect(self.db_path) as db:
                    db.execute(
                        """
                        CREATE TABLE IF NOT EXISTS trips (
                            trip_id TEXT PRIMARY KEY,
                            data TEXT NOT NULL
                        )
                        """
                    )

                    db.execute(
                        """
                        CREATE TABLE IF NOT EXISTS current_trip (
                            trip_id TEXT PRIMARY KEY,
                            data TEXT NOT NULL
                        )
                        """
                    )

                    db.execute(
                        """
                        CREATE TABLE IF NOT EXISTS last_trip (
                            trip_id TEXT PRIMARY KEY,
                            data TEXT NOT NULL
                        )
                        """
                    )

                    db.execute(
                        """
                        CREATE TABLE IF NOT EXISTS current_charge (
                            charge_id TEXT PRIMARY KEY,
                            data TEXT NOT NULL
                        )
                        """
                    )

                    db.execute(
                        """
                        CREATE TABLE IF NOT EXISTS charges (
                            charge_id TEXT PRIMARY KEY,
                            data TEXT NOT NULL
                        )
                        """
                    )

                    db.execute(
                        """
                        CREATE TABLE IF NOT EXISTS last_charge (
                            charge_id TEXT PRIMARY KEY,
                            data TEXT NOT NULL
                        )
                        """
                    )

                    db.execute(
                        """
                        CREATE TABLE IF NOT EXISTS statistics (
                            id INTEGER PRIMARY KEY CHECK (id = 1),
                            data TEXT NOT NULL
                        )
                        """
                    )

                    db.execute(
                        """
                        CREATE TABLE IF NOT EXISTS diagnostics (
                            id INTEGER PRIMARY KEY CHECK (id = 1),
                            data TEXT NOT NULL
                        )
                        """
                    )

                    db.execute(
                        """
                        CREATE TABLE IF NOT EXISTS user_charging_sites (
                            site_id TEXT PRIMARY KEY,
                            data TEXT NOT NULL
                        )
                        """
                    )
                    db.execute(
                        """
                        CREATE TABLE IF NOT EXISTS pending_charging_sites (
                            pending_id TEXT PRIMARY KEY,
                            data TEXT NOT NULL
                        )
                        """
                    )

                    db.execute(
                        """
                        CREATE TABLE IF NOT EXISTS journeys (
                            journey_id TEXT PRIMARY KEY,
                            data TEXT NOT NULL
                        )
                        """
                    )

                    db.execute(
                        """
                        CREATE TABLE IF NOT EXISTS current_journey (
                            journey_id TEXT PRIMARY KEY,
                            data TEXT NOT NULL
                        )
                        """
                    )

                    db.execute(
                        """
                        CREATE TABLE IF NOT EXISTS last_journey (
                            journey_id TEXT PRIMARY KEY,
                            data TEXT NOT NULL
                        )
                        """
                    )

                    db.execute(
                        """
                        CREATE TABLE IF NOT EXISTS metadata (
                            id INTEGER PRIMARY KEY CHECK (id = 1),
                            data TEXT NOT NULL
                        )
                        """
                    )

                    db.execute(
                        """
                        CREATE TABLE IF NOT EXISTS charge_metadata (
                            charge_id TEXT PRIMARY KEY,
                            data TEXT NOT NULL
                        )
                        """
                    )

                    db.execute(
                        """
                        CREATE TABLE IF NOT EXISTS pause_metadata (
                            pause_id TEXT PRIMARY KEY,
                            data TEXT NOT NULL
                        )
                        """
                    )

                    db.execute(
                        """
                        CREATE TABLE IF NOT EXISTS user_receipt_parser_profiles (
                            profile_id TEXT PRIMARY KEY,
                            data TEXT NOT NULL
                        )
                        """
                    )

                    db.execute(
                        """
                        CREATE TABLE IF NOT EXISTS receipts (
                            receipt_id TEXT PRIMARY KEY,
                            target_type TEXT NOT NULL,
                            target_id TEXT NOT NULL,
                            data TEXT NOT NULL
                        )
                        """
                    )
                    db.execute(
                        """
                        CREATE INDEX IF NOT EXISTS idx_receipts_target
                        ON receipts (target_type, target_id)
                        """
                    )

                    db.execute(
                        """
                        CREATE TABLE IF NOT EXISTS routes (
                            trip_id TEXT PRIMARY KEY,
                            data TEXT NOT NULL
                        )
                        """
                    )

                    db.execute(
                        """
                        CREATE VIEW IF NOT EXISTS v_top_location_trips AS
                        SELECT
                            trip_id,
                            data,
                            json_extract(data, '$.include_in_statistics') AS include_in_statistics,
                            json_extract(data, '$.distance_km') AS distance_km,
                            json_extract(data, '$.start_latitude') AS start_latitude,
                            json_extract(data, '$.start_longitude') AS start_longitude,
                            json_extract(data, '$.end_latitude') AS end_latitude,
                            json_extract(data, '$.end_longitude') AS end_longitude,
                            json_extract(data, '$.start_address') AS start_address,
                            json_extract(data, '$.end_address') AS end_address
                        FROM trips
                        """
                    )

                    db.execute(
                        """
                        CREATE VIEW IF NOT EXISTS v_top_route_trips AS
                        SELECT
                            trip_id,
                            data,
                            json_extract(data, '$.include_in_statistics') AS include_in_statistics,
                            json_extract(data, '$.distance_km') AS distance_km,
                            json_extract(data, '$.start_latitude') AS start_latitude,
                            json_extract(data, '$.start_longitude') AS start_longitude,
                            json_extract(data, '$.end_latitude') AS end_latitude,
                            json_extract(data, '$.end_longitude') AS end_longitude,
                            json_extract(data, '$.consumption_kwh_100km') AS consumption_kwh_100km,
                            json_extract(data, '$.start_address') AS start_address,
                            json_extract(data, '$.end_address') AS end_address
                        FROM trips
                        """
                    )


                    db.execute(
                        """
                        CREATE VIEW IF NOT EXISTS v_top_trip_trips AS
                        SELECT
                            trip_id,
                            data,
                            json_extract(data, '$.include_in_statistics') AS include_in_statistics,
                            json_extract(data, '$.distance_km') AS distance_km
                        FROM trips
                        """
                    )


                    db.execute(
                        """
                        CREATE VIEW IF NOT EXISTS v_top_journey_journeys AS
                        SELECT
                            journey_id,
                            data,
                            json_extract(data, '$.distance_km') AS distance_km
                        FROM journeys
                        """
                    )


                    db.execute(
                        """
                        CREATE VIEW IF NOT EXISTS v_top_charging_charges AS
                        SELECT
                            charge_id,
                            data,
                            json_extract(data, '$.include_in_statistics') AS include_in_statistics
                        FROM charges
                        """
                    )


                    db.execute(
                        """
                        CREATE VIEW IF NOT EXISTS v_top_day_journeys AS
                        SELECT
                            journey_id,
                            data,
                            json_extract(data, '$.date') AS date,
                            json_extract(data, '$.distance_km') AS distance_km
                        FROM journeys
                        """
                    )


                    db.commit()


            try:
                await self.hass.async_add_executor_job(
                    functools.partial(_setup)
                )
            except Exception:
                self.hass.data.pop(runtime_key, None)
                _LOGGER.exception(
                    "Unable to initialize Ford Triplog SQLite database"
                )
                return

            self.hass.data[runtime_key] = True
            _LOGGER.info(
                "Ford Triplog SQLite database initialized: %s",
                self.db_path,
            )

    async def load_storage_mirror_snapshot(
        self,
        trip_ids: list[str],
        charge_ids: list[str],
    ) -> dict[str, Any]:
        """Load current SQLite values needed by the main initial mirror."""

        normalized_trip_ids = [
            str(value).strip()
            for value in trip_ids
            if str(value).strip()
        ]
        normalized_charge_ids = [
            str(value).strip()
            for value in charge_ids
            if str(value).strip()
        ]

        self._log_read(
            "storage_mirror_snapshot "
            f"trips={len(normalized_trip_ids)} "
            f"charges={len(normalized_charge_ids)}"
        )

        def _decode(payload: Any) -> dict[str, Any] | None:
            if payload is None:
                return None
            try:
                value = json.loads(payload)
            except (TypeError, json.JSONDecodeError):
                return None
            return value if isinstance(value, dict) else None

        def _read() -> dict[str, Any]:
            result: dict[str, Any] = {
                "trips": {},
                "charges": {},
                "current_trip": None,
                "current_charge": None,
                "last_trip": None,
                "last_charge": None,
                "statistics": None,
                "diagnostics": None,
            }

            with sqlite3.connect(self.db_path) as db:
                if normalized_trip_ids:
                    placeholders = ",".join("?" for _ in normalized_trip_ids)
                    rows = db.execute(
                        f"SELECT trip_id, data FROM trips "
                        f"WHERE trip_id IN ({placeholders})",
                        normalized_trip_ids,
                    ).fetchall()
                    for trip_id, payload in rows:
                        value = _decode(payload)
                        if value is not None:
                            result["trips"][str(trip_id)] = value

                if normalized_charge_ids:
                    placeholders = ",".join("?" for _ in normalized_charge_ids)
                    rows = db.execute(
                        f"SELECT charge_id, data FROM charges "
                        f"WHERE charge_id IN ({placeholders})",
                        normalized_charge_ids,
                    ).fetchall()
                    for charge_id, payload in rows:
                        value = _decode(payload)
                        if value is not None:
                            result["charges"][str(charge_id)] = value

                single_queries = {
                    "current_trip": "SELECT data FROM current_trip LIMIT 1",
                    "current_charge": "SELECT data FROM current_charge LIMIT 1",
                    "last_trip": "SELECT data FROM last_trip LIMIT 1",
                    "last_charge": "SELECT data FROM last_charge LIMIT 1",
                    "statistics": "SELECT data FROM statistics WHERE id = 1",
                    "diagnostics": "SELECT data FROM diagnostics WHERE id = 1",
                }

                for key, query in single_queries.items():
                    row = db.execute(query).fetchone()
                    result[key] = _decode(row[0]) if row else None

            return result

        try:
            return await self.hass.async_add_executor_job(
                functools.partial(_read)
            )
        except Exception:
            _LOGGER.exception(
                "Unable to read SQLite main storage mirror snapshot"
            )
            return {
                "trips": {},
                "charges": {},
                "current_trip": None,
                "current_charge": None,
                "last_trip": None,
                "last_charge": None,
                "statistics": None,
                "diagnostics": None,
            }

    async def save_route(
        self,
        data: dict[str, Any],
    ) -> bool:
        """Mirror one route into SQLite."""

        trip_id = data.get("trip_id")
        if not trip_id:
            _LOGGER.error(
                "Unable to mirror route without trip_id"
            )
            return False

        def _write() -> None:
            payload = json.dumps(
                data,
                ensure_ascii=False,
            )

            with sqlite3.connect(self.db_path) as db:
                db.execute(
                    """
                    INSERT OR REPLACE INTO routes (
                        trip_id,
                        data
                    )
                    VALUES (?, ?)
                    """,
                    (
                        str(trip_id),
                        payload,
                    ),
                )
                db.commit()

        try:
            await self.hass.async_add_executor_job(
                functools.partial(_write)
            )

            _LOGGER.debug(
                "Route mirrored to SQLite: %s",
                trip_id,
            )
            return True

        except Exception:
            _LOGGER.exception(
                "Unable to mirror route to SQLite: %s",
                trip_id,
            )
            return False

    async def load_route_mirror_index(
        self,
    ) -> dict[str, dict[str, Any]]:
        """Load route payloads keyed by trip_id for mirror comparison."""

        self._log_read("route_mirror_index")

        def _read() -> dict[str, dict[str, Any]]:
            with sqlite3.connect(self.db_path) as db:
                rows = db.execute(
                    "SELECT trip_id, data FROM routes"
                ).fetchall()

            result: dict[str, dict[str, Any]] = {}
            for trip_id, payload in rows:
                try:
                    data = json.loads(payload)
                except (TypeError, json.JSONDecodeError):
                    continue
                if isinstance(data, dict):
                    result[str(trip_id)] = data
            return result

        try:
            result = await self.hass.async_add_executor_job(
                functools.partial(_read)
            )
            _LOGGER.debug(
                "SQLite route mirror index loaded: %d",
                len(result),
            )
            return result
        except Exception:
            _LOGGER.exception("Unable to read SQLite route mirror index")
            return {}

    async def load_routes_for_trip_ids(
        self,
        trip_ids: list[str],
    ) -> list[dict[str, Any]]:
        """Load routes for multiple Trip IDs with one SQLite query."""

        normalized_ids = [
            str(trip_id).strip()
            for trip_id in trip_ids
            if str(trip_id).strip()
        ]
        if not normalized_ids:
            return []

        self._log_read(f"route_trip_ids={len(normalized_ids)}")

        def _read() -> list[dict[str, Any]]:
            placeholders = ",".join("?" for _ in normalized_ids)
            with sqlite3.connect(self.db_path) as db:
                rows = db.execute(
                    f"SELECT trip_id, data FROM routes "
                    f"WHERE trip_id IN ({placeholders})",
                    normalized_ids,
                ).fetchall()

            by_id: dict[str, dict[str, Any]] = {}
            for trip_id, payload in rows:
                try:
                    data = json.loads(payload)
                except (TypeError, json.JSONDecodeError):
                    continue
                if isinstance(data, dict):
                    by_id[str(trip_id)] = data

            return [
                by_id[trip_id]
                for trip_id in normalized_ids
                if trip_id in by_id
            ]

        try:
            return await self.hass.async_add_executor_job(
                functools.partial(_read)
            )
        except Exception:
            _LOGGER.exception("Unable to read routes for Trip IDs from SQLite")
            return []

    async def load_route(
        self,
        trip_id: str,
    ) -> dict[str, Any] | None:
        """Load one route from SQLite."""

        normalized_id = str(trip_id).strip()
        if not normalized_id:
            return None

        self._log_read(f"route_trip_id={normalized_id}")

        def _read() -> dict[str, Any] | None:
            with sqlite3.connect(self.db_path) as db:
                row = db.execute(
                    "SELECT data FROM routes WHERE trip_id = ?",
                    (normalized_id,),
                ).fetchone()

            if row is None:
                return None

            data = json.loads(row[0])
            return data if isinstance(data, dict) else None

        try:
            return await self.hass.async_add_executor_job(
                functools.partial(_read)
            )
        except Exception:
            _LOGGER.exception(
                "Unable to read route from SQLite: %s",
                normalized_id,
            )
            return None

    async def load_last_route(self) -> dict[str, Any] | None:
        """Load the most recently created route from SQLite."""

        self._log_read("last_route")

        def _read() -> dict[str, Any] | None:
            with sqlite3.connect(self.db_path) as db:
                row = db.execute(
                    """
                    SELECT data
                    FROM routes
                    ORDER BY rowid DESC
                    LIMIT 1
                    """
                ).fetchone()

            if row is None:
                return None

            data = json.loads(row[0])
            return data if isinstance(data, dict) else None

        try:
            return await self.hass.async_add_executor_job(
                functools.partial(_read)
            )
        except Exception:
            _LOGGER.exception("Unable to read last route from SQLite")
            return None

    async def load_all_routes(self) -> list[dict[str, Any]]:
        """Load all routes from SQLite."""

        self._log_read("routes")

        def _read() -> list[dict[str, Any]]:
            with sqlite3.connect(self.db_path) as db:
                rows = db.execute(
                    """
                    SELECT data
                    FROM routes
                    ORDER BY rowid ASC
                    """
                ).fetchall()

            routes: list[dict[str, Any]] = []
            for row in rows:
                try:
                    data = json.loads(row[0])
                except (TypeError, json.JSONDecodeError):
                    continue
                if isinstance(data, dict):
                    routes.append(data)

            return routes

        try:
            return await self.hass.async_add_executor_job(
                functools.partial(_read)
            )
        except Exception:
            _LOGGER.exception("Unable to read routes from SQLite")
            return []

    async def save_trip(
        self,
        data: dict[str, Any],
    ) -> bool:
        """Mirror one trip into SQLite."""

        trip_id = data.get("trip_id")

        if not trip_id:
            _LOGGER.error(
                "Unable to mirror trip without trip_id"
            )
            return False

        def _write() -> None:
            payload = json.dumps(
                data,
                ensure_ascii=False,
            )

            with sqlite3.connect(self.db_path) as db:
                db.execute(
                    """
                    INSERT OR REPLACE INTO trips (
                        trip_id,
                        data
                    )
                    VALUES (?, ?)
                    """,
                    (
                        str(trip_id),
                        payload,
                    ),
                )
                db.commit()

        try:
            await self.hass.async_add_executor_job(
                functools.partial(_write)
            )

            _LOGGER.debug(
                "Trip mirrored to SQLite: %s",
                trip_id,
            )
            return True

        except Exception:
            _LOGGER.exception(
                "Unable to mirror trip to SQLite: %s",
                trip_id,
            )
            return False

    async def load_top_location_trips(self) -> list[dict[str, Any]]:
        """Load the trip fields required by the Top Locations sensor in one query."""

        self._log_read("view=v_top_location_trips")
        started = time.perf_counter()

        def _read() -> list[dict[str, Any]]:
            with sqlite3.connect(self.db_path) as db:
                rows = db.execute(
                    """
                    SELECT
                        trip_id,
                        data,
                        include_in_statistics,
                        distance_km,
                        start_latitude,
                        start_longitude,
                        end_latitude,
                        end_longitude,
                        start_address,
                        end_address
                    FROM v_top_location_trips
                    """
                ).fetchall()

            result: list[dict[str, Any]] = []
            for row in rows:
                data = json.loads(row[1])
                if not isinstance(data, dict):
                    continue

                # Keep the original JSON payload as the source of truth for
                # address objects and any fields not needed by the view.
                result.append(data)

            return result

        try:
            result = await self.hass.async_add_executor_job(
                functools.partial(_read)
            )
            _LOGGER.debug(
                "SQLite Top Locations load finished: trips=%d elapsed=%.3fs",
                len(result),
                time.perf_counter() - started,
            )
            return result
        except Exception:
            _LOGGER.exception(
                "Unable to read Top Locations trips from SQLite view"
            )
            return []

    async def load_top_charging_charges(self) -> list[dict[str, Any]]:
        """Load statistics-eligible charging sessions from the SQLite view."""

        self._log_read("view=v_top_charging_charges")

        def _read() -> list[dict[str, Any]]:
            with sqlite3.connect(self.db_path) as db:
                rows = db.execute(
                    """
                    SELECT data
                    FROM v_top_charging_charges
                    WHERE COALESCE(include_in_statistics, 1) = 1
                    """
                ).fetchall()

            result: list[dict[str, Any]] = []
            for (payload,) in rows:
                data = json.loads(payload)
                if isinstance(data, dict):
                    result.append(data)
            return result

        try:
            return await self.hass.async_add_executor_job(
                functools.partial(_read)
            )
        except Exception:
            _LOGGER.exception(
                "Unable to read Top Charging data from SQLite view"
            )
            return []

    async def load_top_day_journeys(self) -> list[dict[str, Any]]:
        """Load archived Journeys used by the Top Day aggregation."""

        self._log_read("view=v_top_day_journeys")

        def _read() -> list[dict[str, Any]]:
            with sqlite3.connect(self.db_path) as db:
                rows = db.execute(
                    """
                    SELECT data
                    FROM v_top_day_journeys
                    WHERE distance_km IS NOT NULL
                    """
                ).fetchall()

            result: list[dict[str, Any]] = []
            for (payload,) in rows:
                data = json.loads(payload)
                if isinstance(data, dict):
                    result.append(data)
            return result

        try:
            return await self.hass.async_add_executor_job(
                functools.partial(_read)
            )
        except Exception:
            _LOGGER.exception(
                "Unable to read Top Day Journeys from SQLite view"
            )
            return []

    async def load_top_journey(self) -> dict[str, Any] | None:
        """Load the longest archived Journey from the SQLite view."""

        self._log_read("view=v_top_journey_journeys")

        def _read() -> dict[str, Any] | None:
            with sqlite3.connect(self.db_path) as db:
                row = db.execute(
                    """
                    SELECT journey_id, data
                    FROM v_top_journey_journeys
                    WHERE distance_km IS NOT NULL
                    ORDER BY distance_km DESC, journey_id ASC
                    LIMIT 1
                    """
                ).fetchone()

            if not row:
                return None

            data = json.loads(row[1])
            return data if isinstance(data, dict) else None

        try:
            return await self.hass.async_add_executor_job(
                functools.partial(_read)
            )
        except Exception:
            _LOGGER.exception(
                "Unable to read Top Journey from SQLite view"
            )
            return None

    async def load_top_trip(self) -> dict[str, Any] | None:
        """Load the longest statistics-eligible trip from the SQLite view."""

        self._log_read("view=v_top_trip_trips")

        def _read() -> dict[str, Any] | None:
            with sqlite3.connect(self.db_path) as db:
                row = db.execute(
                    """
                    SELECT trip_id, data
                    FROM v_top_trip_trips
                    WHERE COALESCE(include_in_statistics, 1) = 1
                      AND distance_km IS NOT NULL
                    ORDER BY distance_km DESC, trip_id ASC
                    LIMIT 1
                    """
                ).fetchone()

            if not row:
                return None

            data = json.loads(row[1])
            return data if isinstance(data, dict) else None

        try:
            return await self.hass.async_add_executor_job(
                functools.partial(_read)
            )
        except Exception:
            _LOGGER.exception(
                "Unable to read Top Trip from SQLite view"
            )
            return None

    async def load_top_route_trips(self) -> list[dict[str, Any]]:
        """Load the trip fields required by the Top Routes sensor in one query."""

        self._log_read("view=v_top_route_trips")

        def _read() -> list[dict[str, Any]]:
            with sqlite3.connect(self.db_path) as db:
                rows = db.execute(
                    """
                    SELECT
                        trip_id,
                        data,
                        include_in_statistics,
                        distance_km,
                        consumption_kwh_100km,
                        start_latitude,
                        start_longitude,
                        end_latitude,
                        end_longitude,
                        start_address,
                        end_address
                    FROM v_top_route_trips
                    """
                ).fetchall()

            result: list[dict[str, Any]] = []
            for row in rows:
                data = json.loads(row[1])
                if not isinstance(data, dict):
                    continue
                result.append(data)
            return result

        try:
            return await self.hass.async_add_executor_job(
                functools.partial(_read)
            )
        except Exception:
            _LOGGER.exception(
                "Unable to read Top Routes trips from SQLite view"
            )
            return []

    async def load_trip(
        self,
        trip_id: str,
    ) -> dict[str, Any] | None:
        """Load one archived trip from SQLite."""

        normalized_id = str(trip_id).strip()
        if not normalized_id:
            return None

        self._log_read(f"trip_id={normalized_id}")

        def _read() -> dict[str, Any] | None:
            with sqlite3.connect(self.db_path) as db:
                row = db.execute(
                    "SELECT data FROM trips WHERE trip_id = ?",
                    (normalized_id,),
                ).fetchone()

            if row is None:
                return None

            return json.loads(row[0])

        try:
            return await self.hass.async_add_executor_job(
                functools.partial(_read)
            )
        except Exception:
            _LOGGER.exception(
                "Unable to read trip from SQLite: %s",
                normalized_id,
            )
            return None

    async def load_all_trips(self) -> list[dict[str, Any]]:
        """Load all archived trips from SQLite."""

        self._log_read("trips")

        def _read() -> list[dict[str, Any]]:
            with sqlite3.connect(self.db_path) as db:
                rows = db.execute(
                    """
                    SELECT data
                    FROM trips
                    ORDER BY
                        json_extract(data, '$.start_time') ASC,
                        trip_id ASC
                    """
                ).fetchall()

            trips: list[dict[str, Any]] = []
            for (payload,) in rows:
                try:
                    data = json.loads(payload)
                except (TypeError, json.JSONDecodeError):
                    continue

                if isinstance(data, dict):
                    trips.append(data)

            return trips

        try:
            trips = await self.hass.async_add_executor_job(
                functools.partial(_read)
            )
            _LOGGER.debug(
                "SQLite trips loaded: %d",
                len(trips),
            )
            return trips
        except Exception:
            _LOGGER.exception(
                "Unable to read trips from SQLite"
            )
            return []

    async def load_charge(
        self,
        charge_id: str,
    ) -> dict[str, Any] | None:
        """Load one archived charging session from SQLite."""

        normalized_id = str(charge_id).strip()
        if not normalized_id:
            return None

        self._log_read(f"charge_id={normalized_id}")

        def _read() -> dict[str, Any] | None:
            with sqlite3.connect(self.db_path) as db:
                row = db.execute(
                    "SELECT data FROM charges WHERE charge_id = ?",
                    (normalized_id,),
                ).fetchone()

            if row is None:
                return None

            return json.loads(row[0])

        try:
            return await self.hass.async_add_executor_job(
                functools.partial(_read)
            )
        except Exception:
            _LOGGER.exception(
                "Unable to read charge from SQLite: %s",
                normalized_id,
            )
            return None

    async def save_current_trip(
        self,
        data: dict[str, Any],
    ) -> bool:
        """Mirror current trip into SQLite."""

        trip_id = data.get("trip_id")

        if not trip_id:
            _LOGGER.error(
                "Unable to mirror current trip without trip_id"
            )
            return False

        def _write() -> None:
            payload = json.dumps(
                data,
                ensure_ascii=False,
            )

            with sqlite3.connect(self.db_path) as db:
                db.execute(
                    """
                    INSERT OR REPLACE INTO current_trip (
                        trip_id,
                        data
                    )
                    VALUES (?, ?)
                    """,
                    (
                        str(trip_id),
                        payload,
                    ),
                )
                db.commit()

        try:
            await self.hass.async_add_executor_job(
                functools.partial(_write)
            )

            _LOGGER.debug(
                "Current trip mirrored to SQLite: %s",
                trip_id,
            )
            return True

        except Exception:
            _LOGGER.exception(
                "Unable to mirror current trip to SQLite: %s",
                trip_id,
            )
            return False

    async def load_current_trip(self) -> dict[str, Any] | None:
        """Load current trip from SQLite."""

        self._log_read("current_trip")

        def _read() -> dict[str, Any] | None:
            with sqlite3.connect(self.db_path) as db:
                row = db.execute(
                    "SELECT data FROM current_trip LIMIT 1"
                ).fetchone()

            if row is None:
                return None

            return json.loads(row[0])

        try:
            return await self.hass.async_add_executor_job(
                functools.partial(_read)
            )
        except Exception:
            _LOGGER.exception(
                "Unable to read current trip from SQLite"
            )
            return None

    async def delete_current_trip(self) -> bool:
        """Delete current trip mirror from SQLite."""

        def _delete() -> None:
            with sqlite3.connect(self.db_path) as db:
                db.execute("DELETE FROM current_trip")
                db.commit()

        try:
            await self.hass.async_add_executor_job(
                functools.partial(_delete)
            )

            _LOGGER.debug(
                "Current trip removed from SQLite"
            )
            return True

        except Exception:
            _LOGGER.exception(
                "Unable to remove current trip from SQLite"
            )
            return False

    async def load_last_trip(self) -> dict[str, Any] | None:
        """Load last trip from SQLite."""

        self._log_read("last_trip")

        def _read() -> dict[str, Any] | None:
            with sqlite3.connect(self.db_path) as db:
                row = db.execute(
                    "SELECT data FROM last_trip LIMIT 1"
                ).fetchone()

            if row is None:
                return None

            return json.loads(row[0])

        try:
            return await self.hass.async_add_executor_job(
                functools.partial(_read)
            )
        except Exception:
            _LOGGER.exception(
                "Unable to read last trip from SQLite"
            )
            return None

    async def save_last_trip(
        self,
        data: dict[str, Any],
    ) -> bool:
        """Mirror last trip into SQLite."""

        trip_id = data.get("trip_id")

        if not trip_id:
            _LOGGER.error(
                "Unable to mirror last trip without trip_id"
            )
            return False

        def _write() -> None:
            payload = json.dumps(
                data,
                ensure_ascii=False,
            )

            with sqlite3.connect(self.db_path) as db:
                # last_trip is a single-record cache.
                db.execute("DELETE FROM last_trip")
                db.execute(
                    """
                    INSERT INTO last_trip (
                        trip_id,
                        data
                    )
                    VALUES (?, ?)
                    """,
                    (
                        str(trip_id),
                        payload,
                    ),
                )
                db.commit()

        try:
            await self.hass.async_add_executor_job(
                functools.partial(_write)
            )

            _LOGGER.debug(
                "Last trip mirrored to SQLite: %s",
                trip_id,
            )
            return True

        except Exception:
            _LOGGER.exception(
                "Unable to mirror last trip to SQLite: %s",
                trip_id,
            )
            return False

    async def save_current_charge(
        self,
        data: dict[str, Any],
    ) -> bool:
        """Mirror current charging session into SQLite."""

        charge_id = data.get("charge_id")

        if not charge_id:
            _LOGGER.error(
                "Unable to mirror current charge without charge_id"
            )
            return False

        def _write() -> None:
            payload = json.dumps(
                data,
                ensure_ascii=False,
            )

            with sqlite3.connect(self.db_path) as db:
                db.execute(
                    """
                    INSERT OR REPLACE INTO current_charge (
                        charge_id,
                        data
                    )
                    VALUES (?, ?)
                    """,
                    (
                        str(charge_id),
                        payload,
                    ),
                )
                db.commit()

        try:
            await self.hass.async_add_executor_job(
                functools.partial(_write)
            )

            _LOGGER.debug(
                "Current charge mirrored to SQLite: %s",
                charge_id,
            )
            return True

        except Exception:
            _LOGGER.exception(
                "Unable to mirror current charge to SQLite: %s",
                charge_id,
            )
            return False

    async def load_current_charge(
        self,
    ) -> dict[str, Any] | None:
        """Load current charging session from SQLite."""

        self._log_read("current_charge")

        def _read() -> dict[str, Any] | None:
            with sqlite3.connect(self.db_path) as db:
                row = db.execute(
                    "SELECT data FROM current_charge LIMIT 1"
                ).fetchone()

            if row is None:
                return None

            return json.loads(row[0])

        try:
            return await self.hass.async_add_executor_job(
                functools.partial(_read)
            )
        except Exception:
            _LOGGER.exception(
                "Unable to read current charge from SQLite"
            )
            return None

    async def delete_current_charge(self) -> bool:
        """Delete current charging-session mirror from SQLite."""

        def _delete() -> None:
            with sqlite3.connect(self.db_path) as db:
                db.execute("DELETE FROM current_charge")
                db.commit()

        try:
            await self.hass.async_add_executor_job(
                functools.partial(_delete)
            )

            _LOGGER.debug(
                "Current charge removed from SQLite"
            )
            return True

        except Exception:
            _LOGGER.exception(
                "Unable to remove current charge from SQLite"
            )
            return False

    async def load_last_charge(
        self,
    ) -> dict[str, Any] | None:
        """Load last charging session from SQLite."""

        self._log_read("last_charge")

        def _read() -> dict[str, Any] | None:
            with sqlite3.connect(self.db_path) as db:
                row = db.execute(
                    "SELECT data FROM last_charge LIMIT 1"
                ).fetchone()

            if row is None:
                return None

            return json.loads(row[0])

        try:
            return await self.hass.async_add_executor_job(
                functools.partial(_read)
            )
        except Exception:
            _LOGGER.exception(
                "Unable to read last charge from SQLite"
            )
            return None

    async def save_charge(
        self,
        data: dict[str, Any],
    ) -> bool:
        """Mirror one completed charging session into SQLite."""

        charge_id = data.get("charge_id")

        if not charge_id:
            _LOGGER.error(
                "Unable to mirror charge without charge_id"
            )
            return False

        def _write() -> None:
            payload = json.dumps(
                data,
                ensure_ascii=False,
            )

            with sqlite3.connect(self.db_path) as db:
                db.execute(
                    """
                    INSERT OR REPLACE INTO charges (
                        charge_id,
                        data
                    )
                    VALUES (?, ?)
                    """,
                    (
                        str(charge_id),
                        payload,
                    ),
                )
                db.commit()

        try:
            await self.hass.async_add_executor_job(
                functools.partial(_write)
            )

            _LOGGER.debug(
                "Charge mirrored to SQLite: %s",
                charge_id,
            )
            return True

        except Exception:
            _LOGGER.exception(
                "Unable to mirror charge to SQLite: %s",
                charge_id,
            )
            return False

    async def save_last_charge(
        self,
        data: dict[str, Any],
    ) -> bool:
        """Mirror last charging session into SQLite."""

        charge_id = data.get("charge_id")

        if not charge_id:
            _LOGGER.error(
                "Unable to mirror last charge without charge_id"
            )
            return False

        def _write() -> None:
            payload = json.dumps(
                data,
                ensure_ascii=False,
            )

            with sqlite3.connect(self.db_path) as db:
                # last_charge is a single-record cache.
                db.execute("DELETE FROM last_charge")
                db.execute(
                    """
                    INSERT INTO last_charge (
                        charge_id,
                        data
                    )
                    VALUES (?, ?)
                    """,
                    (
                        str(charge_id),
                        payload,
                    ),
                )
                db.commit()

        try:
            await self.hass.async_add_executor_job(
                functools.partial(_write)
            )

            _LOGGER.debug(
                "Last charge mirrored to SQLite: %s",
                charge_id,
            )
            return True

        except Exception:
            _LOGGER.exception(
                "Unable to mirror last charge to SQLite: %s",
                charge_id,
            )
            return False

    async def save_statistics(
        self,
        data: dict[str, Any],
    ) -> bool:
        """Mirror statistics cache into SQLite."""

        def _write() -> None:
            payload = json.dumps(
                data,
                ensure_ascii=False,
            )

            with sqlite3.connect(self.db_path) as db:
                db.execute(
                    """
                    INSERT OR REPLACE INTO statistics (
                        id,
                        data
                    )
                    VALUES (1, ?)
                    """,
                    (payload,),
                )
                db.commit()

        try:
            await self.hass.async_add_executor_job(
                functools.partial(_write)
            )

            _LOGGER.debug(
                "Statistics mirrored to SQLite"
            )
            return True

        except Exception:
            _LOGGER.exception(
                "Unable to mirror statistics to SQLite"
            )
            return False

    async def load_statistics(self) -> dict[str, Any] | None:
        """Load statistics cache from SQLite."""

        self._log_read("statistics")

        def _read() -> dict[str, Any] | None:
            with sqlite3.connect(self.db_path) as db:
                row = db.execute(
                    "SELECT data FROM statistics WHERE id = 1"
                ).fetchone()

            if row is None:
                return None

            return json.loads(row[0])

        try:
            return await self.hass.async_add_executor_job(
                functools.partial(_read)
            )
        except Exception:
            _LOGGER.exception(
                "Unable to read statistics from SQLite"
            )
            return None

    async def save_diagnostics(
        self,
        data: dict[str, Any],
    ) -> bool:
        """Mirror diagnostics cache into SQLite."""

        def _write() -> None:
            payload = json.dumps(
                data,
                ensure_ascii=False,
            )

            with sqlite3.connect(self.db_path) as db:
                db.execute(
                    """
                    INSERT OR REPLACE INTO diagnostics (
                        id,
                        data
                    )
                    VALUES (1, ?)
                    """,
                    (payload,),
                )
                db.commit()

        try:
            await self.hass.async_add_executor_job(
                functools.partial(_write)
            )

            _LOGGER.debug(
                "Diagnostics mirrored to SQLite"
            )
            return True

        except Exception:
            _LOGGER.exception(
                "Unable to mirror diagnostics to SQLite"
            )
            return False

    async def load_user_charging_sites(self) -> list[dict[str, Any]]:
        """Load all user-defined charging sites from SQLite."""

        self._log_read("user_charging_sites")

        def _read() -> list[dict[str, Any]]:
            with sqlite3.connect(self.db_path) as db:
                rows = db.execute(
                    """
                    SELECT data
                    FROM user_charging_sites
                    ORDER BY site_id ASC
                    """
                ).fetchall()

            sites: list[dict[str, Any]] = []
            for (payload,) in rows:
                try:
                    data = json.loads(payload)
                except (TypeError, json.JSONDecodeError):
                    continue

                if isinstance(data, dict):
                    sites.append(data)

            return sites

        try:
            sites = await self.hass.async_add_executor_job(
                functools.partial(_read)
            )
            _LOGGER.debug(
                "SQLite user charging sites loaded: %d",
                len(sites),
            )
            return sites
        except Exception:
            _LOGGER.exception(
                "Unable to read user charging sites from SQLite"
            )
            return []

    async def load_pending_charging_sites(self) -> list[dict[str, Any]]:
        """Load pending charging sites from SQLite."""
        self._log_read("pending_charging_sites")

        def _read() -> list[dict[str, Any]]:
            with sqlite3.connect(self.db_path) as db:
                rows = db.execute(
                    "SELECT data FROM pending_charging_sites ORDER BY rowid ASC"
                ).fetchall()
            result = []
            for (payload,) in rows:
                try:
                    data = json.loads(payload)
                except (TypeError, json.JSONDecodeError):
                    continue
                if isinstance(data, dict):
                    result.append(data)
            return result

        try:
            result = await self.hass.async_add_executor_job(functools.partial(_read))
            _LOGGER.debug("SQLite pending charging sites loaded: %d", len(result))
            return result
        except Exception:
            _LOGGER.exception("Unable to read pending charging sites from SQLite")
            return []

    async def save_pending_charging_sites(self, sites: list[dict[str, Any]]) -> bool:
        """Replace the pending charging-site collection in SQLite."""
        def _write() -> None:
            rows = []
            for site in sites:
                pending_id = site.get("id")
                if not pending_id:
                    raise ValueError("Pending charging site has no id")
                rows.append((str(pending_id), json.dumps(site, ensure_ascii=False)))
            with sqlite3.connect(self.db_path) as db:
                db.execute("DELETE FROM pending_charging_sites")
                if rows:
                    db.executemany(
                        "INSERT INTO pending_charging_sites (pending_id, data) VALUES (?, ?)",
                        rows,
                    )
                db.commit()
        try:
            await self.hass.async_add_executor_job(functools.partial(_write))
            _LOGGER.debug("Pending charging sites saved to SQLite: %d", len(sites))
            return True
        except Exception:
            _LOGGER.exception("Unable to save pending charging sites to SQLite")
            return False

    async def save_user_charging_sites(
        self,
        sites: list[dict[str, Any]],
    ) -> bool:
        """Mirror the complete user charging-site database into SQLite."""

        def _write() -> None:
            rows: list[tuple[str, str]] = []

            for site in sites:
                site_id = site.get("site_id")
                if not site_id:
                    raise ValueError(
                        "Unable to mirror user charging site without site_id"
                    )

                rows.append(
                    (
                        str(site_id),
                        json.dumps(site, ensure_ascii=False),
                    )
                )

            with sqlite3.connect(self.db_path) as db:
                # async_save() represents the complete JSON site list,
                # therefore replace the complete SQLite mirror as well.
                db.execute("DELETE FROM user_charging_sites")

                if rows:
                    db.executemany(
                        """
                        INSERT INTO user_charging_sites (
                            site_id,
                            data
                        )
                        VALUES (?, ?)
                        """,
                        rows,
                    )

                db.commit()

        try:
            await self.hass.async_add_executor_job(
                functools.partial(_write)
            )

            _LOGGER.debug(
                "User charging sites mirrored to SQLite: %s",
                len(sites),
            )
            return True

        except Exception:
            _LOGGER.exception(
                "Unable to mirror user charging sites to SQLite"
            )
            return False

    async def save_journey(
        self,
        data: dict[str, Any],
    ) -> bool:
        """Mirror one archived journey into SQLite."""

        journey_id = data.get("journey_id")
        if not journey_id:
            _LOGGER.error("Unable to mirror journey without journey_id")
            return False

        def _write() -> None:
            payload = json.dumps(data, ensure_ascii=False)
            with sqlite3.connect(self.db_path) as db:
                db.execute(
                    """
                    INSERT OR REPLACE INTO journeys (journey_id, data)
                    VALUES (?, ?)
                    """,
                    (str(journey_id), payload),
                )
                db.commit()

        try:
            await self.hass.async_add_executor_job(functools.partial(_write))
            _LOGGER.debug("Journey mirrored to SQLite: %s", journey_id)
            return True
        except Exception:
            _LOGGER.exception("Unable to mirror journey to SQLite: %s", journey_id)
            return False

    async def load_journey_mirror_index(
        self,
    ) -> dict[str, dict[str, Any]]:
        """Load archived journey payloads keyed by journey_id for mirror comparison."""

        self._log_read("journey_mirror_index")

        def _read() -> dict[str, dict[str, Any]]:
            with sqlite3.connect(self.db_path) as db:
                rows = db.execute(
                    "SELECT journey_id, data FROM journeys"
                ).fetchall()

            result: dict[str, dict[str, Any]] = {}
            for journey_id, payload in rows:
                try:
                    data = json.loads(payload)
                except (TypeError, json.JSONDecodeError):
                    continue

                if isinstance(data, dict):
                    result[str(journey_id)] = data

            return result

        try:
            result = await self.hass.async_add_executor_job(
                functools.partial(_read)
            )
            _LOGGER.debug(
                "SQLite journey mirror index loaded: %d",
                len(result),
            )
            return result
        except Exception:
            _LOGGER.exception(
                "Unable to read SQLite journey mirror index"
            )
            return {}

    async def load_journey(
        self,
        journey_id: str,
    ) -> dict[str, Any] | None:
        """Load one archived journey from SQLite."""

        normalized_id = str(journey_id).strip()
        if not normalized_id:
            return None

        self._log_read(f"journey_id={normalized_id}")

        def _read() -> dict[str, Any] | None:
            with sqlite3.connect(self.db_path) as db:
                row = db.execute(
                    "SELECT data FROM journeys WHERE journey_id = ?",
                    (normalized_id,),
                ).fetchone()

            if row is None:
                return None

            return json.loads(row[0])

        try:
            return await self.hass.async_add_executor_job(
                functools.partial(_read)
            )
        except Exception:
            _LOGGER.exception(
                "Unable to read journey from SQLite: %s",
                normalized_id,
            )
            return None

    async def load_all_journeys(self) -> list[dict[str, Any]]:
        """Load all archived journeys from SQLite."""

        self._log_read("journeys")

        def _read() -> list[dict[str, Any]]:
            with sqlite3.connect(self.db_path) as db:
                rows = db.execute(
                    """
                    SELECT data
                    FROM journeys
                    ORDER BY
                        json_extract(data, '$.start_time') ASC,
                        journey_id ASC
                    """
                ).fetchall()

            journeys: list[dict[str, Any]] = []
            for (payload,) in rows:
                try:
                    data = json.loads(payload)
                except (TypeError, json.JSONDecodeError):
                    continue

                if isinstance(data, dict):
                    journeys.append(data)

            return journeys

        try:
            journeys = await self.hass.async_add_executor_job(
                functools.partial(_read)
            )
            _LOGGER.debug(
                "SQLite journeys loaded: %d",
                len(journeys),
            )
            return journeys
        except Exception:
            _LOGGER.exception(
                "Unable to read journeys from SQLite"
            )
            return []

    async def load_all_charges(self) -> list[dict[str, Any]]:
        """Load all archived charging sessions from SQLite."""

        self._log_read("charges")

        def _read() -> list[dict[str, Any]]:
            with sqlite3.connect(self.db_path) as db:
                rows = db.execute(
                    """
                    SELECT data
                    FROM charges
                    ORDER BY
                        json_extract(data, '$.start_time') ASC,
                        charge_id ASC
                    """
                ).fetchall()

            charges: list[dict[str, Any]] = []
            for (payload,) in rows:
                try:
                    data = json.loads(payload)
                except (TypeError, json.JSONDecodeError):
                    continue

                if isinstance(data, dict):
                    charges.append(data)

            return charges

        try:
            charges = await self.hass.async_add_executor_job(
                functools.partial(_read)
            )
            _LOGGER.debug(
                "SQLite charges loaded: %d",
                len(charges),
            )
            return charges
        except Exception:
            _LOGGER.exception(
                "Unable to read charges from SQLite"
            )
            return []

    async def load_current_journey(self) -> dict[str, Any] | None:
        """Load the current journey from SQLite."""

        self._log_read("current_journey")

        def _read() -> dict[str, Any] | None:
            with sqlite3.connect(self.db_path) as db:
                row = db.execute(
                    "SELECT data FROM current_journey LIMIT 1"
                ).fetchone()

            if row is None:
                return None

            return json.loads(row[0])

        try:
            return await self.hass.async_add_executor_job(
                functools.partial(_read)
            )
        except Exception:
            _LOGGER.exception(
                "Unable to read current journey from SQLite"
            )
            return None

    async def load_last_journey(self) -> dict[str, Any] | None:
        """Load the last completed journey from SQLite.

        The dedicated last_journey cache is preferred. If it is missing,
        fall back to the newest archived journey. This keeps SQLite-only
        operation working even when the JSON cache file is absent.
        """

        self._log_read("last_journey")

        def _read() -> dict[str, Any] | None:
            with sqlite3.connect(self.db_path) as db:
                row = db.execute(
                    "SELECT data FROM last_journey LIMIT 1"
                ).fetchone()

                if row is not None:
                    data = json.loads(row[0])
                    if isinstance(data, dict):
                        return data

                # SQLite-only fallback: derive the last completed journey
                # from the archived journey table instead of requiring the
                # optional last_journey cache.
                row = db.execute(
                    """
                    SELECT data
                    FROM journeys
                    WHERE json_extract(data, '$.end_time') IS NOT NULL
                    ORDER BY json_extract(data, '$.end_time') DESC,
                             journey_id DESC
                    LIMIT 1
                    """
                ).fetchone()

            if row is None:
                return None

            data = json.loads(row[0])
            return data if isinstance(data, dict) else None

        try:
            data = await self.hass.async_add_executor_job(
                functools.partial(_read)
            )

            if data is not None:
                _LOGGER.debug(
                    "SQLite last journey loaded: %s",
                    data.get("journey_id", "unknown"),
                )
            else:
                _LOGGER.debug(
                    "SQLite last journey: no cache and no archived journey found"
                )

            return data

        except Exception:
            _LOGGER.exception(
                "Unable to read last journey from SQLite"
            )
            return None

    async def delete_journey(self, journey_id: str) -> bool:
        """Delete one archived journey from SQLite."""

        def _delete() -> None:
            with sqlite3.connect(self.db_path) as db:
                db.execute(
                    "DELETE FROM journeys WHERE journey_id = ?",
                    (str(journey_id),),
                )
                db.commit()

        try:
            await self.hass.async_add_executor_job(functools.partial(_delete))
            return True
        except Exception:
            _LOGGER.exception("Unable to delete journey from SQLite: %s", journey_id)
            return False

    async def delete_all_journeys(self) -> bool:
        """Delete all archived journey mirrors."""

        def _delete() -> None:
            with sqlite3.connect(self.db_path) as db:
                db.execute("DELETE FROM journeys")
                db.commit()

        try:
            await self.hass.async_add_executor_job(functools.partial(_delete))
            return True
        except Exception:
            _LOGGER.exception("Unable to delete all journeys from SQLite")
            return False

    async def save_current_journey(self, data: dict[str, Any]) -> bool:
        """Mirror current journey into SQLite."""

        journey_id = data.get("journey_id")
        if not journey_id:
            return False

        def _write() -> None:
            payload = json.dumps(data, ensure_ascii=False)
            with sqlite3.connect(self.db_path) as db:
                db.execute("DELETE FROM current_journey")
                db.execute(
                    "INSERT INTO current_journey (journey_id, data) VALUES (?, ?)",
                    (str(journey_id), payload),
                )
                db.commit()

        try:
            await self.hass.async_add_executor_job(functools.partial(_write))
            return True
        except Exception:
            _LOGGER.exception("Unable to mirror current journey to SQLite")
            return False

    async def delete_current_journey(self) -> bool:
        """Clear current journey mirror."""

        def _delete() -> None:
            with sqlite3.connect(self.db_path) as db:
                db.execute("DELETE FROM current_journey")
                db.commit()

        try:
            await self.hass.async_add_executor_job(functools.partial(_delete))
            return True
        except Exception:
            _LOGGER.exception("Unable to clear current journey from SQLite")
            return False

    async def save_last_journey(self, data: dict[str, Any]) -> bool:
        """Mirror last completed journey into SQLite."""

        journey_id = data.get("journey_id")
        if not journey_id:
            return False

        def _write() -> None:
            payload = json.dumps(data, ensure_ascii=False)
            with sqlite3.connect(self.db_path) as db:
                db.execute("DELETE FROM last_journey")
                db.execute(
                    "INSERT INTO last_journey (journey_id, data) VALUES (?, ?)",
                    (str(journey_id), payload),
                )
                db.commit()

        try:
            await self.hass.async_add_executor_job(functools.partial(_write))
            return True
        except Exception:
            _LOGGER.exception("Unable to mirror last journey to SQLite")
            return False

    async def delete_last_journey(self) -> bool:
        """Clear last journey mirror."""

        def _delete() -> None:
            with sqlite3.connect(self.db_path) as db:
                db.execute("DELETE FROM last_journey")
                db.commit()

        try:
            await self.hass.async_add_executor_job(functools.partial(_delete))
            return True
        except Exception:
            _LOGGER.exception("Unable to clear last journey from SQLite")
            return False

    async def load_all_receipts(self) -> list[dict[str, Any]]:
        """Load all receipts from SQLite."""

        self._log_read("receipts")

        def _read() -> list[dict[str, Any]]:
            with sqlite3.connect(self.db_path) as db:
                rows = db.execute(
                    """
                    SELECT receipt_id, target_type, target_id, data
                    FROM receipts
                    ORDER BY receipt_id ASC
                    """
                ).fetchall()

            result: list[dict[str, Any]] = []
            for receipt_id, target_type, target_id, payload in rows:
                try:
                    data = json.loads(payload)
                except (TypeError, json.JSONDecodeError):
                    continue

                if not isinstance(data, dict):
                    continue

                value = dict(data)
                value["receipt_id"] = str(receipt_id)
                value["target_type"] = str(target_type)
                value["target_id"] = str(target_id)
                result.append(value)

            return result

        try:
            result = await self.hass.async_add_executor_job(
                functools.partial(_read)
            )
            _LOGGER.debug(
                "SQLite receipts loaded: %d",
                len(result),
            )
            return result
        except Exception:
            _LOGGER.exception("Unable to read receipts from SQLite")
            return []

    async def load_receipt(
        self,
        receipt_id: str,
    ) -> dict[str, Any] | None:
        """Load one receipt from SQLite."""

        self._log_read(f"receipt={receipt_id}")

        def _read() -> dict[str, Any] | None:
            with sqlite3.connect(self.db_path) as db:
                row = db.execute(
                    """
                    SELECT target_type, target_id, data
                    FROM receipts
                    WHERE receipt_id = ?
                    """,
                    (str(receipt_id),),
                ).fetchone()

            if row is None:
                return None

            target_type, target_id, payload = row
            try:
                data = json.loads(payload)
            except (TypeError, json.JSONDecodeError):
                return None

            if not isinstance(data, dict):
                return None

            value = dict(data)
            value["receipt_id"] = str(receipt_id)
            value["target_type"] = str(target_type)
            value["target_id"] = str(target_id)
            return value

        try:
            return await self.hass.async_add_executor_job(
                functools.partial(_read)
            )
        except Exception:
            _LOGGER.exception(
                "Unable to read receipt from SQLite: %s",
                receipt_id,
            )
            return None

    async def save_receipt(
        self,
        target_type: str,
        target_id: str,
        receipt: dict[str, Any],
    ) -> bool:
        """Insert or replace one receipt in SQLite."""

        receipt_id = str(receipt.get("receipt_id") or "").strip()
        if not receipt_id:
            raise ValueError("Receipt ID is required")

        payload = dict(receipt)
        payload.pop("target_type", None)
        payload.pop("target_id", None)

        def _write() -> None:
            with sqlite3.connect(self.db_path) as db:
                db.execute(
                    """
                    INSERT INTO receipts (
                        receipt_id,
                        target_type,
                        target_id,
                        data
                    )
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(receipt_id) DO UPDATE SET
                        target_type = excluded.target_type,
                        target_id = excluded.target_id,
                        data = excluded.data
                    """,
                    (
                        receipt_id,
                        str(target_type),
                        str(target_id),
                        json.dumps(payload, ensure_ascii=False),
                    ),
                )
                db.commit()

        try:
            await self.hass.async_add_executor_job(
                functools.partial(_write)
            )
            _LOGGER.debug(
                "Receipt saved to SQLite: %s target=%s:%s",
                receipt_id,
                target_type,
                target_id,
            )
            return True
        except Exception:
            _LOGGER.exception(
                "Unable to save receipt to SQLite: %s",
                receipt_id,
            )
            return False

    async def delete_receipt(
        self,
        receipt_id: str,
    ) -> bool:
        """Delete one receipt from SQLite."""

        def _delete() -> bool:
            with sqlite3.connect(self.db_path) as db:
                cursor = db.execute(
                    "DELETE FROM receipts WHERE receipt_id = ?",
                    (str(receipt_id),),
                )
                db.commit()
                return cursor.rowcount > 0

        try:
            return await self.hass.async_add_executor_job(
                functools.partial(_delete)
            )
        except Exception:
            _LOGGER.exception(
                "Unable to delete receipt from SQLite: %s",
                receipt_id,
            )
            return False

    async def save_all_receipts(
        self,
        receipts: list[dict[str, Any]],
    ) -> bool:
        """Replace the complete receipt collection in SQLite."""

        def _write() -> None:
            rows: list[tuple[str, str, str, str]] = []

            for receipt in receipts:
                if not isinstance(receipt, dict):
                    continue

                receipt_id = str(
                    receipt.get("receipt_id") or ""
                ).strip()
                target_type = str(
                    receipt.get("target_type") or ""
                ).strip()
                target_id = str(
                    receipt.get("target_id") or ""
                ).strip()

                if not receipt_id or not target_type or not target_id:
                    continue

                payload = dict(receipt)
                payload.pop("target_type", None)
                payload.pop("target_id", None)

                rows.append(
                    (
                        receipt_id,
                        target_type,
                        target_id,
                        json.dumps(payload, ensure_ascii=False),
                    )
                )

            with sqlite3.connect(self.db_path) as db:
                db.execute("DELETE FROM receipts")
                if rows:
                    db.executemany(
                        """
                        INSERT INTO receipts (
                            receipt_id,
                            target_type,
                            target_id,
                            data
                        )
                        VALUES (?, ?, ?, ?)
                        """,
                        rows,
                    )
                db.commit()

        try:
            await self.hass.async_add_executor_job(
                functools.partial(_write)
            )
            _LOGGER.debug(
                "Receipts saved to SQLite: %d",
                len(receipts),
            )
            return True
        except Exception:
            _LOGGER.exception("Unable to save receipts to SQLite")
            return False

    async def load_user_receipt_parser_profiles(
        self,
    ) -> list[dict[str, Any]]:
        """Load all user-created receipt parser profiles from SQLite."""

        self._log_read("user_receipt_parser_profiles")

        def _read() -> list[dict[str, Any]]:
            with sqlite3.connect(self.db_path) as db:
                rows = db.execute(
                    """
                    SELECT data
                    FROM user_receipt_parser_profiles
                    ORDER BY profile_id ASC
                    """
                ).fetchall()

            result: list[dict[str, Any]] = []
            for (payload,) in rows:
                try:
                    value = json.loads(payload)
                except (TypeError, json.JSONDecodeError):
                    continue
                if (
                    isinstance(value, dict)
                    and str(value.get("profile_id") or "").strip()
                ):
                    result.append(value)
            return result

        try:
            result = await self.hass.async_add_executor_job(
                functools.partial(_read)
            )
            _LOGGER.debug(
                "SQLite user receipt parser profiles loaded: %d",
                len(result),
            )
            return result
        except Exception:
            _LOGGER.exception(
                "Unable to read user receipt parser profiles from SQLite"
            )
            return []

    async def save_user_receipt_parser_profile(
        self,
        profile: dict[str, Any],
    ) -> bool:
        """Insert or replace one user receipt parser profile."""

        profile_id = str(profile.get("profile_id") or "").strip()
        if not profile_id:
            raise ValueError("Receipt parser profile ID is required")

        payload = json.dumps(profile, ensure_ascii=False)

        def _write() -> None:
            with sqlite3.connect(self.db_path) as db:
                db.execute(
                    """
                    INSERT INTO user_receipt_parser_profiles (
                        profile_id,
                        data
                    )
                    VALUES (?, ?)
                    ON CONFLICT(profile_id) DO UPDATE SET
                        data = excluded.data
                    """,
                    (profile_id, payload),
                )
                db.commit()

        try:
            await self.hass.async_add_executor_job(
                functools.partial(_write)
            )
            _LOGGER.debug(
                "User receipt parser profile saved to SQLite: %s",
                profile_id,
            )
            return True
        except Exception:
            _LOGGER.exception(
                "Unable to save user receipt parser profile to SQLite: %s",
                profile_id,
            )
            return False

    async def save_all_user_receipt_parser_profiles(
        self,
        profiles: list[dict[str, Any]],
    ) -> bool:
        """Replace all user receipt parser profiles in SQLite."""

        def _write() -> None:
            rows: list[tuple[str, str]] = []
            used_ids: set[str] = set()

            for profile in profiles:
                if not isinstance(profile, dict):
                    continue
                profile_id = str(profile.get("profile_id") or "").strip()
                if not profile_id or profile_id in used_ids:
                    continue
                used_ids.add(profile_id)
                rows.append(
                    (
                        profile_id,
                        json.dumps(profile, ensure_ascii=False),
                    )
                )

            with sqlite3.connect(self.db_path) as db:
                db.execute("DELETE FROM user_receipt_parser_profiles")
                if rows:
                    db.executemany(
                        """
                        INSERT INTO user_receipt_parser_profiles (
                            profile_id,
                            data
                        )
                        VALUES (?, ?)
                        """,
                        rows,
                    )
                db.commit()

        try:
            await self.hass.async_add_executor_job(
                functools.partial(_write)
            )
            _LOGGER.debug(
                "User receipt parser profiles saved to SQLite: %d",
                len(profiles),
            )
            return True
        except Exception:
            _LOGGER.exception(
                "Unable to save user receipt parser profiles to SQLite"
            )
            return False

    async def load_all_pause_metadata(self) -> dict[str, dict[str, Any]]:
        """Load all persistent pause metadata from SQLite."""
        self._log_read("pause_metadata")

        def _read() -> dict[str, dict[str, Any]]:
            with sqlite3.connect(self.db_path) as db:
                rows = db.execute(
                    "SELECT pause_id, data FROM pause_metadata ORDER BY pause_id ASC"
                ).fetchall()
            result: dict[str, dict[str, Any]] = {}
            for pause_id, payload in rows:
                try:
                    value = json.loads(payload)
                except (TypeError, json.JSONDecodeError):
                    continue
                if isinstance(value, dict):
                    result[str(pause_id)] = value
            return result

        try:
            result = await self.hass.async_add_executor_job(
                functools.partial(_read)
            )
            _LOGGER.debug("SQLite pause metadata loaded: %d", len(result))
            return result
        except Exception:
            _LOGGER.exception("Unable to read pause metadata from SQLite")
            return {}

    async def save_all_pause_metadata(
        self,
        items: dict[str, dict[str, Any]],
    ) -> bool:
        """Replace the complete persistent pause-metadata collection."""

        def _write() -> None:
            rows: list[tuple[str, str]] = []
            for pause_id, value in items.items():
                normalized_id = str(pause_id).strip()
                if not normalized_id or not isinstance(value, dict):
                    continue
                payload = dict(value)
                payload.pop("receipts", None)
                rows.append(
                    (normalized_id, json.dumps(payload, ensure_ascii=False))
                )

            with sqlite3.connect(self.db_path) as db:
                db.execute("DELETE FROM pause_metadata")
                if rows:
                    db.executemany(
                        "INSERT INTO pause_metadata (pause_id, data) VALUES (?, ?)",
                        rows,
                    )
                db.commit()

        try:
            await self.hass.async_add_executor_job(functools.partial(_write))
            _LOGGER.debug("Pause metadata saved to SQLite: %d", len(items))
            return True
        except Exception:
            _LOGGER.exception("Unable to save pause metadata to SQLite")
            return False

    async def load_all_charge_metadata(self) -> dict[str, dict[str, Any]]:
        """Load all persistent charging-session metadata from SQLite."""

        self._log_read("charge_metadata")

        def _read() -> dict[str, dict[str, Any]]:
            with sqlite3.connect(self.db_path) as db:
                rows = db.execute(
                    """
                    SELECT charge_id, data
                    FROM charge_metadata
                    ORDER BY charge_id ASC
                    """
                ).fetchall()

            result: dict[str, dict[str, Any]] = {}
            for charge_id, payload in rows:
                try:
                    data = json.loads(payload)
                except (TypeError, json.JSONDecodeError):
                    continue
                if isinstance(data, dict):
                    result[str(charge_id)] = data
            return result

        try:
            result = await self.hass.async_add_executor_job(
                functools.partial(_read)
            )
            _LOGGER.debug(
                "SQLite charge metadata loaded: %d",
                len(result),
            )
            return result
        except Exception:
            _LOGGER.exception(
                "Unable to read charge metadata from SQLite"
            )
            return {}

    async def save_all_charge_metadata(
        self,
        items: dict[str, dict[str, Any]],
    ) -> bool:
        """Replace the complete persistent charge-metadata collection."""

        def _write() -> None:
            rows: list[tuple[str, str]] = []
            for charge_id, value in items.items():
                normalized_id = str(charge_id).strip()
                if not normalized_id or not isinstance(value, dict):
                    continue
                rows.append(
                    (
                        normalized_id,
                        json.dumps(value, ensure_ascii=False),
                    )
                )

            with sqlite3.connect(self.db_path) as db:
                db.execute("DELETE FROM charge_metadata")
                if rows:
                    db.executemany(
                        """
                        INSERT INTO charge_metadata (charge_id, data)
                        VALUES (?, ?)
                        """,
                        rows,
                    )
                db.commit()

        try:
            await self.hass.async_add_executor_job(
                functools.partial(_write)
            )
            _LOGGER.debug(
                "Charge metadata saved to SQLite: %d",
                len(items),
            )
            return True
        except Exception:
            _LOGGER.exception(
                "Unable to save charge metadata to SQLite"
            )
            return False

    async def save_metadata(self, data: dict[str, Any]) -> bool:
        """Mirror complete metadata.json into SQLite."""
        def _write() -> None:
            payload = json.dumps(data, ensure_ascii=False)
            with sqlite3.connect(self.db_path) as db:
                db.execute(
                    "INSERT OR REPLACE INTO metadata (id, data) VALUES (1, ?)",
                    (payload,),
                )
                db.commit()
        try:
            await self.hass.async_add_executor_job(functools.partial(_write))
            _LOGGER.debug("Metadata mirrored to SQLite")
            return True
        except Exception:
            _LOGGER.exception("Unable to mirror metadata to SQLite")
            return False


    async def load_metadata(self) -> dict[str, Any] | None:
        """Load complete metadata from SQLite."""

        self._log_read("metadata")

        def _read() -> dict[str, Any] | None:
            with sqlite3.connect(self.db_path) as db:
                row = db.execute(
                    "SELECT data FROM metadata WHERE id = 1"
                ).fetchone()

            if row is None:
                return None

            data = json.loads(row[0])
            return data if isinstance(data, dict) else None

        try:
            data = await self.hass.async_add_executor_job(
                functools.partial(_read)
            )
            _LOGGER.debug(
                "SQLite metadata loaded: %s",
                "present" if data is not None else "empty",
            )
            return data
        except Exception:
            _LOGGER.exception("Unable to read metadata from SQLite")
            return None
