"""
Ford Triplog

SQLite storage mirror.

Version: 2.1.0
Build: 01
Changes: Initial SQLite database with trip mirror support
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
