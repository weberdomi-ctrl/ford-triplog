"""
Ford Triplog

Charging location resolver.

Version: 1.5.0
Phase: 3.5
Build: 10

Changes:
- Uses the same stable charging-site fields for user and OSM records.
- Applies power, capacity and connector lists from user locations.
- Keeps resolver priority FordPass, user database, OSM.
"""

from __future__ import annotations

import logging
import math
from typing import Any

from homeassistant.core import HomeAssistant

from .charge import Charge
from .pending_charging_site_storage import PendingChargingSiteStorage
from .user_charging_site_storage import UserChargingSiteStorage

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
        user_storage: UserChargingSiteStorage,
        pending_storage: PendingChargingSiteStorage,
    ) -> None:
        self.hass = hass
        self.config = config
        self.user_storage = user_storage
        self.pending_storage = pending_storage

    async def async_resolve(self, charge: Charge) -> Charge:
        """Resolve charging-location data according to source priority."""
        if self._apply_fordpass_location(charge):
            return charge

        _LOGGER.debug(
            "No usable FordPass charging location for charge %s",
            charge.charge_id,
        )

        if await self._apply_user_location(charge):
            return charge

        # OSM data is already attached by the coordinator at charge start or
        # charge end. Leaving the charge unchanged preserves that fallback.
        if charge.charging_site_id:
            _LOGGER.debug(
                "Keeping existing OSM charging location for charge %s: %s",
                charge.charge_id,
                charge.charging_site_id,
            )
        else:
            _LOGGER.debug(
                "No FordPass, user-defined, or OSM charging location for "
                "charge %s",
                charge.charge_id,
            )
            try:
                await self.pending_storage.async_add_from_charge(charge)
            except (OSError, ValueError) as error:
                _LOGGER.warning(
                    "Could not store unresolved charging location: %s",
                    error,
                )

        return charge

    async def _apply_user_location(self, charge: Charge) -> bool:
        """Apply the nearest matching user-defined charging site."""
        latitude = charge.end_latitude
        longitude = charge.end_longitude

        if latitude is None or longitude is None:
            latitude = charge.start_latitude
            longitude = charge.start_longitude

        if latitude is None or longitude is None:
            return False

        try:
            charge_latitude = float(latitude)
            charge_longitude = float(longitude)
        except (TypeError, ValueError):
            return False

        try:
            sites = await self.user_storage.async_load()
        except (OSError, ValueError) as error:
            _LOGGER.warning(
                "User charging-site database could not be loaded: %s",
                error,
            )
            return False

        best_site: dict[str, Any] | None = None
        best_distance: float | None = None

        for site in sites:
            try:
                distance = self._distance_meters(
                    charge_latitude,
                    charge_longitude,
                    float(site["latitude"]),
                    float(site["longitude"]),
                )
                radius = float(site["radius"])
            except (KeyError, TypeError, ValueError):
                continue

            if distance > radius:
                continue

            if best_distance is None or distance < best_distance:
                best_site = site
                best_distance = distance

        if best_site is None or best_distance is None:
            return False

        charge.charging_site_id = str(best_site["site_id"])
        charge.charging_site_name = best_site.get("name")
        charge.charging_site_brand = best_site.get("brand")
        charge.charging_site_operator = best_site.get("operator")
        charge.charging_site_network = best_site.get("network")

        charge.charging_site_power_kw = [
            float(value)
            for value in (best_site.get("power_kw") or [])
        ]
        charge.charging_site_capacity = [
            float(value)
            for value in (best_site.get("capacity") or [])
        ]
        charge.charging_site_connectors = [
            str(value)
            for value in (best_site.get("connectors") or [])
        ]

        charge.charging_site_quality = (
            best_site.get("quality") or "user"
        )
        charge.charging_site_distance_m = round(best_distance, 1)

        _LOGGER.info(
            "Resolved charging location for charge %s from user database: "
            "name=%s id=%s distance=%.1fm",
            charge.charge_id,
            charge.charging_site_name,
            best_site["site_id"],
            best_distance,
        )
        return True

    @staticmethod
    def _distance_meters(
        latitude_1: float,
        longitude_1: float,
        latitude_2: float,
        longitude_2: float,
    ) -> float:
        """Return the distance between two coordinates in meters."""
        earth_radius_m = 6_371_000.0

        lat_1 = math.radians(latitude_1)
        lat_2 = math.radians(latitude_2)
        delta_lat = math.radians(latitude_2 - latitude_1)
        delta_lon = math.radians(longitude_2 - longitude_1)

        value = (
            math.sin(delta_lat / 2) ** 2
            + math.cos(lat_1)
            * math.cos(lat_2)
            * math.sin(delta_lon / 2) ** 2
        )

        return earth_radius_m * 2 * math.atan2(
            math.sqrt(value),
            math.sqrt(1 - value),
        )

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
