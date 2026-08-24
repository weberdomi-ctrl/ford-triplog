"""
Ford Triplog

Track your Ford.

Storage layer for trips, charging, recovery data and cache.

Version: 2.3.0
Build: 23001
Changes: Step 1 - central trip/charge storage runs SQLite-only.
         Existing JSON data is imported during setup for upgrade safety.
         Legacy JSON files are kept untouched and are no longer written.
"""

from __future__ import annotations

import functools
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import SIGNAL_LAST_TRIP_UPDATED, VERSION
from .database import FordTriplogDatabase

_LOGGER = logging.getLogger(__name__)

STORAGE_SCHEMA = 1


class FordTriplogStorage:
    """Persistent SQLite storage manager for Ford Triplog."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self.base_path = Path(hass.config.path(".storage", "ford_triplog"))

        # These directories are retained for legacy import/rollback only.
        # FordTriplogStorage no longer writes runtime JSON data to them.
        self.recovery_path = self.base_path / "recovery"
        self.trips_path = self.base_path / "trips"
        self.charges_path = self.base_path / "charges"
        self.cache_path = self.base_path / "cache"

        self.database = FordTriplogDatabase(hass, self.base_path)

        # Step 1 of the 2.3 storage cleanup: this storage class is always
        # SQLite-backed. Other storage classes are migrated in later steps.
        self.read_backend = "sqlite"

    async def async_setup(self) -> None:
        """Initialize SQLite and import legacy JSON once per HA runtime."""

        # Keep legacy directories available so existing installations can be
        # imported safely. They are no longer used for runtime writes here.
        for path in (
            self.recovery_path,
            self.trips_path,
            self.charges_path,
            self.cache_path,
        ):
            path.mkdir(parents=True, exist_ok=True)

        await self.database.async_setup()

        migration_id = "legacy_central_import_v23"
        if not await self.database.is_migration_completed(migration_id):
            completed = await self._import_legacy_json_storage()
            if completed:
                await self.database.mark_migration_completed(migration_id)
        else:
            _LOGGER.debug("Legacy central-storage JSON import already completed")

        _LOGGER.info("Ford Triplog central storage backend: sqlite")
        _LOGGER.debug("Ford Triplog central storage initialized")

    def _add_metadata(self, data: dict[str, Any]) -> dict[str, Any]:
        """Add storage metadata."""

        result = dict(data)
        result.setdefault("schema", STORAGE_SCHEMA)
        result.setdefault("generator", "Ford Triplog")
        result.setdefault("version", VERSION)
        result.setdefault("created", datetime.utcnow().isoformat() + "Z")
        return result

    async def _load_legacy_json(self, path: Path) -> dict[str, Any] | None:
        """Load one legacy JSON record for upgrade import only."""

        def _read() -> dict[str, Any] | None:
            if not path.exists():
                return None
            with path.open("r", encoding="utf-8") as file:
                value = json.load(file)
            return value if isinstance(value, dict) else None

        try:
            return await self.hass.async_add_executor_job(
                functools.partial(_read)
            )
        except Exception:
            _LOGGER.exception("Unable to load legacy JSON %s", path)
            return None

    async def _list_legacy_json(self, root: Path) -> list[Path]:
        """Return legacy JSON files below one storage directory."""

        def _list() -> list[Path]:
            if not root.exists():
                return []
            return sorted(root.rglob("*.json"))

        return await self.hass.async_add_executor_job(_list)

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

    async def _import_legacy_json_storage(self) -> None:
        """Import only missing legacy JSON records into SQLite.

        SQLite is authoritative once a record exists. Legacy files are left
        untouched for rollback safety, but they never overwrite SQLite.
        """

        imported = {
            "trips": 0,
            "charges": 0,
            "current_trip": 0,
            "current_charge": 0,
            "last_trip": 0,
            "last_charge": 0,
            "statistics": 0,
            "diagnostics": 0,
        }
        unchanged = {key: 0 for key in imported}

        trip_records: list[tuple[str, dict[str, Any]]] = []
        for path in await self._list_legacy_json(self.trips_path):
            data = await self._load_legacy_json(path)
            if not isinstance(data, dict):
                continue
            trip_id = str(data.get("trip_id") or "").strip()
            if not trip_id:
                _LOGGER.warning(
                    "Legacy trip import skipped, missing trip_id: %s", path
                )
                continue
            trip_records.append((trip_id, data))

        charge_records: list[tuple[str, dict[str, Any]]] = []
        for path in await self._list_legacy_json(self.charges_path):
            data = await self._load_legacy_json(path)
            if not isinstance(data, dict):
                continue
            charge_id = str(data.get("charge_id") or "").strip()
            if not charge_id:
                _LOGGER.warning(
                    "Legacy charge import skipped, missing charge_id: %s", path
                )
                continue
            charge_records.append((charge_id, data))

        single_sources: dict[str, dict[str, Any] | None] = {}
        for key, path in (
            ("current_trip", self._current_trip_file()),
            ("current_charge", self._current_charge_file()),
            ("last_trip", self._last_trip_file()),
            ("last_charge", self._last_charge_file()),
            ("statistics", self._statistics_file()),
            ("diagnostics", self._diagnostics_file()),
        ):
            data = await self._load_legacy_json(path)
            single_sources[key] = (
                self._add_metadata(data) if isinstance(data, dict) else None
            )

        snapshot = await self.database.load_storage_mirror_snapshot(
            [trip_id for trip_id, _ in trip_records],
            [charge_id for charge_id, _ in charge_records],
        )

        sqlite_trips = snapshot.get("trips", {})
        for trip_id, data in trip_records:
            if trip_id in sqlite_trips:
                unchanged["trips"] += 1
                continue
            if await self.database.save_trip(data):
                imported["trips"] += 1

        sqlite_charges = snapshot.get("charges", {})
        for charge_id, data in charge_records:
            if charge_id in sqlite_charges:
                unchanged["charges"] += 1
                continue
            if await self.database.save_charge(data):
                imported["charges"] += 1

        single_savers = {
            "current_trip": self.database.save_current_trip,
            "current_charge": self.database.save_current_charge,
            "last_trip": self.database.save_last_trip,
            "last_charge": self.database.save_last_charge,
            "statistics": self.database.save_statistics,
            "diagnostics": self.database.save_diagnostics,
        }

        for key, saver in single_savers.items():
            data = single_sources.get(key)
            if data is None:
                continue
            if snapshot.get(key) is not None:
                unchanged[key] += 1
                continue
            if await saver(data):
                imported[key] += 1

        _LOGGER.info(
            "Legacy central-storage JSON import completed: imported[%s] unchanged[%s]",
            ", ".join(f"{key}={value}" for key, value in imported.items()),
            ", ".join(f"{key}={value}" for key, value in unchanged.items()),
        )
        return True

    @staticmethod
    def _archive_id_from_path(path: Path) -> str | None:
        """Derive the timestamp-based archive ID from a legacy filename."""

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

    async def load_trip_file(self, path: Path) -> dict[str, Any] | None:
        """Load one trip from SQLite using a legacy archive path as ID hint."""

        trip_id = self._archive_id_from_path(path)
        if not trip_id:
            _LOGGER.error("Unable to derive trip_id from legacy path %s", path)
            return None
        return await self.database.load_trip(trip_id)

    async def load_charge_file(self, path: Path) -> dict[str, Any] | None:
        """Load one charge from SQLite using a legacy archive path as ID hint."""

        charge_id = self._archive_id_from_path(path)
        if not charge_id:
            _LOGGER.error("Unable to derive charge_id from legacy path %s", path)
            return None
        return await self.database.load_charge(charge_id)

    async def save_current_trip(self, data: dict[str, Any]) -> bool:
        """Save current trip to SQLite."""
        return await self.database.save_current_trip(self._add_metadata(data))

    async def load_current_trip(self) -> dict[str, Any] | None:
        """Load current trip from SQLite."""
        return await self.database.load_current_trip()

    async def delete_current_trip(self) -> None:
        """Delete current trip from SQLite."""
        await self.database.delete_current_trip()

    async def save_current_charge(self, data: dict[str, Any]) -> bool:
        """Save current charge to SQLite."""
        return await self.database.save_current_charge(self._add_metadata(data))

    async def load_current_charge(self) -> dict[str, Any] | None:
        """Load current charge from SQLite."""
        return await self.database.load_current_charge()

    async def delete_current_charge(self) -> None:
        """Delete current charge from SQLite."""
        await self.database.delete_current_charge()

    async def save_trip(self, data: dict[str, Any]) -> bool:
        """Archive completed trip in SQLite."""

        if not data.get("start_time"):
            _LOGGER.error("Trip without start_time")
            return False

        return await self.database.save_trip(self._add_metadata(data))

    async def save_charge(self, data: dict[str, Any]) -> bool:
        """Archive completed charging session in SQLite."""

        if not data.get("start_time"):
            _LOGGER.error("Charge without start_time")
            return False

        return await self.database.save_charge(self._add_metadata(data))

    async def list_trips(self) -> list[Path]:
        """Return legacy trip paths for compatibility only.

        Runtime collection reads use ``load_archived_trips`` and therefore
        SQLite. This helper remains temporarily for callers that still carry a
        path-based API and will be removed in a later cleanup step.
        """
        return await self._list_legacy_json(self.trips_path)

    async def list_charges(self) -> list[Path]:
        """Return legacy charge paths for compatibility only."""
        return await self._list_legacy_json(self.charges_path)

    async def load_archived_trips(self) -> list[dict[str, Any]]:
        """Load all archived trips from SQLite."""
        return await self.database.load_all_trips()

    async def load_archived_charges(self) -> list[dict[str, Any]]:
        """Load all archived charging sessions from SQLite."""
        return await self.database.load_all_charges()

    async def find_charge_path(self, charge_id: str) -> Path | None:
        """Return a legacy JSON path when one still exists.

        The path is not used as a data source. It exists only for temporary
        compatibility with the old path-based API.
        """

        normalized_id = str(charge_id or "").strip()
        if not normalized_id:
            return None

        if await self.database.load_charge(normalized_id) is None:
            return None

        for path in reversed(await self._list_legacy_json(self.charges_path)):
            data = await self._load_legacy_json(path)
            if (
                isinstance(data, dict)
                and str(data.get("charge_id") or "").strip() == normalized_id
            ):
                return path

        # No legacy file is required in 2.3. Return a stable virtual path for
        # the temporary tuple API used by ChargeManager.
        return self.charges_path / f"{normalized_id}.sqlite"

    async def load_charge_by_id(
        self,
        charge_id: str,
    ) -> tuple[Path, dict[str, Any]] | None:
        """Return compatibility path and SQLite data for one charge."""

        normalized_id = str(charge_id or "").strip()
        if not normalized_id:
            return None

        data = await self.database.load_charge(normalized_id)
        if not isinstance(data, dict):
            return None

        path = await self.find_charge_path(normalized_id)
        if path is None:
            path = self.charges_path / f"{normalized_id}.sqlite"

        return path, data

    async def save_charge_file(self, path: Path, data: dict[str, Any]) -> bool:
        """Compatibility wrapper: update one archived charge in SQLite."""

        charge_id = str(data.get("charge_id") or "").strip()
        if not charge_id:
            charge_id = self._archive_id_from_path(path) or ""

        if not charge_id:
            _LOGGER.error("Unable to determine charge_id for SQLite update")
            return False

        updated = dict(data)
        updated["charge_id"] = charge_id
        return await self.database.save_charge(self._add_metadata(updated))

    async def update_charge(
        self,
        charge_id: str,
        data: dict[str, Any],
    ) -> bool:
        """Update one existing archived charging session in SQLite."""

        normalized_id = str(charge_id or "").strip()
        if not normalized_id:
            return False

        existing = await self.database.load_charge(normalized_id)
        if existing is None:
            _LOGGER.warning(
                "Unable to update missing SQLite charging session: %s",
                normalized_id,
            )
            return False

        updated = dict(existing)
        updated.update(data)
        updated["charge_id"] = normalized_id

        if not await self.database.save_charge(self._add_metadata(updated)):
            _LOGGER.error("SQLite update failed for charge %s", normalized_id)
            return False

        last_charge = await self.database.load_last_charge()
        if (
            isinstance(last_charge, dict)
            and str(last_charge.get("charge_id") or "").strip() == normalized_id
        ):
            await self.database.save_last_charge(self._add_metadata(updated))

        _LOGGER.debug("SQLite charge updated: %s", normalized_id)
        return True

    async def delete_charge(self, charge_id: str) -> bool:
        """Delete one archived charging session from SQLite only."""

        normalized_id = str(charge_id or "").strip()
        if not normalized_id:
            return False

        if await self.database.load_charge(normalized_id) is None:
            _LOGGER.warning(
                "Unable to delete missing charging session: %s",
                normalized_id,
            )
            return False

        if not await self.database.delete_charge(normalized_id):
            _LOGGER.error("SQLite deletion failed for charge %s", normalized_id)
            return False

        _LOGGER.info("Archived charging session deleted: %s", normalized_id)
        return True

    async def clear_last_charge(self) -> None:
        """Clear last-charge cache in SQLite."""
        await self.database.delete_last_charge()

    async def synchronize_last_charge(self) -> dict[str, Any] | None:
        """Rebuild last_charge from the newest remaining SQLite charge."""

        charges = await self.load_archived_charges()
        if not charges:
            await self.clear_last_charge()
            return None

        def _sort_key(item: dict[str, Any]) -> tuple[str, str]:
            return (
                str(item.get("end_time") or item.get("start_time") or ""),
                str(item.get("charge_id") or ""),
            )

        newest = max(charges, key=_sort_key)
        if not await self.save_last_charge(newest):
            _LOGGER.error("Unable to synchronize last_charge after deletion")
            return None

        return newest

    async def save_last_trip(self, data: dict[str, Any]) -> bool:
        """Save latest trip cache to SQLite and notify listeners."""
        payload = self._add_metadata(data)
        saved = await self.database.save_last_trip(payload)
        if saved:
            async_dispatcher_send(
                self.hass,
                SIGNAL_LAST_TRIP_UPDATED,
                str(payload.get("trip_id") or ""),
            )
        return saved

    async def load_last_trip(self) -> dict[str, Any] | None:
        """Load latest trip cache from SQLite."""
        return await self.database.load_last_trip()

    async def _load_archived_charge_by_id(
        self,
        charge_id: str | None,
    ) -> dict[str, Any] | None:
        """Return one archived charging session from SQLite."""

        normalized_id = str(charge_id or "").strip()
        if not normalized_id:
            return None
        return await self.database.load_charge(normalized_id)

    async def save_last_charge(self, data: dict[str, Any]) -> bool:
        """Save the latest charging-session cache to SQLite.

        The completed charging session is already archived. Use that SQLite
        record as a defensive source for charging-site fields if the cache
        input unexpectedly contains empty values.
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
                "Recovered charging-site fields for last_charge %s from archived charge: %s",
                last_charge.get("charge_id"),
                ", ".join(recovered_fields),
            )

        return await self.database.save_last_charge(
            self._add_metadata(last_charge)
        )

    async def load_last_charge(self) -> dict[str, Any] | None:
        """Load latest charging-session cache from SQLite."""
        return await self.database.load_last_charge()

    async def save_statistics(self, data: dict[str, Any]) -> bool:
        """Save statistics to SQLite."""
        return await self.database.save_statistics(self._add_metadata(data))

    async def load_statistics(self) -> dict[str, Any] | None:
        """Load statistics from SQLite."""
        return await self.database.load_statistics()

    async def save_diagnostics(self, data: dict[str, Any]) -> bool:
        """Save diagnostics to SQLite."""
        return await self.database.save_diagnostics(self._add_metadata(data))

    async def load_diagnostics(self) -> dict[str, Any] | None:
        """Load diagnostics from SQLite."""
        return await self.database.load_diagnostics()

    async def validate_storage(self) -> bool:
        """Validate the central SQLite storage."""
        await self.async_setup()
        return self.base_path.exists()

    async def rebuild_cache(self) -> None:
        """Rebuild cache placeholder."""
        _LOGGER.info("Cache rebuild requested")
