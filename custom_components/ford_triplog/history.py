"""
Ford Triplog

History and statistics.

Version: 1.2.0
"""

from __future__ import annotations

import logging
from datetime import datetime

_LOGGER = logging.getLogger(__name__)


class FordTriplogHistory:
    """Manage trip history and statistics."""

    def __init__(self, storage):
        self.storage = storage

    async def get_last_trip(self):
        return await self.storage.load_last_trip()
    
    async def get_last_charge(self):
        return await self.storage.load_last_charge()

    async def get_all_trips(self):
        trips = []

        for path in await self.storage.list_trips():
            trip = await self.storage.load_trip_file(path)
            if trip:
                trips.append(trip)

        return trips

    async def get_all_charges(self):
        charges = []

        for path in await self.storage.list_charges():
            charge = await self.storage.load_charge_file(path)
            if charge:
                charges.append(charge)

        return charges

    async def get_statistics(self):
        trips = await self.get_all_trips()
        charges = await self.get_all_charges()

        total_distance = 0.0
        total_duration = 0
        total_energy = 0.0
        total_trip_soc_used = 0.0
        charge_count = 0
        total_charge_duration = 0.0
        total_soc_added = 0
        total_start_soc = 0.0
        total_end_soc = 0.0



        for charge in charges:
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
            total_distance += float(trip.get("distance_km") or 0)
            total_duration += int(trip.get("duration_seconds") or 0)
            total_energy += float(trip.get("energy_used_kwh") or 0)

            start_soc = trip.get("start_soc")
            end_soc = trip.get("end_soc")

            if start_soc is not None and end_soc is not None:
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
            total_distance / len(trips)
            if trips
            else 0
        )

        average_trip_duration = (
            total_duration / len(trips)
            if trips
            else 0
        )

        average_trip_energy = (
            total_energy / len(trips)
            if trips
            else 0
        )

        average_trip_soc_used = (
            total_trip_soc_used / len(trips)
            if trips
            else 0
        )

        average_trip_consumption = (
            (total_energy / total_distance) * 100
            if total_distance > 0
            else 0
        )

        return {
            "trip_count": len(trips),
            "total_distance_km": round(total_distance, 1),
            "total_duration_seconds": total_duration,
            "total_energy_used_kwh": round(total_energy, 2),
            "average_trip_distance_km": round(average_trip_distance, 1),
            "average_trip_duration_seconds": round(average_trip_duration, 1),
            "average_trip_energy_used_kwh": round(average_trip_energy, 2),
            "average_trip_consumption": round(average_trip_consumption, 1,),
            "average_trip_soc_used": round(average_trip_soc_used, 1),
            "charge_count": charge_count,
            "total_charge_duration": round(total_charge_duration, 1),
            "average_charge_duration": round(average_charge_duration, 1),
            "average_soc_added": round(average_soc_added, 1),
            "average_start_soc": round(average_start_soc, 1),
            "average_end_soc": round(average_end_soc, 1),

        }

    async def refresh_statistics(self):
        statistics = await self.get_statistics()
        await self.storage.save_statistics(statistics)

        _LOGGER.debug("Statistics refreshed: %s", statistics)

        return statistics
