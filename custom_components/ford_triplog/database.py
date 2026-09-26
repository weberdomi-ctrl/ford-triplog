"""
Ford Triplog

SQLite storage backend.

Version: 2.5.0-dev
Build: 25020
Changes: Store global home charging tariff periods in SQLite.
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
    """SQLite storage backend for Ford Triplog."""

    def __init__(
        self,
        hass: HomeAssistant,
        base_path: Path,
        vehicle_id: int = 1,
    ) -> None:
        self.hass = hass
        self.db_path = base_path / "ford_triplog.db"
        normalized_vehicle_id = int(vehicle_id)
        if normalized_vehicle_id < 1:
            raise ValueError("vehicle_id must be >= 1")
        self.vehicle_id = normalized_vehicle_id

    def _log_read(self, resource: str) -> None:
        """Log a SQLite read at DEBUG level for development diagnostics."""
        _LOGGER.debug("SQLite READ: %s", resource)

    async def async_ensure_vehicle(
        self,
        *,
        vin: str | None = None,
        name: str | None = None,
        manufacturer: str | None = None,
        model: str | None = None,
        battery_capacity_kwh: float | None = None,
        preferred_vehicle_id: int | None = None,
        source: str | None = None,
        allow_duplicate_vin: bool = False,
        alias_of_vehicle_id: int | None = None,
    ) -> dict[str, Any]:
        """Create or update one vehicle and return its database record.

        Normally a VIN resolves to one primary vehicle row. For development
        and migration tests the same physical VIN may explicitly be added as a
        separate logical vehicle. Such rows are marked as aliases and keep a
        reference to the primary vehicle.
        """

        await self.async_setup()

        normalized_vin = str(vin).strip().upper() if vin else None
        normalized_name = str(name).strip() if name else None
        normalized_manufacturer = (
            str(manufacturer).strip() if manufacturer else None
        )
        normalized_model = str(model).strip() if model else None
        normalized_source = str(source).strip() if source else None
        normalized_battery = (
            float(battery_capacity_kwh)
            if battery_capacity_kwh is not None
            else None
        )
        preferred_id = (
            int(preferred_vehicle_id)
            if preferred_vehicle_id is not None
            else None
        )
        if preferred_id is not None and preferred_id < 1:
            preferred_id = None

        alias_of_id = (
            int(alias_of_vehicle_id)
            if alias_of_vehicle_id is not None
            else None
        )
        if alias_of_id is not None and alias_of_id < 1:
            alias_of_id = None

        def _ensure() -> dict[str, Any]:
            now = time.strftime("%Y-%m-%dT%H:%M:%S%z")
            with sqlite3.connect(self.db_path) as db:
                db.row_factory = sqlite3.Row
                db.execute("PRAGMA foreign_keys = ON")

                row = None

                # A ConfigEntry that already owns a vehicle_id always keeps it.
                # This is essential for duplicate-VIN test aliases on restart.
                if preferred_id is not None:
                    candidate = db.execute(
                        "SELECT * FROM vehicles WHERE vehicle_id = ?",
                        (preferred_id,),
                    ).fetchone()
                    if candidate is not None:
                        candidate_vin = (
                            str(candidate["vin"]).strip().upper()
                            if candidate["vin"]
                            else None
                        )
                        if (
                            allow_duplicate_vin
                            or normalized_vin is None
                            or candidate_vin is None
                            or candidate_vin == normalized_vin
                        ):
                            row = candidate

                # Normal production behaviour: one primary row per VIN.
                if row is None and normalized_vin and not allow_duplicate_vin:
                    row = db.execute(
                        """
                        SELECT * FROM vehicles
                        WHERE vin = ? AND alias_of_vehicle_id IS NULL
                        ORDER BY vehicle_id
                        LIMIT 1
                        """,
                        (normalized_vin,),
                    ).fetchone()

                resolved_alias_of = alias_of_id
                if row is None and allow_duplicate_vin and normalized_vin:
                    if resolved_alias_of is None:
                        primary = db.execute(
                            """
                            SELECT vehicle_id FROM vehicles
                            WHERE vin = ? AND alias_of_vehicle_id IS NULL
                            ORDER BY vehicle_id
                            LIMIT 1
                            """,
                            (normalized_vin,),
                        ).fetchone()
                        if primary is not None:
                            resolved_alias_of = int(primary["vehicle_id"])

                    # If there is no primary vehicle after all, fall back to a
                    # normal primary row instead of creating an orphan alias.
                    if resolved_alias_of is None:
                        allow_alias = False
                    else:
                        allow_alias = True
                else:
                    allow_alias = bool(allow_duplicate_vin and resolved_alias_of)

                if row is None:
                    if preferred_id is not None:
                        occupied = db.execute(
                            "SELECT 1 FROM vehicles WHERE vehicle_id = ?",
                            (preferred_id,),
                        ).fetchone()
                    else:
                        occupied = True

                    values = (
                        normalized_vin,
                        normalized_name,
                        normalized_manufacturer,
                        normalized_model,
                        normalized_battery,
                        normalized_source,
                        resolved_alias_of if allow_alias else None,
                        1 if allow_alias else 0,
                        now,
                        now,
                    )

                    if preferred_id is not None and not occupied:
                        db.execute(
                            """
                            INSERT INTO vehicles (
                                vehicle_id, vin, name, manufacturer, model,
                                battery_capacity_kwh, source,
                                alias_of_vehicle_id, is_test_alias,
                                created_at, updated_at
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (preferred_id, *values),
                        )
                        vehicle_id = preferred_id
                    else:
                        cursor = db.execute(
                            """
                            INSERT INTO vehicles (
                                vin, name, manufacturer, model,
                                battery_capacity_kwh, source,
                                alias_of_vehicle_id, is_test_alias,
                                created_at, updated_at
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            values,
                        )
                        vehicle_id = int(cursor.lastrowid)
                else:
                    vehicle_id = int(row["vehicle_id"])
                    db.execute(
                        """
                        UPDATE vehicles
                        SET vin = COALESCE(?, vin),
                            name = COALESCE(?, name),
                            manufacturer = COALESCE(?, manufacturer),
                            model = COALESCE(?, model),
                            battery_capacity_kwh = COALESCE(?, battery_capacity_kwh),
                            source = COALESCE(?, source),
                            alias_of_vehicle_id = COALESCE(?, alias_of_vehicle_id),
                            is_test_alias = CASE
                                WHEN ? THEN 1
                                ELSE is_test_alias
                            END,
                            updated_at = ?
                        WHERE vehicle_id = ?
                        """,
                        (
                            normalized_vin,
                            normalized_name,
                            normalized_manufacturer,
                            normalized_model,
                            normalized_battery,
                            normalized_source,
                            resolved_alias_of if allow_duplicate_vin else None,
                            bool(allow_duplicate_vin),
                            now,
                            vehicle_id,
                        ),
                    )

                db.commit()
                result = db.execute(
                    "SELECT * FROM vehicles WHERE vehicle_id = ?",
                    (vehicle_id,),
                ).fetchone()
                if result is None:
                    raise RuntimeError("Vehicle record disappeared after update")
                return dict(result)

        return await self.hass.async_add_executor_job(_ensure)


    async def async_delete_vehicle(
        self,
        vehicle_id: int | None = None,
    ) -> dict[str, Any]:
        """Delete one vehicle and all vehicle-scoped SQLite records.

        This is intended for permanent Home Assistant ConfigEntry removal,
        not for a normal reload/unload. Global master data such as custom
        places, charging sites and parser profiles is intentionally kept.

        If the deleted vehicle is the primary row of duplicate-VIN test
        aliases, the oldest remaining alias is promoted to the new primary
        row and the other aliases are re-parented to it.
        """

        await self.async_setup()
        selected_id = int(vehicle_id or self.vehicle_id)
        if selected_id < 1:
            raise ValueError("vehicle_id must be >= 1")

        def _delete() -> dict[str, Any]:
            deleted_counts: dict[str, int] = {}
            promoted_vehicle_id: int | None = None
            reparented_vehicle_ids: list[int] = []

            with sqlite3.connect(self.db_path) as db:
                db.row_factory = sqlite3.Row
                db.execute("PRAGMA foreign_keys = ON")

                vehicle = db.execute(
                    "SELECT * FROM vehicles WHERE vehicle_id = ?",
                    (selected_id,),
                ).fetchone()
                if vehicle is None:
                    return {
                        "deleted": False,
                        "vehicle_id": selected_id,
                        "deleted_counts": {},
                        "promoted_vehicle_id": None,
                        "reparented_vehicle_ids": [],
                    }

                parent_id = (
                    int(vehicle["alias_of_vehicle_id"])
                    if vehicle["alias_of_vehicle_id"] is not None
                    else None
                )
                children = db.execute(
                    """
                    SELECT vehicle_id
                    FROM vehicles
                    WHERE alias_of_vehicle_id = ?
                    ORDER BY vehicle_id
                    """,
                    (selected_id,),
                ).fetchall()
                child_ids = [int(row["vehicle_id"]) for row in children]

                db.execute("BEGIN IMMEDIATE")
                try:
                    if child_ids:
                        if parent_id is not None:
                            db.execute(
                                """
                                UPDATE vehicles
                                SET alias_of_vehicle_id = ?, updated_at = ?
                                WHERE alias_of_vehicle_id = ?
                                """,
                                (
                                    parent_id,
                                    time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                                    selected_id,
                                ),
                            )
                            reparented_vehicle_ids = list(child_ids)
                        else:
                            # Keep foreign-key validity while removing a
                            # primary row: temporarily let the future primary
                            # reference itself, then point all siblings at it.
                            promoted_vehicle_id = child_ids[0]
                            now = time.strftime("%Y-%m-%dT%H:%M:%S%z")
                            db.execute(
                                """
                                UPDATE vehicles
                                SET alias_of_vehicle_id = ?, updated_at = ?
                                WHERE vehicle_id = ?
                                """,
                                (promoted_vehicle_id, now, promoted_vehicle_id),
                            )
                            if len(child_ids) > 1:
                                placeholders = ",".join("?" for _ in child_ids[1:])
                                db.execute(
                                    f"""
                                    UPDATE vehicles
                                    SET alias_of_vehicle_id = ?, updated_at = ?
                                    WHERE vehicle_id IN ({placeholders})
                                    """,
                                    (promoted_vehicle_id, now, *child_ids[1:]),
                                )
                                reparented_vehicle_ids = list(child_ids[1:])

                    # Delete every vehicle-scoped table generically so future
                    # schema additions cannot leave orphan data behind.
                    table_rows = db.execute(
                        """
                        SELECT name
                        FROM sqlite_master
                        WHERE type = 'table'
                          AND name NOT LIKE 'sqlite_%'
                        """
                    ).fetchall()
                    for table_row in table_rows:
                        table_name = str(table_row["name"])
                        if table_name == "vehicles":
                            continue
                        quoted_table = '"' + table_name.replace('"', '""') + '"'
                        columns = {
                            str(row[1])
                            for row in db.execute(
                                f"PRAGMA table_info({quoted_table})"
                            ).fetchall()
                        }
                        if "vehicle_id" not in columns:
                            continue
                        cursor = db.execute(
                            f"DELETE FROM {quoted_table} WHERE vehicle_id = ?",
                            (selected_id,),
                        )
                        if cursor.rowcount and cursor.rowcount > 0:
                            deleted_counts[table_name] = int(cursor.rowcount)

                    db.execute(
                        "DELETE FROM vehicles WHERE vehicle_id = ?",
                        (selected_id,),
                    )

                    if promoted_vehicle_id is not None:
                        db.execute(
                            """
                            UPDATE vehicles
                            SET alias_of_vehicle_id = NULL,
                                is_test_alias = 0,
                                updated_at = ?
                            WHERE vehicle_id = ?
                            """,
                            (
                                time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                                promoted_vehicle_id,
                            ),
                        )

                    violations = db.execute("PRAGMA foreign_key_check").fetchall()
                    if violations:
                        raise RuntimeError(
                            "Foreign-key violations after deleting Ford Triplog vehicle "
                            f"{selected_id}: {violations!r}"
                        )

                    db.commit()
                except Exception:
                    db.rollback()
                    raise

            return {
                "deleted": True,
                "vehicle_id": selected_id,
                "deleted_counts": deleted_counts,
                "promoted_vehicle_id": promoted_vehicle_id,
                "reparented_vehicle_ids": reparented_vehicle_ids,
            }

        return await self.hass.async_add_executor_job(_delete)


    async def async_list_vehicles(self) -> list[dict[str, Any]]:
        """Return all persistent vehicle registry records ordered by id."""

        await self.async_setup()

        def _read() -> list[dict[str, Any]]:
            with sqlite3.connect(self.db_path) as db:
                db.row_factory = sqlite3.Row
                rows = db.execute(
                    "SELECT * FROM vehicles ORDER BY vehicle_id"
                ).fetchall()
                return [dict(row) for row in rows]

        return await self.hass.async_add_executor_job(_read)


    async def async_get_vehicle(
        self,
        vehicle_id: int | None = None,
    ) -> dict[str, Any] | None:
        """Return one vehicle registry record."""

        await self.async_setup()
        selected_id = int(vehicle_id or self.vehicle_id)

        def _read() -> dict[str, Any] | None:
            with sqlite3.connect(self.db_path) as db:
                db.row_factory = sqlite3.Row
                row = db.execute(
                    "SELECT * FROM vehicles WHERE vehicle_id = ?",
                    (selected_id,),
                ).fetchone()
                return dict(row) if row is not None else None

        return await self.hass.async_add_executor_job(_read)

    async def validate_json_identity(
        self,
        json_records: dict[str, dict[str, Any] | None],
        json_collections: dict[str, dict[str, dict[str, Any]]],
    ) -> dict[str, Any]:
        """Compare JSON storage records with their SQLite storage.

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
                            "SELECT data FROM current_trip WHERE vehicle_id = ? LIMIT 1",
                            (self.vehicle_id,),
                        ).fetchone()
                    elif name == "current_charge":
                        row = db.execute(
                            "SELECT data FROM current_charge WHERE vehicle_id = ? LIMIT 1",
                            (self.vehicle_id,),
                        ).fetchone()
                    elif name == "last_trip":
                        row = db.execute(
                            "SELECT data FROM last_trip WHERE vehicle_id = ? LIMIT 1",
                            (self.vehicle_id,),
                        ).fetchone()
                    elif name == "last_charge":
                        row = db.execute(
                            "SELECT data FROM last_charge WHERE vehicle_id = ? LIMIT 1",
                            (self.vehicle_id,),
                        ).fetchone()
                    elif name == "statistics":
                        row = db.execute(
                            "SELECT data FROM statistics WHERE vehicle_id = ? AND id = 1",
                            (self.vehicle_id,),
                        ).fetchone()
                    elif name == "diagnostics":
                        row = db.execute(
                            "SELECT data FROM diagnostics WHERE vehicle_id = ? AND id = 1",
                            (self.vehicle_id,),
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
                        f"FROM {table} WHERE vehicle_id = ?",
                        (self.vehicle_id,),
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
                    db.row_factory = sqlite3.Row

                    # Build 25007 extends the vehicle registry so the same
                    # physical VIN can explicitly be used as a second logical
                    # test vehicle. Normal rows remain unique per VIN through
                    # a partial unique index; only marked aliases may duplicate
                    # an existing VIN.
                    vehicle_info = db.execute(
                        "PRAGMA table_info(vehicles)"
                    ).fetchall()
                    vehicle_columns = {str(row[1]) for row in vehicle_info}
                    vehicle_registry_upgrade = bool(vehicle_info) and not {
                        "source",
                        "alias_of_vehicle_id",
                        "is_test_alias",
                    }.issubset(vehicle_columns)

                    if vehicle_registry_upgrade:
                        backup_path = self.db_path.with_name(
                            "ford_triplog_pre_25007.db"
                        )
                        if not backup_path.exists():
                            with sqlite3.connect(backup_path) as backup_db:
                                db.backup(backup_db)
                            _LOGGER.info(
                                "Created SQLite pre-25007 vehicle-registry backup: %s",
                                backup_path,
                            )

                        db.execute("PRAGMA foreign_keys = OFF")
                        try:
                            db.execute("BEGIN IMMEDIATE")
                            db.execute("DROP TABLE IF EXISTS vehicles_25007_new")
                            db.execute(
                                """
                                CREATE TABLE vehicles_25007_new (
                                    vehicle_id INTEGER PRIMARY KEY AUTOINCREMENT,
                                    vin TEXT,
                                    name TEXT,
                                    manufacturer TEXT,
                                    model TEXT,
                                    battery_capacity_kwh REAL,
                                    source TEXT,
                                    alias_of_vehicle_id INTEGER,
                                    is_test_alias INTEGER NOT NULL DEFAULT 0,
                                    created_at TEXT NOT NULL,
                                    updated_at TEXT NOT NULL,
                                    FOREIGN KEY (alias_of_vehicle_id)
                                        REFERENCES vehicles(vehicle_id)
                                )
                                """
                            )
                            db.execute(
                                """
                                INSERT INTO vehicles_25007_new (
                                    vehicle_id, vin, name, manufacturer, model,
                                    battery_capacity_kwh, source,
                                    alias_of_vehicle_id, is_test_alias,
                                    created_at, updated_at
                                )
                                SELECT
                                    vehicle_id, vin, name, manufacturer, model,
                                    battery_capacity_kwh, NULL, NULL, 0,
                                    created_at, updated_at
                                FROM vehicles
                                """
                            )
                            db.execute("DROP TABLE vehicles")
                            db.execute(
                                "ALTER TABLE vehicles_25007_new RENAME TO vehicles"
                            )
                            db.commit()
                            _LOGGER.info(
                                "Migrated SQLite vehicle registry for duplicate-VIN test aliases"
                            )
                        except Exception:
                            db.rollback()
                            raise

                    db.execute(
                        """
                        CREATE TABLE IF NOT EXISTS vehicles (
                            vehicle_id INTEGER PRIMARY KEY AUTOINCREMENT,
                            vin TEXT,
                            name TEXT,
                            manufacturer TEXT,
                            model TEXT,
                            battery_capacity_kwh REAL,
                            source TEXT,
                            alias_of_vehicle_id INTEGER,
                            is_test_alias INTEGER NOT NULL DEFAULT 0,
                            created_at TEXT NOT NULL,
                            updated_at TEXT NOT NULL,
                            FOREIGN KEY (alias_of_vehicle_id)
                                REFERENCES vehicles(vehicle_id)
                        )
                        """
                    )
                    db.execute(
                        """
                        CREATE UNIQUE INDEX IF NOT EXISTS idx_vehicles_primary_vin
                        ON vehicles (vin)
                        WHERE vin IS NOT NULL AND alias_of_vehicle_id IS NULL
                        """
                    )
                    db.execute(
                        """
                        CREATE INDEX IF NOT EXISTS idx_vehicles_alias_of
                        ON vehicles (alias_of_vehicle_id)
                        """
                    )
                    db.execute(
                        """
                        CREATE UNIQUE INDEX IF NOT EXISTS idx_vehicles_alias_source
                        ON vehicles (vin, source)
                        WHERE vin IS NOT NULL
                          AND source IS NOT NULL
                          AND alias_of_vehicle_id IS NOT NULL
                        """
                    )
                    db.execute("PRAGMA foreign_keys = ON")
                    now = time.strftime("%Y-%m-%dT%H:%M:%S%z")
                    db.execute(
                        """
                        INSERT OR IGNORE INTO vehicles (
                            vehicle_id, name, created_at, updated_at
                        )
                        VALUES (1, ?, ?, ?)
                        """,
                        ("Vehicle 1", now, now),
                    )

                    db.execute(
                        """
                        CREATE TABLE IF NOT EXISTS trips (
                            vehicle_id INTEGER NOT NULL DEFAULT 1,
                            trip_id TEXT NOT NULL,
                            data TEXT NOT NULL,
                            PRIMARY KEY (vehicle_id, trip_id),
                            FOREIGN KEY (vehicle_id) REFERENCES vehicles(vehicle_id)
                        )
                        """
                    )

                    db.execute(
                        """
                        CREATE TABLE IF NOT EXISTS current_trip (
                            vehicle_id INTEGER NOT NULL DEFAULT 1,
                            trip_id TEXT NOT NULL,
                            data TEXT NOT NULL,
                            PRIMARY KEY (vehicle_id, trip_id),
                            FOREIGN KEY (vehicle_id) REFERENCES vehicles(vehicle_id)
                        )
                        """
                    )

                    db.execute(
                        """
                        CREATE TABLE IF NOT EXISTS last_trip (
                            vehicle_id INTEGER NOT NULL DEFAULT 1,
                            trip_id TEXT NOT NULL,
                            data TEXT NOT NULL,
                            PRIMARY KEY (vehicle_id, trip_id),
                            FOREIGN KEY (vehicle_id) REFERENCES vehicles(vehicle_id)
                        )
                        """
                    )

                    db.execute(
                        """
                        CREATE TABLE IF NOT EXISTS current_charge (
                            vehicle_id INTEGER NOT NULL DEFAULT 1,
                            charge_id TEXT NOT NULL,
                            data TEXT NOT NULL,
                            PRIMARY KEY (vehicle_id, charge_id),
                            FOREIGN KEY (vehicle_id) REFERENCES vehicles(vehicle_id)
                        )
                        """
                    )

                    db.execute(
                        """
                        CREATE TABLE IF NOT EXISTS charges (
                            vehicle_id INTEGER NOT NULL DEFAULT 1,
                            charge_id TEXT NOT NULL,
                            data TEXT NOT NULL,
                            PRIMARY KEY (vehicle_id, charge_id),
                            FOREIGN KEY (vehicle_id) REFERENCES vehicles(vehicle_id)
                        )
                        """
                    )

                    db.execute(
                        """
                        CREATE TABLE IF NOT EXISTS last_charge (
                            vehicle_id INTEGER NOT NULL DEFAULT 1,
                            charge_id TEXT NOT NULL,
                            data TEXT NOT NULL,
                            PRIMARY KEY (vehicle_id, charge_id),
                            FOREIGN KEY (vehicle_id) REFERENCES vehicles(vehicle_id)
                        )
                        """
                    )

                    db.execute(
                        """
                        CREATE TABLE IF NOT EXISTS statistics (
                            vehicle_id INTEGER NOT NULL DEFAULT 1,
                            id INTEGER NOT NULL CHECK (id = 1),
                            data TEXT NOT NULL,
                            PRIMARY KEY (vehicle_id, id),
                            FOREIGN KEY (vehicle_id) REFERENCES vehicles(vehicle_id)
                        )
                        """
                    )

                    db.execute(
                        """
                        CREATE TABLE IF NOT EXISTS diagnostics (
                            vehicle_id INTEGER NOT NULL DEFAULT 1,
                            id INTEGER NOT NULL CHECK (id = 1),
                            data TEXT NOT NULL,
                            PRIMARY KEY (vehicle_id, id),
                            FOREIGN KEY (vehicle_id) REFERENCES vehicles(vehicle_id)
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
                        CREATE TABLE IF NOT EXISTS user_places (
                            place_id TEXT PRIMARY KEY,
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
                            vehicle_id INTEGER NOT NULL DEFAULT 1,
                            journey_id TEXT NOT NULL,
                            data TEXT NOT NULL,
                            PRIMARY KEY (vehicle_id, journey_id),
                            FOREIGN KEY (vehicle_id) REFERENCES vehicles(vehicle_id)
                        )
                        """
                    )

                    db.execute(
                        """
                        CREATE TABLE IF NOT EXISTS current_journey (
                            vehicle_id INTEGER NOT NULL DEFAULT 1,
                            journey_id TEXT NOT NULL,
                            data TEXT NOT NULL,
                            PRIMARY KEY (vehicle_id, journey_id),
                            FOREIGN KEY (vehicle_id) REFERENCES vehicles(vehicle_id)
                        )
                        """
                    )

                    db.execute(
                        """
                        CREATE TABLE IF NOT EXISTS last_journey (
                            vehicle_id INTEGER NOT NULL DEFAULT 1,
                            journey_id TEXT NOT NULL,
                            data TEXT NOT NULL,
                            PRIMARY KEY (vehicle_id, journey_id),
                            FOREIGN KEY (vehicle_id) REFERENCES vehicles(vehicle_id)
                        )
                        """
                    )

                    db.execute(
                        """
                        CREATE TABLE IF NOT EXISTS metadata (
                            vehicle_id INTEGER NOT NULL DEFAULT 1,
                            id INTEGER NOT NULL CHECK (id = 1),
                            data TEXT NOT NULL,
                            PRIMARY KEY (vehicle_id, id),
                            FOREIGN KEY (vehicle_id) REFERENCES vehicles(vehicle_id)
                        )
                        """
                    )

                    db.execute(
                        """
                        CREATE TABLE IF NOT EXISTS charge_metadata (
                            vehicle_id INTEGER NOT NULL DEFAULT 1,
                            charge_id TEXT NOT NULL,
                            data TEXT NOT NULL,
                            PRIMARY KEY (vehicle_id, charge_id),
                            FOREIGN KEY (vehicle_id) REFERENCES vehicles(vehicle_id)
                        )
                        """
                    )

                    db.execute(
                        """
                        CREATE TABLE IF NOT EXISTS pause_metadata (
                            vehicle_id INTEGER NOT NULL DEFAULT 1,
                            pause_id TEXT NOT NULL,
                            data TEXT NOT NULL,
                            PRIMARY KEY (vehicle_id, pause_id),
                            FOREIGN KEY (vehicle_id) REFERENCES vehicles(vehicle_id)
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
                            vehicle_id INTEGER NOT NULL DEFAULT 1,
                            receipt_id TEXT NOT NULL,
                            target_type TEXT NOT NULL,
                            target_id TEXT NOT NULL,
                            data TEXT NOT NULL,
                            PRIMARY KEY (vehicle_id, receipt_id),
                            FOREIGN KEY (vehicle_id) REFERENCES vehicles(vehicle_id)
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
                            vehicle_id INTEGER NOT NULL DEFAULT 1,
                            trip_id TEXT NOT NULL,
                            data TEXT NOT NULL,
                            PRIMARY KEY (vehicle_id, trip_id),
                            FOREIGN KEY (vehicle_id) REFERENCES vehicles(vehicle_id)
                        )
                        """
                    )
                    db.execute(
                        """
                        CREATE TABLE IF NOT EXISTS migration_state (
                            migration_id TEXT PRIMARY KEY,
                            completed_at TEXT NOT NULL
                        )
                        """
                    )

                    db.execute(
                        """
                        CREATE TABLE IF NOT EXISTS home_charging_tariffs (
                            tariff_id INTEGER PRIMARY KEY AUTOINCREMENT,
                            valid_from TEXT NOT NULL,
                            valid_to TEXT NOT NULL,
                            price_per_kwh REAL NOT NULL CHECK (price_per_kwh >= 0),
                            currency TEXT NOT NULL DEFAULT 'CHF',
                            created_at TEXT NOT NULL,
                            updated_at TEXT NOT NULL,
                            CHECK (valid_to >= valid_from)
                        )
                        """
                    )
                    db.execute(
                        """
                        CREATE UNIQUE INDEX IF NOT EXISTS idx_home_charging_tariffs_range
                        ON home_charging_tariffs (valid_from, valid_to)
                        """
                    )
                    db.execute(
                        """
                        CREATE INDEX IF NOT EXISTS idx_home_charging_tariffs_dates
                        ON home_charging_tariffs (valid_from, valid_to)
                        """
                    )

                    # Existing 2.4 databases have no vehicle_id column and
                    # use the record ID as the sole primary key. Rebuild only
                    # those tables once and assign all legacy rows to vehicle 1.
                    vehicle_table_definitions: dict[
                        str, tuple[str, tuple[str, ...], tuple[str, ...]]
                    ] = {
                        "trips": (
                            """CREATE TABLE {table} (vehicle_id INTEGER NOT NULL DEFAULT 1, trip_id TEXT NOT NULL, data TEXT NOT NULL, PRIMARY KEY (vehicle_id, trip_id), FOREIGN KEY (vehicle_id) REFERENCES vehicles(vehicle_id))""",
                            ("trip_id", "data"),
                            ("vehicle_id", "trip_id"),
                        ),
                        "current_trip": (
                            """CREATE TABLE {table} (vehicle_id INTEGER NOT NULL DEFAULT 1, trip_id TEXT NOT NULL, data TEXT NOT NULL, PRIMARY KEY (vehicle_id, trip_id), FOREIGN KEY (vehicle_id) REFERENCES vehicles(vehicle_id))""",
                            ("trip_id", "data"),
                            ("vehicle_id", "trip_id"),
                        ),
                        "last_trip": (
                            """CREATE TABLE {table} (vehicle_id INTEGER NOT NULL DEFAULT 1, trip_id TEXT NOT NULL, data TEXT NOT NULL, PRIMARY KEY (vehicle_id, trip_id), FOREIGN KEY (vehicle_id) REFERENCES vehicles(vehicle_id))""",
                            ("trip_id", "data"),
                            ("vehicle_id", "trip_id"),
                        ),
                        "current_charge": (
                            """CREATE TABLE {table} (vehicle_id INTEGER NOT NULL DEFAULT 1, charge_id TEXT NOT NULL, data TEXT NOT NULL, PRIMARY KEY (vehicle_id, charge_id), FOREIGN KEY (vehicle_id) REFERENCES vehicles(vehicle_id))""",
                            ("charge_id", "data"),
                            ("vehicle_id", "charge_id"),
                        ),
                        "charges": (
                            """CREATE TABLE {table} (vehicle_id INTEGER NOT NULL DEFAULT 1, charge_id TEXT NOT NULL, data TEXT NOT NULL, PRIMARY KEY (vehicle_id, charge_id), FOREIGN KEY (vehicle_id) REFERENCES vehicles(vehicle_id))""",
                            ("charge_id", "data"),
                            ("vehicle_id", "charge_id"),
                        ),
                        "last_charge": (
                            """CREATE TABLE {table} (vehicle_id INTEGER NOT NULL DEFAULT 1, charge_id TEXT NOT NULL, data TEXT NOT NULL, PRIMARY KEY (vehicle_id, charge_id), FOREIGN KEY (vehicle_id) REFERENCES vehicles(vehicle_id))""",
                            ("charge_id", "data"),
                            ("vehicle_id", "charge_id"),
                        ),
                        "statistics": (
                            """CREATE TABLE {table} (vehicle_id INTEGER NOT NULL DEFAULT 1, id INTEGER NOT NULL CHECK (id = 1), data TEXT NOT NULL, PRIMARY KEY (vehicle_id, id), FOREIGN KEY (vehicle_id) REFERENCES vehicles(vehicle_id))""",
                            ("id", "data"),
                            ("vehicle_id", "id"),
                        ),
                        "diagnostics": (
                            """CREATE TABLE {table} (vehicle_id INTEGER NOT NULL DEFAULT 1, id INTEGER NOT NULL CHECK (id = 1), data TEXT NOT NULL, PRIMARY KEY (vehicle_id, id), FOREIGN KEY (vehicle_id) REFERENCES vehicles(vehicle_id))""",
                            ("id", "data"),
                            ("vehicle_id", "id"),
                        ),
                        "journeys": (
                            """CREATE TABLE {table} (vehicle_id INTEGER NOT NULL DEFAULT 1, journey_id TEXT NOT NULL, data TEXT NOT NULL, PRIMARY KEY (vehicle_id, journey_id), FOREIGN KEY (vehicle_id) REFERENCES vehicles(vehicle_id))""",
                            ("journey_id", "data"),
                            ("vehicle_id", "journey_id"),
                        ),
                        "current_journey": (
                            """CREATE TABLE {table} (vehicle_id INTEGER NOT NULL DEFAULT 1, journey_id TEXT NOT NULL, data TEXT NOT NULL, PRIMARY KEY (vehicle_id, journey_id), FOREIGN KEY (vehicle_id) REFERENCES vehicles(vehicle_id))""",
                            ("journey_id", "data"),
                            ("vehicle_id", "journey_id"),
                        ),
                        "last_journey": (
                            """CREATE TABLE {table} (vehicle_id INTEGER NOT NULL DEFAULT 1, journey_id TEXT NOT NULL, data TEXT NOT NULL, PRIMARY KEY (vehicle_id, journey_id), FOREIGN KEY (vehicle_id) REFERENCES vehicles(vehicle_id))""",
                            ("journey_id", "data"),
                            ("vehicle_id", "journey_id"),
                        ),
                        "metadata": (
                            """CREATE TABLE {table} (vehicle_id INTEGER NOT NULL DEFAULT 1, id INTEGER NOT NULL CHECK (id = 1), data TEXT NOT NULL, PRIMARY KEY (vehicle_id, id), FOREIGN KEY (vehicle_id) REFERENCES vehicles(vehicle_id))""",
                            ("id", "data"),
                            ("vehicle_id", "id"),
                        ),
                        "charge_metadata": (
                            """CREATE TABLE {table} (vehicle_id INTEGER NOT NULL DEFAULT 1, charge_id TEXT NOT NULL, data TEXT NOT NULL, PRIMARY KEY (vehicle_id, charge_id), FOREIGN KEY (vehicle_id) REFERENCES vehicles(vehicle_id))""",
                            ("charge_id", "data"),
                            ("vehicle_id", "charge_id"),
                        ),
                        "pause_metadata": (
                            """CREATE TABLE {table} (vehicle_id INTEGER NOT NULL DEFAULT 1, pause_id TEXT NOT NULL, data TEXT NOT NULL, PRIMARY KEY (vehicle_id, pause_id), FOREIGN KEY (vehicle_id) REFERENCES vehicles(vehicle_id))""",
                            ("pause_id", "data"),
                            ("vehicle_id", "pause_id"),
                        ),
                        "receipts": (
                            """CREATE TABLE {table} (vehicle_id INTEGER NOT NULL DEFAULT 1, receipt_id TEXT NOT NULL, target_type TEXT NOT NULL, target_id TEXT NOT NULL, data TEXT NOT NULL, PRIMARY KEY (vehicle_id, receipt_id), FOREIGN KEY (vehicle_id) REFERENCES vehicles(vehicle_id))""",
                            ("receipt_id", "target_type", "target_id", "data"),
                            ("vehicle_id", "receipt_id"),
                        ),
                        "routes": (
                            """CREATE TABLE {table} (vehicle_id INTEGER NOT NULL DEFAULT 1, trip_id TEXT NOT NULL, data TEXT NOT NULL, PRIMARY KEY (vehicle_id, trip_id), FOREIGN KEY (vehicle_id) REFERENCES vehicles(vehicle_id))""",
                            ("trip_id", "data"),
                            ("vehicle_id", "trip_id"),
                        ),
                    }

                    # Commit harmless setup changes before taking a legacy
                    # database backup. The backup is created only when at least
                    # one vehicle-scoped table still uses the pre-2.5 schema.
                    db.commit()
                    migration_required = False
                    for table_name, (
                        _create_sql,
                        _data_columns,
                        expected_pk,
                    ) in vehicle_table_definitions.items():
                        info = db.execute(
                            f"PRAGMA table_info({table_name})"
                        ).fetchall()
                        columns = {str(row[1]) for row in info}
                        pk_columns = [
                            str(row[1])
                            for row in sorted(
                                info,
                                key=lambda item: int(item[5] or 0),
                            )
                            if int(row[5] or 0) > 0
                        ]
                        if (
                            "vehicle_id" not in columns
                            or tuple(pk_columns) != expected_pk
                        ):
                            migration_required = True
                            break

                    if migration_required:
                        backup_path = self.db_path.with_name(
                            "ford_triplog_pre_25002.db"
                        )
                        if not backup_path.exists():
                            with sqlite3.connect(backup_path) as backup_db:
                                db.backup(backup_db)
                            _LOGGER.info(
                                "Created SQLite pre-2.5 migration backup: %s",
                                backup_path,
                            )

                    # Make the schema rebuild atomic. In Python sqlite3 legacy
                    # transaction mode, DDL before the first DML statement may
                    # otherwise be committed independently. An explicit BEGIN
                    # guarantees that every rename/create/copy/drop below is
                    # rolled back together if any migration step fails.
                    db.execute("BEGIN IMMEDIATE")

                    # Drop derived views before table renames. SQLite otherwise
                    # may rewrite their SQL to point at the temporary table.
                    for view_name in (
                        "v_top_location_trips",
                        "v_top_route_trips",
                        "v_top_trip_trips",
                        "v_top_journey_journeys",
                        "v_top_charging_charges",
                        "v_top_day_journeys",
                    ):
                        db.execute(f"DROP VIEW IF EXISTS {view_name}")

                    for table_name, (
                        create_sql,
                        data_columns,
                        expected_pk,
                    ) in vehicle_table_definitions.items():
                        info = db.execute(
                            f"PRAGMA table_info({table_name})"
                        ).fetchall()
                        columns = {str(row[1]) for row in info}
                        pk_columns = [
                            str(row[1])
                            for row in sorted(info, key=lambda item: int(item[5] or 0))
                            if int(row[5] or 0) > 0
                        ]
                        schema_ready = (
                            "vehicle_id" in columns
                            and tuple(pk_columns) == expected_pk
                        )
                        if schema_ready:
                            continue

                        legacy_name = f"{table_name}_pre_25002"
                        db.execute(f"DROP TABLE IF EXISTS {legacy_name}")
                        db.execute(
                            f"ALTER TABLE {table_name} RENAME TO {legacy_name}"
                        )
                        db.execute(create_sql.format(table=table_name))
                        column_list = ", ".join(data_columns)
                        db.execute(
                            f"INSERT INTO {table_name} (vehicle_id, {column_list}) "
                            f"SELECT 1, {column_list} FROM {legacy_name}"
                        )
                        db.execute(f"DROP TABLE {legacy_name}")
                        _LOGGER.info(
                            "Migrated SQLite table %s to vehicle-aware schema",
                            table_name,
                        )

                    # Recreate indexes that may have been removed while a table
                    # was rebuilt above.
                    db.execute("DROP INDEX IF EXISTS idx_receipts_target")
                    db.execute(
                        """
                        CREATE INDEX IF NOT EXISTS idx_receipts_target
                        ON receipts (vehicle_id, target_type, target_id)
                        """
                    )

                    for view_name in (
                        "v_top_location_trips",
                        "v_top_route_trips",
                        "v_top_trip_trips",
                        "v_top_journey_journeys",
                        "v_top_charging_charges",
                        "v_top_day_journeys",
                    ):
                        db.execute(f"DROP VIEW IF EXISTS {view_name}")

                    db.execute(
                        """
                        CREATE VIEW IF NOT EXISTS v_top_location_trips AS
                        SELECT
                            vehicle_id,
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
                            vehicle_id,
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
                            vehicle_id,
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
                            vehicle_id,
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
                            vehicle_id,
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
                            vehicle_id,
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

    async def load_home_charging_tariffs(self) -> list[dict[str, Any]]:
        """Load global home charging tariff periods from SQLite."""

        await self.async_setup()
        self._log_read("home_charging_tariffs")

        def _read() -> list[dict[str, Any]]:
            with sqlite3.connect(self.db_path) as db:
                db.row_factory = sqlite3.Row
                rows = db.execute(
                    """
                    SELECT tariff_id, valid_from, valid_to, price_per_kwh,
                           currency, created_at, updated_at
                    FROM home_charging_tariffs
                    ORDER BY valid_from ASC, valid_to ASC, tariff_id ASC
                    """
                ).fetchall()
            return [dict(row) for row in rows]

        try:
            rows = await self.hass.async_add_executor_job(_read)
            _LOGGER.debug(
                "SQLite home charging tariffs loaded: %d",
                len(rows),
            )
            return rows
        except Exception:
            _LOGGER.exception(
                "Unable to read home charging tariffs from SQLite"
            )
            return []

    async def save_home_charging_tariffs(
        self,
        tariffs: list[dict[str, Any]],
    ) -> bool:
        """Replace the global home charging tariff table atomically."""

        await self.async_setup()

        normalized: list[tuple[str, str, float, str]] = []
        for item in tariffs or []:
            if not isinstance(item, dict):
                continue
            try:
                valid_from = str(item["valid_from"]).strip()
                valid_to = str(item["valid_to"]).strip()
                price = max(0.0, float(item["price_per_kwh"]))
                currency = str(item.get("currency") or "CHF").strip().upper()
                # Validate ISO calendar dates without changing storage format.
                time.strptime(valid_from, "%Y-%m-%d")
                time.strptime(valid_to, "%Y-%m-%d")
            except (KeyError, TypeError, ValueError):
                raise ValueError("Invalid home charging tariff period")
            if valid_to < valid_from:
                raise ValueError("Home charging tariff end is before start")
            normalized.append((valid_from, valid_to, price, currency or "CHF"))

        normalized.sort(key=lambda item: (item[0], item[1]))
        for index, current in enumerate(normalized):
            for previous in normalized[:index]:
                if current[0] <= previous[1] and current[1] >= previous[0]:
                    raise ValueError("Overlapping home charging tariff periods")

        def _write() -> None:
            now = time.strftime("%Y-%m-%dT%H:%M:%S%z")
            with sqlite3.connect(self.db_path) as db:
                db.execute("BEGIN IMMEDIATE")
                try:
                    db.execute("DELETE FROM home_charging_tariffs")
                    for valid_from, valid_to, price, currency in normalized:
                        db.execute(
                            """
                            INSERT INTO home_charging_tariffs (
                                valid_from, valid_to, price_per_kwh, currency,
                                created_at, updated_at
                            ) VALUES (?, ?, ?, ?, ?, ?)
                            """,
                            (
                                valid_from,
                                valid_to,
                                price,
                                currency,
                                now,
                                now,
                            ),
                        )
                    db.commit()
                except Exception:
                    db.rollback()
                    raise

        try:
            await self.hass.async_add_executor_job(_write)
            _LOGGER.info(
                "SQLite home charging tariffs saved: %d",
                len(normalized),
            )
            return True
        except Exception:
            _LOGGER.exception(
                "Unable to save home charging tariffs to SQLite"
            )
            return False

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
                        f"WHERE vehicle_id = ? AND trip_id IN ({placeholders})",
                        [self.vehicle_id, *normalized_trip_ids],
                    ).fetchall()
                    for trip_id, payload in rows:
                        value = _decode(payload)
                        if value is not None:
                            result["trips"][str(trip_id)] = value

                if normalized_charge_ids:
                    placeholders = ",".join("?" for _ in normalized_charge_ids)
                    rows = db.execute(
                        f"SELECT charge_id, data FROM charges "
                        f"WHERE vehicle_id = ? AND charge_id IN ({placeholders})",
                        [self.vehicle_id, *normalized_charge_ids],
                    ).fetchall()
                    for charge_id, payload in rows:
                        value = _decode(payload)
                        if value is not None:
                            result["charges"][str(charge_id)] = value

                single_queries = {
                    "current_trip": "SELECT data FROM current_trip WHERE vehicle_id = ? LIMIT 1",
                    "current_charge": "SELECT data FROM current_charge WHERE vehicle_id = ? LIMIT 1",
                    "last_trip": "SELECT data FROM last_trip WHERE vehicle_id = ? LIMIT 1",
                    "last_charge": "SELECT data FROM last_charge WHERE vehicle_id = ? LIMIT 1",
                    "statistics": "SELECT data FROM statistics WHERE vehicle_id = ? AND id = 1",
                    "diagnostics": "SELECT data FROM diagnostics WHERE vehicle_id = ? AND id = 1",
                }

                for key, query in single_queries.items():
                    row = db.execute(query, (self.vehicle_id,)).fetchone()
                    result[key] = _decode(row[0]) if row else None

            return result

        try:
            return await self.hass.async_add_executor_job(
                functools.partial(_read)
            )
        except Exception:
            _LOGGER.exception(
                "Unable to read SQLite main storage storage snapshot"
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

    async def is_migration_completed(self, migration_id: str) -> bool:
        """Return whether a persistent migration marker exists."""
        def _read() -> bool:
            with sqlite3.connect(self.db_path) as db:
                row = db.execute(
                    "SELECT 1 FROM migration_state WHERE migration_id = ? LIMIT 1",
                    (str(migration_id),),
                ).fetchone()
                return row is not None
        return await self.hass.async_add_executor_job(_read)

    async def mark_migration_completed(self, migration_id: str) -> bool:
        """Persist a completed migration marker."""
        def _write() -> None:
            with sqlite3.connect(self.db_path) as db:
                db.execute(
                    "INSERT OR REPLACE INTO migration_state "
                    "(migration_id, completed_at) VALUES (?, datetime('now'))",
                    (str(migration_id),),
                )
                db.commit()
        try:
            await self.hass.async_add_executor_job(_write)
            _LOGGER.info("SQLite migration marked complete: %s", migration_id)
            return True
        except Exception:
            _LOGGER.exception("Unable to mark SQLite migration complete: %s", migration_id)
            return False

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
                    INSERT INTO routes (
                        vehicle_id,
                        trip_id,
                        data
                    )
                    VALUES (?, ?, ?)
                    ON CONFLICT(vehicle_id, trip_id) DO UPDATE SET
                        data = excluded.data
                    """,
                    (
                        self.vehicle_id,
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
                "Route saved to SQLite: %s",
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
        """Load route payloads keyed by trip_id for legacy import comparison."""

        self._log_read("route_mirror_index")

        def _read() -> dict[str, dict[str, Any]]:
            with sqlite3.connect(self.db_path) as db:
                rows = db.execute(
                    "SELECT trip_id, data FROM routes WHERE vehicle_id = ?",
                    (self.vehicle_id,),
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
                    f"WHERE vehicle_id = ? AND trip_id IN ({placeholders})",
                    [self.vehicle_id, *normalized_ids],
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
                    "SELECT data FROM routes WHERE vehicle_id = ? AND trip_id = ?",
                    (self.vehicle_id, normalized_id),
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
                    WHERE vehicle_id = ?
                      AND COALESCE(
                        json_extract(data, '$.status'),
                        'completed'
                    ) = 'completed'
                    ORDER BY rowid DESC
                    LIMIT 1
                    """,
                    (self.vehicle_id,),
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
                    WHERE vehicle_id = ?
                    ORDER BY rowid ASC
                    """,
                    (self.vehicle_id,),
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
                        vehicle_id,
                        trip_id,
                        data
                    )
                    VALUES (?, ?, ?)
                    """,
                    (
                        self.vehicle_id,
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
                "Trip saved to SQLite: %s",
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
                    WHERE vehicle_id = ?
                    """,
                    (self.vehicle_id,),
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
                    WHERE vehicle_id = ?
                      AND COALESCE(include_in_statistics, 1) = 1
                    """,
                    (self.vehicle_id,),
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
                    WHERE vehicle_id = ?
                      AND distance_km IS NOT NULL
                    """,
                    (self.vehicle_id,),
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
                    WHERE vehicle_id = ?
                      AND distance_km IS NOT NULL
                    ORDER BY distance_km DESC, journey_id ASC
                    LIMIT 1
                    """,
                    (self.vehicle_id,),
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
                    WHERE vehicle_id = ?
                      AND COALESCE(include_in_statistics, 1) = 1
                      AND distance_km IS NOT NULL
                    ORDER BY distance_km DESC, trip_id ASC
                    LIMIT 1
                    """,
                    (self.vehicle_id,),
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
                    WHERE vehicle_id = ?
                    """,
                    (self.vehicle_id,),
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
                    "SELECT data FROM trips WHERE vehicle_id = ? AND trip_id = ?",
                    (self.vehicle_id, normalized_id),
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
                    WHERE vehicle_id = ?
                    ORDER BY
                        json_extract(data, '$.start_time') ASC,
                        trip_id ASC
                    """,
                    (self.vehicle_id,),
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
                    "SELECT data FROM charges WHERE vehicle_id = ? AND charge_id = ?",
                    (self.vehicle_id, normalized_id),
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
                        vehicle_id,
                        trip_id,
                        data
                    )
                    VALUES (?, ?, ?)
                    """,
                    (
                        self.vehicle_id,
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
                "Current trip saved to SQLite: %s",
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
                    "SELECT data FROM current_trip WHERE vehicle_id = ? LIMIT 1",
                    (self.vehicle_id,),
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
        """Delete current trip storage from SQLite."""

        def _delete() -> None:
            with sqlite3.connect(self.db_path) as db:
                db.execute("DELETE FROM current_trip WHERE vehicle_id = ?", (self.vehicle_id,))
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
                    "SELECT data FROM last_trip WHERE vehicle_id = ? LIMIT 1",
                    (self.vehicle_id,),
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
                db.execute("DELETE FROM last_trip WHERE vehicle_id = ?", (self.vehicle_id,))
                db.execute(
                    """
                    INSERT INTO last_trip (
                        vehicle_id,
                        trip_id,
                        data
                    )
                    VALUES (?, ?, ?)
                    """,
                    (
                        self.vehicle_id,
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
                "Last trip saved to SQLite: %s",
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
                        vehicle_id,
                        charge_id,
                        data
                    )
                    VALUES (?, ?, ?)
                    """,
                    (
                        self.vehicle_id,
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
                "Current charge saved to SQLite: %s",
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
                    "SELECT data FROM current_charge WHERE vehicle_id = ? LIMIT 1",
                    (self.vehicle_id,),
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
        """Delete current charging-session storage from SQLite."""

        def _delete() -> None:
            with sqlite3.connect(self.db_path) as db:
                db.execute("DELETE FROM current_charge WHERE vehicle_id = ?", (self.vehicle_id,))
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
                    "SELECT data FROM last_charge WHERE vehicle_id = ? LIMIT 1",
                    (self.vehicle_id,),
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
                        vehicle_id,
                        charge_id,
                        data
                    )
                    VALUES (?, ?, ?)
                    """,
                    (
                        self.vehicle_id,
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
                "Charge saved to SQLite: %s",
                charge_id,
            )
            return True

        except Exception:
            _LOGGER.exception(
                "Unable to mirror charge to SQLite: %s",
                charge_id,
            )
            return False

    async def delete_charge(
        self,
        charge_id: str,
    ) -> bool:
        """Delete one archived charging session from SQLite."""

        normalized_id = str(charge_id).strip()
        if not normalized_id:
            return False

        def _delete() -> bool:
            with sqlite3.connect(self.db_path) as db:
                cursor = db.execute(
                    "DELETE FROM charges WHERE vehicle_id = ? AND charge_id = ?",
                    (self.vehicle_id, normalized_id),
                )
                db.commit()
                return cursor.rowcount > 0

        try:
            deleted = await self.hass.async_add_executor_job(
                functools.partial(_delete)
            )
            if deleted:
                _LOGGER.info(
                    "Charge removed from SQLite: %s",
                    normalized_id,
                )
            return deleted
        except Exception:
            _LOGGER.exception(
                "Unable to remove charge from SQLite: %s",
                normalized_id,
            )
            return False

    async def delete_last_charge(self) -> bool:
        """Clear the last-charge cache in SQLite."""

        def _delete() -> None:
            with sqlite3.connect(self.db_path) as db:
                db.execute("DELETE FROM last_charge WHERE vehicle_id = ?", (self.vehicle_id,))
                db.commit()

        try:
            await self.hass.async_add_executor_job(
                functools.partial(_delete)
            )
            return True
        except Exception:
            _LOGGER.exception(
                "Unable to clear last charge from SQLite"
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
                db.execute("DELETE FROM last_charge WHERE vehicle_id = ?", (self.vehicle_id,))
                db.execute(
                    """
                    INSERT INTO last_charge (
                        vehicle_id,
                        charge_id,
                        data
                    )
                    VALUES (?, ?, ?)
                    """,
                    (
                        self.vehicle_id,
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
                "Last charge saved to SQLite: %s",
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
                        vehicle_id,
                        id,
                        data
                    )
                    VALUES (?, 1, ?)
                    """,
                    (self.vehicle_id, payload),
                )
                db.commit()

        try:
            await self.hass.async_add_executor_job(
                functools.partial(_write)
            )

            _LOGGER.debug(
                "Statistics saved to SQLite"
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
                    "SELECT data FROM statistics WHERE vehicle_id = ? AND id = 1",
                    (self.vehicle_id,),
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
                        vehicle_id,
                        id,
                        data
                    )
                    VALUES (?, 1, ?)
                    """,
                    (self.vehicle_id, payload),
                )
                db.commit()

        try:
            await self.hass.async_add_executor_job(
                functools.partial(_write)
            )

            _LOGGER.debug(
                "Diagnostics saved to SQLite"
            )
            return True

        except Exception:
            _LOGGER.exception(
                "Unable to mirror diagnostics to SQLite"
            )
            return False

    async def load_diagnostics(self) -> dict[str, Any] | None:
        """Load diagnostics cache from SQLite."""

        self._log_read("diagnostics")

        def _read() -> dict[str, Any] | None:
            with sqlite3.connect(self.db_path) as db:
                row = db.execute(
                    "SELECT data FROM diagnostics WHERE vehicle_id = ? AND id = 1",
                    (self.vehicle_id,),
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
                "Unable to read diagnostics from SQLite"
            )
            return None

    async def load_user_places(self) -> list[dict[str, Any]]:
        """Load all user-defined places from SQLite."""

        self._log_read("user_places")

        def _read() -> list[dict[str, Any]]:
            with sqlite3.connect(self.db_path) as db:
                rows = db.execute(
                    "SELECT data FROM user_places ORDER BY place_id ASC"
                ).fetchall()
            result: list[dict[str, Any]] = []
            for (payload,) in rows:
                try:
                    data = json.loads(payload)
                except (TypeError, json.JSONDecodeError):
                    continue
                if isinstance(data, dict):
                    result.append(data)
            return result

        try:
            result = await self.hass.async_add_executor_job(
                functools.partial(_read)
            )
            _LOGGER.debug("SQLite user places loaded: %d", len(result))
            return result
        except Exception:
            _LOGGER.exception("Unable to read user places from SQLite")
            return []

    async def save_user_places(self, places: list[dict[str, Any]]) -> bool:
        """Replace the complete user-defined place collection in SQLite."""

        def _write() -> None:
            rows: list[tuple[str, str]] = []
            for place in places:
                place_id = place.get("place_id")
                if not place_id:
                    raise ValueError("User place has no place_id")
                rows.append((str(place_id), json.dumps(place, ensure_ascii=False)))
            with sqlite3.connect(self.db_path) as db:
                db.execute("DELETE FROM user_places")
                if rows:
                    db.executemany(
                        "INSERT INTO user_places (place_id, data) VALUES (?, ?)",
                        rows,
                    )
                db.commit()

        try:
            await self.hass.async_add_executor_job(functools.partial(_write))
            _LOGGER.debug("User places saved to SQLite: %d", len(places))
            return True
        except Exception:
            _LOGGER.exception("Unable to save user places to SQLite")
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
                # therefore replace the complete SQLite storage as well.
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
                "User charging sites saved to SQLite: %s",
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
                    INSERT OR REPLACE INTO journeys (vehicle_id, journey_id, data)
                    VALUES (?, ?, ?)
                    """,
                    (self.vehicle_id, str(journey_id), payload),
                )
                db.commit()

        try:
            await self.hass.async_add_executor_job(functools.partial(_write))
            _LOGGER.debug("Journey saved to SQLite: %s", journey_id)
            return True
        except Exception:
            _LOGGER.exception("Unable to mirror journey to SQLite: %s", journey_id)
            return False

    async def load_journey_mirror_index(
        self,
    ) -> dict[str, dict[str, Any]]:
        """Load archived journey payloads keyed by journey_id for legacy import comparison."""

        self._log_read("journey_mirror_index")

        def _read() -> dict[str, dict[str, Any]]:
            with sqlite3.connect(self.db_path) as db:
                rows = db.execute(
                    "SELECT journey_id, data FROM journeys WHERE vehicle_id = ?",
                    (self.vehicle_id,),
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
                    "SELECT data FROM journeys WHERE vehicle_id = ? AND journey_id = ?",
                    (self.vehicle_id, normalized_id),
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
                    WHERE vehicle_id = ?
                    ORDER BY
                        json_extract(data, '$.start_time') ASC,
                        journey_id ASC
                    """,
                    (self.vehicle_id,),
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
                    WHERE vehicle_id = ?
                    ORDER BY
                        json_extract(data, '$.start_time') ASC,
                        charge_id ASC
                    """,
                    (self.vehicle_id,),
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
                    "SELECT data FROM current_journey WHERE vehicle_id = ? LIMIT 1",
                    (self.vehicle_id,),
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
                    "SELECT data FROM last_journey WHERE vehicle_id = ? LIMIT 1",
                    (self.vehicle_id,),
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
                    WHERE vehicle_id = ?
                      AND json_extract(data, '$.end_time') IS NOT NULL
                    ORDER BY json_extract(data, '$.end_time') DESC,
                             journey_id DESC
                    LIMIT 1
                    """,
                    (self.vehicle_id,),
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
                    "DELETE FROM journeys WHERE vehicle_id = ? AND journey_id = ?",
                    (self.vehicle_id, str(journey_id)),
                )
                db.commit()

        try:
            await self.hass.async_add_executor_job(functools.partial(_delete))
            return True
        except Exception:
            _LOGGER.exception("Unable to delete journey from SQLite: %s", journey_id)
            return False

    async def delete_all_journeys(self) -> bool:
        """Delete all archived journey records."""

        def _delete() -> None:
            with sqlite3.connect(self.db_path) as db:
                db.execute("DELETE FROM journeys WHERE vehicle_id = ?", (self.vehicle_id,))
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
                db.execute("DELETE FROM current_journey WHERE vehicle_id = ?", (self.vehicle_id,))
                db.execute(
                    "INSERT INTO current_journey (vehicle_id, journey_id, data) VALUES (?, ?, ?)",
                    (self.vehicle_id, str(journey_id), payload),
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
                db.execute("DELETE FROM current_journey WHERE vehicle_id = ?", (self.vehicle_id,))
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
                db.execute("DELETE FROM last_journey WHERE vehicle_id = ?", (self.vehicle_id,))
                db.execute(
                    "INSERT INTO last_journey (vehicle_id, journey_id, data) VALUES (?, ?, ?)",
                    (self.vehicle_id, str(journey_id), payload),
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
                db.execute("DELETE FROM last_journey WHERE vehicle_id = ?", (self.vehicle_id,))
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
                    WHERE vehicle_id = ?
                    ORDER BY receipt_id ASC
                    """,
                    (self.vehicle_id,),
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
                    WHERE vehicle_id = ? AND receipt_id = ?
                    """,
                    (self.vehicle_id, str(receipt_id)),
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
                        vehicle_id,
                        receipt_id,
                        target_type,
                        target_id,
                        data
                    )
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(vehicle_id, receipt_id) DO UPDATE SET
                        target_type = excluded.target_type,
                        target_id = excluded.target_id,
                        data = excluded.data
                    """,
                    (
                        self.vehicle_id,
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
                    "DELETE FROM receipts WHERE vehicle_id = ? AND receipt_id = ?",
                    (self.vehicle_id, str(receipt_id)),
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
            rows: list[tuple[int, str, str, str, str]] = []

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
                        self.vehicle_id,
                        receipt_id,
                        target_type,
                        target_id,
                        json.dumps(payload, ensure_ascii=False),
                    )
                )

            with sqlite3.connect(self.db_path) as db:
                db.execute("DELETE FROM receipts WHERE vehicle_id = ?", (self.vehicle_id,))
                if rows:
                    db.executemany(
                        """
                        INSERT INTO receipts (
                            vehicle_id,
                            receipt_id,
                            target_type,
                            target_id,
                            data
                        )
                        VALUES (?, ?, ?, ?, ?)
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
                    "SELECT pause_id, data FROM pause_metadata WHERE vehicle_id = ? ORDER BY pause_id ASC",
                    (self.vehicle_id,),
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
                db.execute("DELETE FROM pause_metadata WHERE vehicle_id = ?", (self.vehicle_id,))
                if rows:
                    db.executemany(
                        "INSERT INTO pause_metadata (vehicle_id, pause_id, data) VALUES (?, ?, ?)",
                        [
                            (self.vehicle_id, pause_id, payload)
                            for pause_id, payload in rows
                        ],
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
                    WHERE vehicle_id = ?
                    ORDER BY charge_id ASC
                    """,
                    (self.vehicle_id,),
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
                db.execute("DELETE FROM charge_metadata WHERE vehicle_id = ?", (self.vehicle_id,))
                if rows:
                    db.executemany(
                        """
                        INSERT INTO charge_metadata (vehicle_id, charge_id, data)
                        VALUES (?, ?, ?)
                        """,
                        [
                            (self.vehicle_id, charge_id, payload)
                            for charge_id, payload in rows
                        ],
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
                    "INSERT OR REPLACE INTO metadata (vehicle_id, id, data) VALUES (?, 1, ?)",
                    (self.vehicle_id, payload),
                )
                db.commit()
        try:
            await self.hass.async_add_executor_job(functools.partial(_write))
            _LOGGER.debug("Metadata saved to SQLite")
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
                    "SELECT data FROM metadata WHERE vehicle_id = ? AND id = 1",
                    (self.vehicle_id,),
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
