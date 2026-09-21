"""Shared multi-vehicle UI context for Ford Triplog."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from .const import DOMAIN


VEHICLE_CONTEXT_KEY = "vehicle_context_id"
VEHICLE_CONTEXT_MANUAL_KEY = "vehicle_context_manual"


def _domain_data(hass: HomeAssistant) -> dict[str, Any]:
    """Return Ford Triplog runtime data."""

    return hass.data.setdefault(DOMAIN, {})


def iter_vehicle_runtimes(hass: HomeAssistant) -> list[tuple[int, str, dict[str, Any]]]:
    """Return loaded Ford Triplog vehicle runtimes sorted by vehicle id."""

    vehicles: list[tuple[int, str, dict[str, Any]]] = []
    for entry_id, runtime_data in _domain_data(hass).items():
        if not isinstance(runtime_data, dict):
            continue

        raw_vehicle_id = runtime_data.get("vehicle_id")
        if raw_vehicle_id is None:
            continue

        try:
            vehicle_id = int(raw_vehicle_id)
        except (TypeError, ValueError):
            continue

        if vehicle_id < 1:
            continue

        vehicles.append((vehicle_id, str(entry_id), runtime_data))

    vehicles.sort(key=lambda item: item[0])
    return vehicles


def get_vehicle_runtime(
    hass: HomeAssistant,
    vehicle_id: int,
) -> tuple[str, dict[str, Any]] | None:
    """Return the loaded runtime for one vehicle id."""

    wanted = int(vehicle_id)
    for current_id, entry_id, runtime_data in iter_vehicle_runtimes(hass):
        if current_id == wanted:
            return entry_id, runtime_data
    return None


def get_selected_vehicle_id(
    hass: HomeAssistant,
    *,
    fallback: int | None = None,
) -> int | None:
    """Return the currently selected vehicle UI context."""

    domain_data = _domain_data(hass)
    raw_selected = domain_data.get(VEHICLE_CONTEXT_KEY)
    if raw_selected is not None:
        try:
            selected = int(raw_selected)
        except (TypeError, ValueError):
            selected = None
        if selected is not None and get_vehicle_runtime(hass, selected) is not None:
            return selected

    if fallback is not None:
        try:
            fallback_id = int(fallback)
        except (TypeError, ValueError):
            fallback_id = None
        if fallback_id is not None and get_vehicle_runtime(hass, fallback_id) is not None:
            domain_data[VEHICLE_CONTEXT_KEY] = fallback_id
            return fallback_id

    vehicles = iter_vehicle_runtimes(hass)
    if not vehicles:
        return None

    selected = vehicles[0][0]
    domain_data[VEHICLE_CONTEXT_KEY] = selected
    return selected


def set_selected_vehicle_id(
    hass: HomeAssistant,
    vehicle_id: int,
) -> int:
    """Set the shared Ford Triplog vehicle UI context."""

    selected = int(vehicle_id)
    if get_vehicle_runtime(hass, selected) is None:
        raise ValueError(f"Ford Triplog vehicle {selected} is not loaded")

    domain_data = _domain_data(hass)
    domain_data[VEHICLE_CONTEXT_KEY] = selected
    domain_data[VEHICLE_CONTEXT_MANUAL_KEY] = True
    return selected


def ensure_vehicle_context(
    hass: HomeAssistant,
    vehicle_id: int,
) -> int:
    """Initialize the shared vehicle context without overriding a manual choice."""

    domain_data = _domain_data(hass)
    manual = bool(domain_data.get(VEHICLE_CONTEXT_MANUAL_KEY, False))
    selected = get_selected_vehicle_id(hass, fallback=vehicle_id)

    # During startup ConfigEntries are not guaranteed to load in vehicle-id
    # order. Until a user explicitly changes the context, prefer the lowest
    # loaded id so legacy vehicle 1 remains the deterministic default.
    if not manual:
        vehicles = iter_vehicle_runtimes(hass)
        if vehicles:
            selected = vehicles[0][0]
            domain_data[VEHICLE_CONTEXT_KEY] = selected

    return int(selected if selected is not None else vehicle_id)


def remove_vehicle_context_if_unloaded(
    hass: HomeAssistant,
    vehicle_id: int,
) -> None:
    """Move the context away from an unloaded vehicle when needed."""

    domain_data = _domain_data(hass)
    try:
        selected = int(domain_data.get(VEHICLE_CONTEXT_KEY))
    except (TypeError, ValueError):
        selected = None

    if selected != int(vehicle_id):
        return

    domain_data.pop(VEHICLE_CONTEXT_KEY, None)
    domain_data.pop(VEHICLE_CONTEXT_MANUAL_KEY, None)
    get_selected_vehicle_id(hass)
