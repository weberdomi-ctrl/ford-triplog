"""
Ford Triplog

History and statistics.

Version: 2.3.0
Build: 23047 - Net trip energy / recuperation statistics fix
Changes:
- Use signed SOC-derived trip energy so recuperation reduces net consumption.
- Recalculate legacy trips from SOC and configured battery capacity.
- Exclude zero-distance trips from energy/consumption statistics.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from time import monotonic
from typing import Any

_LOGGER = logging.getLogger(__name__)

# All sensor entities are updated almost simultaneously. Keep the compact
# sensor snapshot briefly so only one entity performs the three SQLite reads.
_SENSOR_CACHE_TTL_SECONDS = 1.0


class FordTriplogHistory:
    """Manage trip history and statistics."""

    def __init__(self, storage, battery_capacity_kwh: float | None = None):
        self.storage = storage
        try:
            capacity = float(battery_capacity_kwh)
        except (TypeError, ValueError):
            capacity = 77.0
        self.battery_capacity_kwh = capacity if capacity > 0 else 77.0
        self._sensor_data_lock = asyncio.Lock()
        self._sensor_data_cache: tuple[
            dict[str, Any],
            dict[str, Any] | None,
            dict[str, Any] | None,
        ] | None = None
        self._sensor_data_cache_time = 0.0

    async def get_last_trip(self):
        return await self.storage.load_last_trip()

    async def get_last_charge(self):
        return await self.storage.load_last_charge()

    async def get_sensor_data(self):
        """Return the shared compact data snapshot used by all sensors.

        Unlike ``get_statistics()``, this does not scan the trip and charging
        archives. It reads only the SQLite statistics, last_trip and
        last_charge records. Concurrent sensor updates share the same snapshot.
        """
        now = monotonic()
        if (
            self._sensor_data_cache is not None
            and now - self._sensor_data_cache_time < _SENSOR_CACHE_TTL_SECONDS
        ):
            return self._sensor_data_cache

        async with self._sensor_data_lock:
            now = monotonic()
            if (
                self._sensor_data_cache is not None
                and now - self._sensor_data_cache_time
                < _SENSOR_CACHE_TTL_SECONDS
            ):
                return self._sensor_data_cache

            statistics, last_trip, last_charge = await asyncio.gather(
                self.storage.load_statistics(),
                self.storage.load_last_trip(),
                self.storage.load_last_charge(),
            )

            snapshot = (
                statistics or {},
                last_trip,
                last_charge,
            )
            self._sensor_data_cache = snapshot
            self._sensor_data_cache_time = monotonic()
            return snapshot

    def invalidate_sensor_data(self) -> None:
        """Invalidate the compact sensor snapshot."""
        self._sensor_data_cache = None
        self._sensor_data_cache_time = 0.0

    async def get_all_trips(self):
        """Load all archived trips from the selected storage backend."""
        return await self.storage.load_archived_trips()

    async def get_all_charges(self):
        """Load all archived charges from the selected storage backend."""
        return await self.storage.load_archived_charges()


    def _trip_net_energy_kwh(
        self,
        trip: dict[str, Any],
        distance_km: float,
    ) -> float:
        """Return signed net battery energy for one trip.

        Positive values mean net battery discharge. Negative values mean the
        trip ended with more SOC than it started with (net recuperation).
        Legacy 2.2/early-2.3 rows may contain ``energy_used_kwh = 0`` for
        recuperation trips, so SOC remains the authoritative fallback.
        Zero-distance records are excluded from energy statistics.
        """

        if distance_km <= 0:
            return 0.0

        try:
            stored_energy = float(trip.get("energy_used_kwh") or 0.0)
        except (TypeError, ValueError):
            stored_energy = 0.0

        # Preserve already calculated historical consumption. Older releases
        # may have used a different configured battery capacity, so blindly
        # recalculating every trip with today's setting would rewrite history.
        # Signed values from Build 23047 are preserved here as well.
        if abs(stored_energy) > 1e-9:
            return stored_energy

        start_soc = trip.get("start_soc")
        end_soc = trip.get("end_soc")

        try:
            start_soc_value = float(start_soc)
            end_soc_value = float(end_soc)
        except (TypeError, ValueError):
            return stored_energy

        # The legacy clipping bug affected only net-recuperation trips:
        # ``energy_used_kwh`` was overwritten with 0 although end SOC was
        # higher. Reconstruct exactly those rows.
        if end_soc_value <= start_soc_value:
            return stored_energy

        capacity_value = trip.get("battery_capacity_kwh")
        try:
            capacity = float(capacity_value)
        except (TypeError, ValueError):
            capacity = self.battery_capacity_kwh

        if capacity <= 0:
            capacity = self.battery_capacity_kwh

        return (start_soc_value - end_soc_value) * capacity / 100.0

    async def get_statistics(self):
        """Recalculate statistics from all archived records."""
        trips = await self.get_all_trips()
        charges = await self.get_all_charges()

        total_distance = 0.0
        total_duration = 0
        total_energy = 0.0
        total_trip_soc_used = 0.0
        charge_count = 0
        total_charge_duration = 0.0
        total_soc_added = 0.0
        total_start_soc = 0.0
        total_end_soc = 0.0
        trip_count = 0
        energy_trip_count = 0
        top_trip: dict[str, Any] | None = None
        top_trip_distance = -1.0

        for charge in charges:
            if not charge.get("include_in_statistics", True):
                continue

            charge_count += 1

            start_soc = charge.get("start_soc")
            end_soc = charge.get("end_soc")

            if start_soc is not None:
                total_start_soc += start_soc

            if end_soc is not None:
                total_end_soc += end_soc

            if start_soc is not None and end_soc is not None:
                total_soc_added += end_soc - start_soc

            start_time = charge.get("start_time")
            end_time = charge.get("end_time")

            if start_time and end_time:
                start_dt = datetime.fromisoformat(start_time)
                end_dt = datetime.fromisoformat(end_time)
                total_charge_duration += (
                    end_dt - start_dt
                ).total_seconds()

        for trip in trips:
            if not trip.get("include_in_statistics", True):
                continue

            trip_count += 1

            distance = float(trip.get("distance_km") or 0)
            duration_seconds = int(trip.get("duration_seconds") or 0)
            energy_used = self._trip_net_energy_kwh(trip, distance)

            total_distance += distance
            total_duration += duration_seconds
            if distance > 0:
                total_energy += energy_used
                energy_trip_count += 1

            if distance > top_trip_distance:
                top_trip_distance = distance

                consumption = (
                    round((energy_used / distance) * 100, 1)
                    if distance > 0
                    else None
                )

                top_trip = {
                    "trip_id": trip.get("trip_id"),
                    "distance_km": round(distance, 1),
                    "duration_seconds": duration_seconds,
                    "start_time": trip.get("start_time"),
                    "end_time": trip.get("end_time"),
                    "start_address": trip.get("start_address"),
                    "end_address": trip.get("end_address"),
                    "energy_used_kwh": round(energy_used, 2),
                    "consumption_kwh_100km": consumption,
                }

            start_soc = trip.get("start_soc")
            end_soc = trip.get("end_soc")

            if (
                distance > 0
                and start_soc is not None
                and end_soc is not None
            ):
                total_trip_soc_used += start_soc - end_soc

        average_charge_duration = (
            total_charge_duration / charge_count
            if charge_count
            else 0
        )
        average_soc_added = (
            total_soc_added / charge_count
            if charge_count
            else 0
        )
        average_start_soc = (
            total_start_soc / charge_count
            if charge_count
            else 0
        )
        average_end_soc = (
            total_end_soc / charge_count
            if charge_count
            else 0
        )
        average_trip_distance = (
            total_distance / trip_count
            if trip_count
            else 0
        )
        average_trip_duration = (
            total_duration / trip_count
            if trip_count
            else 0
        )
        average_trip_energy = (
            total_energy / energy_trip_count
            if energy_trip_count
            else 0
        )
        average_trip_soc_used = (
            total_trip_soc_used / energy_trip_count
            if energy_trip_count
            else 0
        )
        average_trip_consumption = (
            (total_energy / total_distance) * 100
            if total_distance > 0
            else 0
        )

        return {
            "trip_count": trip_count,
            "total_distance_km": round(total_distance, 1),
            "total_duration_seconds": total_duration,
            "total_energy_used_kwh": round(total_energy, 2),
            "average_trip_distance_km": round(average_trip_distance, 1),
            "average_trip_duration_seconds": round(average_trip_duration, 1),
            "average_trip_energy_used_kwh": round(average_trip_energy, 2),
            "average_trip_consumption": round(average_trip_consumption, 1),
            "average_trip_soc_used": round(average_trip_soc_used, 1),
            "charge_count": charge_count,
            "total_charge_duration": round(total_charge_duration, 1),
            "average_charge_duration": round(average_charge_duration, 1),
            "average_soc_added": round(average_soc_added, 1),
            "average_start_soc": round(average_start_soc, 1),
            "average_end_soc": round(average_end_soc, 1),
            "top_trip": top_trip,
        }

    async def refresh_statistics(self):
        """Recalculate and persist statistics, then clear sensor cache."""
        statistics = await self.get_statistics()
        await self.storage.save_statistics(statistics)
        self.invalidate_sensor_data()

        _LOGGER.debug("Statistics refreshed: %s", statistics)
        return statistics
