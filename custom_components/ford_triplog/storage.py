"""
Ford Triplog

Track your Ford.

Storage layer for trips, charging, recovery data and cache.

Version: 1.3.4
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

from .const import VERSION

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


    async def async_setup(self) -> None:
        """Initialize storage directories."""

        for path in (
            self.recovery_path,
            self.trips_path,
            self.charges_path,
            self.cache_path,
        ):
            path.mkdir(parents=True, exist_ok=True)

        _LOGGER.debug("Ford Triplog storage initialized")

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

    async def load_trip_file(
        self,
        path: Path,
    ) -> dict[str, Any] | None:
        """Load archived trip file."""

        return await self._load_json(path)
    
    async def load_charge_file(
        self,
        path: Path,
    ) -> dict[str, Any] | None:
        """Load archived charge file."""

        return await self._load_json(path)


    async def _delete_file(
        self,
        path: Path,
    ) -> None:
        """Delete file without blocking the event loop."""

        def _delete() -> None:
            if path.exists():
                path.unlink()

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
        return await self._save_json(
            self._current_trip_file(),
            data,
        )

    async def load_current_trip(self) -> dict[str, Any] | None:
        return await self._load_json(
            self._current_trip_file()
        )

    async def delete_current_trip(self) -> None:
        await self._delete_file(
            self._current_trip_file()
        )

    async def save_current_charge(
        self,
        data: dict[str, Any],
    ) -> bool:
        return await self._save_json(
            self._current_charge_file(),
            data,
        )

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

        return await self._save_json(path, data)

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

        return await self._save_json(path, data)


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


    async def save_last_trip(self, data: dict[str, Any]) -> bool:
        return await self._save_json(
            self._last_trip_file(),
            data,
        )

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

        return await self._save_json(
            self._last_charge_file(),
            last_charge,
        )

    async def load_last_charge(
        self,
    ) -> dict[str, Any] | None:
        return await self._load_json(
            self._last_charge_file()
        )


    async def save_statistics(self, data: dict[str, Any]) -> bool:
        return await self._save_json(
            self._statistics_file(),
            data,
        )

    async def load_statistics(self) -> dict[str, Any] | None:
        return await self._load_json(
            self._statistics_file()
        )

    async def save_diagnostics(self, data: dict[str, Any]) -> bool:
        return await self._save_json(
            self._diagnostics_file(),
            data,
        )

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
