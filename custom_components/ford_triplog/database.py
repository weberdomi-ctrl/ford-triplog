"""
Ford Triplog

SQLite storage mirror.

Version: 2.1.0
Build: 16
Changes: Add Top Locations SQL view read support
"""

from __future__ import annotations

import functools
import json
import logging
import sqlite3
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
        """Initialize SQLite database."""

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


                db.commit()

        try:
            await self.hass.async_add_executor_job(
                functools.partial(_setup)
            )

            _LOGGER.info(
                "Ford Triplog SQLite database initialized: %s",
                self.db_path,
            )

        except Exception:
            _LOGGER.exception(
                "Unable to initialize Ford Triplog SQLite database"
            )

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
            return await self.hass.async_add_executor_job(
                functools.partial(_read)
            )
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
        """Load the last completed journey from SQLite."""

        self._log_read("last_journey")

        def _read() -> dict[str, Any] | None:
            with sqlite3.connect(self.db_path) as db:
                row = db.execute(
                    "SELECT data FROM last_journey LIMIT 1"
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
