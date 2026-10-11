"""Charging-zone tariff configuration, independent of vehicle-specific legacy tariffs."""
from __future__ import annotations
import sqlite3
from pathlib import Path
from homeassistant.core import HomeAssistant
from .const import STORAGE_DIR
from .database import FordTriplogDatabase

class ZoneTariffStorage:
    def __init__(self, hass: HomeAssistant):
        self.hass = hass
        self.database = FordTriplogDatabase(hass, Path(hass.config.path(".storage", STORAGE_DIR)))

    async def async_setup(self):
        await self.database.async_setup()
        def setup():
            with sqlite3.connect(self.database.db_path) as db:
                db.execute("""CREATE TABLE IF NOT EXISTS charging_zone_tariffs (
                    zone_id TEXT PRIMARY KEY, mode TEXT NOT NULL DEFAULT 'fixed',
                    price_per_kwh REAL NOT NULL DEFAULT 0,
                    price_sensor TEXT, interval_minutes INTEGER NOT NULL DEFAULT 15,
                    currency TEXT NOT NULL DEFAULT 'CHF', updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )""")
        await self.hass.async_add_executor_job(setup)
        def setup_periods():
            with sqlite3.connect(self.database.db_path) as db:
                db.execute("""CREATE TABLE IF NOT EXISTS charging_zone_seasonal_periods (
                    period_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    zone_id TEXT NOT NULL, valid_from TEXT NOT NULL, valid_to TEXT NOT NULL,
                    price_per_kwh REAL NOT NULL, currency TEXT NOT NULL DEFAULT 'CHF'
                )""")
        await self.hass.async_add_executor_job(setup_periods)
        await self.hass.async_add_executor_job(self._migrate_home_tariffs)

    def _migrate_home_tariffs(self):
        """Snapshot existing vehicle tariffs for zone.home, without altering charges.

        The shared zone setting remains independent; existing periods are preserved
        per vehicle because two vehicles may have different prices.
        """
        with sqlite3.connect(self.database.db_path) as db:
            db.execute("""CREATE TABLE IF NOT EXISTS charging_zone_legacy_tariffs (
                zone_id TEXT NOT NULL,
                vehicle_id INTEGER NOT NULL,
                source_tariff_id INTEGER NOT NULL,
                valid_from TEXT NOT NULL,
                valid_to TEXT NOT NULL,
                price_per_kwh REAL NOT NULL,
                currency TEXT NOT NULL,
                PRIMARY KEY (zone_id, vehicle_id, source_tariff_id)
            )""")
            db.execute("""CREATE TABLE IF NOT EXISTS charging_zone_migrations (
                migration_id TEXT PRIMARY KEY,
                completed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )""")
            migration_id = 'zone_home_vehicle_tariff_snapshot_v1'
            if db.execute("SELECT 1 FROM charging_zone_migrations WHERE migration_id=?", (migration_id,)).fetchone():
                return
            columns = {row[1] for row in db.execute('PRAGMA table_info(home_charging_tariffs)')}
            if {'vehicle_id', 'tariff_id', 'valid_from', 'valid_to', 'price_per_kwh', 'currency'} <= columns:
                db.execute("""INSERT OR IGNORE INTO charging_zone_legacy_tariffs
                    (zone_id,vehicle_id,source_tariff_id,valid_from,valid_to,price_per_kwh,currency)
                    SELECT 'zone.home',vehicle_id,tariff_id,valid_from,valid_to,price_per_kwh,currency
                    FROM home_charging_tariffs WHERE vehicle_id IS NOT NULL""")
                count = db.execute("SELECT COUNT(*) FROM charging_zone_legacy_tariffs WHERE zone_id='zone.home'").fetchone()[0]
                if count and not db.execute("SELECT 1 FROM charging_zone_tariffs WHERE zone_id='zone.home'").fetchone():
                    db.execute("""INSERT INTO charging_zone_tariffs
                        (zone_id,mode,price_per_kwh,interval_minutes,currency)
                        VALUES ('zone.home','seasonal',0,15,'CHF')""")
            db.execute('INSERT INTO charging_zone_migrations(migration_id) VALUES (?)', (migration_id,))

    async def async_legacy_sources(self, zone_id: str):
        """List preserved vehicle tariff snapshots available for explicit import."""
        def load():
            with sqlite3.connect(self.database.db_path) as db:
                return [dict(vehicle_id=row[0], count=row[1]) for row in db.execute(
                    "SELECT vehicle_id, COUNT(*) FROM charging_zone_legacy_tariffs WHERE zone_id=? GROUP BY vehicle_id ORDER BY vehicle_id", (zone_id,)
                )]
        return await self.hass.async_add_executor_job(load)

    async def async_import_legacy(self, zone_id: str, vehicle_id: int):
        """Copy one vehicle's periods into an empty zone; never overwrite or merge."""
        def do_import():
            with sqlite3.connect(self.database.db_path) as db:
                db.execute("BEGIN IMMEDIATE")
                existing = db.execute("SELECT COUNT(*) FROM charging_zone_seasonal_periods WHERE zone_id=?", (zone_id,)).fetchone()[0]
                if existing:
                    raise ValueError("Zone already has seasonal periods; import refused")
                rows = db.execute("""SELECT valid_from, valid_to, price_per_kwh, currency
                    FROM charging_zone_legacy_tariffs WHERE zone_id=? AND vehicle_id=?
                    ORDER BY valid_from, valid_to""", (zone_id, vehicle_id)).fetchall()
                if not rows:
                    raise ValueError("No preserved vehicle tariffs")
                for idx, a in enumerate(rows):
                    if any(a[0] <= b[1] and a[1] >= b[0] for b in rows[:idx]):
                        raise ValueError("Source periods overlap; import refused")
                db.executemany("""INSERT INTO charging_zone_seasonal_periods
                    (zone_id,valid_from,valid_to,price_per_kwh,currency) VALUES (?,?,?,?,?)""",
                    [(zone_id, *r) for r in rows])
                return len(rows)
        return await self.hass.async_add_executor_job(do_import)

    async def async_load(self, zone_id: str):
        def load():
            with sqlite3.connect(self.database.db_path) as db:
                db.row_factory = sqlite3.Row
                row = db.execute("SELECT * FROM charging_zone_tariffs WHERE zone_id=?", (zone_id,)).fetchone()
                return dict(row) if row else None
        return await self.hass.async_add_executor_job(load)

    async def async_save(self, *, zone_id, mode, price_per_kwh=0, price_sensor='', interval_minutes=15, currency='CHF'):
        if not zone_id.startswith('zone.') or mode not in ('fixed', 'seasonal', 'dynamic'):
            raise ValueError('Invalid zone or mode')
        if int(interval_minutes) not in (5, 15, 30, 60) or float(price_per_kwh) < 0:
            raise ValueError('Invalid price or interval')
        if mode == 'dynamic' and (not price_sensor or not price_sensor.startswith('sensor.')):
            raise ValueError('Dynamic tariff requires an HA price sensor')
        if currency not in ('CHF', 'EUR'):
            raise ValueError('Unsupported currency')
        def save():
            with sqlite3.connect(self.database.db_path) as db:
                db.execute("""INSERT INTO charging_zone_tariffs
                    (zone_id,mode,price_per_kwh,price_sensor,interval_minutes,currency)
                    VALUES (?,?,?,?,?,?) ON CONFLICT(zone_id) DO UPDATE SET
                    mode=excluded.mode,price_per_kwh=excluded.price_per_kwh,
                    price_sensor=excluded.price_sensor,interval_minutes=excluded.interval_minutes,
                    currency=excluded.currency,updated_at=CURRENT_TIMESTAMP""",
                    (zone_id,mode,float(price_per_kwh),price_sensor or None,int(interval_minutes),currency))
        await self.hass.async_add_executor_job(save)

    async def async_load_periods(self, zone_id):
        def load():
            with sqlite3.connect(self.database.db_path) as db:
                db.row_factory = sqlite3.Row
                return [dict(row) for row in db.execute("SELECT * FROM charging_zone_seasonal_periods WHERE zone_id=? ORDER BY valid_from", (zone_id,))]
        return await self.hass.async_add_executor_job(load)

    async def async_get_period(self, period_id):
        def load():
            with sqlite3.connect(self.database.db_path) as db:
                db.row_factory = sqlite3.Row
                row = db.execute("SELECT * FROM charging_zone_seasonal_periods WHERE period_id=?", (period_id,)).fetchone()
                return dict(row) if row else None
        return await self.hass.async_add_executor_job(load)

    async def async_save_period(self, *, zone_id, period_id, valid_from, valid_to, price_per_kwh, currency):
        from datetime import date
        start, end = date.fromisoformat(valid_from), date.fromisoformat(valid_to)
        if end < start or start.year != end.year or price_per_kwh < 0 or currency not in ("CHF", "EUR"):
            raise ValueError("Invalid tariff period")
        def save():
            with sqlite3.connect(self.database.db_path) as db:
                overlap = db.execute("""SELECT 1 FROM charging_zone_seasonal_periods
                    WHERE zone_id=? AND period_id != ? AND valid_from <= ? AND valid_to >= ?""",
                    (zone_id, period_id or -1, valid_to, valid_from)).fetchone()
                if overlap:
                    raise ValueError("Overlapping periods")
                if period_id is None:
                    db.execute("INSERT INTO charging_zone_seasonal_periods(zone_id,valid_from,valid_to,price_per_kwh,currency) VALUES (?,?,?,?,?)", (zone_id,valid_from,valid_to,price_per_kwh,currency))
                else:
                    db.execute("UPDATE charging_zone_seasonal_periods SET valid_from=?,valid_to=?,price_per_kwh=?,currency=? WHERE period_id=? AND zone_id=?", (valid_from,valid_to,price_per_kwh,currency,period_id,zone_id))
        await self.hass.async_add_executor_job(save)

    async def async_delete_period(self, period_id, zone_id):
        def delete():
            with sqlite3.connect(self.database.db_path) as db:
                db.execute("DELETE FROM charging_zone_seasonal_periods WHERE period_id=? AND zone_id=?", (period_id,zone_id))
        await self.hass.async_add_executor_job(delete)
