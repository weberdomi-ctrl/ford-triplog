"""
Ford Triplog

History and statistics.

Version: 1.0.1
"""

from __future__ import annotations

import logging

_LOGGER = logging.getLogger(__name__)


class FordTriplogHistory:
    """Manage trip history and statistics."""

    def __init__(self, storage):
        self.storage = storage

    async def get_last_trip(self):
        return await self.storage.load_last_trip()

    async def get_all_trips(self):
        trips = []

        for path in await self.storage.list_trips():
            trip = await self.storage.load_trip_file(path)
            if trip:
                trips.append(trip)

        return trips

    async def get_statistics(self):
        trips = await self.get_all_trips()

        total_distance = 0.0
        total_duration = 0
        total_energy = 0.0

        for trip in trips:
            total_distance += float(trip.get("distance_km") or 0)
            total_duration += int(trip.get("duration_seconds") or 0)
            total_energy += float(trip.get("energy_used_kwh") or 0)

        return {
            "trip_count": len(trips),
            "total_distance_km": round(total_distance, 1),
            "total_duration_seconds": total_duration,
            "total_energy_used_kwh": round(total_energy, 2),
        }

    async def refresh_statistics(self):
        statistics = await self.get_statistics()
        await self.storage.save_statistics(statistics)

        _LOGGER.debug("Statistics refreshed: %s", statistics)

        return statistics
