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
        """Return the charge unchanged.

        Phase 1 only establishes the resolver interface and coordinator
        integration. Data-source priority and enrichment are implemented in
        the following phases.
        """
        _LOGGER.debug(
            "Charging location resolver called for charge %s",
            charge.charge_id,
        )
        return charge
