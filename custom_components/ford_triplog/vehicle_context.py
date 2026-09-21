"""Shared multi-vehicle UI context for Ford Triplog."""

from __future__ import annotations

from typing import Any, Callable

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import (
    async_dispatcher_connect,
    async_dispatcher_send,
)

from .const import (
    CONF_VEHICLE_NAME,
    DOMAIN,
    SIGNAL_VEHICLE_CONTEXT_UPDATED,
    SIGNAL_VEHICLE_DATA_UPDATED,
    SIGNAL_VEHICLE_LIST_UPDATED,
)


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


def vehicle_display_name(
    hass: HomeAssistant,
    vehicle_id: int,
    runtime_data: dict[str, Any] | None = None,
) -> str:
    """Return one stable user-facing vehicle name."""

    if runtime_data is None:
        resolved = get_vehicle_runtime(hass, vehicle_id)
        runtime_data = resolved[1] if resolved is not None else {}
        entry_id = resolved[0] if resolved is not None else None
    else:
        entry_id = next(
            (
                entry_id
                for current_id, entry_id, current_runtime in iter_vehicle_runtimes(hass)
                if current_id == int(vehicle_id) and current_runtime is runtime_data
            ),
            None,
        )

    vehicle = runtime_data.get("vehicle") or {}
    config = runtime_data.get("config") or {}
    entry = hass.config_entries.async_get_entry(entry_id) if entry_id else None

    return str(
        config.get(CONF_VEHICLE_NAME)
        or vehicle.get("name")
        or vehicle.get("model")
        or (entry.title if entry is not None else "")
        or f"Vehicle {int(vehicle_id)}"
    )


def vehicle_option_map(hass: HomeAssistant) -> dict[str, int]:
    """Return unique display labels mapped to vehicle ids."""

    raw: list[tuple[int, str]] = [
        (vehicle_id, vehicle_display_name(hass, vehicle_id, runtime_data))
        for vehicle_id, _entry_id, runtime_data in iter_vehicle_runtimes(hass)
    ]

    counts: dict[str, int] = {}
    for _vehicle_id, label in raw:
        counts[label] = counts.get(label, 0) + 1

    options: dict[str, int] = {}
    for vehicle_id, label in raw:
        display = label if counts.get(label, 0) == 1 else f"{label} (ID {vehicle_id})"
        options[display] = vehicle_id

    return options


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
    """Set the shared Ford Triplog vehicle UI context and notify entities."""

    selected = int(vehicle_id)
    if get_vehicle_runtime(hass, selected) is None:
        raise ValueError(f"Ford Triplog vehicle {selected} is not loaded")

    domain_data = _domain_data(hass)
    previous = domain_data.get(VEHICLE_CONTEXT_KEY)
    try:
        previous_id = int(previous) if previous is not None else None
    except (TypeError, ValueError):
        previous_id = None

    domain_data[VEHICLE_CONTEXT_KEY] = selected
    domain_data[VEHICLE_CONTEXT_MANUAL_KEY] = True

    if previous_id != selected:
        async_dispatcher_send(
            hass,
            SIGNAL_VEHICLE_CONTEXT_UPDATED,
            selected,
        )

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



def notify_vehicle_list_updated(hass: HomeAssistant) -> None:
    """Notify shared UI entities that the loaded vehicle list changed."""

    async_dispatcher_send(hass, SIGNAL_VEHICLE_LIST_UPDATED)

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
    replacement = get_selected_vehicle_id(hass)
    if replacement is not None:
        async_dispatcher_send(
            hass,
            SIGNAL_VEHICLE_CONTEXT_UPDATED,
            int(replacement),
        )


class VehicleRuntimeProxy:
    """Delegate object access to the currently selected vehicle runtime."""

    def __init__(
        self,
        hass: HomeAssistant,
        runtime_key: str,
        fallback_entry_id: str,
    ) -> None:
        self.hass = hass
        self.runtime_key = runtime_key
        self.fallback_entry_id = fallback_entry_id

    def _runtime_data(self) -> dict[str, Any]:
        fallback_runtime = _domain_data(self.hass).get(self.fallback_entry_id, {})
        fallback_vehicle_id = None
        if isinstance(fallback_runtime, dict):
            try:
                fallback_vehicle_id = int(fallback_runtime.get("vehicle_id"))
            except (TypeError, ValueError):
                fallback_vehicle_id = None

        selected = get_selected_vehicle_id(
            self.hass,
            fallback=fallback_vehicle_id,
        )
        if selected is not None:
            resolved = get_vehicle_runtime(self.hass, selected)
            if resolved is not None:
                return resolved[1]

        if isinstance(fallback_runtime, dict):
            return fallback_runtime
        return {}

    def _target(self) -> Any:
        runtime_data = self._runtime_data()
        target = runtime_data.get(self.runtime_key)
        if target is None:
            raise AttributeError(
                f"Ford Triplog runtime object {self.runtime_key!r} is unavailable"
            )
        return target

    def __getattr__(self, name: str) -> Any:
        return getattr(self._target(), name)


class CoordinatorVehicleRuntimeProxy(VehicleRuntimeProxy):
    """Coordinator proxy with listeners following the selected vehicle."""

    def __init__(self, hass: HomeAssistant, fallback_entry_id: str) -> None:
        super().__init__(hass, "coordinator", fallback_entry_id)

    def async_add_listener(
        self,
        update_callback: Callable[[], None],
    ) -> Callable[[], None]:
        """Listen for selected-vehicle data and context changes."""

        @callback
        def _handle_vehicle_data(vehicle_id: int, *_args: Any) -> None:
            selected = get_selected_vehicle_id(self.hass)
            try:
                updated_vehicle = int(vehicle_id)
            except (TypeError, ValueError):
                return
            if selected is not None and updated_vehicle == int(selected):
                update_callback()

        @callback
        def _handle_context_change(_vehicle_id: int, *_args: Any) -> None:
            update_callback()

        remove_data = async_dispatcher_connect(
            self.hass,
            SIGNAL_VEHICLE_DATA_UPDATED,
            _handle_vehicle_data,
        )
        remove_context = async_dispatcher_connect(
            self.hass,
            SIGNAL_VEHICLE_CONTEXT_UPDATED,
            _handle_context_change,
        )

        def _remove() -> None:
            remove_data()
            remove_context()

        return _remove
