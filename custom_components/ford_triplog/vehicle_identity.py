"""Vehicle identity helpers for Ford Triplog."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .const import (
    CONF_CHARGING,
    CONF_IGNITION,
    CONF_LAST_CHARGE,
    CONF_ODOMETER,
    CONF_SOC,
    CONF_TRACKER,
)

# VINs are 17 characters and do not use I, O or Q.
_VIN_RE = re.compile(r"(?<![A-Z0-9])([A-HJ-NPR-Z0-9]{17})(?![A-Z0-9])", re.IGNORECASE)
_VIN_LABEL_RE = re.compile(r"\bVIN\s*[:=\-]?\s*([A-HJ-NPR-Z0-9]{17})\b", re.IGNORECASE)

_SOURCE_ENTITY_KEYS = (
    CONF_IGNITION,
    CONF_ODOMETER,
    CONF_SOC,
    CONF_CHARGING,
    CONF_LAST_CHARGE,
    CONF_TRACKER,
)


@dataclass(slots=True, frozen=True)
class FordTriplogVehicleIdentity:
    """Vehicle identity discovered from Home Assistant registries."""

    vin: str | None = None
    name: str | None = None
    manufacturer: str | None = None
    model: str | None = None
    source: str | None = None
    device_id: str | None = None
    entity_id: str | None = None

    @property
    def unique_key(self) -> str | None:
        """Return a stable config-entry unique key when available."""
        if self.vin:
            return f"vehicle:{self.vin.lower()}"
        if self.device_id:
            return f"device:{self.device_id}"
        return None


def _extract_vin(value: Any) -> str | None:
    """Extract a VIN from a registry value."""
    if value is None:
        return None
    text = str(value).strip().upper()
    if not text:
        return None

    labelled = _VIN_LABEL_RE.search(text)
    if labelled:
        return labelled.group(1).upper()

    match = _VIN_RE.search(text)
    if match:
        return match.group(1).upper()
    return None


def _clean_vehicle_name(value: Any, vin: str | None) -> str | None:
    """Return a human-readable device name without an embedded VIN."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None

    if vin:
        text = re.sub(
            rf"\s*[\[(]?\s*VIN\s*:\s*{re.escape(vin)}\s*[\])]?\s*",
            " ",
            text,
            flags=re.IGNORECASE,
        ).strip()
        text = re.sub(r"\s{2,}", " ", text)

    if vin and text.upper() == f"VIN: {vin}":
        return None
    if _extract_vin(text) == text.upper():
        return None
    return text or None


def async_detect_vehicle_identity(
    hass: HomeAssistant,
    config: dict[str, Any],
) -> FordTriplogVehicleIdentity:
    """Discover vehicle identity from the configured source entities."""
    entity_registry = er.async_get(hass)
    device_registry = dr.async_get(hass)

    candidates: list[tuple[Any, Any]] = []
    for key in _SOURCE_ENTITY_KEYS:
        entity_id = config.get(key)
        if not entity_id:
            continue
        entity_entry = entity_registry.async_get(str(entity_id))
        if entity_entry is None:
            continue
        device_entry = (
            device_registry.async_get(entity_entry.device_id)
            if entity_entry.device_id
            else None
        )
        candidates.append((entity_entry, device_entry))

    if not candidates:
        return FordTriplogVehicleIdentity()

    # Prefer the first configured entity that belongs to a device. The normal
    # Ford Connect/FordPass setup points all vehicle entities at the same HA device.
    entity_entry, device_entry = next(
        ((entity, device) for entity, device in candidates if device is not None),
        candidates[0],
    )

    vin: str | None = None
    if device_entry is not None:
        for identifier in device_entry.identifiers:
            for part in identifier:
                vin = _extract_vin(part)
                if vin:
                    break
            if vin:
                break

        if not vin:
            for value in (
                getattr(device_entry, "name_by_user", None),
                getattr(device_entry, "name", None),
                getattr(device_entry, "model", None),
                getattr(device_entry, "serial_number", None),
            ):
                vin = _extract_vin(value)
                if vin:
                    break

    if not vin:
        for entity, _device in candidates:
            for value in (
                getattr(entity, "entity_id", None),
                getattr(entity, "name", None),
                getattr(entity, "original_name", None),
                getattr(entity, "unique_id", None),
            ):
                vin = _extract_vin(value)
                if vin:
                    break
            if vin:
                break

    name: str | None = None
    manufacturer: str | None = None
    model: str | None = None
    if device_entry is not None:
        manufacturer_value = getattr(device_entry, "manufacturer", None)
        model_value = getattr(device_entry, "model", None)
        manufacturer = str(manufacturer_value).strip() if manufacturer_value else None
        model = str(model_value).strip() if model_value else None
        for value in (
            getattr(device_entry, "name_by_user", None),
            getattr(device_entry, "name", None),
            model_value,
        ):
            name = _clean_vehicle_name(value, vin)
            if name:
                break

    source_value = getattr(entity_entry, "platform", None)
    source = str(source_value).strip() if source_value else None

    return FordTriplogVehicleIdentity(
        vin=vin,
        name=name,
        manufacturer=manufacturer,
        model=model,
        source=source,
        device_id=getattr(entity_entry, "device_id", None),
        entity_id=getattr(entity_entry, "entity_id", None),
    )
