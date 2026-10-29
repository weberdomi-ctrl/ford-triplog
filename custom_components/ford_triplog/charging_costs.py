"""Central charging-cost calculation for Ford Triplog."""

from __future__ import annotations

import logging
import math
import sqlite3
from datetime import date
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .charge import Charge
from .const import CONF_JOURNEY_HOME_ZONE, CONF_VEHICLE_ID, STORAGE_DIR
from .zone_tariff_storage import ZoneTariffStorage

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
        self._vehicle_id = config.get(CONF_VEHICLE_ID)
        self._zone_tariff_db_path = ZoneTariffStorage(hass).database.db_path

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

    def _zone_tariff_for_charge(self, charge: Charge):
        """Resolve a configured vehicle/zone tariff; never use legacy fallback."""
        latitude = charge.end_latitude if charge.end_latitude is not None else charge.start_latitude
        longitude = charge.end_longitude if charge.end_longitude is not None else charge.start_longitude
        if latitude is None or longitude is None:
            return None
        try:
            lat, lon = float(latitude), float(longitude)
            vehicle_id = int(self._vehicle_id)
        except (ValueError, TypeError):
            return None
        matches = []
        for state in self.hass.states.async_all("zone"):
            try:
                attrs = state.attributes
                radius = max(0.0, float(attrs.get("radius", 100)))
                distance = self._distance_meters(lat, lon, float(attrs["latitude"]), float(attrs["longitude"]))
                if distance <= radius:
                    matches.append((distance, state.entity_id))
            except (ValueError, TypeError, KeyError):
                continue
        if not matches:
            return None
        # The closest matching zone wins; never silently use a different zone's price.
        zone_id = min(matches)[1]
        try:
            with sqlite3.connect(self._zone_tariff_db_path, timeout=2) as db:
                db.row_factory = sqlite3.Row
                row = db.execute("SELECT mode, price_per_kwh, currency FROM charging_vehicle_zone_tariffs WHERE vehicle_id=? AND zone_id=?", (vehicle_id, zone_id)).fetchone()
                if row is None or row["mode"] == "dynamic":
                    return None
                if row["mode"] == "fixed":
                    return (zone_id, float(row["price_per_kwh"]), row["currency"])
                if row["mode"] != "seasonal":
                    return None
                start = self._parse_datetime(charge.start_time)
                if start is None:
                    return None
                day = dt_util.as_local(start).date().isoformat()
                period = db.execute("""SELECT price_per_kwh, currency FROM charging_vehicle_zone_periods
                    WHERE vehicle_id=? AND zone_id=? AND valid_from<=? AND valid_to>=?
                    ORDER BY valid_from DESC LIMIT 1""", (vehicle_id, zone_id, day, day)).fetchone()
                return (zone_id, float(period["price_per_kwh"]), period["currency"]) if period else None
        except (sqlite3.Error, ValueError, TypeError):
            _LOGGER.exception("Unable to resolve vehicle/zone charging tariff")
            return None

    def dynamic_energy_sensor_for_charge(self, charge: Charge) -> tuple[str, str] | None:
        """Return (zone_id, sensor_id) if this vehicle has a dynamic meter.

        Coordinates must match an actual HA zone. This prevents a configured
        home meter from contaminating a charge at a public station.
        """
        latitude = charge.start_latitude if charge.start_latitude is not None else charge.end_latitude
        longitude = charge.start_longitude if charge.start_longitude is not None else charge.end_longitude
        try:
            lat, lon = float(latitude), float(longitude)
            vehicle_id = int(self._vehicle_id)
        except (TypeError, ValueError):
            return None
        matches = []
        for state in self.hass.states.async_all("zone"):
            try:
                attrs = state.attributes
                radius = max(0.0, float(attrs.get("radius", 100)))
                dist = self._distance_meters(lat, lon, float(attrs["latitude"]), float(attrs["longitude"]))
                if dist <= radius:
                    matches.append((dist, state.entity_id))
            except (ValueError, TypeError, KeyError):
                continue
        if not matches:
            return None
        zone_id = min(matches)[1]
        try:
            with sqlite3.connect(self._zone_tariff_db_path, timeout=2) as db:
                row = db.execute(
                    "SELECT mode, energy_sensor FROM charging_vehicle_zone_tariffs WHERE vehicle_id=? AND zone_id=?",
                    (vehicle_id, zone_id),
                ).fetchone()
        except sqlite3.Error:
            _LOGGER.exception("Failed to read dynamic energy meter configuration")
            return None
        if row and row[0] == "dynamic" and isinstance(row[1], str) and row[1].startswith("sensor."):
            return zone_id, row[1]
        return None

    def dynamic_price_tariff_for_charge(self, charge: Charge) -> tuple[str, str] | None:
        """Return (price sensor, currency) for the already matched meter zone."""
        zone_id = charge.external_meter_zone_id
        if not zone_id or not charge.external_meter_entity_id:
            return None
        try:
            vehicle_id = int(self._vehicle_id)
            with sqlite3.connect(self._zone_tariff_db_path, timeout=2) as db:
                row = db.execute(
                    "SELECT mode, price_sensor, energy_sensor, currency "
                    "FROM charging_vehicle_zone_tariffs WHERE vehicle_id=? AND zone_id=?",
                    (vehicle_id, zone_id),
                ).fetchone()
        except (sqlite3.Error, ValueError, TypeError):
            _LOGGER.exception("Failed to read dynamic charging price configuration")
            return None
        if (row is None or row[0] != "dynamic" or row[2] != charge.external_meter_entity_id
                or not isinstance(row[1], str) or not row[1].startswith("sensor.")
                or str(row[3]).upper() not in ("CHF", "EUR")):
            return None
        return row[1], str(row[3]).upper()

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

        # Completed charges, including legacy records, are immutable unless
        # a user explicitly edits the charge or its receipt.
        if charge.cost_finalized:
            return False

        before = charge.to_dict()

        charge.recalculate_costs()

        cost_source = str(
            getattr(charge, "cost_source", "none") or "none"
        ).strip().lower()

        tariff = self._zone_tariff_for_charge(charge) if allow_automatic_tariff else None
        # Clear stale automatic costs if no matching configured zone/tariff exists.
        if cost_source == "home_tariff" and tariff is None:
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

        if allow_automatic_tariff and cost_source not in _PROTECTED_COST_SOURCES and tariff:
            energy, energy_source = self._pricing_energy(charge)
            if energy is not None:
                zone_id, tariff_price, tariff_currency = tariff
                charge.energy_cost = round(energy * tariff_price, 4)
                charge.session_fee = 0.0
                charge.time_fee = 0.0
                charge.blocking_fee = 0.0
                charge.parking_fee = 0.0
                charge.other_cost = 0.0
                charge.currency = tariff_currency
                charge.cost_source = "home_tariff"
                # Automatic calculation never constitutes user verification.
                # Preserve an existing explicit confirmation on recalculation.
                if charge.energy_billed_kwh is None and energy_source == "added":
                    charge.energy_billed_source = "estimated"
                charge.recalculate_costs()
                _LOGGER.debug("Zone tariff: charge=%s zone=%s energy=%.3f price=%.4f", charge.charge_id, zone_id, energy, tariff_price)

        after = charge.to_dict()
        return after != before
