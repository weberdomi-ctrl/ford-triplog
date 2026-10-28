"""Test-only Home Assistant energy meter for TEST Dynamic charging sessions.

The meter is deliberately independent of real vehicles and charges. It mirrors
"simulate_dynamic_charging" steps, persists through the simulator's SQLite
storage, and resets on each new simulated charging session.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import SIGNAL_DYNAMIC_TEST_ENERGY_UPDATED


def _restore_test_energy(db_path: Path) -> dict:
    """Restore the most recent zone.home TEST Dynamic simulation meter."""
    empty = {"total_energy_kwh": 0.0, "vehicle_id": None, "closed": False}
    if not db_path.is_file():
        return empty
    with sqlite3.connect(db_path, timeout=15) as db:
        table = db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='dynamic_sim_sessions'"
        ).fetchone()
        if not table:
            return empty
        row = db.execute("""
            SELECT s.vehicle_id, s.closed,
                   (SELECT COALESCE(SUM(st.energy_kwh), 0)
                    FROM dynamic_sim_steps st
                    WHERE st.vehicle_id=s.vehicle_id AND st.zone_id=s.zone_id)
            FROM dynamic_sim_sessions s
            JOIN vehicles v ON v.vehicle_id=s.vehicle_id
            WHERE s.zone_id='zone.home' AND lower(trim(v.name)) LIKE 'test dynamic%'
            ORDER BY s.started_at DESC, s.vehicle_id DESC LIMIT 1
        """).fetchone()
        if row is None:
            return empty
        return {"total_energy_kwh": round(float(row[2] or 0), 6),
                "vehicle_id": int(row[0]), "closed": bool(row[1])}


class FordTriplogDynamicTestEnergySensor(SensorEntity):
    """Simulated session energy (not a real home electricity meter)."""

    _attr_name = "Ford Triplog Test Energie"
    _attr_unique_id = "ford_triplog_dynamic_test_energy_kwh"
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_icon = "mdi:flash"
    _attr_should_poll = False

    def __init__(self, hass: HomeAssistant, db_path: Path) -> None:
        self._hass_ref = hass
        self._db_path = Path(db_path)
        self._value = 0.0
        self._vehicle_id: int | None = None
        self._closed = False
        self._last_action = "initial"

    @property
    def native_value(self) -> float:
        return self._value

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "test_only": True,
            "source": "ford_triplog.simulate_dynamic_charging",
            "meter_type": "session_counter",
            "zone_id": "zone.home",
            "vehicle_id": self._vehicle_id,
            "closed": self._closed,
            "last_action": self._last_action,
        }

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(async_dispatcher_connect(
            self.hass, SIGNAL_DYNAMIC_TEST_ENERGY_UPDATED, self._handle_simulation_update
        ))
        restored = await self.hass.async_add_executor_job(_restore_test_energy, self._db_path)
        self._value = restored["total_energy_kwh"]
        self._vehicle_id = restored["vehicle_id"]
        self._closed = restored["closed"]
        self._last_action = "restore"
        self.async_write_ha_state()

    @callback
    def _handle_simulation_update(
        self, vehicle_id: int, energy_kwh: float, action: str, closed: bool
    ) -> None:
        self._value = max(0.0, round(float(energy_kwh), 6))
        self._vehicle_id = int(vehicle_id)
        self._closed = bool(closed)
        self._last_action = str(action)
        self.async_write_ha_state()
