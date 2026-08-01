"""
Ford Triplog

Track your Ford.

Charging-session management and manual cost handling.

Version: 1.8.2
Release: 1.8.2 - Charge Manager
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant

from .charge import Charge
from .storage import FordTriplogStorage

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True, frozen=True)
class ChargeManagerResult:
    """Result of one Charge Manager operation."""

    action: str
    charge_id: str
    charge: Charge | None = None
    updated: bool = False
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize the operation result."""

        return {
            "action": self.action,
            "charge_id": self.charge_id,
            "updated": self.updated,
            "reason": self.reason,
            "charge": (
                self.charge.to_dict()
                if self.charge is not None
                else None
            ),
        }


class FordTriplogChargeManager:
    """Manage stored charging sessions and manual charging costs."""

    def __init__(
        self,
        hass: HomeAssistant,
        storage: FordTriplogStorage,
    ) -> None:
        """Initialize the Charge Manager."""

        self.hass = hass
        self.storage = storage

    async def async_setup(self) -> None:
        """Initialize the storage layer."""

        await self.storage.async_setup()

    async def async_get_charges(
        self,
        *,
        newest_first: bool = True,
    ) -> list[Charge]:
        """Return all archived charging sessions."""

        paths = await self.storage.list_charges()

        if newest_first:
            paths = list(reversed(paths))

        charges: list[Charge] = []

        for path in paths:
            data = await self.storage.load_charge_file(path)

            if not isinstance(data, dict):
                continue

            try:
                charges.append(Charge.from_dict(data))
            except Exception:
                _LOGGER.exception(
                    "Unable to load charging session from %s",
                    path,
                )

        return charges

    async def async_get_charge(
        self,
        charge_id: str,
    ) -> Charge | None:
        """Return one archived charging session by ID."""

        normalized_id = self._normalize_charge_id(charge_id)
        loaded = await self.storage.load_charge_by_id(normalized_id)

        if loaded is None:
            return None

        _path, data = loaded

        try:
            return Charge.from_dict(data)
        except Exception:
            _LOGGER.exception(
                "Unable to parse charging session %s",
                normalized_id,
            )
            return None

    async def async_get_charge_with_path(
        self,
        charge_id: str,
    ) -> tuple[Path, Charge] | None:
        """Return path and Charge object for one archived session."""

        normalized_id = self._normalize_charge_id(charge_id)
        loaded = await self.storage.load_charge_by_id(normalized_id)

        if loaded is None:
            return None

        path, data = loaded

        try:
            charge = Charge.from_dict(data)
        except Exception:
            _LOGGER.exception(
                "Unable to parse charging session %s",
                normalized_id,
            )
            return None

        return path, charge

    async def async_set_cost(
        self,
        charge_id: str,
        *,
        cost_total: float,
        currency: str,
    ) -> ChargeManagerResult:
        """Set and verify manual costs for one charging session."""

        normalized_id = self._normalize_charge_id(charge_id)
        normalized_cost = self._normalize_cost(cost_total)
        normalized_currency = self._normalize_currency(currency)

        charge = await self.async_get_charge(normalized_id)

        if charge is None:
            return ChargeManagerResult(
                action="set_cost",
                charge_id=normalized_id,
                reason="charge_not_found",
            )

        charge.cost_total = normalized_cost
        charge.currency = normalized_currency
        charge.cost_source = "manual"
        charge.cost_verified = True
        charge.receipt_filename = None
        charge.recalculate_costs()

        saved = await self.storage.update_charge(
            normalized_id,
            charge.to_dict(),
        )

        if not saved:
            return ChargeManagerResult(
                action="set_cost",
                charge_id=normalized_id,
                charge=charge,
                reason="save_failed",
            )

        _LOGGER.info(
            "Manual charging costs saved: charge=%s total=%.2f %s "
            "price_per_kwh=%s",
            normalized_id,
            normalized_cost,
            normalized_currency,
            charge.price_per_kwh,
        )

        return ChargeManagerResult(
            action="set_cost",
            charge_id=normalized_id,
            charge=charge,
            updated=True,
        )

    async def async_clear_cost(
        self,
        charge_id: str,
    ) -> ChargeManagerResult:
        """Remove all stored cost information from one charging session."""

        normalized_id = self._normalize_charge_id(charge_id)
        charge = await self.async_get_charge(normalized_id)

        if charge is None:
            return ChargeManagerResult(
                action="clear_cost",
                charge_id=normalized_id,
                reason="charge_not_found",
            )

        charge.cost_total = None
        charge.currency = None
        charge.price_per_kwh = None
        charge.cost_source = "none"
        charge.cost_verified = False
        charge.receipt_filename = None
        charge.recalculate_costs()

        saved = await self.storage.update_charge(
            normalized_id,
            charge.to_dict(),
        )

        if not saved:
            return ChargeManagerResult(
                action="clear_cost",
                charge_id=normalized_id,
                charge=charge,
                reason="save_failed",
            )

        _LOGGER.info(
            "Charging costs cleared: charge=%s",
            normalized_id,
        )

        return ChargeManagerResult(
            action="clear_cost",
            charge_id=normalized_id,
            charge=charge,
            updated=True,
        )

    async def async_update_charge(
        self,
        charge: Charge,
    ) -> ChargeManagerResult:
        """Persist one already modified Charge object."""

        if not isinstance(charge, Charge):
            raise TypeError("charge must be a Charge object")

        normalized_id = self._normalize_charge_id(charge.charge_id)
        charge.charge_id = normalized_id
        charge.recalculate_costs()

        saved = await self.storage.update_charge(
            normalized_id,
            charge.to_dict(),
        )

        return ChargeManagerResult(
            action="update_charge",
            charge_id=normalized_id,
            charge=charge,
            updated=saved,
            reason=None if saved else "save_failed",
        )

    @staticmethod
    def _normalize_charge_id(value: Any) -> str:
        """Return one required non-empty charge ID."""

        normalized = str(value or "").strip()

        if not normalized:
            raise ValueError("charge_id must not be empty")

        return normalized

    @staticmethod
    def _normalize_cost(value: Any) -> float:
        """Return one non-negative total cost."""

        if isinstance(value, bool):
            raise ValueError("cost_total must be a number")

        try:
            normalized = float(value)
        except (TypeError, ValueError) as error:
            raise ValueError(
                "cost_total must be a number"
            ) from error

        if normalized < 0:
            raise ValueError(
                "cost_total must not be negative"
            )

        return round(normalized, 4)

    @staticmethod
    def _normalize_currency(value: Any) -> str:
        """Return a normalized ISO-style currency code."""

        normalized = str(value or "").strip().upper()

        if len(normalized) != 3 or not normalized.isalpha():
            raise ValueError(
                "currency must be a three-letter code such as CHF or EUR"
            )

        return normalized
