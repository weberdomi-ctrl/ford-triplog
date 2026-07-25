"""
Ford Triplog

User-defined charging-site storage.

Version: 1.5.0
Phase: 3.1
Build: 01

Changes:
- Added persistent JSON storage for user-defined charging sites.
- Added validation and normalization for stored entries.
- Writes are atomic to reduce the risk of corrupted JSON files.

This build only provides the storage layer. Resolver and options-flow
integration follow in later Phase 3 builds.
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
    DEFAULT_USER_CHARGING_SITE_RADIUS,
    STORAGE_DIR,
    USER_CHARGING_SITES_FILE,
    USER_CHARGING_SITES_SCHEMA_VERSION,
)

_LOGGER = logging.getLogger(__name__)


class UserChargingSiteStorage:
    """Persist user-defined charging sites below Home Assistant .storage."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the user charging-site storage."""
        self.hass = hass
        self.storage_directory = Path(
            hass.config.path(".storage", STORAGE_DIR)
        )
        self.storage_path = (
            self.storage_directory / USER_CHARGING_SITES_FILE
        )

    async def async_setup(self) -> None:
        """Create storage directory and an empty database when required."""
        await self.hass.async_add_executor_job(self._setup)

    async def async_load(self) -> list[dict[str, Any]]:
        """Load and normalize all user-defined charging sites."""
        return await self.hass.async_add_executor_job(self._load)

    async def async_save(
        self,
        sites: list[dict[str, Any]],
    ) -> None:
        """Validate and atomically save all user-defined charging sites."""
        await self.hass.async_add_executor_job(self._save, sites)

    async def async_add(
        self,
        site: dict[str, Any],
    ) -> dict[str, Any]:
        """Add a new user-defined charging site and return it."""
        sites = await self.async_load()
        normalized = self._normalize_site(site, generate_id=True)

        if any(item["id"] == normalized["id"] for item in sites):
            raise ValueError(
                f"Charging-site ID already exists: {normalized['id']}"
            )

        sites.append(normalized)
        await self.async_save(sites)
        return normalized

    async def async_update(
        self,
        site_id: str,
        changes: dict[str, Any],
    ) -> dict[str, Any]:
        """Update an existing charging site and return the saved entry."""
        sites = await self.async_load()
        normalized_id = self._clean_required_text(site_id, "site_id")

        for index, existing in enumerate(sites):
            if existing["id"] != normalized_id:
                continue

            merged = {
                **existing,
                **changes,
                "id": normalized_id,
            }
            normalized = self._normalize_site(
                merged,
                generate_id=False,
            )
            sites[index] = normalized
            await self.async_save(sites)
            return normalized

        raise KeyError(
            f"User charging site not found: {normalized_id}"
        )

    async def async_delete(self, site_id: str) -> bool:
        """Delete a charging site and return whether it existed."""
        sites = await self.async_load()
        normalized_id = self._clean_required_text(site_id, "site_id")
        remaining = [
            site for site in sites
            if site["id"] != normalized_id
        ]

        if len(remaining) == len(sites):
            return False

        await self.async_save(remaining)
        return True

    async def async_get(
        self,
        site_id: str,
    ) -> dict[str, Any] | None:
        """Return a charging site by ID."""
        normalized_id = self._clean_required_text(site_id, "site_id")

        for site in await self.async_load():
            if site["id"] == normalized_id:
                return site

        return None

    def _setup(self) -> None:
        """Create the storage directory and initial empty JSON file."""
        self.storage_directory.mkdir(parents=True, exist_ok=True)

        if self.storage_path.exists():
            self._load()
            return

        self._write_payload([])

    def _load(self) -> list[dict[str, Any]]:
        """Synchronously load and validate the JSON database."""
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
        except OSError as error:
            raise OSError(
                f"Could not read {self.storage_path}"
            ) from error

        if not isinstance(raw, dict):
            raise ValueError(
                "User charging-site database root must be an object"
            )

        schema = raw.get("schema")
        if schema != USER_CHARGING_SITES_SCHEMA_VERSION:
            raise ValueError(
                "Unsupported user charging-site schema: "
                f"{schema!r}"
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

            if normalized["id"] in used_ids:
                raise ValueError(
                    "Duplicate user charging-site ID: "
                    f"{normalized['id']}"
                )

            used_ids.add(normalized["id"])
            normalized_sites.append(normalized)

        return normalized_sites

    def _save(self, sites: list[dict[str, Any]]) -> None:
        """Synchronously validate and atomically save all sites."""
        if not isinstance(sites, list):
            raise ValueError("Charging sites must be supplied as a list")

        normalized_sites: list[dict[str, Any]] = []
        used_ids: set[str] = set()

        for site in sites:
            normalized = self._normalize_site(
                site,
                generate_id=True,
            )

            if normalized["id"] in used_ids:
                raise ValueError(
                    "Duplicate user charging-site ID: "
                    f"{normalized['id']}"
                )

            used_ids.add(normalized["id"])
            normalized_sites.append(normalized)

        self._write_payload(normalized_sites)

    def _write_payload(
        self,
        sites: list[dict[str, Any]],
    ) -> None:
        """Atomically write the complete JSON payload."""
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
                )
                + "\n",
                encoding="utf-8",
            )
            os.replace(temporary_path, self.storage_path)
        except OSError:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                _LOGGER.debug(
                    "Could not remove temporary charging-site file %s",
                    temporary_path,
                )
            raise

    @classmethod
    def _normalize_site(
        cls,
        raw_site: dict[str, Any],
        *,
        generate_id: bool,
    ) -> dict[str, Any]:
        """Return a validated and normalized charging-site entry."""
        if not isinstance(raw_site, dict):
            raise ValueError(
                "Each user charging site must be an object"
            )

        raw_id = raw_site.get("id")
        if raw_id is None and generate_id:
            site_id = uuid.uuid4().hex
        else:
            site_id = cls._clean_required_text(raw_id, "id")

        name = cls._clean_required_text(
            raw_site.get("name"),
            "name",
        )
        latitude = cls._coordinate(
            raw_site.get("latitude"),
            "latitude",
            -90.0,
            90.0,
        )
        longitude = cls._coordinate(
            raw_site.get("longitude"),
            "longitude",
            -180.0,
            180.0,
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

        power_kw = cls._optional_float(
            raw_site.get("power_kw"),
            "power_kw",
        )
        if power_kw is not None and power_kw < 0:
            raise ValueError("power_kw must not be negative")

        return {
            "id": site_id,
            "name": name,
            "latitude": latitude,
            "longitude": longitude,
            "radius": radius,
            "operator": cls._optional_text(
                raw_site.get("operator")
            ),
            "network": cls._optional_text(
                raw_site.get("network")
            ),
            "brand": cls._optional_text(
                raw_site.get("brand")
            ),
            "power_kw": power_kw,
            "type": cls._optional_text(
                raw_site.get("type")
            )
            or "public",
            "notes": cls._optional_text(
                raw_site.get("notes")
            ),
        }

    @staticmethod
    def _clean_required_text(
        value: Any,
        field_name: str,
    ) -> str:
        """Return a non-empty string."""
        if value is None:
            raise ValueError(f"{field_name} is required")

        text = str(value).strip()
        if not text:
            raise ValueError(f"{field_name} must not be empty")

        return text

    @staticmethod
    def _optional_text(value: Any) -> str | None:
        """Return a normalized optional string."""
        if value is None:
            return None

        text = str(value).strip()
        return text or None

    @staticmethod
    def _coordinate(
        value: Any,
        field_name: str,
        minimum: float,
        maximum: float,
    ) -> float:
        """Return a validated geographic coordinate."""
        try:
            coordinate = float(value)
        except (TypeError, ValueError) as error:
            raise ValueError(
                f"{field_name} must be numeric"
            ) from error

        if not minimum <= coordinate <= maximum:
            raise ValueError(
                f"{field_name} must be between "
                f"{minimum} and {maximum}"
            )

        return coordinate

    @staticmethod
    def _optional_float(
        value: Any,
        field_name: str,
    ) -> float | None:
        """Return a normalized optional floating-point value."""
        if value is None or value == "":
            return None

        try:
            return float(value)
        except (TypeError, ValueError) as error:
            raise ValueError(
                f"{field_name} must be numeric"
            ) from error
