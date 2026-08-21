"""
Ford Triplog

CSV export helpers.

Version: 2.2.0
Build: 07 - Trip, Journey and Charge CSV export
"""

from __future__ import annotations

import csv
import functools
from datetime import date, datetime
from pathlib import Path
from typing import Any

from aiohttp import web

from homeassistant.core import HomeAssistant
from homeassistant.components.http import HomeAssistantView
from homeassistant.util import dt as dt_util

from .const import DOMAIN
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



JOURNEY_EXPORT_FIELDS = (
    "journey_id",
    "date",
    "start_time",
    "end_time",
    "start_address",
    "end_address",
    "start_latitude",
    "start_longitude",
    "end_latitude",
    "end_longitude",
    "trip_count",
    "charge_count",
    "distance_km",
    "driving_duration_seconds",
    "charging_duration_seconds",
    "total_duration_seconds",
    "energy_used_kwh",
    "energy_charged_kwh",
    "average_consumption_kwh_100km",
    "charging_cost_total",
    "charging_energy_cost",
    "charging_additional_cost",
    "average_charging_price_per_kwh",
    "currency",
    "start_soc",
    "end_soc",
    "soc_delta",
    "soc_used",
    "soc_charged",
    "soc_adjustment",
    "battery_capacity_kwh",
    "battery_energy_delta_kwh",
    "soc_adjustment_kwh",
    "battery_energy_balance_kwh",
    "total_energy_flow_kwh",
    "trip_ids",
    "charge_ids",
)


CHARGE_EXPORT_FIELDS = (
    "charge_id",
    "start_time",
    "end_time",
    "duration_seconds",
    "start_soc",
    "end_soc",
    "energy_added_kwh",
    "energy_billed_kwh",
    "energy_source",
    "energy_billed_source",
    "charging_loss_kwh",
    "charging_loss_percent",
    "energy_cost",
    "session_fee",
    "time_fee",
    "blocking_fee",
    "parking_fee",
    "other_cost",
    "cost_total",
    "currency",
    "energy_price_per_kwh",
    "effective_price_per_kwh",
    "cost_source",
    "cost_verified",
    "start_address",
    "end_address",
    "start_latitude",
    "start_longitude",
    "end_latitude",
    "end_longitude",
    "charging_site_id",
    "charging_site_name",
    "charging_site_brand",
    "charging_site_operator",
    "charging_site_network",
    "charging_site_power_kw",
    "charging_site_capacity",
    "charging_site_connectors",
    "charging_site_quality",
    "charging_site_distance_m",
    "trip_id",
    "previous_trip_id",
    "receipt_filename",
    "notes",
    "tags",
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



def _duration_seconds(start_time: Any, end_time: Any) -> int | None:
    """Return duration in whole seconds for two timestamps."""

    if not start_time or not end_time:
        return None

    try:
        start = datetime.fromisoformat(str(start_time).replace("Z", "+00:00"))
        end = datetime.fromisoformat(str(end_time).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None

    if start.tzinfo is None:
        start = start.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)
    if end.tzinfo is None:
        end = end.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)

    return max(0, int((end - start).total_seconds()))


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



def _journey_row(journey: Any) -> dict[str, Any]:
    """Return one stable CSV row from one archived Journey."""

    data = (
        journey.to_dict()
        if hasattr(journey, "to_dict")
        else dict(journey)
        if isinstance(journey, dict)
        else {}
    )

    return {
        "journey_id": _csv_value(data.get("journey_id")),
        "date": _csv_value(data.get("date")),
        "start_time": _csv_value(data.get("start_time")),
        "end_time": _csv_value(data.get("end_time")),
        "start_address": _address_text(data.get("start_address")),
        "end_address": _address_text(data.get("end_address")),
        "start_latitude": _csv_value(data.get("start_latitude")),
        "start_longitude": _csv_value(data.get("start_longitude")),
        "end_latitude": _csv_value(data.get("end_latitude")),
        "end_longitude": _csv_value(data.get("end_longitude")),
        "trip_count": _csv_value(data.get("trip_count")),
        "charge_count": _csv_value(data.get("charge_count")),
        "distance_km": _csv_value(data.get("distance_km")),
        "driving_duration_seconds": _csv_value(
            data.get("driving_duration_seconds")
        ),
        "charging_duration_seconds": _csv_value(
            data.get("charging_duration_seconds")
        ),
        "total_duration_seconds": _csv_value(
            data.get("total_duration_seconds")
        ),
        "energy_used_kwh": _csv_value(data.get("energy_used_kwh")),
        "energy_charged_kwh": _csv_value(data.get("energy_charged_kwh")),
        "average_consumption_kwh_100km": _csv_value(
            data.get("average_consumption_kwh_100km")
        ),
        "charging_cost_total": _csv_value(
            data.get("charging_cost_total")
        ),
        "charging_energy_cost": _csv_value(
            data.get("charging_energy_cost")
        ),
        "charging_additional_cost": _csv_value(
            data.get("charging_additional_cost")
        ),
        "average_charging_price_per_kwh": _csv_value(
            data.get("average_charging_price_per_kwh")
        ),
        "currency": _csv_value(data.get("currency")),
        "start_soc": _csv_value(data.get("start_soc")),
        "end_soc": _csv_value(data.get("end_soc")),
        "soc_delta": _csv_value(data.get("soc_delta")),
        "soc_used": _csv_value(data.get("soc_used")),
        "soc_charged": _csv_value(data.get("soc_charged")),
        "soc_adjustment": _csv_value(data.get("soc_adjustment")),
        "battery_capacity_kwh": _csv_value(
            data.get("battery_capacity_kwh")
        ),
        "battery_energy_delta_kwh": _csv_value(
            data.get("battery_energy_delta_kwh")
        ),
        "soc_adjustment_kwh": _csv_value(
            data.get("soc_adjustment_kwh")
        ),
        "battery_energy_balance_kwh": _csv_value(
            data.get("battery_energy_balance_kwh")
        ),
        "total_energy_flow_kwh": _csv_value(
            data.get("total_energy_flow_kwh")
        ),
        "trip_ids": ",".join(
            str(value) for value in (data.get("trip_ids") or [])
        ),
        "charge_ids": ",".join(
            str(value) for value in (data.get("charge_ids") or [])
        ),
    }



def _charge_row(charge: Any) -> dict[str, Any]:
    """Return one stable CSV row from one archived charging session."""

    data = (
        charge.to_dict()
        if hasattr(charge, "to_dict")
        else dict(charge)
        if isinstance(charge, dict)
        else {}
    )

    connectors = data.get("charging_site_connectors")
    if isinstance(connectors, (list, tuple, set)):
        connectors_text = ",".join(str(value) for value in connectors)
    else:
        connectors_text = _csv_value(connectors)

    tags = data.get("tags")
    if isinstance(tags, (list, tuple, set)):
        tags_text = ",".join(str(value) for value in tags)
    else:
        tags_text = _csv_value(tags)

    return {
        "charge_id": _csv_value(data.get("charge_id")),
        "start_time": _csv_value(data.get("start_time")),
        "end_time": _csv_value(data.get("end_time")),
        "duration_seconds": _csv_value(
            _duration_seconds(
                data.get("start_time"),
                data.get("end_time"),
            )
        ),
        "start_soc": _csv_value(data.get("start_soc")),
        "end_soc": _csv_value(data.get("end_soc")),
        "energy_added_kwh": _csv_value(data.get("energy_added_kwh")),
        "energy_billed_kwh": _csv_value(data.get("energy_billed_kwh")),
        "energy_source": _csv_value(data.get("energy_source")),
        "energy_billed_source": _csv_value(
            data.get("energy_billed_source")
        ),
        "charging_loss_kwh": _csv_value(data.get("charging_loss_kwh")),
        "charging_loss_percent": _csv_value(
            data.get("charging_loss_percent")
        ),
        "energy_cost": _csv_value(data.get("energy_cost")),
        "session_fee": _csv_value(data.get("session_fee")),
        "time_fee": _csv_value(data.get("time_fee")),
        "blocking_fee": _csv_value(data.get("blocking_fee")),
        "parking_fee": _csv_value(data.get("parking_fee")),
        "other_cost": _csv_value(data.get("other_cost")),
        "cost_total": _csv_value(data.get("cost_total")),
        "currency": _csv_value(data.get("currency")),
        "energy_price_per_kwh": _csv_value(
            data.get("energy_price_per_kwh")
        ),
        "effective_price_per_kwh": _csv_value(
            data.get("effective_price_per_kwh")
        ),
        "cost_source": _csv_value(data.get("cost_source")),
        "cost_verified": _csv_value(data.get("cost_verified")),
        "start_address": _address_text(data.get("start_address")),
        "end_address": _address_text(data.get("end_address")),
        "start_latitude": _csv_value(data.get("start_latitude")),
        "start_longitude": _csv_value(data.get("start_longitude")),
        "end_latitude": _csv_value(data.get("end_latitude")),
        "end_longitude": _csv_value(data.get("end_longitude")),
        "charging_site_id": _csv_value(data.get("charging_site_id")),
        "charging_site_name": _csv_value(data.get("charging_site_name")),
        "charging_site_brand": _csv_value(data.get("charging_site_brand")),
        "charging_site_operator": _csv_value(
            data.get("charging_site_operator")
        ),
        "charging_site_network": _csv_value(
            data.get("charging_site_network")
        ),
        "charging_site_power_kw": _csv_value(
            data.get("charging_site_power_kw")
        ),
        "charging_site_capacity": _csv_value(
            data.get("charging_site_capacity")
        ),
        "charging_site_connectors": connectors_text,
        "charging_site_quality": _csv_value(
            data.get("charging_site_quality")
        ),
        "charging_site_distance_m": _csv_value(
            data.get("charging_site_distance_m")
        ),
        "trip_id": _csv_value(data.get("trip_id")),
        "previous_trip_id": _csv_value(data.get("previous_trip_id")),
        "receipt_filename": _csv_value(data.get("receipt_filename")),
        "notes": _csv_value(data.get("notes")),
        "tags": tags_text,
    }


class FordTriplogExportView(HomeAssistantView):
    """Authenticated HTTP view for downloading generated export files."""

    url = "/api/ford_triplog/exports/{filename}"
    name = "api:ford_triplog:export"
    requires_auth = True

    async def get(
        self,
        request: web.Request,
        filename: str,
    ) -> web.StreamResponse:
        """Return one generated CSV export as an attachment."""

        hass: HomeAssistant = request.app["hass"]
        safe_name = Path(str(filename)).name

        if safe_name != filename or not safe_name.lower().endswith(".csv"):
            raise web.HTTPNotFound()

        export_directory = Path(
            hass.config.path(
                "ford_triplog",
                "export",
            )
        ).resolve()
        path = (export_directory / safe_name).resolve()

        try:
            path.relative_to(export_directory)
        except ValueError as error:
            raise web.HTTPNotFound() from error

        if not await hass.async_add_executor_job(path.is_file):
            raise web.HTTPNotFound()

        response = web.FileResponse(path)
        response.headers["Content-Disposition"] = (
            f'attachment; filename="{safe_name.replace(chr(34), "")}"'
        )
        response.headers["Content-Type"] = "text/csv; charset=utf-8"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "private, no-store"
        return response


class FordTriplogExporter:
    def __init__(self, hass: HomeAssistant, storage: FordTriplogStorage) -> None:
        self.hass = hass
        self.storage = storage
        self.export_path = Path(hass.config.path("ford_triplog", "export"))

        domain_data = hass.data.setdefault(DOMAIN, {})
        if not domain_data.get("export_view_registered"):
            hass.http.register_view(FordTriplogExportView())
            domain_data["export_view_registered"] = True

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
            functools.partial(self._write_csv, output_file, rows, TRIP_EXPORT_FIELDS)
        )

        return {
            "type": "trips",
            "record_count": len(rows),
            "filename": filename,
            "path": str(output_file),
            "start_date": start_date.isoformat() if start_date else "",
            "end_date": end_date.isoformat() if end_date else "",
        }


    async def async_export_journeys(
        self,
        journey_storage: Any,
        *,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> dict[str, Any]:
        """Export archived Journeys to one CSV file."""

        if (
            start_date is not None
            and end_date is not None
            and start_date > end_date
        ):
            raise ValueError("start_date must not be after end_date")

        journeys = await journey_storage.get_all_journeys()

        filtered = []
        for journey in journeys:
            data = (
                journey.to_dict()
                if hasattr(journey, "to_dict")
                else journey
                if isinstance(journey, dict)
                else None
            )
            if not isinstance(data, dict):
                continue

            journey_date = None
            raw_date = data.get("date")
            if raw_date:
                try:
                    journey_date = date.fromisoformat(str(raw_date))
                except ValueError:
                    journey_date = None

            if journey_date is None:
                journey_date = _parse_local_date(data.get("start_time"))

            if journey_date is None:
                continue
            if start_date is not None and journey_date < start_date:
                continue
            if end_date is not None and journey_date > end_date:
                continue

            filtered.append(journey)

        filtered.sort(
            key=lambda item: str(
                getattr(item, "start_time", None)
                or (
                    item.get("start_time")
                    if isinstance(item, dict)
                    else ""
                )
                or ""
            )
        )

        filename = (
            "ford_triplog_journeys_"
            + dt_util.now().strftime("%Y-%m-%d_%H-%M-%S")
            + ".csv"
        )
        output_file = self.export_path / filename
        rows = [_journey_row(journey) for journey in filtered]

        await self.hass.async_add_executor_job(
            functools.partial(
                self._write_csv,
                output_file,
                rows,
                JOURNEY_EXPORT_FIELDS,
            )
        )

        return {
            "type": "journeys",
            "record_count": len(rows),
            "filename": filename,
            "path": str(output_file),
            "start_date": start_date.isoformat() if start_date else "",
            "end_date": end_date.isoformat() if end_date else "",
        }


    async def async_export_charges(
        self,
        charge_manager: Any,
        *,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> dict[str, Any]:
        """Export archived charging sessions to one CSV file."""

        if (
            start_date is not None
            and end_date is not None
            and start_date > end_date
        ):
            raise ValueError("start_date must not be after end_date")

        charges = await charge_manager.async_get_charges(
            newest_first=False
        )

        filtered = []
        for charge in charges:
            data = (
                charge.to_dict()
                if hasattr(charge, "to_dict")
                else charge
                if isinstance(charge, dict)
                else None
            )
            if not isinstance(data, dict):
                continue

            charge_date = _parse_local_date(data.get("start_time"))
            if charge_date is None:
                continue
            if start_date is not None and charge_date < start_date:
                continue
            if end_date is not None and charge_date > end_date:
                continue

            filtered.append(charge)

        filename = (
            "ford_triplog_charges_"
            + dt_util.now().strftime("%Y-%m-%d_%H-%M-%S")
            + ".csv"
        )
        output_file = self.export_path / filename
        rows = [_charge_row(charge) for charge in filtered]

        await self.hass.async_add_executor_job(
            functools.partial(
                self._write_csv,
                output_file,
                rows,
                CHARGE_EXPORT_FIELDS,
            )
        )

        return {
            "type": "charges",
            "record_count": len(rows),
            "filename": filename,
            "path": str(output_file),
            "start_date": start_date.isoformat() if start_date else "",
            "end_date": end_date.isoformat() if end_date else "",
        }

    @staticmethod
    def _write_csv(
        output_file: Path,
        rows: list[dict[str, Any]],
        fieldnames: tuple[str, ...],
    ) -> None:
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with output_file.open("w", encoding="utf-8-sig", newline="") as file_handle:
            writer = csv.DictWriter(
                file_handle,
                fieldnames=fieldnames,
                delimiter=";",
                extrasaction="ignore",
            )
            writer.writeheader()
            writer.writerows(rows)
