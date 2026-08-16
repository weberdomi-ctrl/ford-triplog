"""
Ford Triplog

Track your Ford.

Charging-session management and manual cost handling.

Version: 2.0.2
Release: 2.0.2 - Charge data update notifications
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .charge import Charge
from .const import SIGNAL_CHARGE_DATA_UPDATED
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

        if self.storage.read_backend == "sqlite":
            data_list = await self.storage.database.load_all_charges()
            if newest_first:
                data_list = list(reversed(data_list))

            charges: list[Charge] = []
            for data in data_list:
                try:
                    charges.append(Charge.from_dict(data))
                except Exception:
                    _LOGGER.exception(
                        "Unable to parse SQLite charging session %s",
                        data.get("charge_id", "unknown"),
                    )

            _LOGGER.debug(
                "SQLite charging sessions loaded: %d",
                len(charges),
            )
            return charges

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

        if self.storage.read_backend == "sqlite":
            data = await self.storage.database.load_charge(normalized_id)
            if data is None:
                return None

            try:
                return Charge.from_dict(data)
            except Exception:
                _LOGGER.exception(
                    "Unable to parse SQLite charging session %s",
                    normalized_id,
                )
                return None

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
        currency: str,
        cost_total: float | None = None,
        energy_billed_kwh: float | None = None,
        energy_cost: float | None = None,
        session_fee: float | None = None,
        time_fee: float | None = None,
        blocking_fee: float | None = None,
        parking_fee: float | None = None,
        other_cost: float | None = None,
        energy_billed_source: str = "manual",
    ) -> ChargeManagerResult:
        """Set and verify detailed manual costs for one charging session."""

        normalized_id = self._normalize_charge_id(charge_id)
        normalized_currency = self._normalize_currency(currency)

        normalized_cost = self._normalize_optional_cost(cost_total)
        normalized_energy_billed = self._normalize_optional_cost(
            energy_billed_kwh
        )
        normalized_energy_cost = self._normalize_optional_cost(
            energy_cost
        )
        normalized_session_fee = self._normalize_optional_cost(
            session_fee
        )
        normalized_time_fee = self._normalize_optional_cost(
            time_fee
        )
        normalized_blocking_fee = self._normalize_optional_cost(
            blocking_fee
        )
        normalized_parking_fee = self._normalize_optional_cost(
            parking_fee
        )
        normalized_other_cost = self._normalize_optional_cost(
            other_cost
        )

        charge = await self.async_get_charge(normalized_id)

        if charge is None:
            return ChargeManagerResult(
                action="set_cost",
                charge_id=normalized_id,
                reason="charge_not_found",
            )

        charge.energy_billed_kwh = normalized_energy_billed
        charge.energy_billed_source = str(
            energy_billed_source or "manual"
        ).strip().lower()

        charge.energy_cost = normalized_energy_cost
        charge.session_fee = normalized_session_fee
        charge.time_fee = normalized_time_fee
        charge.blocking_fee = normalized_blocking_fee
        charge.parking_fee = normalized_parking_fee
        charge.other_cost = normalized_other_cost

        # Legacy/simple input remains supported when no detailed cost
        # components are provided.
        detailed_components = (
            normalized_energy_cost,
            normalized_session_fee,
            normalized_time_fee,
            normalized_blocking_fee,
            normalized_parking_fee,
            normalized_other_cost,
        )
        charge.cost_total = (
            normalized_cost
            if not any(value is not None for value in detailed_components)
            else None
        )

        charge.currency = normalized_currency
        charge.cost_source = "manual"
        charge.cost_verified = True
        # Keep an existing receipt filename when manually updating costs.
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
            charge.cost_total or 0.0,
            normalized_currency,
            charge.effective_price_per_kwh,
        )

        async_dispatcher_send(self.hass, SIGNAL_CHARGE_DATA_UPDATED)

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

        charge.energy_billed_kwh = None
        charge.energy_billed_source = "none"
        charge.charging_loss_kwh = None
        charge.charging_loss_percent = None

        charge.energy_cost = None
        charge.session_fee = None
        charge.time_fee = None
        charge.blocking_fee = None
        charge.parking_fee = None
        charge.other_cost = None

        charge.cost_total = None
        charge.currency = None
        charge.energy_price_per_kwh = None
        charge.effective_price_per_kwh = None
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

        async_dispatcher_send(self.hass, SIGNAL_CHARGE_DATA_UPDATED)

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

        if saved:
            async_dispatcher_send(self.hass, SIGNAL_CHARGE_DATA_UPDATED)

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

    @classmethod
    def _normalize_optional_cost(
        cls,
        value: Any,
    ) -> float | None:
        """Return an optional non-negative cost or energy value."""

        if value is None or value == "":
            return None

        return cls._normalize_cost(value)

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
