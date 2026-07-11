"""
Ford Triplog

Geo helper for reverse geocoding.

Version: 1.0.0
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

_LOGGER = logging.getLogger(__name__)


class FordTriplogGeo:
    """Reverse geocoding helper."""

    def __init__(
        self,
        hass: HomeAssistant,
    ) -> None:
        self.hass = hass
        self.session = async_get_clientsession(hass)

    async def reverse_geocode(
        self,
        latitude: float | None,
        longitude: float | None,
    ) -> dict[str, Any] | None:
        """Convert coordinates into address data."""

        if latitude is None or longitude is None:
            return None

        url = (
            "https://nominatim.openstreetmap.org/reverse"
            f"?format=json"
            f"&lat={latitude}"
            f"&lon={longitude}"
            "&zoom=18"
            "&addressdetails=1"
        )

        try:
            async with self.session.get(
                url,
                headers={
                    "User-Agent": "HomeAssistant Ford Triplog"
                },
            ) as response:

                if response.status != 200:
                    _LOGGER.warning(
                        "Geo lookup failed: %s",
                        response.status,
                    )
                    return None

                data = await response.json()

                address = data.get(
                    "address",
                    {},
                )

                return {
                    "display": data.get(
                        "display_name"
                    ),
                    "road": address.get(
                        "road"
                    ),
                    "house_number": address.get(
                        "house_number"
                    ),
                    "postcode": address.get(
                        "postcode"
                    ),
                    "city": (
                        address.get("city")
                        or address.get("town")
                        or address.get("village")
                    ),
                    "state": address.get(
                        "state"
                    ),
                    "country": address.get(
                        "country"
                    ),
                    "latitude": latitude,
                    "longitude": longitude,
                }

        except Exception:
            _LOGGER.exception(
                "Reverse geocoding failed"
            )

            return None
