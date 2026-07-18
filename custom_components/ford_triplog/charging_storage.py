"""Storage handling for charging history."""

from __future__ import annotations

from pathlib import Path

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import DOMAIN
from .charge import Charge


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