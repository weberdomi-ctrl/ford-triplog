"""Global SQLite-backed home charging tariff storage for Ford Triplog."""

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
    """Persist global home charging tariffs in the Triplog database."""

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

    async def async_load(self) -> list[dict[str, Any]]:
        rows = await self.database.load_home_charging_tariffs()
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

    async def async_save(self, periods: list[dict[str, Any]]) -> list[dict[str, Any]]:
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
        if not await self.database.save_home_charging_tariffs(rows):
            raise OSError("Unable to save home charging tariffs")
        return await self.async_load()

    async def async_migrate_config_entries(
        self,
        entries: Iterable[ConfigEntry],
    ) -> list[dict[str, Any]]:
        """Import build-25016/25017 ConfigEntry periods once into SQLite."""

        await self.async_setup()

        # Multiple vehicle ConfigEntries are set up concurrently. Serialize the
        # one-time import so Explorer/JAC cannot both pass the migration marker
        # check before either one has written it.
        domain_data = self.hass.data.setdefault(DOMAIN, {})
        migration_lock = domain_data.setdefault(_MIGRATION_LOCK_KEY, asyncio.Lock())
        async with migration_lock:
            if await self.database.is_migration_completed(_MIGRATION_ID):
                return await self.async_load()

            existing = await self.async_load()
            if existing:
                await self.database.mark_migration_completed(_MIGRATION_ID)
                return existing

            candidates: list[dict[str, Any]] = []
            for entry in entries:
                if getattr(entry, "domain", DOMAIN) != DOMAIN:
                    continue
                config = {**entry.data, **entry.options}
                raw_periods = config.get(CONF_HOME_TARIFF_PERIODS)
                if not isinstance(raw_periods, list):
                    continue
                currency = str(
                    config.get(CONF_HOME_TARIFF_CURRENCY, DEFAULT_HOME_TARIFF_CURRENCY)
                    or DEFAULT_HOME_TARIFF_CURRENCY
                ).strip().upper()
                for item in raw_periods:
                    if not isinstance(item, dict):
                        continue
                    try:
                        candidate = self._normalize_period(
                            item,
                            default_currency=currency,
                        )
                    except (TypeError, ValueError):
                        continue
                    candidate["currency"] = currency or DEFAULT_HOME_TARIFF_CURRENCY
                    candidates.append(candidate)

            accepted: list[dict[str, Any]] = []
            for candidate in sorted(
                candidates,
                key=lambda item: (item["year"], item["valid_from"], item["valid_to"]),
            ):
                duplicate = next(
                    (
                        item for item in accepted
                        if item["year"] == candidate["year"]
                        and item["valid_from"] == candidate["valid_from"]
                        and item["valid_to"] == candidate["valid_to"]
                        and item["price_per_kwh"] == candidate["price_per_kwh"]
                        and item["currency"] == candidate["currency"]
                    ),
                    None,
                )
                if duplicate is not None:
                    continue

                overlaps = any(
                    item["year"] == candidate["year"]
                    and candidate["valid_from"] <= item["valid_to"]
                    and candidate["valid_to"] >= item["valid_from"]
                    for item in accepted
                )
                if overlaps:
                    _LOGGER.warning(
                        "Skipped conflicting ConfigEntry home tariff during SQLite migration: %s",
                        candidate,
                    )
                    continue
                accepted.append(candidate)

            if accepted:
                await self.async_save(accepted)
                _LOGGER.info(
                    "Migrated %d ConfigEntry home tariff periods to SQLite",
                    len(accepted),
                )

            await self.database.mark_migration_completed(_MIGRATION_ID)
            return await self.async_load()
