"""SQLite-backed, isolated dynamic-tariff simulator for TEST Dynamic.

Simulation tables are separate from real charges. No vehicle entities required.
"""
from __future__ import annotations

import json
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


def _transaction(db_path, vehicle_id, zone_id, action, tariff=None, step=None):
    """One SQLite transaction per command, including finalized-session protection."""
    with sqlite3.connect(db_path, timeout=15) as db:
        db.execute('''CREATE TABLE IF NOT EXISTS dynamic_sim_sessions (
            vehicle_id INTEGER NOT NULL, zone_id TEXT NOT NULL,
            tariff_json TEXT NOT NULL, started_at TEXT NOT NULL,
            closed INTEGER NOT NULL DEFAULT 0, closed_at TEXT,
            PRIMARY KEY(vehicle_id, zone_id))''')
        db.execute('''CREATE TABLE IF NOT EXISTS dynamic_sim_steps (
            step_id INTEGER PRIMARY KEY AUTOINCREMENT,
            vehicle_id INTEGER NOT NULL, zone_id TEXT NOT NULL,
            at TEXT NOT NULL, energy_kwh REAL NOT NULL,
            price_per_kwh REAL NOT NULL, cost REAL NOT NULL, sensor TEXT NOT NULL)''')
        key = (vehicle_id, zone_id)
        if action == 'reset':
            db.execute('DELETE FROM dynamic_sim_steps WHERE vehicle_id=? AND zone_id=?', key)
            db.execute('DELETE FROM dynamic_sim_sessions WHERE vehicle_id=? AND zone_id=?', key)
            return {'action': action, 'vehicle_id': vehicle_id, 'zone_id': zone_id, 'reset': True}
        if action == 'start':
            if tariff is None:
                raise ServiceValidationError('Dynamic tariff missing')
            db.execute('DELETE FROM dynamic_sim_steps WHERE vehicle_id=? AND zone_id=?', key)
            db.execute('''INSERT INTO dynamic_sim_sessions
                (vehicle_id,zone_id,tariff_json,started_at,closed,closed_at)
                VALUES (?,?,?,?,0,NULL)
                ON CONFLICT(vehicle_id,zone_id) DO UPDATE SET
                tariff_json=excluded.tariff_json, started_at=excluded.started_at,
                closed=0, closed_at=NULL''', (*key, json.dumps(tariff), datetime.now(timezone.utc).isoformat()))
        row = db.execute('SELECT tariff_json,started_at,closed FROM dynamic_sim_sessions WHERE vehicle_id=? AND zone_id=?', key).fetchone()
        if row is None:
            raise ServiceValidationError('No simulation session; call start first')
        saved_tariff = json.loads(row[0])
        if action == 'step':
            if row[2]:
                raise ServiceValidationError('Simulation already stopped')
            if step is None:
                raise ServiceValidationError('Price sample missing')
            if step['sensor'] != saved_tariff['price_sensor']:
                raise ServiceValidationError('Configured price sensor changed; restart simulation')
            db.execute('''INSERT INTO dynamic_sim_steps
                (vehicle_id,zone_id,at,energy_kwh,price_per_kwh,cost,sensor)
                VALUES (?,?,?,?,?,?,?)''', (*key, step['at'], step['energy_kwh'], step['price_per_kwh'], step['cost'], step['sensor']))
        if action == 'stop' and not row[2]:
            db.execute('UPDATE dynamic_sim_sessions SET closed=1,closed_at=? WHERE vehicle_id=? AND zone_id=?',
                       (datetime.now(timezone.utc).isoformat(), *key))
        rows = db.execute('''SELECT at,energy_kwh,price_per_kwh,cost,sensor FROM dynamic_sim_steps
            WHERE vehicle_id=? AND zone_id=? ORDER BY step_id''', key).fetchall()
        steps = [dict(zip(('at','energy_kwh','price_per_kwh','cost','sensor'), r)) for r in rows]
        closed = bool(db.execute('SELECT closed FROM dynamic_sim_sessions WHERE vehicle_id=? AND zone_id=?', key).fetchone()[0])
        return {
            'action': action, 'vehicle_id': vehicle_id, 'zone_id': zone_id,
            'currency': saved_tariff['currency'], 'price_sensor': saved_tariff['price_sensor'],
            'closed': closed, 'started_at': row[1],
            'total_energy_kwh': round(sum(s['energy_kwh'] for s in steps), 6),
            'total_cost': round(sum(s['cost'] for s in steps), 6), 'steps': steps,
            'note': 'Persistent SQLite simulation; production charging records unchanged',
        }


def register(hass):
    if hass.services.has_service('ford_triplog', SERVICE):
        return
    storage = ZoneTariffStorage(hass)

    async def handler(call):
        action = call.data['action']
        zone_id = call.data.get('zone_id', 'zone.home')
        vehicle_id = await hass.async_add_executor_job(
            _read_test_vehicle, storage.database.db_path, call.data.get('vehicle_id'))
        tariff = None
        step = None
        if action == 'start':
            tariff = await storage.async_load_vehicle(vehicle_id, zone_id)
            if not tariff or tariff.get('mode') != 'dynamic':
                raise ServiceValidationError('TEST Dynamic has no dynamic tariff for this zone')
            if not tariff.get('price_sensor'):
                raise ServiceValidationError('Dynamic price sensor missing')
        if action == 'step':
            # Read the current sensor for this configured vehicle/zone. The transaction
            # checks the sensor matches the snapshot stored at session start.
            current_tariff = await storage.async_load_vehicle(vehicle_id, zone_id)
            if not current_tariff or current_tariff.get('mode') != 'dynamic':
                raise ServiceValidationError('Dynamic tariff not configured')
            sensor_id = current_tariff.get('price_sensor')
            state = hass.states.get(sensor_id) if sensor_id else None
            if state is None or state.state in ('unknown', 'unavailable'):
                raise ServiceValidationError(f'Price sensor unavailable: {sensor_id}')
            try:
                price = float(state.state)
            except (ValueError, TypeError) as exc:
                raise ServiceValidationError('Price sensor is not numeric') from exc
            if not isfinite(price) or price < 0:
                raise ServiceValidationError('Invalid price sensor value')
            unit = str(state.attributes.get('unit_of_measurement') or '').upper()
            currency = str(current_tariff.get('currency') or 'CHF').upper()
            if unit and not unit.startswith(currency + '/'):
                raise ServiceValidationError(f'Currency mismatch: {unit} vs {currency}/kWh')
            energy = float(call.data.get('energy_kwh', 1.0))
            step = {'at': datetime.now(timezone.utc).isoformat(), 'energy_kwh': energy,
                    'price_per_kwh': price, 'cost': round(energy * price, 8), 'sensor': sensor_id}
        return await hass.async_add_executor_job(
            _transaction, storage.database.db_path, vehicle_id, zone_id, action, tariff, step)

    hass.services.async_register('ford_triplog', SERVICE, handler, schema=SCHEMA, supports_response=SupportsResponse.ONLY)
