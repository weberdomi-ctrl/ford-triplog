"""Home Assistant sidebar and archive access for Ford Triplog."""

from asyncio import Lock
from datetime import date
from math import isfinite
from pathlib import Path

import voluptuous as vol
from homeassistant.components import frontend, panel_custom, websocket_api
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .charge import Charge
from .const import BUILD, DOMAIN
from .journey import build_pause_id

_PANEL_PATH = "ford-triplog-logbook"
_SCRIPT_PATH = "/ford_triplog/logbook.js"
_API_REGISTERED = "_logbook_api_registered"


def _vehicles(hass):
    return {
        entry.entry_id: entry.title
        for entry in hass.config_entries.async_entries(DOMAIN)
        if "charge_manager" in hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
    }


def _timestamp(value, *, local=False):
    try:
        parsed = dt_util.parse_datetime(value or "")
    except (TypeError, ValueError):
        return None
    if parsed is not None and parsed.tzinfo is None:
        return parsed.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE if local else dt_util.UTC)
    return parsed


@websocket_api.require_admin
@websocket_api.websocket_command({
    vol.Required("type"): "ford_triplog/logbook",
    vol.Optional("entry_id"): str,
    vol.Optional("date"): str,
})
@websocket_api.async_response
async def async_logbook(hass, connection, msg):
    """Return selectable vehicles and one day's archived entries."""
    vehicles = _vehicles(hass)
    entry_id = msg.get("entry_id")
    if entry_id is not None and entry_id not in vehicles:
        connection.send_error(msg["id"], "not_found", "Vehicle is unavailable")
        return
    try:
        selected_date = date.fromisoformat(msg.get("date", dt_util.now().date().isoformat()))
    except ValueError:
        connection.send_error(msg["id"], "invalid_format", "Invalid date")
        return
    entry_id = entry_id or next(iter(vehicles), None)
    rows = []
    if entry_id:
        runtime = hass.data[DOMAIN][entry_id]

        def add_row(kind, start_time, **details):
            start = _timestamp(start_time)
            if start and dt_util.as_local(start).date() == selected_date:
                rows.append((start.timestamp(), {
                    "type": kind, "start_time": start.isoformat(), **details,
                }))

        for trip in await runtime["history"].get_all_trips():
            add_row("trip", trip.get("start_time"), distance_km=trip.get("distance_km"))

        for charge in await runtime["charge_manager"].async_get_charges():
            add_row(
                "charge", charge.start_time,
                charge_id=charge.charge_id,
                location=charge.manual_location,
                detected_location=charge.charging_site_name,
                note=charge.notes,
                energy_kwh=charge.energy_billed_kwh
                if charge.energy_billed_kwh is not None else charge.energy_added_kwh,
                cost_total=charge.cost_total,
                currency=charge.currency,
            )

        for journey in await runtime["journey_storage"].get_all_journeys():
            for current, following in zip(journey.items, journey.items[1:]):
                start = _timestamp(current.end_time)
                end = _timestamp(following.start_time)
                if not start or not end or end <= start:
                    continue
                duration = (end - start).total_seconds()
                if duration <= 180 and "charge" in (current.item_type, following.item_type):
                    continue
                pause_id = build_pause_id(current.item_id, following.item_id)
                override = journey.pause_overrides.get(pause_id, {})
                add_row(
                    "pause", current.end_time,
                    journey_id=journey.journey_id,
                    pause_id=pause_id,
                    duration_seconds=duration,
                    detected_location=current.end_location or following.start_location,
                    details=override,
                )

    connection.send_result(msg["id"], {
        "vehicles": vehicles,
        "entry_id": entry_id,
        "date": selected_date.isoformat(),
        "rows": [row for _, row in sorted(rows, key=lambda item: item[0])],
    })


@websocket_api.require_admin
@websocket_api.websocket_command({
    vol.Required("type"): "ford_triplog/logbook/add_charge",
    vol.Required("entry_id"): str,
    vol.Required("charge_id"): vol.Match(r"manual_[a-f0-9]{32}$"),
    vol.Required("start_time"): str,
    vol.Required("end_time"): str,
    vol.Required("energy_kwh"): vol.Coerce(float),
    vol.Optional("location", default=""): vol.All(str, vol.Length(max=200)),
    vol.Optional("note", default=""): vol.All(str, vol.Length(max=2000)),
    vol.Optional("cost_total"): vol.Coerce(float),
    vol.Optional("currency"): vol.Match(r"[A-Z]{3}$"),
})
@websocket_api.async_response
async def async_add_charge(hass, connection, msg):
    """Archive a manually entered charging session."""
    entry_id = msg["entry_id"]
    if entry_id not in _vehicles(hass):
        connection.send_error(msg["id"], "not_found", "Vehicle is unavailable")
        return

    start = _timestamp(msg["start_time"], local=True)
    end = _timestamp(msg["end_time"], local=True)
    energy = msg["energy_kwh"]
    cost = msg.get("cost_total")
    currency = msg.get("currency")
    if (
        not start or not end or dt_util.as_utc(end) <= dt_util.as_utc(start)
        or end > dt_util.utcnow()
        or not isfinite(energy) or energy <= 0
        or (cost is not None and (not isfinite(cost) or cost < 0 or currency is None))
    ):
        connection.send_error(msg["id"], "invalid_format", "Check times, energy and cost")
        return

    manager = hass.data[DOMAIN][entry_id]["charge_manager"]
    charge = Charge()
    charge.charge_id = msg["charge_id"]
    charge.created = dt_util.utcnow().isoformat()
    charge.start_time = start.isoformat()
    charge.end_time = end.isoformat()
    charge.data_source = "manual"
    charge.energy_billed_kwh = energy
    charge.energy_billed_source = "manual"
    charge.manual_location = msg["location"].strip() or None
    charge.notes = msg["note"].strip() or None
    if cost is not None:
        charge.cost_total = cost
        charge.currency = currency
        charge.cost_source = "manual"
        charge.cost_verified = True
        charge.finalize_costs()

    if not await manager.async_archive_manual_charge(charge):
        connection.send_error(msg["id"], "archive_failed", "Charging session could not be saved")
        return
    connection.send_result(msg["id"], {"charge_id": charge.charge_id})


@websocket_api.require_admin
@websocket_api.websocket_command({
    vol.Required("type"): "ford_triplog/logbook/edit_charge",
    vol.Required("entry_id"): str,
    vol.Required("charge_id"): vol.All(str, vol.Length(min=1)),
    vol.Required("location"): vol.All(str, vol.Length(max=200)),
    vol.Required("note"): vol.All(str, vol.Length(max=2000)),
    vol.Optional("cost_total"): vol.Any(None, vol.Coerce(float)),
    vol.Optional("currency"): vol.Any(None, vol.Match(r"[A-Z]{3}$")),
})
@websocket_api.async_response
async def async_edit_charge(hass, connection, msg):
    """Edit an archived charge without dropping its receipt or energy data."""
    entry_id = msg["entry_id"]
    if entry_id not in _vehicles(hass):
        connection.send_error(msg["id"], "not_found", "Vehicle is unavailable")
        return
    manager = hass.data[DOMAIN][entry_id]["charge_manager"]
    charge = await manager.async_get_charge(msg["charge_id"])
    if charge is None:
        connection.send_error(msg["id"], "not_found", "Charging session is unavailable")
        return

    charge.manual_location = msg["location"].strip() or None
    charge.notes = msg["note"].strip() or None
    if "cost_total" in msg:
        cost = msg["cost_total"]
        currency = msg.get("currency")
        if cost is not None and (not isfinite(cost) or cost < 0 or not currency):
            connection.send_error(msg["id"], "invalid_format", "Check the total and currency")
            return
        charge.begin_manual_cost_edit()
        # A manual total supersedes the component breakdown.
        charge.energy_cost = charge.session_fee = charge.time_fee = None
        charge.blocking_fee = charge.parking_fee = charge.other_cost = None
        charge.cost_total = cost
        charge.currency = currency if cost is not None else None
        charge.cost_source = "manual" if cost is not None else "none"
        charge.cost_verified = cost is not None
        charge.finalize_costs()

    result = await manager.async_update_charge(charge)
    if not result.updated:
        connection.send_error(msg["id"], "archive_failed", "Charging session could not be saved")
        return
    connection.send_result(msg["id"])


async def async_register_logbook(hass: HomeAssistant) -> None:
    """Register the shared sidebar once for all configured vehicles."""
    domain_data = hass.data[DOMAIN]
    if "_logbook_registration_lock" not in domain_data:
        domain_data["_logbook_registration_lock"] = Lock()
    async with domain_data["_logbook_registration_lock"]:
        if not domain_data.get(_API_REGISTERED):
            script = Path(__file__).parent / "frontend" / "logbook.js"
            await hass.http.async_register_static_paths([
                StaticPathConfig(_SCRIPT_PATH, str(script), cache_headers=False)
            ])
            websocket_api.async_register_command(hass, async_logbook)
            websocket_api.async_register_command(hass, async_add_charge)
            websocket_api.async_register_command(hass, async_edit_charge)
            domain_data[_API_REGISTERED] = True
        if not domain_data.get("_logbook_panel_registered"):
            await panel_custom.async_register_panel(
                hass,
                webcomponent_name="ford-triplog-logbook",
                frontend_url_path=_PANEL_PATH,
                sidebar_title="Triplog",
                sidebar_icon="mdi:book-open-page-variant",
                module_url=f"{_SCRIPT_PATH}?v={BUILD}",
                require_admin=True,
                trust_external=True,
            )
            domain_data["_logbook_panel_registered"] = True


def async_remove_logbook_if_unused(hass: HomeAssistant) -> None:
    """Remove the sidebar when the final vehicle is unloaded."""
    domain_data = hass.data[DOMAIN]
    if not _vehicles(hass) and domain_data.pop("_logbook_panel_registered", False):
        frontend.async_remove_panel(hass, _PANEL_PATH)
