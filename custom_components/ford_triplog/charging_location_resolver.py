"""
Ford Triplog

Charging location resolver.

Version: 1.5.0
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant

from .charge import Charge

_LOGGER = logging.getLogger(__name__)

_INVALID_TEXT_VALUES = {
    "",
    "unknown",
    "unsaved",
    "none",
    "null",
    "n/a",
    "not available",
}


class ChargingLocationResolver:
    """Resolve and enrich charging-location information."""

    def __init__(
        self,
        hass: HomeAssistant,
        config: dict[str, Any],
    ) -> None:
        self.hass = hass
        self.config = config

    async def async_resolve(self, charge: Charge) -> Charge:
        """Resolve charging-location data according to source priority."""
        if self._apply_fordpass_location(charge):
            return charge

        _LOGGER.debug(
            "No usable FordPass charging location for charge %s",
            charge.charge_id,
        )
        return charge

    def _apply_fordpass_location(self, charge: Charge) -> bool:
        """Apply usable location information from FordPass Last Charge."""
        snapshot = charge.fordpass_last_charge
        if not isinstance(snapshot, dict):
            return False

        attributes = snapshot.get("attributes")
        if not isinstance(attributes, dict):
            return False

        location = attributes.get("location")
        if not isinstance(location, dict):
            return False

        name = self._clean_text(location.get("name"))
        network = self._clean_text(location.get("network"))

        # FordPass often returns UNSAVED/UNKNOWN without a real station.
        # At least one meaningful station identifier must be available.
        if name is None and network is None:
            return False

        if name is not None:
            charge.charging_site_name = name

        if network is not None:
            charge.charging_site_network = network
            charge.charging_site_operator = network

        charge.charging_site_quality = "fordpass"
        charge.charging_site_distance_m = 0.0

        _LOGGER.info(
            "Resolved charging location for charge %s from FordPass: "
            "name=%s network=%s",
            charge.charge_id,
            name,
            network,
        )
        return True

    @staticmethod
    def _clean_text(value: Any) -> str | None:
        """Return a normalized meaningful text value."""
        if value is None:
            return None

        text = str(value).strip()
        if text.casefold() in _INVALID_TEXT_VALUES:
            return None

        return text
