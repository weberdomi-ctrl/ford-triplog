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
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import SIGNAL_DYNAMIC_TEST_ENERGY_UPDATED
from .external_energy_meter import read_energy_kwh, charging_energy_kwh
from .dynamic_energy_pricing import calculate_dynamic_pricing

from .zone_tariff_storage import ZoneTariffStorage

SERVICE = 'simulate_dynamic_charging'
SCHEMA = vol.Schema({
    vol.Required('action'): vol.In(['start', 'step', 'meter_adjust', 'stop', 'status', 'reset', 'publish']),
    vol.Optional('vehicle_id'): vol.Coerce(int),
    vol.Optional('zone_id', default='zone.home'): str,
    vol.Optional('energy_kwh'): vol.All(vol.Coerce(float), vol.Range(min=0.000001)),
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
        # Additive migration for existing simulator databases.
        cols = {r[1] for r in db.execute('PRAGMA table_info(dynamic_sim_sessions)')}
        for col, typ in [('meter_start', 'REAL'), ('meter_end', 'REAL'),
                         ('meter_kind', 'TEXT'), ('meter_sensor', 'TEXT'),
                         ('meter_energy', 'REAL'), ('meter_adjustment', 'REAL NOT NULL DEFAULT 0')]:
            if col not in cols:
                db.execute(f'ALTER TABLE dynamic_sim_sessions ADD COLUMN {col} {typ}')
        db.execute('''CREATE TABLE IF NOT EXISTS dynamic_sim_steps (
            step_id INTEGER PRIMARY KEY AUTOINCREMENT,
            vehicle_id INTEGER NOT NULL, zone_id TEXT NOT NULL,
            at TEXT NOT NULL, energy_kwh REAL NOT NULL,
            price_per_kwh REAL NOT NULL, cost REAL NOT NULL, sensor TEXT NOT NULL)''')
        key = (vehicle_id, zone_id)
        if action == 'meter_snapshot':
            # Snapshot is stored in the same SQLite DB and keyed to the
            # active/closed session; no real vehicle charge is touched.
            if step is None:
                raise ServiceValidationError('Missing simulated meter reading')
            row = db.execute('SELECT closed, meter_start, meter_kind, meter_sensor, meter_end FROM dynamic_sim_sessions WHERE vehicle_id=? AND zone_id=?', key).fetchone()
            if not row:
                raise ServiceValidationError('Simulation session missing')
            if step['phase'] == 'start' and not row[0]:
                db.execute('UPDATE dynamic_sim_sessions SET meter_sensor=?,meter_start=?,meter_kind=?,meter_end=NULL,meter_energy=NULL WHERE vehicle_id=? AND zone_id=?',
                           (step['sensor'], step['value'], step['kind'], *key))
            elif step['phase'] == 'stop' and row[0] and row[3] == step['sensor'] and row[4] is None:
                measured = charging_energy_kwh(row[1], step['value'], row[2]) if row[2] == step['kind'] else None
                db.execute('UPDATE dynamic_sim_sessions SET meter_end=?,meter_energy=? WHERE vehicle_id=? AND zone_id=?',
                           (step['value'], measured, *key))
            return {'action': 'meter_snapshot', 'phase': step['phase'], 'meter_energy_kwh': measured if step['phase'] == 'stop' else None}
        if action == 'meter_adjust':
            # Test-only network energy adjustment, separate from vehicle energy
            # and from the dynamic price steps. Useful to simulate AC losses.
            row = db.execute('SELECT closed FROM dynamic_sim_sessions WHERE vehicle_id=? AND zone_id=?', key).fetchone()
            if row is None:
                raise ServiceValidationError('No simulation session; call start first')
            if row[0]:
                raise ServiceValidationError('Simulation already stopped')
            if step is None:
                raise ServiceValidationError('Meter adjustment missing')
            db.execute('''UPDATE dynamic_sim_sessions
                SET meter_adjustment=meter_adjustment+?
                WHERE vehicle_id=? AND zone_id=?''', (step['energy_kwh'], *key))
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
                closed=0, closed_at=NULL, meter_start=NULL, meter_end=NULL,
                meter_kind=NULL, meter_sensor=NULL, meter_energy=NULL, meter_adjustment=0''', (*key, json.dumps(tariff), datetime.now(timezone.utc).isoformat()))
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
        just_closed = action == 'stop' and not row[2]
        if just_closed:
            db.execute('UPDATE dynamic_sim_sessions SET closed=1,closed_at=? WHERE vehicle_id=? AND zone_id=?',
                       (datetime.now(timezone.utc).isoformat(), *key))
        if action == 'publish':
            if not row[2]:
                raise ServiceValidationError('Stop the simulation before publishing')
            # A stable, test-only charge ID avoids collisions with real sessions.
            charge_id = 'SIMDYN_' + str(vehicle_id) + '_' + row[1].replace('-', '').replace(':', '').replace('+', '_').replace('.', '_')
            existing = db.execute('SELECT data FROM charges WHERE vehicle_id=? AND charge_id=?',
                                  (vehicle_id, charge_id)).fetchone()
            if existing is not None:
                saved = json.loads(existing[0])
                return {'action': 'publish', 'vehicle_id': vehicle_id, 'zone_id': zone_id,
                        'charge_id': charge_id, 'already_published': True,
                        'total_energy_kwh': saved.get('energy_added_kwh'),
                        'meter_total_energy_kwh': saved.get('energy_billed_kwh'),
                        'energy_billed_kwh': saved.get('energy_billed_kwh'),
                        'energy_billed_source': saved.get('energy_billed_source'),
                        'total_cost': saved.get('cost_total'), 'currency': saved.get('currency'),
                        'meter_pricing_applied': saved.get('dynamic_meter_pricing_applied', False),
                        'meter_allocation_method': saved.get('dynamic_meter_allocation_method'),
                        'excluded_from_statistics': True}
            step_rows = db.execute('''SELECT at,energy_kwh,price_per_kwh,cost,sensor FROM dynamic_sim_steps
                WHERE vehicle_id=? AND zone_id=? ORDER BY step_id''', key).fetchall()
            if not step_rows:
                raise ServiceValidationError('Cannot publish a simulation without energy steps')
            original_steps = [dict(zip(('at','energy_kwh','price_per_kwh','cost','sensor'), r)) for r in step_rows]
            closed_at = db.execute('SELECT closed_at FROM dynamic_sim_sessions WHERE vehicle_id=? AND zone_id=?', key).fetchone()[0]
            meter_row = db.execute('SELECT meter_energy, meter_sensor, meter_start, meter_end, meter_kind FROM dynamic_sim_sessions WHERE vehicle_id=? AND zone_id=?', key).fetchone()
            meter_energy = float(meter_row[0]) if meter_row and meter_row[0] is not None else None
            priced = calculate_dynamic_pricing(original_steps, meter_energy)
            total_energy = priced['total_energy_kwh']
            billed = priced['energy_billed_kwh']
            total_cost = priced['total_cost']
            billed_source = 'meter' if priced['meter_pricing_applied'] else 'estimated'
            effective_price = total_cost / billed
            # This is an explicitly labelled test charge, excluded from statistics.
            payload = {
                'charge_id': charge_id, 'created': row[1], 'start_time': row[1],
                'end_time': closed_at, 'detected_start_time': row[1],
                'detected_end_time': closed_at, 'charging_type': 'AC_BASIC',
                'data_source': 'dynamic_simulation', 'energy_added_kwh': total_energy,
                'energy_source': 'simulation', 'energy_billed_kwh': billed,
                'energy_billed_source': billed_source,
                'external_meter_entity_id': meter_row[1] if meter_row else None,
                'external_meter_start_kwh': meter_row[2] if meter_row else None,
                'external_meter_end_kwh': meter_row[3] if meter_row else None,
                'external_meter_kind': meter_row[4] if meter_row else None,
                'energy_cost': total_cost,
                'cost_total': total_cost, 'currency': saved_tariff['currency'],
                'energy_price_per_kwh': effective_price,
                'effective_price_per_kwh': effective_price,
                'price_per_kwh': effective_price, 'cost_source': 'dynamic_simulation',
                'cost_finalized': True, 'cost_verified': False,
                'include_in_statistics': False, 'exclusion_reason': 'Test Dynamic simulation',
                'notes': 'TEST Dynamic – simulated dynamic tariff (' + zone_id + ')',
                'dynamic_price_steps': priced['steps'],
                'dynamic_vehicle_only_cost': priced['vehicle_only_cost'],
                'dynamic_meter_pricing_applied': priced['meter_pricing_applied'],
                'dynamic_meter_allocation_method': priced['meter_allocation_method'],
            }
            db.execute('INSERT INTO charges(vehicle_id,charge_id,data) VALUES(?,?,?)',
                       (vehicle_id, charge_id, json.dumps(payload, ensure_ascii=False)))
            return {'action': 'publish', 'vehicle_id': vehicle_id, 'zone_id': zone_id,
                    'charge_id': charge_id, 'already_published': False,
                    'total_energy_kwh': total_energy,
                    'meter_total_energy_kwh': billed if priced['meter_pricing_applied'] else total_energy,
                    'energy_billed_kwh': billed,
                    'energy_billed_source': billed_source, 'total_cost': total_cost,
                    'vehicle_only_cost': priced['vehicle_only_cost'],
                    'meter_pricing_applied': priced['meter_pricing_applied'],
                    'meter_allocation_method': priced['meter_allocation_method'],
                    'currency': saved_tariff['currency'], 'excluded_from_statistics': True}
        rows = db.execute('''SELECT at,energy_kwh,price_per_kwh,cost,sensor FROM dynamic_sim_steps
            WHERE vehicle_id=? AND zone_id=? ORDER BY step_id''', key).fetchall()
        steps = [dict(zip(('at','energy_kwh','price_per_kwh','cost','sensor'), r)) for r in rows]
        session_row = db.execute('''SELECT closed, meter_adjustment, meter_energy FROM dynamic_sim_sessions
            WHERE vehicle_id=? AND zone_id=?''', key).fetchone()
        closed = bool(session_row[0])
        meter_total = (round(float(session_row[2]), 6) if closed and session_row[2] is not None
                       else round(sum(s['energy_kwh'] for s in steps) + float(session_row[1] or 0), 6))
        # Use the captured, validated meter reading only after stop. An
        # unconfirmed live HA state must never overwrite the finalized result.
        priced = calculate_dynamic_pricing(steps, session_row[2] if closed else None)
        return {
            'action': action, 'vehicle_id': vehicle_id, 'zone_id': zone_id,
            'currency': saved_tariff['currency'], 'price_sensor': saved_tariff['price_sensor'],
            'closed': closed, 'just_closed': bool(just_closed), 'started_at': row[1],
            'total_energy_kwh': priced['total_energy_kwh'],
            'meter_total_energy_kwh': meter_total,
            'energy_billed_kwh': priced['energy_billed_kwh'] if priced['meter_pricing_applied'] else None,
            'total_cost': priced['total_cost'], 'vehicle_only_cost': priced['vehicle_only_cost'],
            'meter_pricing_applied': priced['meter_pricing_applied'],
            'meter_allocation_method': priced['meter_allocation_method'],
            'steps': priced['steps'],
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
        if action == 'meter_adjust':
            if 'energy_kwh' not in call.data:
                raise ServiceValidationError('energy_kwh required for meter_adjust')
            # The adjustment is an independent test meter increment; it does
            # not add FordPass energy or a price step to the charge.
            step = {'energy_kwh': float(call.data['energy_kwh'])}
        response = await hass.async_add_executor_job(
            _transaction, storage.database.db_path, vehicle_id, zone_id, action, tariff, step)
        # A test-only HA sensor mirrors the session meter; no production charge
        # or energy calculation is changed by this notification.
        if zone_id == 'zone.home':
            async_dispatcher_send(
                hass,
                SIGNAL_DYNAMIC_TEST_ENERGY_UPDATED,
                vehicle_id,
                float(response.get('meter_total_energy_kwh', response.get('total_energy_kwh')) or 0.0),
                action,
                bool(response.get('closed', False)),
            )
        if action == 'start' or (action == 'stop' and response.get('just_closed')):
            current_tariff = tariff if action == 'start' else await storage.async_load_vehicle(vehicle_id, zone_id)
            sensor_id = (current_tariff or {}).get('energy_sensor')
            if sensor_id and (current_tariff or {}).get('mode') == 'dynamic':
                state = hass.states.get(sensor_id)
                # The test-only meter must belong to this test vehicle.
                if state and state.attributes.get('test_only') and state.attributes.get('vehicle_id') not in (None, vehicle_id):
                    state = None
                reading = read_energy_kwh(state)
                if reading is not None:
                    value, kind = reading
                    await hass.async_add_executor_job(
                        _transaction, storage.database.db_path, vehicle_id, zone_id,
                        'meter_snapshot', None,
                        {'phase': action, 'sensor': sensor_id, 'value': value, 'kind': kind},
                    )
                    if action == 'stop':
                        updated = await hass.async_add_executor_job(
                            _transaction, storage.database.db_path, vehicle_id, zone_id, 'status'
                        )
                        updated['action'] = 'stop'
                        updated['just_closed'] = response.get('just_closed', False)
                        response = updated
        return response

    hass.services.async_register('ford_triplog', SERVICE, handler, schema=SCHEMA, supports_response=SupportsResponse.ONLY)
