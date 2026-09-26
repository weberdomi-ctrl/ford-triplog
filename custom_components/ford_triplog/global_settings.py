"""Global Ford Triplog settings shared by all configured vehicles.

Build 25016 moves infrastructure settings that are not vehicle-specific out of
individual ConfigEntry semantics. SQLite is the single persistent source;
legacy per-entry values are imported once on first startup after upgrade.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.core import HomeAssistant

from .const import (
    CONF_OCR_API_KEY,
    CONF_OCR_ENABLED,
    CONF_OCR_TIMEOUT,
    CONF_OCR_URL,
    CONF_OSRM_ENABLED,
    CONF_OSRM_MATCH_RADIUS,
    CONF_OSRM_URL,
    DEFAULT_OCR_API_KEY,
    DEFAULT_OCR_ENABLED,
    DEFAULT_OCR_TIMEOUT,
    DEFAULT_OCR_URL,
    DEFAULT_OSRM_ENABLED,
    DEFAULT_OSRM_MATCH_RADIUS,
    DEFAULT_OSRM_URL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

_CACHE_KEY = "global_settings"
_LOCK_KEY = "global_settings_lock"

OCR_KEYS = (
    CONF_OCR_ENABLED,
    CONF_OCR_URL,
    CONF_OCR_API_KEY,
    CONF_OCR_TIMEOUT,
)
OSRM_KEYS = (
    CONF_OSRM_ENABLED,
    CONF_OSRM_URL,
    CONF_OSRM_MATCH_RADIUS,
)
GLOBAL_SETTING_KEYS = frozenset((*OCR_KEYS, *OSRM_KEYS))


def _defaults() -> dict[str, Any]:
    return {
        CONF_OCR_ENABLED: DEFAULT_OCR_ENABLED,
        CONF_OCR_URL: DEFAULT_OCR_URL,
        CONF_OCR_API_KEY: DEFAULT_OCR_API_KEY,
        CONF_OCR_TIMEOUT: DEFAULT_OCR_TIMEOUT,
        CONF_OSRM_ENABLED: DEFAULT_OSRM_ENABLED,
        CONF_OSRM_URL: DEFAULT_OSRM_URL,
        CONF_OSRM_MATCH_RADIUS: DEFAULT_OSRM_MATCH_RADIUS,
    }


def _normalize(settings: dict[str, Any] | None) -> dict[str, Any]:
    normalized = _defaults()
    if isinstance(settings, dict):
        for key in GLOBAL_SETTING_KEYS:
            if key in settings:
                normalized[key] = settings[key]

    normalized[CONF_OCR_ENABLED] = bool(normalized[CONF_OCR_ENABLED])
    normalized[CONF_OCR_URL] = str(normalized[CONF_OCR_URL] or "").strip().rstrip("/")
    normalized[CONF_OCR_API_KEY] = str(normalized[CONF_OCR_API_KEY] or "").strip()
    try:
        normalized[CONF_OCR_TIMEOUT] = max(3, int(normalized[CONF_OCR_TIMEOUT]))
    except (TypeError, ValueError):
        normalized[CONF_OCR_TIMEOUT] = DEFAULT_OCR_TIMEOUT

    normalized[CONF_OSRM_ENABLED] = bool(normalized[CONF_OSRM_ENABLED])
    normalized[CONF_OSRM_URL] = str(normalized[CONF_OSRM_URL] or "").strip().rstrip("/")
    try:
        normalized[CONF_OSRM_MATCH_RADIUS] = max(
            1.0,
            float(normalized[CONF_OSRM_MATCH_RADIUS]),
        )
    except (TypeError, ValueError):
        normalized[CONF_OSRM_MATCH_RADIUS] = float(DEFAULT_OSRM_MATCH_RADIUS)

    return normalized


def get_global_settings(hass: HomeAssistant) -> dict[str, Any]:
    """Return cached normalized global settings.

    Integration setup loads the persistent values before runtimes are created.
    Defaults are returned defensively if a flow is opened unusually early.
    """

    domain_data = hass.data.setdefault(DOMAIN, {})
    cached = domain_data.get(_CACHE_KEY)
    if isinstance(cached, dict):
        return _normalize(cached)
    return _defaults()


def apply_global_settings(
    hass: HomeAssistant,
    config: dict[str, Any],
) -> dict[str, Any]:
    """Overlay global infrastructure settings onto a vehicle configuration."""

    merged = dict(config)
    merged.update(get_global_settings(hass))
    return merged


def _legacy_category(
    hass: HomeAssistant,
    keys: tuple[str, ...],
    enabled_key: str,
) -> dict[str, Any]:
    """Select one legacy per-entry category for one-time migration.

    Prefer an explicitly enabled ConfigEntry, because multi-vehicle test setups
    may contain disabled/default values on newer entries while the original
    vehicle owns the working OCR/OSRM configuration.
    """

    candidates: list[dict[str, Any]] = []
    for entry in hass.config_entries.async_entries(DOMAIN):
        merged = {**entry.data, **entry.options}
        if any(key in merged for key in keys):
            candidates.append(merged)

    source = next(
        (candidate for candidate in candidates if bool(candidate.get(enabled_key))),
        None,
    )
    if source is None and candidates:
        source = candidates[0]
    if source is None:
        return {}

    return {key: source[key] for key in keys if key in source}


def _legacy_settings(hass: HomeAssistant) -> dict[str, Any]:
    migrated = _defaults()
    migrated.update(_legacy_category(hass, OCR_KEYS, CONF_OCR_ENABLED))
    migrated.update(_legacy_category(hass, OSRM_KEYS, CONF_OSRM_ENABLED))
    return _normalize(migrated)


async def async_load_global_settings(
    hass: HomeAssistant,
    database: Any,
) -> dict[str, Any]:
    """Load global settings, migrating legacy per-entry values once."""

    domain_data = hass.data.setdefault(DOMAIN, {})
    cached = domain_data.get(_CACHE_KEY)
    if isinstance(cached, dict):
        return _normalize(cached)

    lock = domain_data.get(_LOCK_KEY)
    if not isinstance(lock, asyncio.Lock):
        lock = asyncio.Lock()
        domain_data[_LOCK_KEY] = lock

    async with lock:
        cached = domain_data.get(_CACHE_KEY)
        if isinstance(cached, dict):
            return _normalize(cached)

        stored = await database.load_global_settings()
        if stored is None:
            stored = _legacy_settings(hass)
            if not await database.save_global_settings(stored):
                _LOGGER.warning(
                    "Unable to persist migrated Ford Triplog global settings"
                )
            else:
                _LOGGER.info(
                    "Ford Triplog global settings initialized from legacy ConfigEntry values: "
                    "ocr_enabled=%s osrm_enabled=%s",
                    stored[CONF_OCR_ENABLED],
                    stored[CONF_OSRM_ENABLED],
                )

        normalized = _normalize(stored)
        domain_data[_CACHE_KEY] = normalized
        return dict(normalized)


async def async_save_global_settings(
    hass: HomeAssistant,
    database: Any,
    updates: dict[str, Any],
) -> dict[str, Any]:
    """Persist global settings and apply them to all live vehicle runtimes."""

    current = await async_load_global_settings(hass, database)
    for key, value in updates.items():
        if key in GLOBAL_SETTING_KEYS:
            current[key] = value
    normalized = _normalize(current)

    if not await database.save_global_settings(normalized):
        raise OSError("Unable to save Ford Triplog global settings")

    domain_data = hass.data.setdefault(DOMAIN, {})
    domain_data[_CACHE_KEY] = normalized

    # Keep all already loaded vehicle runtimes in sync immediately. This avoids
    # reloading every ConfigEntry just because one shared infrastructure value
    # changed while still making the new settings effective for active trips.
    for runtime_data in list(domain_data.values()):
        if not isinstance(runtime_data, dict):
            continue

        runtime_config = runtime_data.get("config")
        if isinstance(runtime_config, dict):
            runtime_config.update(normalized)

        route_tracker = runtime_data.get("route_tracker")
        if route_tracker is not None:
            route_tracker.osrm_enabled = bool(normalized[CONF_OSRM_ENABLED])
            route_tracker.osrm_url = str(normalized[CONF_OSRM_URL] or "")
            route_tracker.osrm_match_radius = float(
                normalized[CONF_OSRM_MATCH_RADIUS]
            )

    _LOGGER.info(
        "Ford Triplog global settings updated: ocr_enabled=%s osrm_enabled=%s",
        normalized[CONF_OCR_ENABLED],
        normalized[CONF_OSRM_ENABLED],
    )
    return dict(normalized)
