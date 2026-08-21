"""
Ford Triplog

CSV export helpers.

Version: 2.2.0
Build: 05 - Trip CSV export
"""

from __future__ import annotations

import csv
import functools
from datetime import date, datetime
from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .storage import FordTriplogStorage


TRIP_EXPORT_FIELDS = (
    "trip_id",
    "start_time",
    "end_time",
    "distance_km",
    "duration_seconds",
    "start_soc",
    "end_soc",
    "soc_used",
    "energy_used_kwh",
    "consumption_kwh_100km",
    "start_location",
    "end_location",
    "start_address",
    "end_address",
    "start_latitude",
    "start_longitude",
    "end_latitude",
    "end_longitude",
)


def _parse_local_date(value: Any) -> date | None:
    if not value:
        return None
    try:
        timestamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)
    return dt_util.as_local(timestamp).date()


def _address_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in ("display", "display_name", "formatted"):
            text = value.get(key)
            if text:
                return str(text)
        parts = [
            value.get("road") or value.get("street"),
            value.get("house_number"),
            value.get("postcode"),
            value.get("city")
            or value.get("town")
            or value.get("village")
            or value.get("municipality"),
            value.get("country"),
        ]
        return ", ".join(str(part).strip() for part in parts if part not in (None, ""))
    return str(value)


def _csv_value(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return value
    return str(value)


def _trip_row(trip: dict[str, Any]) -> dict[str, Any]:
    return {
        "trip_id": _csv_value(trip.get("trip_id")),
        "start_time": _csv_value(trip.get("start_time")),
        "end_time": _csv_value(trip.get("end_time")),
        "distance_km": _csv_value(trip.get("distance_km")),
        "duration_seconds": _csv_value(trip.get("duration_seconds")),
        "start_soc": _csv_value(trip.get("start_soc")),
        "end_soc": _csv_value(trip.get("end_soc")),
        "soc_used": _csv_value(trip.get("soc_used")),
        "energy_used_kwh": _csv_value(trip.get("energy_used_kwh")),
        "consumption_kwh_100km": _csv_value(trip.get("consumption_kwh_100km")),
        "start_location": _csv_value(trip.get("start_location")),
        "end_location": _csv_value(trip.get("end_location")),
        "start_address": _address_text(trip.get("start_address")),
        "end_address": _address_text(trip.get("end_address")),
        "start_latitude": _csv_value(trip.get("start_latitude")),
        "start_longitude": _csv_value(trip.get("start_longitude")),
        "end_latitude": _csv_value(trip.get("end_latitude")),
        "end_longitude": _csv_value(trip.get("end_longitude")),
    }


class FordTriplogExporter:
    def __init__(self, hass: HomeAssistant, storage: FordTriplogStorage) -> None:
        self.hass = hass
        self.storage = storage
        self.export_path = Path(hass.config.path("ford_triplog", "export"))

    async def async_export_trips(
        self,
        *,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> dict[str, Any]:
        if start_date is not None and end_date is not None and start_date > end_date:
            raise ValueError("start_date must not be after end_date")

        trips = await self.storage.load_archived_trips()
        filtered = []

        for trip in trips:
            if not isinstance(trip, dict):
                continue
            trip_date = _parse_local_date(trip.get("start_time"))
            if trip_date is None:
                continue
            if start_date is not None and trip_date < start_date:
                continue
            if end_date is not None and trip_date > end_date:
                continue
            filtered.append(trip)

        filtered.sort(key=lambda item: str(item.get("start_time") or ""))

        filename = "ford_triplog_trips_" + dt_util.now().strftime("%Y-%m-%d_%H-%M-%S") + ".csv"
        output_file = self.export_path / filename
        rows = [_trip_row(trip) for trip in filtered]

        await self.hass.async_add_executor_job(
            functools.partial(self._write_csv, output_file, rows)
        )

        return {
            "type": "trips",
            "record_count": len(rows),
            "filename": filename,
            "path": str(output_file),
            "start_date": start_date.isoformat() if start_date else "",
            "end_date": end_date.isoformat() if end_date else "",
        }

    @staticmethod
    def _write_csv(output_file: Path, rows: list[dict[str, Any]]) -> None:
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with output_file.open("w", encoding="utf-8-sig", newline="") as file_handle:
            writer = csv.DictWriter(
                file_handle,
                fieldnames=TRIP_EXPORT_FIELDS,
                delimiter=";",
                extrasaction="ignore",
            )
            writer.writeheader()
            writer.writerows(rows)
