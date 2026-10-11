"""Isolated dynamic tariff simulator for the TEST Dynamic vehicle.

This does not create production charging sessions. Each step uses the
current HA price state; the caller may set the demo sensor between steps.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from math import isfinite

import voluptuous as vol
from homeassistant.exceptions import ServiceValidationError
from homeassistant.core import SupportsResponse

from .zone_tariff_storage import ZoneTariffStorage

SERVICE = 'simulate_dynamic_charging'
SCHEMA = vol.Schema({
    vol.Required('action'): vol.In(['start', 'step', 'stop', 'status', 'reset']),
    vol.Optional('vehicle_id'): vol.Coerce(int),
    vol.Optional('zone_id', default='zone.home'): str,
    vol.Optional('energy_kwh', default=1.0): vol.All(vol.Coerce(float), vol.Range(min=0.000001)),
})


def _read_test_vehicle(db_path, vehicle_id):
    with sqlite3.connect(db_path) as db:
        db.row_factory = sqlite3.Row
        if vehicle_id is not None:
            row = db.execute('SELECT vehicle_id,name FROM vehicles WHERE vehicle_id=?', (vehicle_id,)).fetchone()
        else:
            rows = db.execute("SELECT vehicle_id,name FROM vehicles WHERE lower(trim(name)) LIKE 'test dynamic%'").fetchall()
            if len(rows) != 1:
                raise ServiceValidationError('TEST Dynamic vehicle not uniquely found; specify vehicle_id')
            row = rows[0]
        if row is None or not str(row['name']).strip().casefold().startswith('test dynamic'):
            raise ServiceValidationError('Simulation restricted to vehicle named TEST Dynamic')
        return int(row['vehicle_id'])


def register(hass):
    if hass.services.has_service('ford_triplog', SERVICE):
        return
    sessions = {}
    storage = ZoneTariffStorage(hass)

    async def handler(call):
        action = call.data['action']
        zone_id = call.data.get('zone_id', 'zone.home')
        requested_id = call.data.get('vehicle_id')
        vehicle_id = await hass.async_add_executor_job(_read_test_vehicle, storage.database.db_path, requested_id)
        key = (vehicle_id, zone_id)
        if action == 'reset':
            sessions.pop(key, None)
            return {'action': action, 'vehicle_id': vehicle_id, 'zone_id': zone_id, 'reset': True}
        if action == 'start':
            tariff = await storage.async_load_vehicle(vehicle_id, zone_id)
            if not tariff or tariff.get('mode') != 'dynamic':
                raise ServiceValidationError('TEST Dynamic has no dynamic tariff for this zone')
            if not tariff.get('price_sensor'):
                raise ServiceValidationError('Dynamic price sensor missing')
            sessions[key] = {'tariff': tariff, 'steps': [], 'closed': False}
        session = sessions.get(key)
        if session is None:
            raise ServiceValidationError('No simulation session; call start first')
        if action == 'step':
            if session['closed']:
                raise ServiceValidationError('Simulation already stopped')
            sensor_id = session['tariff']['price_sensor']
            state = hass.states.get(sensor_id)
            if state is None or state.state in ('unknown', 'unavailable'):
                raise ServiceValidationError(f'Price sensor unavailable: {sensor_id}')
            try:
                price = float(state.state)
            except (ValueError, TypeError) as exc:
                raise ServiceValidationError('Price sensor is not numeric') from exc
            if not isfinite(price) or price < 0:
                raise ServiceValidationError('Invalid price sensor value')
            sensor_unit = str(state.attributes.get('unit_of_measurement') or '').upper()
            currency = session['tariff']['currency'].upper()
            if sensor_unit and not sensor_unit.startswith(currency + '/'):
                raise ServiceValidationError(f'Currency mismatch: {sensor_unit} vs {currency}/kWh')
            energy = float(call.data.get('energy_kwh', 1.0))
            session['steps'].append({'at': datetime.now(timezone.utc).isoformat(), 'energy_kwh': energy, 'price_per_kwh': price, 'cost': round(energy * price, 8), 'sensor': sensor_id})
        if action == 'stop':
            session['closed'] = True
        steps = session['steps']
        return {
            'action': action, 'vehicle_id': vehicle_id, 'zone_id': zone_id,
            'currency': session['tariff']['currency'], 'price_sensor': session['tariff']['price_sensor'],
            'closed': session['closed'], 'total_energy_kwh': round(sum(s['energy_kwh'] for s in steps), 6),
            'total_cost': round(sum(s['cost'] for s in steps), 6), 'steps': list(steps),
            'note': 'Isolated in-memory simulation; no real charging records changed',
        }

    hass.services.async_register('ford_triplog', SERVICE, handler, schema=SCHEMA, supports_response=SupportsResponse.ONLY)
