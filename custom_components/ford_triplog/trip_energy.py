"""
Ford Triplog Trip
Version 1.3.2
"""

from __future__ import annotations

from datetime import datetime


class TripCalculator:
    """Energy calculations."""

    BATTERY_CAPACITY_KWH = 77

    @staticmethod
    def calculate_energy(
        soc_used: float,
    ) -> float:
        return round(
            soc_used * TripCalculator.BATTERY_CAPACITY_KWH / 100,
            2,
        )

    @staticmethod
    def calculate_consumption(
        energy_kwh: float,
        distance_km: float,
    ) -> float | None:

        if not distance_km or distance_km <= 0:
            return None

        return round(
            energy_kwh / distance_km * 100,
            1,
        )


def add_energy_values(data: dict) -> dict:
    """Add calculated consumption values."""

    soc_used = data.get("soc_used")
    distance = data.get("distance_km")

    if soc_used is not None:
        energy = TripCalculator.calculate_energy(
            soc_used
        )

        data["energy_used_kwh"] = energy

        data["consumption_kwh_100km"] = (
            TripCalculator.calculate_consumption(
                energy,
                distance,
            )
        )

    return data
