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
