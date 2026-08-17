"""Central charging-cost calculation for Ford Triplog."""

from __future__ import annotations

import logging
import math
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .charge import Charge
from .const import CONF_JOURNEY_HOME_ZONE

_LOGGER = logging.getLogger(__name__)

CONF_HOME_TARIFF_ENABLED = "home_tariff_enabled"
CONF_HOME_TARIFF_SUMMER_PRICE = "home_tariff_summer_price"
CONF_HOME_TARIFF_WINTER_PRICE = "home_tariff_winter_price"
CONF_HOME_TARIFF_CURRENCY = "home_tariff_currency"

DEFAULT_HOME_ZONE_ENTITY_ID = "zone.home"
DEFAULT_HOME_TARIFF_SUMMER_PRICE = 0.28
DEFAULT_HOME_TARIFF_WINTER_PRICE = 0.38
DEFAULT_HOME_TARIFF_CURRENCY = "CHF"

_PROTECTED_COST_SOURCES = {"manual", "ocr"}


class FordTriplogChargingCostCalculator:
    """Apply automatic charging tariffs without overwriting real costs."""

    def __init__(
        self,
        hass: HomeAssistant,
        config: dict[str, Any],
    ) -> None:
        self.hass = hass

        self.home_tariff_enabled = bool(
            config.get(CONF_HOME_TARIFF_ENABLED, False)
        )
        self.home_zone_entity_id = str(
            config.get(
                CONF_JOURNEY_HOME_ZONE,
                DEFAULT_HOME_ZONE_ENTITY_ID,
            )
            or DEFAULT_HOME_ZONE_ENTITY_ID
        ).strip()
        self.home_tariff_summer_price = max(
            0.0,
            float(
                config.get(
                    CONF_HOME_TARIFF_SUMMER_PRICE,
                    DEFAULT_HOME_TARIFF_SUMMER_PRICE,
                )
            ),
        )
        self.home_tariff_winter_price = max(
            0.0,
            float(
                config.get(
                    CONF_HOME_TARIFF_WINTER_PRICE,
                    DEFAULT_HOME_TARIFF_WINTER_PRICE,
                )
            ),
        )
        self.home_tariff_currency = str(
            config.get(
                CONF_HOME_TARIFF_CURRENCY,
                DEFAULT_HOME_TARIFF_CURRENCY,
            )
            or DEFAULT_HOME_TARIFF_CURRENCY
        ).strip().upper()

    @staticmethod
    def _distance_meters(
        latitude_1: float,
        longitude_1: float,
        latitude_2: float,
        longitude_2: float,
    ) -> float:
        earth_radius_m = 6_371_000

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

    def _is_home_charge(self, charge: Charge) -> bool:
        zone_state = self.hass.states.get(self.home_zone_entity_id)
        if zone_state is None:
            return False

        latitude = (
            charge.start_latitude
            if charge.start_latitude is not None
            else charge.end_latitude
        )
        longitude = (
            charge.start_longitude
            if charge.start_longitude is not None
            else charge.end_longitude
        )

        try:
            zone_latitude = float(zone_state.attributes.get("latitude"))
            zone_longitude = float(zone_state.attributes.get("longitude"))
            zone_radius = max(
                0.0,
                float(zone_state.attributes.get("radius", 100)),
            )
            charge_latitude = float(latitude)
            charge_longitude = float(longitude)
        except (TypeError, ValueError):
            return False

        return (
            self._distance_meters(
                zone_latitude,
                zone_longitude,
                charge_latitude,
                charge_longitude,
            )
            <= zone_radius
        )

    @staticmethod
    def _parse_datetime(value: Any):
        if not value:
            return None

        parsed = dt_util.parse_datetime(str(value))
        if parsed is None:
            return None

        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt_util.UTC)

        return parsed

    @staticmethod
    def _pricing_energy(charge: Charge) -> tuple[float | None, str | None]:
        try:
            billed = float(charge.energy_billed_kwh)
            if billed > 0:
                return billed, "billed"
        except (TypeError, ValueError):
            pass

        try:
            added = float(charge.energy_added_kwh)
            if added > 0:
                return added, "added"
        except (TypeError, ValueError):
            pass

        return None, None

    def recalculate(
        self,
        charge: Charge,
        *,
        allow_automatic_tariff: bool = True,
    ) -> bool:
        """Recalculate one charge and return whether stored values changed."""

        before = charge.to_dict()

        charge.recalculate_costs()

        cost_source = str(
            getattr(charge, "cost_source", "none") or "none"
        ).strip().lower()

        if (
            allow_automatic_tariff
            and cost_source not in _PROTECTED_COST_SOURCES
            and self.home_tariff_enabled
            and self._is_home_charge(charge)
        ):
            start_time = self._parse_datetime(charge.start_time)
            energy, energy_source = self._pricing_energy(charge)

            if start_time is not None and energy is not None:
                local_start = dt_util.as_local(start_time)

                if 4 <= local_start.month <= 9:
                    tariff_name = "summer"
                    tariff_price = self.home_tariff_summer_price
                else:
                    tariff_name = "winter"
                    tariff_price = self.home_tariff_winter_price

                charge.energy_cost = round(energy * tariff_price, 4)
                charge.session_fee = 0.0
                charge.time_fee = 0.0
                charge.blocking_fee = 0.0
                charge.parking_fee = 0.0
                charge.other_cost = 0.0
                charge.currency = self.home_tariff_currency
                charge.cost_source = "home_tariff"
                charge.cost_verified = True

                if (
                    charge.energy_billed_kwh is None
                    and energy_source == "added"
                ):
                    charge.energy_billed_source = "estimated"

                charge.recalculate_costs()

                _LOGGER.debug(
                    "Home tariff recalculated: charge=%s tariff=%s "
                    "energy=%.2f source=%s total=%.2f %s",
                    charge.charge_id,
                    tariff_name,
                    energy,
                    energy_source,
                    charge.cost_total or 0.0,
                    charge.currency,
                )

        after = charge.to_dict()
        return after != before
