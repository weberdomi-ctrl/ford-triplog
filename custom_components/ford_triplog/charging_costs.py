"""Central charging-cost calculation for Ford Triplog."""

from __future__ import annotations

import logging
import math
from datetime import date
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
CONF_HOME_TARIFF_PERIODS = "home_tariff_periods"

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
        self.home_tariff_periods = self._normalize_tariff_periods(
            config.get(CONF_HOME_TARIFF_PERIODS)
        )
        self._legacy_tariff_configured = (
            CONF_HOME_TARIFF_SUMMER_PRICE in config
            or CONF_HOME_TARIFF_WINTER_PRICE in config
        )


    def _normalize_tariff_periods(self, value: Any) -> list[dict[str, Any]]:
        """Return validated year-based home tariff periods."""

        if not isinstance(value, list):
            return []

        normalized: list[dict[str, Any]] = []
        for item in value:
            if not isinstance(item, dict):
                continue

            try:
                year = int(item.get("year"))
                valid_from = str(item.get("valid_from") or "").strip()
                valid_to = str(item.get("valid_to") or "").strip()
                price = max(0.0, float(item.get("price_per_kwh")))
                start = date.fromisoformat(f"{year:04d}-{valid_from}")
                end = date.fromisoformat(f"{year:04d}-{valid_to}")
            except (TypeError, ValueError):
                continue

            if end < start:
                continue

            currency = str(
                item.get("currency") or self.home_tariff_currency
            ).strip().upper()
            normalized.append(
                {
                    "year": year,
                    "valid_from": valid_from,
                    "valid_to": valid_to,
                    "price_per_kwh": price,
                    "currency": currency or self.home_tariff_currency,
                }
            )

        normalized.sort(
            key=lambda item: (
                int(item["year"]),
                str(item["valid_from"]),
                str(item["valid_to"]),
            )
        )
        return normalized

    def _tariff_for_date(
        self,
        local_date: date,
    ) -> tuple[str, float, str] | None:
        """Return the configured home tariff for a local calendar date."""

        if self.home_tariff_periods:
            iso_month_day = local_date.strftime("%m-%d")
            for period in self.home_tariff_periods:
                if int(period["year"]) != local_date.year:
                    continue
                if (
                    str(period["valid_from"])
                    <= iso_month_day
                    <= str(period["valid_to"])
                ):
                    return (
                        f"{period['year']}:"
                        f"{period['valid_from']}-{period['valid_to']}",
                        float(period["price_per_kwh"]),
                        str(period.get("currency") or self.home_tariff_currency),
                    )
            return None

        # Backward compatibility for installations that already stored the
        # former fixed summer/winter tariff options. New configurations use
        # explicit year-based periods instead.
        if self._legacy_tariff_configured:
            if 4 <= local_date.month <= 9:
                return (
                    "legacy_summer",
                    self.home_tariff_summer_price,
                    self.home_tariff_currency,
                )
            return (
                "legacy_winter",
                self.home_tariff_winter_price,
                self.home_tariff_currency,
            )

        return None

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

        # A completed charging session should be classified by the newest
        # known charging position. Start GPS can still be stale from the trip
        # immediately before plugging in.
        latitude = (
            charge.end_latitude
            if charge.end_latitude is not None
            else charge.start_latitude
        )
        longitude = (
            charge.end_longitude
            if charge.end_longitude is not None
            else charge.start_longitude
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

        is_home_charge = self._is_home_charge(charge)

        # Remove an earlier automatic Home tariff when repaired/newer GPS
        # proves that the charging session was not at Home. Never touch manual
        # or OCR costs.
        if cost_source == "home_tariff" and (
            not allow_automatic_tariff
            or not self.home_tariff_enabled
            or not is_home_charge
        ):
            charge.energy_cost = None
            charge.session_fee = None
            charge.time_fee = None
            charge.blocking_fee = None
            charge.parking_fee = None
            charge.other_cost = None
            charge.cost_total = None
            charge.currency = None
            charge.cost_source = "none"
            charge.cost_verified = False
            charge.recalculate_costs()
            cost_source = "none"

        if (
            allow_automatic_tariff
            and cost_source not in _PROTECTED_COST_SOURCES
            and self.home_tariff_enabled
            and is_home_charge
        ):
            start_time = self._parse_datetime(charge.start_time)
            energy, energy_source = self._pricing_energy(charge)

            tariff = None
            if start_time is not None:
                local_start = dt_util.as_local(start_time)
                tariff = self._tariff_for_date(local_start.date())

            if start_time is not None and energy is not None and tariff:
                tariff_name, tariff_price, tariff_currency = tariff

                charge.energy_cost = round(energy * tariff_price, 4)
                charge.session_fee = 0.0
                charge.time_fee = 0.0
                charge.blocking_fee = 0.0
                charge.parking_fee = 0.0
                charge.other_cost = 0.0
                charge.currency = tariff_currency
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
            elif cost_source == "home_tariff" and start_time is not None:
                # A year-based tariff schedule is authoritative. If the
                # charging date is no longer covered, remove the stale
                # automatically calculated cost instead of silently using a
                # tariff from another year or period.
                charge.energy_cost = None
                charge.session_fee = None
                charge.time_fee = None
                charge.blocking_fee = None
                charge.parking_fee = None
                charge.other_cost = None
                charge.cost_total = None
                charge.currency = None
                charge.cost_source = "none"
                charge.cost_verified = False
                charge.recalculate_costs()

        after = charge.to_dict()
        return after != before
