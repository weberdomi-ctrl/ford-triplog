"""
Ford Triplog

User-defined charging-site storage.

Version: 1.5.0
Phase: 3.5
Build: 10

Changes:
- Aligns user charging-site records with the stable OSM charging-site fields.
- Migrates legacy records using "id" and scalar power values automatically.
- Keeps user-specific radius, type, address and notes fields.
- Writes are atomic.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant

from .const import (
    CONF_STORAGE_READ_BACKEND,
    DEFAULT_STORAGE_READ_BACKEND,
    DEFAULT_USER_CHARGING_SITE_RADIUS,
    DOMAIN,
    STORAGE_DIR,
    STORAGE_READ_BACKEND_SQLITE,
    USER_CHARGING_SITES_FILE,
    USER_CHARGING_SITES_SCHEMA_VERSION,
)
from .database import FordTriplogDatabase

_LOGGER = logging.getLogger(__name__)


class UserChargingSiteStorage:
    """Persist user-defined charging sites below Home Assistant .storage."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self.storage_directory = Path(
            hass.config.path(".storage", STORAGE_DIR)
        )
        self.storage_path = self.storage_directory / USER_CHARGING_SITES_FILE
        self.database = FordTriplogDatabase(
            hass,
            self.storage_directory,
        )

        self.read_backend = DEFAULT_STORAGE_READ_BACKEND
        self._sites: list[dict[str, Any]] | None = None
        entries = hass.config_entries.async_entries(DOMAIN)
        if len(entries) == 1:
            self.read_backend = str(
                entries[0].options.get(
                    CONF_STORAGE_READ_BACKEND,
                    DEFAULT_STORAGE_READ_BACKEND,
                )
            )

    async def async_setup(self) -> None:
        """Initialize user charging-site storage."""

        await self.database.async_setup()

        if self.read_backend == STORAGE_READ_BACKEND_SQLITE:
            # SQLite-only must never create an empty JSON file or clear an
            # existing SQLite table merely because the JSON file is absent.
            sqlite_sites = await self.database.load_user_charging_sites()

            if sqlite_sites:
                self._sites = self._normalize_sites(
                    sqlite_sites,
                    generate_id=False,
                )
                return

            # Safe one-time recovery/mirror when a legacy JSON file still
            # exists and SQLite is empty.
            if self.storage_path.exists():
                json_sites = await self.hass.async_add_executor_job(self._load)
                if json_sites:
                    await self.database.save_user_charging_sites(json_sites)
                    _LOGGER.info(
                        "Imported %d user charging sites from JSON into SQLite",
                        len(json_sites),
                    )
                    self._sites = json_sites
                    return

            self._sites = []
            return

        await self.hass.async_add_executor_job(self._setup)

        # Keep SQLite populated while JSON is the selected read backend,
        # but do not wipe an existing SQLite table because an old JSON file
        # happens to be empty.
        json_sites = await self.hass.async_add_executor_job(self._load)
        self._sites = json_sites

        if json_sites:
            await self.database.save_user_charging_sites(json_sites)

    async def async_load(self) -> list[dict[str, Any]]:
        """Load user charging sites from the selected backend."""

        if self._sites is None:
            if self.read_backend == STORAGE_READ_BACKEND_SQLITE:
                sites = await self.database.load_user_charging_sites()
                self._sites = self._normalize_sites(
                    sites,
                    generate_id=False,
                )
            else:
                self._sites = await self.hass.async_add_executor_job(
                    self._load
                )

        return list(self._sites)

    async def async_save(self, sites: list[dict[str, Any]]) -> None:
        """Save user charging sites to the selected backend."""

        normalized_sites = self._normalize_sites(
            sites,
            generate_id=True,
        )

        if self.read_backend == STORAGE_READ_BACKEND_SQLITE:
            saved = await self.database.save_user_charging_sites(
                normalized_sites
            )
            if not saved:
                raise OSError(
                    "Unable to save user charging sites to SQLite"
                )

            self._sites = normalized_sites
            return

        await self.hass.async_add_executor_job(
            self._write_payload,
            normalized_sites,
        )

        # JSON mode continues to maintain the SQLite mirror.
        saved = await self.database.save_user_charging_sites(
            normalized_sites
        )
        if not saved:
            raise OSError(
                "Unable to mirror user charging sites to SQLite"
            )

        self._sites = normalized_sites

    async def async_add(self, site: dict[str, Any]) -> dict[str, Any]:
        sites = await self.async_load()
        normalized = self._normalize_site(site, generate_id=True)

        if any(item["site_id"] == normalized["site_id"] for item in sites):
            raise ValueError(
                f"Charging-site ID already exists: {normalized['site_id']}"
            )

        sites.append(normalized)
        await self.async_save(sites)
        return normalized

    async def async_update(
        self,
        site_id: str,
        changes: dict[str, Any],
    ) -> dict[str, Any]:
        sites = await self.async_load()
        normalized_id = self._clean_required_text(site_id, "site_id")

        for index, existing in enumerate(sites):
            if existing["site_id"] != normalized_id:
                continue

            merged = {
                **existing,
                **changes,
                "site_id": normalized_id,
            }
            normalized = self._normalize_site(
                merged,
                generate_id=False,
            )
            sites[index] = normalized
            await self.async_save(sites)
            return normalized

        raise KeyError(f"User charging site not found: {normalized_id}")

    async def async_delete(self, site_id: str) -> bool:
        sites = await self.async_load()
        normalized_id = self._clean_required_text(site_id, "site_id")
        remaining = [
            site for site in sites
            if site["site_id"] != normalized_id
        ]

        if len(remaining) == len(sites):
            return False

        await self.async_save(remaining)
        return True

    async def async_get(self, site_id: str) -> dict[str, Any] | None:
        normalized_id = self._clean_required_text(site_id, "site_id")

        for site in await self.async_load():
            if site["site_id"] == normalized_id:
                return site

        return None

    def _setup(self) -> None:
        self.storage_directory.mkdir(parents=True, exist_ok=True)

        if self.storage_path.exists():
            self._load()
            return

        self._write_payload([])

    def _load(self) -> list[dict[str, Any]]:
        if not self.storage_path.exists():
            self._setup()

        try:
            raw = json.loads(
                self.storage_path.read_text(encoding="utf-8")
            )
        except json.JSONDecodeError as error:
            raise ValueError(
                "User charging-site database contains invalid JSON"
            ) from error

        if not isinstance(raw, dict):
            raise ValueError(
                "User charging-site database root must be an object"
            )

        if raw.get("schema") != USER_CHARGING_SITES_SCHEMA_VERSION:
            raise ValueError(
                "Unsupported user charging-site schema: "
                f"{raw.get('schema')!r}"
            )

        raw_sites = raw.get("sites")
        if not isinstance(raw_sites, list):
            raise ValueError(
                "User charging-site database 'sites' must be a list"
            )

        normalized_sites: list[dict[str, Any]] = []
        used_ids: set[str] = set()

        for raw_site in raw_sites:
            normalized = self._normalize_site(
                raw_site,
                generate_id=False,
            )
            site_id = normalized["site_id"]

            if site_id in used_ids:
                raise ValueError(
                    f"Duplicate user charging-site ID: {site_id}"
                )

            used_ids.add(site_id)
            normalized_sites.append(normalized)

        return normalized_sites

    def _save(self, sites: list[dict[str, Any]]) -> None:
        normalized_sites = self._normalize_sites(
            sites,
            generate_id=True,
        )
        self._write_payload(normalized_sites)

    @classmethod
    def _normalize_sites(
        cls,
        sites: list[dict[str, Any]],
        *,
        generate_id: bool,
    ) -> list[dict[str, Any]]:
        if not isinstance(sites, list):
            raise ValueError("Charging sites must be supplied as a list")

        normalized_sites: list[dict[str, Any]] = []
        used_ids: set[str] = set()

        for site in sites:
            normalized = cls._normalize_site(
                site,
                generate_id=generate_id,
            )
            site_id = normalized["site_id"]

            if site_id in used_ids:
                raise ValueError(
                    f"Duplicate user charging-site ID: {site_id}"
                )

            used_ids.add(site_id)
            normalized_sites.append(normalized)

        return normalized_sites

    def _write_payload(self, sites: list[dict[str, Any]]) -> None:
        self.storage_directory.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema": USER_CHARGING_SITES_SCHEMA_VERSION,
            "sites": sites,
        }
        temporary_path = self.storage_path.with_suffix(
            self.storage_path.suffix + ".tmp"
        )

        try:
            temporary_path.write_text(
                json.dumps(
                    payload,
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=False,
                ) + "\n",
                encoding="utf-8",
            )
            os.replace(temporary_path, self.storage_path)
        except OSError:
            temporary_path.unlink(missing_ok=True)
            raise

    @classmethod
    def _normalize_site(
        cls,
        raw_site: dict[str, Any],
        *,
        generate_id: bool,
    ) -> dict[str, Any]:
        if not isinstance(raw_site, dict):
            raise ValueError("Each user charging site must be an object")

        # Legacy Build 01-09 records used "id".
        raw_id = raw_site.get("site_id", raw_site.get("id"))
        if raw_id is None and generate_id:
            site_id = f"user:{uuid.uuid4().hex}"
        else:
            site_id = cls._clean_required_text(raw_id, "site_id")
            if not site_id.startswith("user:"):
                site_id = f"user:{site_id}"

        name = cls._clean_required_text(raw_site.get("name"), "name")
        latitude = cls._coordinate(
            raw_site.get("latitude"), "latitude", -90.0, 90.0
        )
        longitude = cls._coordinate(
            raw_site.get("longitude"), "longitude", -180.0, 180.0
        )

        radius = cls._optional_float(
            raw_site.get(
                "radius",
                DEFAULT_USER_CHARGING_SITE_RADIUS,
            ),
            "radius",
        )
        if radius is None or radius <= 0 or radius > 5000:
            raise ValueError(
                "radius must be greater than 0 and at most 5000 meters"
            )

        power_kw = cls._number_list(
            raw_site.get("power_kw"),
            "power_kw",
        )
        capacity = cls._number_list(
            raw_site.get("capacity"),
            "capacity",
        )
        connectors = cls._text_list(
            raw_site.get("connectors")
        )

        quality = cls._optional_text(raw_site.get("quality")) or "user"

        return {
            # Stable OSM-compatible runtime fields.
            "site_id": site_id,
            "latitude": latitude,
            "longitude": longitude,
            "name": name,
            "brand": cls._optional_text(raw_site.get("brand")),
            "operator": cls._optional_text(raw_site.get("operator")),
            "network": cls._optional_text(raw_site.get("network")),
            "power_kw": power_kw,
            "capacity": capacity,
            "connectors": connectors,
            "quality": quality,
            "member_count": 1,
            "osm_ids": cls._text_list(raw_site.get("osm_ids")),

            # User-specific management fields.
            "radius": radius,
            "type": cls._optional_text(raw_site.get("type")) or "public",
            "street": cls._optional_text(raw_site.get("street")),
            "house_number": cls._optional_text(
                raw_site.get("house_number")
            ),
            "postcode": cls._optional_text(raw_site.get("postcode")),
            "city": cls._optional_text(raw_site.get("city")),
            "country": cls._optional_text(raw_site.get("country")),
            "notes": cls._optional_text(raw_site.get("notes")),
            "source": "user",
        }

    @staticmethod
    def _clean_required_text(value: Any, field_name: str) -> str:
        if value is None:
            raise ValueError(f"{field_name} is required")

        text = str(value).strip()
        if not text:
            raise ValueError(f"{field_name} must not be empty")

        return text

    @staticmethod
    def _optional_text(value: Any) -> str | None:
        if value is None:
            return None

        text = str(value).strip()
        return text or None

    @classmethod
    def _text_list(cls, value: Any) -> list[str]:
        if value in (None, "", [], ()):
            return []

        if isinstance(value, str):
            parts = value.replace(";", ",").split(",")
        elif isinstance(value, (list, tuple, set)):
            parts = value
        else:
            parts = [value]

        result: list[str] = []
        for item in parts:
            text = cls._optional_text(item)
            if text and text not in result:
                result.append(text)
        return result

    @staticmethod
    def _coordinate(
        value: Any,
        field_name: str,
        minimum: float,
        maximum: float,
    ) -> float:
        try:
            coordinate = float(value)
        except (TypeError, ValueError) as error:
            raise ValueError(
                f"{field_name} must be numeric"
            ) from error

        if not minimum <= coordinate <= maximum:
            raise ValueError(
                f"{field_name} must be between {minimum} and {maximum}"
            )

        return coordinate

    @staticmethod
    def _optional_float(
        value: Any,
        field_name: str,
    ) -> float | None:
        if value is None or value == "":
            return None

        try:
            return float(value)
        except (TypeError, ValueError) as error:
            raise ValueError(
                f"{field_name} must be numeric"
            ) from error

    @classmethod
    def _number_list(
        cls,
        value: Any,
        field_name: str,
    ) -> list[float]:
        if value in (None, "", [], ()):
            return []

        values = value if isinstance(value, (list, tuple, set)) else [value]
        result: list[float] = []

        for item in values:
            number = cls._optional_float(item, field_name)
            if number is None:
                continue
            if number < 0:
                raise ValueError(f"{field_name} must not be negative")
            if number not in result:
                result.append(number)

        return result
