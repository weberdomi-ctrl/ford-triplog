"""
Ford Triplog

Pending unknown charging-location storage.

Version: 1.5.0
Phase: 3.5
Build: 10

Changes:
- Stores pending records with OSM-compatible charging-site fields.
- Preserves address data for prefilled user-location creation.
- Keeps nearby-location deduplication.
"""

from __future__ import annotations

import json
import math
import os
import uuid
from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant

from .charge import Charge
from .const import (
    PENDING_CHARGING_SITE_DEDUP_RADIUS,
    PENDING_CHARGING_SITES_FILE,
    PENDING_CHARGING_SITES_SCHEMA_VERSION,
    STORAGE_DIR,
)


class PendingChargingSiteStorage:
    """Persist unresolved charging locations below Home Assistant .storage."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self.storage_directory = Path(
            hass.config.path(".storage", STORAGE_DIR)
        )
        self.storage_path = (
            self.storage_directory / PENDING_CHARGING_SITES_FILE
        )

    async def async_setup(self) -> None:
        await self.hass.async_add_executor_job(self._setup)

    async def async_load(self) -> list[dict[str, Any]]:
        return await self.hass.async_add_executor_job(self._load)

    async def async_add_from_charge(
        self,
        charge: Charge,
    ) -> dict[str, Any] | None:
        return await self.hass.async_add_executor_job(
            self._add_from_charge,
            charge,
        )

    async def async_delete(self, pending_id: str) -> bool:
        return await self.hass.async_add_executor_job(
            self._delete,
            pending_id,
        )

    def _setup(self) -> None:
        self.storage_directory.mkdir(parents=True, exist_ok=True)
        if not self.storage_path.exists():
            self._write([])

    def _load(self) -> list[dict[str, Any]]:
        if not self.storage_path.exists():
            self._setup()

        raw = json.loads(self.storage_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("Pending charging-site database must be an object")
        if raw.get("schema") != PENDING_CHARGING_SITES_SCHEMA_VERSION:
            raise ValueError("Unsupported pending charging-site schema")

        sites = raw.get("sites")
        if not isinstance(sites, list):
            raise ValueError("Pending charging-site sites must be a list")

        return [site for site in sites if isinstance(site, dict)]

    def _add_from_charge(
        self,
        charge: Charge,
    ) -> dict[str, Any] | None:
        latitude = charge.end_latitude
        longitude = charge.end_longitude
        address = charge.end_address

        if latitude is None or longitude is None:
            latitude = charge.start_latitude
            longitude = charge.start_longitude
            address = charge.start_address

        try:
            latitude = float(latitude)
            longitude = float(longitude)
        except (TypeError, ValueError):
            return None

        sites = self._load()

        for existing in sites:
            try:
                distance = self._distance_meters(
                    latitude,
                    longitude,
                    float(existing["latitude"]),
                    float(existing["longitude"]),
                )
            except (KeyError, TypeError, ValueError):
                continue

            if distance <= PENDING_CHARGING_SITE_DEDUP_RADIUS:
                existing["last_charge_id"] = charge.charge_id
                existing["address"] = address or existing.get("address")
                self._write(sites)
                return existing

        site = {
            "id": uuid.uuid4().hex,
            "site_id": f"pending:{uuid.uuid4().hex}",
            "charge_id": charge.charge_id,
            "last_charge_id": charge.charge_id,
            "latitude": latitude,
            "longitude": longitude,
            "address": address,
            "name": self._suggested_name(address),
            "brand": charge.charging_site_brand,
            "operator": charge.charging_site_operator,
            "network": charge.charging_site_network,
            "power_kw": list(charge.charging_site_power_kw or []),
            "capacity": list(charge.charging_site_capacity or []),
            "connectors": list(charge.charging_site_connectors or []),
            "quality": charge.charging_site_quality or "unknown",
            "member_count": 1,
            "osm_ids": [],
        }
        sites.append(site)
        self._write(sites)
        return site

    def _delete(self, pending_id: str) -> bool:
        sites = self._load()
        remaining = [
            site
            for site in sites
            if str(site.get("id")) != str(pending_id)
        ]
        if len(remaining) == len(sites):
            return False
        self._write(remaining)
        return True

    def _write(self, sites: list[dict[str, Any]]) -> None:
        self.storage_directory.mkdir(parents=True, exist_ok=True)
        temporary_path = self.storage_path.with_suffix(
            self.storage_path.suffix + ".tmp"
        )
        payload = {
            "schema": PENDING_CHARGING_SITES_SCHEMA_VERSION,
            "sites": sites,
        }
        temporary_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary_path, self.storage_path)

    @staticmethod
    def _suggested_name(address: Any) -> str:
        if isinstance(address, dict):
            for key in (
                "name",
                "road",
                "street",
                "city",
                "town",
                "village",
                "municipality",
            ):
                value = address.get(key)
                if value:
                    return str(value)
        if isinstance(address, str) and address.strip():
            return address.strip()
        return "Unbekannter Ladeort"

    @staticmethod
    def _distance_meters(
        latitude_1: float,
        longitude_1: float,
        latitude_2: float,
        longitude_2: float,
    ) -> float:
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
