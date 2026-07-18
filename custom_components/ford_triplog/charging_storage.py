"""Storage handling for charging history."""

from __future__ import annotations

from pathlib import Path

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .charge import Charge
from .const import DOMAIN

CURRENT_CHARGE_FILE = "current_charge.json"
CHARGING_HISTORY_FILE = "charging_history.json"

STORAGE_VERSION = 1


class FordTriplogChargingStorage:
    """Handle charging storage."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize storage."""
        self._hass = hass

        storage_path = Path(hass.config.path(DOMAIN))
        storage_path.mkdir(parents=True, exist_ok=True)

        self._current_charge = Store(
            hass,
            STORAGE_VERSION,
            str(storage_path / CURRENT_CHARGE_FILE),
        )

        self._history = Store(
            hass,
            STORAGE_VERSION,
            str(storage_path / CHARGING_HISTORY_FILE),
        )

    async def async_load_history(self) -> list[Charge]:
        """Load charging history."""

        data = await self._history.async_load()

        if not data:
            return []

        return [
            Charge.from_dict(item)
            for item in data.get("charges", [])
        ]
    
    async def async_save_history(self, charges: list[Charge]) -> None:
        """Save charging history."""

        await self._history.async_save(
            {
                "charges": [
                    charge.to_dict()
                    for charge in charges
                ]
            }
        )

    async def async_load_current_charge(self) -> Charge | None:
        """Load current charging session."""

        data = await self._current_charge.async_load()

        if not data:
            return None

        return Charge.from_dict(data)
    
    async def async_save_current_charge(self, charge: Charge) -> None:
        """Save current charging session."""

        await self._current_charge.async_save(
            charge.to_dict()
        )

    async def async_save_current_charge(self, charge: Charge) -> None:
        """Save current charging session."""

        await self._current_charge.async_save(
            charge.to_dict()
        )
