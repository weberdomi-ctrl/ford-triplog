"""
Ford Triplog

Track your Ford.

Storage layer for trips, charging, recovery data and cache.

Version: 2.1.0
Build: 16
Changes: Add SQLite statistics read backend
"""

from __future__ import annotations

import json
import logging
import os
import functools
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant

from .const import (
    CONF_STORAGE_READ_BACKEND,
    DEFAULT_STORAGE_READ_BACKEND,
    DOMAIN,
    STORAGE_READ_BACKEND_SQLITE,
    VERSION,
)
from .database import FordTriplogDatabase

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
        self.charges_path = self.base_path / "charges"
        self.cache_path = self.base_path / "cache"

        self.database = FordTriplogDatabase(
            hass,
            self.base_path,
        )

        # Phase 2: selectable read backend.
        # JSON remains the safe default. The active config entry is read
        # here so existing callers do not need to change their constructor.
        self.read_backend = DEFAULT_STORAGE_READ_BACKEND
        entries = hass.config_entries.async_entries(DOMAIN)
        if len(entries) == 1:
            self.read_backend = str(
                entries[0].options.get(
                    CONF_STORAGE_READ_BACKEND,
                    DEFAULT_STORAGE_READ_BACKEND,
                )
            )


    async def async_setup(self) -> None:
        """Initialize storage directories."""

        for path in (
            self.recovery_path,
            self.trips_path,
            self.charges_path,
            self.cache_path,
        ):
            path.mkdir(parents=True, exist_ok=True)

        await self.database.async_setup()

        # Phase 1: mirror all existing JSON-backed storage into SQLite
        # after creating the database. JSON remains the production source.
        await self._mirror_existing_storage()

        _LOGGER.info(
            "Ford Triplog read backend: %s",
            self.read_backend,
        )
        _LOGGER.debug("Ford Triplog storage initialized")

    async def _mirror_existing_storage(self) -> None:
        """Mirror existing JSON storage into SQLite on initial setup."""

        mirrored = {
            "trips": 0,
            "charges": 0,
            "current_trip": 0,
            "current_charge": 0,
            "last_trip": 0,
            "last_charge": 0,
            "statistics": 0,
            "diagnostics": 0,
        }

        for path in await self.list_trips():
            # Phase 1 mirror source is always JSON, regardless of the
            # selected Phase 2 read backend.
            data = await self._load_json(path)

            if not isinstance(data, dict):
                _LOGGER.error(
                    "Initial SQLite mirror skipped trip: invalid JSON: %s",
                    path,
                )
                continue

            trip_id = data.get("trip_id")
            if not trip_id:
                _LOGGER.error(
                    "Initial SQLite mirror skipped trip: missing trip_id: %s",
                    path,
                )
                continue

            if await self.database.save_trip(data):
                mirrored["trips"] += 1
            else:
                _LOGGER.error(
                    "Initial SQLite mirror failed for trip %s: %s",
                    trip_id,
                    path,
                )

        for path in await self.list_charges():
            # Phase 1 mirror source is always JSON, regardless of the
            # selected Phase 2 read backend.
            data = await self._load_json(path)

            if not isinstance(data, dict):
                _LOGGER.error(
                    "Initial SQLite mirror skipped charge: invalid JSON: %s",
                    path,
                )
                continue

            charge_id = data.get("charge_id")
            if not charge_id:
                _LOGGER.error(
                    "Initial SQLite mirror skipped charge: missing charge_id: %s",
                    path,
                )
                continue

            if await self.database.save_charge(data):
                mirrored["charges"] += 1
            else:
                _LOGGER.error(
                    "Initial SQLite mirror failed for charge %s: %s",
                    charge_id,
                    path,
                )

        cache_files = (
            (
                self._current_trip_file(),
                self.load_current_trip,
                self.database.save_current_trip,
                "current_trip",
            ),
            (
                self._current_charge_file(),
                self.load_current_charge,
                self.database.save_current_charge,
                "current_charge",
            ),
            (
                self._last_trip_file(),
                self.load_last_trip,
                self.database.save_last_trip,
                "last_trip",
            ),
            (
                self._last_charge_file(),
                self.load_last_charge,
                self.database.save_last_charge,
                "last_charge",
            ),
        )

        for path, loader, saver, key in cache_files:
            if not path.exists():
                continue

            data = await loader()
            if isinstance(data, dict):
                if await saver(self._add_metadata(data)):
                    mirrored[key] += 1

        # Phase 1 mirror source is always JSON, regardless of the
        # selected Phase 2 read backend. Do not read the SQLite copy here.
        statistics = await self._load_json(self._statistics_file())
        if isinstance(statistics, dict):
            if await self.database.save_statistics(
                self._add_metadata(statistics)
            ):
                mirrored["statistics"] += 1

        diagnostics = await self._load_json(self._diagnostics_file())
        if isinstance(diagnostics, dict):
            if await self.database.save_diagnostics(
                self._add_metadata(diagnostics)
            ):
                mirrored["diagnostics"] += 1

        _LOGGER.info(
            "Initial SQLite mirror completed: %s",
            ", ".join(
                f"{key}={value}"
                for key, value in mirrored.items()
            ),
        )

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

        def _write():
            path.parent.mkdir(
                parents=True,
                exist_ok=True,
            )
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=path.parent,
                delete=False,
            ) as file:
                json.dump(
                    self._add_metadata(data),
                    file,
                    indent=2,
                    ensure_ascii=False,
                )

                file.flush()
                os.fsync(file.fileno())

                temp = Path(file.name)

            os.replace(temp, path)

           
        try:
            await self.hass.async_add_executor_job(
                functools.partial(_write)
            )
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

        def _read():
            if not path.exists():
                return None

            with path.open(
                "r",
                encoding="utf-8",
            ) as file:
                return json.load(file)

        try:
            return await self.hass.async_add_executor_job(
                functools.partial(_read)
            )

        except Exception:
            _LOGGER.exception(
                "Unable to load %s",
                path,
            )
            return None

    @staticmethod
    def _archive_id_from_path(path: Path) -> str | None:
        """Derive the timestamp-based archive ID from a JSON filename."""

        stem = path.stem
        if len(stem) < 19:
            return None

        timestamp = stem[:19]
        if (
            timestamp[4] != "-"
            or timestamp[7] != "-"
            or timestamp[10] != "_"
            or timestamp[13] != "-"
            or timestamp[16] != "-"
        ):
            return None

        return (
            timestamp[0:4]
            + timestamp[5:7]
            + timestamp[8:10]
            + "T"
            + timestamp[11:13]
            + timestamp[14:16]
            + timestamp[17:19]
        )

    async def load_trip_file(
        self,
        path: Path,
    ) -> dict[str, Any] | None:
        """Load archived trip from the selected read backend."""

        if self.read_backend != STORAGE_READ_BACKEND_SQLITE:
            return await self._load_json(path)

        trip_id = self._archive_id_from_path(path)
        if not trip_id:
            _LOGGER.error(
                "SQLite trip read skipped: unable to derive trip_id from %s",
                path,
            )
            return None

        data = await self.database.load_trip(trip_id)
        if data is None:
            _LOGGER.error(
                "SQLite trip read failed: trip_id=%s path=%s",
                trip_id,
                path,
            )
            return None

        return data
    
    async def load_charge_file(
        self,
        path: Path,
    ) -> dict[str, Any] | None:
        """Load archived charge from the selected read backend."""

        if self.read_backend != STORAGE_READ_BACKEND_SQLITE:
            return await self._load_json(path)

        charge_id = self._archive_id_from_path(path)
        if not charge_id:
            _LOGGER.error(
                "SQLite charge read skipped: unable to derive charge_id from %s",
                path,
            )
            return None

        data = await self.database.load_charge(charge_id)
        if data is None:
            _LOGGER.error(
                "SQLite charge read failed: charge_id=%s path=%s",
                charge_id,
                path,
            )
            return None

        return data


    async def _delete_file(
        self,
        path: Path,
    ) -> None:
        """Delete file without blocking the event loop."""

        def _delete() -> None:
            # Idempotent deletion: another task may already have removed
            # the recovery file between scheduling and execution.
            path.unlink(missing_ok=True)

        await self.hass.async_add_executor_job(_delete)

    def _current_trip_file(self) -> Path:
        return self.recovery_path / "current_trip.json"
    
    def _current_charge_file(self) -> Path:
        return self.recovery_path / "current_charge.json"

    def _last_trip_file(self) -> Path:
        return self.cache_path / "last_trip.json"
    
    def _last_charge_file(self) -> Path:
        return self.cache_path / "last_charge.json"

    def _statistics_file(self) -> Path:
        return self.cache_path / "statistics.json"

    def _diagnostics_file(self) -> Path:
        return self.cache_path / "diagnostics.json"



    async def save_current_trip(self, data: dict[str, Any]) -> bool:
        json_saved = await self._save_json(
            self._current_trip_file(),
            data,
        )

        if not json_saved:
            return False

        await self.database.save_current_trip(
            self._add_metadata(data)
        )

        return True

    async def load_current_trip(self) -> dict[str, Any] | None:
        return await self._load_json(
            self._current_trip_file()
        )

    async def delete_current_trip(self) -> None:
        await self._delete_file(
            self._current_trip_file()
        )

        await self.database.delete_current_trip()

    async def save_current_charge(
        self,
        data: dict[str, Any],
    ) -> bool:
        json_saved = await self._save_json(
            self._current_charge_file(),
            data,
        )

        if not json_saved:
            return False

        await self.database.save_current_charge(
            self._add_metadata(data)
        )

        return True

    async def load_current_charge(
        self,
    ) -> dict[str, Any] | None:
        return await self._load_json(
            self._current_charge_file()
        )

    async def delete_current_charge(
        self,
    ) -> None:
        await self._delete_file(
            self._current_charge_file()
        )

        await self.database.delete_current_charge()



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

        json_saved = await self._save_json(path, data)

        if not json_saved:
            return False

        await self.database.save_trip(
            self._add_metadata(data)
        )

        return True

    async def save_charge(self, data: dict[str, Any]) -> bool:
        """Archive completed charging session."""

        start = data.get("start_time")

        if not start:
            _LOGGER.error("Charge without start_time")
            return False

        timestamp = datetime.fromisoformat(
            start.replace("Z", "+00:00")
        )

        folder = (
            self.charges_path
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

        json_saved = await self._save_json(path, data)

        if not json_saved:
            return False

        await self.database.save_charge(
            self._add_metadata(data)
        )

        return True


    async def list_trips(self) -> list[Path]:
        """Return archived trips without blocking the event loop."""

        def _list() -> list[Path]:
            if not self.trips_path.exists():
                return []

            return sorted(self.trips_path.rglob("*.json"))

        return await self.hass.async_add_executor_job(_list)
    
    async def list_charges(self) -> list[Path]:
        """Return archived charging sessions without blocking the event loop."""

        def _list() -> list[Path]:
            if not self.charges_path.exists():
                return []

            return sorted(self.charges_path.rglob("*.json"))

        return await self.hass.async_add_executor_job(_list)


    async def find_charge_path(
        self,
        charge_id: str,
    ) -> Path | None:
        """Return the archived file path matching one charge ID."""

        normalized_id = str(charge_id).strip()
        if not normalized_id:
            return None

        for path in reversed(await self.list_charges()):
            charge = await self.load_charge_file(path)

            if (
                isinstance(charge, dict)
                and str(charge.get("charge_id", "")).strip()
                == normalized_id
            ):
                return path

        return None

    async def load_charge_by_id(
        self,
        charge_id: str,
    ) -> tuple[Path, dict[str, Any]] | None:
        """Return path and data for one archived charging session."""

        path = await self.find_charge_path(charge_id)
        if path is None:
            return None

        charge = await self.load_charge_file(path)
        if not isinstance(charge, dict):
            return None

        return path, charge

    async def save_charge_file(
        self,
        path: Path,
        data: dict[str, Any],
    ) -> bool:
        """Overwrite one existing archived charging-session file."""

        resolved_path = path.resolve()
        charges_root = self.charges_path.resolve()

        try:
            resolved_path.relative_to(charges_root)
        except ValueError:
            _LOGGER.error(
                "Refusing to write charge file outside charge storage: %s",
                resolved_path,
            )
            return False

        if resolved_path.suffix.lower() != ".json":
            _LOGGER.error(
                "Refusing to write non-JSON charge file: %s",
                resolved_path,
            )
            return False

        if not resolved_path.exists():
            _LOGGER.error(
                "Archived charge file does not exist: %s",
                resolved_path,
            )
            return False

        return await self._save_json(
            resolved_path,
            data,
        )

    async def update_charge(
        self,
        charge_id: str,
        data: dict[str, Any],
    ) -> bool:
        """Update one existing archived charging session by charge ID."""

        loaded = await self.load_charge_by_id(charge_id)
        if loaded is None:
            _LOGGER.warning(
                "Unable to update missing charging session: %s",
                charge_id,
            )
            return False

        path, existing = loaded
        updated = dict(existing)
        updated.update(data)

        normalized_id = str(charge_id).strip()
        updated["charge_id"] = normalized_id

        saved = await self.save_charge_file(
            path,
            updated,
        )

        if not saved:
            return False

        # Keep the SQLite archive in sync when an existing charge is edited.
        db_saved = await self.database.save_charge(
            self._add_metadata(updated)
        )

        if not db_saved:
            _LOGGER.error(
                "SQLite update failed for charge %s",
                normalized_id,
            )
            return False

        last_charge = await self.load_last_charge()
        if (
            isinstance(last_charge, dict)
            and str(last_charge.get("charge_id", "")).strip()
            == normalized_id
        ):
            await self.save_last_charge(updated)

        return True


    async def save_last_trip(self, data: dict[str, Any]) -> bool:
        json_saved = await self._save_json(
            self._last_trip_file(),
            data,
        )

        if not json_saved:
            return False

        await self.database.save_last_trip(
            self._add_metadata(data)
        )

        return True

    async def load_last_trip(self) -> dict[str, Any] | None:
        return await self._load_json(
            self._last_trip_file()
        )

    async def _load_archived_charge_by_id(
        self,
        charge_id: str | None,
    ) -> dict[str, Any] | None:
        """Return the archived charging session matching ``charge_id``."""

        if not charge_id:
            return None

        for path in reversed(await self.list_charges()):
            charge = await self.load_charge_file(path)

            if charge and charge.get("charge_id") == charge_id:
                return charge

        return None

    async def save_last_charge(
        self,
        data: dict[str, Any],
    ) -> bool:
        """Save the latest charging session cache.

        The completed charging session is archived immediately before this
        method is called. Use that archived record as a defensive source for
        charging-site fields if the cache input unexpectedly contains empty
        values.
        """

        last_charge = dict(data)
        archived_charge = await self._load_archived_charge_by_id(
            last_charge.get("charge_id")
        )

        charging_site_fields = (
            "charging_site_id",
            "charging_site_name",
            "charging_site_brand",
            "charging_site_operator",
            "charging_site_network",
            "charging_site_power_kw",
            "charging_site_capacity",
            "charging_site_connectors",
            "charging_site_quality",
            "charging_site_distance_m",
        )

        recovered_fields: list[str] = []

        if archived_charge:
            for field in charging_site_fields:
                current_value = last_charge.get(field)
                archived_value = archived_charge.get(field)

                if current_value in (None, [], "") and archived_value not in (
                    None,
                    [],
                    "",
                ):
                    last_charge[field] = archived_value
                    recovered_fields.append(field)

        if recovered_fields:
            _LOGGER.warning(
                "Recovered charging-site fields for last_charge %s from "
                "archived charge: %s",
                last_charge.get("charge_id"),
                ", ".join(recovered_fields),
            )

        _LOGGER.debug(
            "Saving last_charge %s with charging site %s",
            last_charge.get("charge_id"),
            (
                last_charge.get("charging_site_name")
                or last_charge.get("charging_site_brand")
                or last_charge.get("charging_site_operator")
                or last_charge.get("charging_site_id")
            ),
        )

        json_saved = await self._save_json(
            self._last_charge_file(),
            last_charge,
        )

        if not json_saved:
            return False

        await self.database.save_last_charge(
            self._add_metadata(last_charge)
        )

        return True

    async def load_last_charge(
        self,
    ) -> dict[str, Any] | None:
        return await self._load_json(
            self._last_charge_file()
        )


    async def save_statistics(self, data: dict[str, Any]) -> bool:
        json_saved = await self._save_json(
            self._statistics_file(),
            data,
        )

        if not json_saved:
            return False

        await self.database.save_statistics(
            self._add_metadata(data)
        )

        return True

    async def load_statistics(self) -> dict[str, Any] | None:
        return await self._load_json(
            self._statistics_file()
        )

    async def save_diagnostics(self, data: dict[str, Any]) -> bool:
        json_saved = await self._save_json(
            self._diagnostics_file(),
            data,
        )

        if not json_saved:
            return False

        await self.database.save_diagnostics(
            self._add_metadata(data)
        )

        return True

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
