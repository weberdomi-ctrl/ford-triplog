"""Vehicle-scoped SQLite-backed home charging tariff storage for Ford Triplog."""

from __future__ import annotations

import asyncio
import logging
from datetime import date
from pathlib import Path
from typing import Any, Iterable

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, STORAGE_DIR
from .database import FordTriplogDatabase
from .charging_costs import (
    CONF_HOME_TARIFF_CURRENCY,
    CONF_HOME_TARIFF_PERIODS,
    DEFAULT_HOME_TARIFF_CURRENCY,
)

_LOGGER = logging.getLogger(__name__)
_MIGRATION_ID = "home_charging_tariffs_config_entries_25018"
_MIGRATION_LOCK_KEY = "_home_tariff_migration_lock"


class FordTriplogHomeTariffStorage:
    """Persist vehicle-specific home charging tariffs in the Triplog database."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        storage_directory = Path(hass.config.path(".storage", STORAGE_DIR))
        self.database = FordTriplogDatabase(hass, storage_directory)

    async def async_setup(self) -> None:
        await self.database.async_setup()

    @staticmethod
    def _normalize_period(item: dict[str, Any], *, default_currency: str = "CHF") -> dict[str, Any]:
        """Normalize UI/config or database tariff data to the runtime shape."""

        price = max(0.0, float(item.get("price_per_kwh")))
        currency = str(item.get("currency") or default_currency or "CHF").strip().upper()

        raw_from = str(item.get("valid_from") or "").strip()
        raw_to = str(item.get("valid_to") or "").strip()
        year_value = item.get("year")

        if len(raw_from) == 10 and len(raw_to) == 10:
            start = date.fromisoformat(raw_from)
            end = date.fromisoformat(raw_to)
            if start.year != end.year:
                raise ValueError("A home tariff period must stay within one calendar year")
            year = start.year
        else:
            year = int(year_value)
            start = date.fromisoformat(f"{year:04d}-{raw_from}")
            end = date.fromisoformat(f"{year:04d}-{raw_to}")

        if end < start:
            raise ValueError("Home tariff end is before start")

        return {
            "tariff_id": item.get("tariff_id"),
            "year": year,
            "valid_from": start.strftime("%m-%d"),
            "valid_to": end.strftime("%m-%d"),
            "price_per_kwh": round(price, 6),
            "currency": currency or DEFAULT_HOME_TARIFF_CURRENCY,
        }

    async def async_load(self, vehicle_id: int) -> list[dict[str, Any]]:
        rows = await self.database.load_home_charging_tariffs(vehicle_id)
        periods: list[dict[str, Any]] = []
        for row in rows:
            try:
                periods.append(self._normalize_period(row))
            except (TypeError, ValueError):
                _LOGGER.warning(
                    "Ignoring invalid home charging tariff row: %s",
                    row.get("tariff_id") if isinstance(row, dict) else "unknown",
                )
        periods.sort(key=lambda item: (item["year"], item["valid_from"], item["valid_to"]))
        return periods

    async def async_save(self, periods: list[dict[str, Any]], vehicle_id: int) -> list[dict[str, Any]]:
        normalized = [self._normalize_period(item) for item in periods]
        normalized.sort(key=lambda item: (item["year"], item["valid_from"], item["valid_to"]))

        rows = [
            {
                "tariff_id": item.get("tariff_id"),
                "valid_from": f"{item['year']:04d}-{item['valid_from']}",
                "valid_to": f"{item['year']:04d}-{item['valid_to']}",
                "price_per_kwh": item["price_per_kwh"],
                "currency": item.get("currency") or DEFAULT_HOME_TARIFF_CURRENCY,
            }
            for item in normalized
        ]
        if not await self.database.save_home_charging_tariffs(rows, vehicle_id):
            raise OSError("Unable to save home charging tariffs")
        return await self.async_load(vehicle_id)

    async def async_migrate_config_entries(self, entries: Iterable[ConfigEntry]) -> None:
        """Deprecated: database.async_setup now performs the one-time migration."""
        raise RuntimeError("Use vehicle-specific async_load(vehicle_id) instead")
