"""
Ford Triplog

CSV export helpers.

Version: 2.2.0
Build: 07 - Trip, Journey and Charge CSV export
"""

from __future__ import annotations

import csv
import functools
import math
from datetime import date, datetime
from pathlib import Path
from typing import Any

from aiohttp import web

from homeassistant.core import HomeAssistant
from homeassistant.components.http import HomeAssistantView
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .storage import FordTriplogStorage
from .user_charging_site_storage import UserChargingSiteStorage


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


MONTHLY_DRIVING_EXPORT_FIELDS = (
    "month",
    "distance_km",
    "trip_count",
    "journey_count",
    "driving_duration_seconds",
    "driving_duration_hours",
    "energy_used_kwh",
    "average_consumption_kwh_100km",
    "soc_used",
    "soc_recovered",
    "regenerated_energy_kwh",
    "regen_trip_count",
)


MONTHLY_CHARGING_EXPORT_FIELDS = (
    "month",
    "home_energy_kwh",
    "home_cost",
    "home_charge_count",
    "work_energy_kwh",
    "work_cost",
    "work_charge_count",
    "external_energy_kwh",
    "external_cost",
    "external_charge_count",
    "total_energy_kwh",
    "total_cost",
    "total_charge_count",
    "currency",
    "billed_count",
    "vehicle_count",
    "charging_status_count",
    "ford_last_charge_count",
    "soc_calculated_count",
)


CHARGE_EXPORT_FIELDS = (
    "charge_id",
    "start_time",
    "end_time",
    "detected_start_time",
    "detected_end_time",
    "duration_seconds",
    "start_soc",
    "end_soc",
    "initial_start_soc",
    "stabilized_start_soc",
    "stabilized_start_soc_time",
    "start_soc_source",
    "completion_soc",
    "completion_time",
    "end_soc_source",
    "fordpass_start_soc",
    "fordpass_end_soc",
    "charging_type",
    "energy_added_kwh",
    "energy_added_kwh_fordpass",
    "energy_added_kwh_charging_status",
    "energy_added_kwh_calculated",
    "charger_energy_output_kwh",
    "last_live_charging_soc",
    "last_live_charging_status",
    "last_live_charging_updated_at",
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
    "auto_memo",
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


def _normalize_filter_date(value: Any) -> date | None:
    """Normalize config-flow date values before export comparisons."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return date.fromisoformat(text)
        except ValueError as error:
            raise ValueError(f"Invalid export date: {value!r}") from error
    raise ValueError(f"Unsupported export date type: {type(value).__name__}")


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
        "detected_start_time": _csv_value(data.get("detected_start_time")),
        "detected_end_time": _csv_value(data.get("detected_end_time")),
        "duration_seconds": _csv_value(
            _duration_seconds(
                data.get("start_time"),
                data.get("end_time"),
            )
        ),
        "start_soc": _csv_value(data.get("start_soc")),
        "end_soc": _csv_value(data.get("end_soc")),
        "initial_start_soc": _csv_value(data.get("initial_start_soc")),
        "stabilized_start_soc": _csv_value(
            data.get("stabilized_start_soc")
        ),
        "stabilized_start_soc_time": _csv_value(
            data.get("stabilized_start_soc_time")
        ),
        "start_soc_source": _csv_value(data.get("start_soc_source")),
        "completion_soc": _csv_value(data.get("completion_soc")),
        "completion_time": _csv_value(data.get("completion_time")),
        "end_soc_source": _csv_value(data.get("end_soc_source")),
        "fordpass_start_soc": _csv_value(data.get("fordpass_start_soc")),
        "fordpass_end_soc": _csv_value(data.get("fordpass_end_soc")),
        "charging_type": _csv_value(data.get("charging_type")),
        "energy_added_kwh": _csv_value(data.get("energy_added_kwh")),
        "energy_added_kwh_fordpass": _csv_value(
            data.get("energy_added_kwh_fordpass")
        ),
        "energy_added_kwh_charging_status": _csv_value(
            data.get("energy_added_kwh_charging_status")
        ),
        "energy_added_kwh_calculated": _csv_value(
            data.get("energy_added_kwh_calculated")
        ),
        "charger_energy_output_kwh": _csv_value(
            data.get("charger_energy_output_kwh")
        ),
        "last_live_charging_soc": _csv_value(
            data.get("last_live_charging_soc")
        ),
        "last_live_charging_status": _csv_value(
            data.get("last_live_charging_status")
        ),
        "last_live_charging_updated_at": _csv_value(
            data.get("last_live_charging_updated_at")
        ),
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


def _optional_float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _charge_energy_for_statistics(charge: dict[str, Any]) -> tuple[float, str]:
    priorities = (
        ("energy_billed_kwh", "billed"),
        ("energy_added_kwh", "vehicle"),
        ("energy_added_kwh_charging_status", "charging_status"),
        ("energy_added_kwh_fordpass", "ford_last_charge"),
        ("energy_added_kwh_calculated", "soc_calculated"),
    )
    for key, source in priorities:
        value = _optional_float(charge.get(key))
        if value is not None and value >= 0:
            return value, source
    return 0.0, "none"


def _distance_meters(
    latitude_1: float,
    longitude_1: float,
    latitude_2: float,
    longitude_2: float,
) -> float:
    earth_radius_m = 6_371_000.0
    lat_1 = math.radians(latitude_1)
    lat_2 = math.radians(latitude_2)
    delta_lat = math.radians(latitude_2 - latitude_1)
    delta_lon = math.radians(longitude_2 - longitude_1)
    value = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat_1)
        * math.cos(lat_2)
        * math.sin(delta_lon / 2) ** 2
    )
    return earth_radius_m * 2 * math.atan2(
        math.sqrt(value), math.sqrt(1 - value)
    )


def _charge_site_type(
    charge: dict[str, Any],
    sites: list[dict[str, Any]],
) -> str:
    cost_source = str(charge.get("cost_source") or "").strip().lower()
    if cost_source == "home_tariff":
        return "home"

    explicit_type = str(
        charge.get("charging_site_type") or ""
    ).strip().lower()
    if explicit_type in {"home", "work"}:
        return explicit_type

    charge_site_id = str(charge.get("charging_site_id") or "").strip()
    if charge_site_id:
        for site in sites:
            if str(site.get("site_id") or "").strip() == charge_site_id:
                site_type = str(site.get("type") or "public").strip().lower()
                if site_type in {"home", "work"}:
                    return site_type

    latitude = charge.get("end_latitude")
    longitude = charge.get("end_longitude")
    if latitude is None or longitude is None:
        latitude = charge.get("start_latitude")
        longitude = charge.get("start_longitude")

    try:
        charge_lat = float(latitude)
        charge_lon = float(longitude)
    except (TypeError, ValueError):
        return "external"

    best_type = "external"
    best_distance: float | None = None
    for site in sites:
        site_type = str(site.get("type") or "public").strip().lower()
        if site_type not in {"home", "work"}:
            continue
        try:
            distance = _distance_meters(
                charge_lat,
                charge_lon,
                float(site["latitude"]),
                float(site["longitude"]),
            )
            radius = float(site.get("radius") or 0.0)
        except (KeyError, TypeError, ValueError):
            continue
        if radius <= 0 or distance > radius:
            continue
        if best_distance is None or distance < best_distance:
            best_distance = distance
            best_type = site_type

    return best_type


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
        start_date: date | str | None = None,
        end_date: date | str | None = None,
    ) -> dict[str, Any]:
        start_date = _normalize_filter_date(start_date)
        end_date = _normalize_filter_date(end_date)

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
        start_date: date | str | None = None,
        end_date: date | str | None = None,
    ) -> dict[str, Any]:
        """Export archived Journeys to one CSV file."""

        start_date = _normalize_filter_date(start_date)
        end_date = _normalize_filter_date(end_date)

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
        start_date: date | str | None = None,
        end_date: date | str | None = None,
    ) -> dict[str, Any]:
        """Export archived charging sessions to one CSV file."""

        start_date = _normalize_filter_date(start_date)
        end_date = _normalize_filter_date(end_date)

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

    async def async_export_monthly_driving_statistics(
        self,
        journey_storage: Any,
        *,
        battery_capacity_kwh: float | None = None,
    ) -> dict[str, Any]:
        """Export the complete driving history aggregated by calendar month."""

        trips = await self.storage.load_archived_trips()
        journeys = await journey_storage.get_all_journeys()
        periods: dict[str, dict[str, float | int]] = {}

        def empty_period() -> dict[str, float | int]:
            return {
                "distance": 0.0,
                "trip_count": 0,
                "journey_count": 0,
                "duration_seconds": 0,
                "energy_used": 0.0,
                "soc_used": 0.0,
                "soc_recovered": 0.0,
                "regenerated_energy": 0.0,
                "regen_trip_count": 0,
            }

        def optional_float(value: Any) -> float | None:
            try:
                return float(value) if value is not None else None
            except (TypeError, ValueError):
                return None

        def optional_int(value: Any) -> int:
            try:
                return int(value) if value is not None else 0
            except (TypeError, ValueError):
                return 0

        def parse_local_datetime(value: Any) -> datetime | None:
            if not value:
                return None
            try:
                parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
                return dt_util.as_local(parsed)
            except (TypeError, ValueError):
                return None

        fallback_capacity = optional_float(battery_capacity_kwh) or 0.0

        for trip in trips:
            if not isinstance(trip, dict):
                continue
            local_start = parse_local_datetime(trip.get("start_time"))
            if local_start is None:
                continue

            month = local_start.strftime("%Y-%m")
            period = periods.setdefault(month, empty_period())
            distance = max(0.0, optional_float(trip.get("distance_km")) or 0.0)
            duration = max(0, optional_int(trip.get("duration_seconds")))
            energy = optional_float(trip.get("energy_used_kwh")) or 0.0
            soc_used = optional_float(trip.get("soc_used")) or 0.0

            stored_soc_recovered = max(
                0.0, optional_float(trip.get("soc_recovered")) or 0.0
            )
            stored_regenerated = max(
                0.0, optional_float(trip.get("regenerated_energy_kwh")) or 0.0
            )

            if stored_soc_recovered > 0.0 and stored_regenerated > 0.0:
                soc_recovered = stored_soc_recovered
                regenerated = stored_regenerated
            elif distance > 0.0:
                start_soc = optional_float(trip.get("start_soc"))
                end_soc = optional_float(trip.get("end_soc"))
                if start_soc is not None and end_soc is not None:
                    soc_recovered = max(end_soc - start_soc, 0.0)
                    capacity = optional_float(trip.get("battery_capacity_kwh"))
                    if capacity is None or capacity <= 0.0:
                        capacity = fallback_capacity
                    regenerated = (
                        soc_recovered * capacity / 100.0
                        if soc_recovered > 0.0 and capacity > 0.0
                        else 0.0
                    )
                else:
                    soc_recovered = stored_soc_recovered
                    regenerated = stored_regenerated
            else:
                soc_recovered = stored_soc_recovered
                regenerated = stored_regenerated

            period["distance"] = float(period["distance"]) + distance
            period["trip_count"] = int(period["trip_count"]) + 1
            period["duration_seconds"] = int(period["duration_seconds"]) + duration
            period["energy_used"] = float(period["energy_used"]) + energy
            period["soc_used"] = float(period["soc_used"]) + soc_used
            period["soc_recovered"] = float(period["soc_recovered"]) + soc_recovered
            period["regenerated_energy"] = (
                float(period["regenerated_energy"]) + regenerated
            )
            if soc_recovered > 0.0 or regenerated > 0.0:
                period["regen_trip_count"] = int(period["regen_trip_count"]) + 1

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
            local_start = parse_local_datetime(data.get("start_time"))
            if local_start is None:
                continue
            month = local_start.strftime("%Y-%m")
            # Do not create a month from a Journey alone. The driving export is
            # anchored to archived Trips, matching the monthly sensor semantics.
            if month in periods:
                periods[month]["journey_count"] = (
                    int(periods[month]["journey_count"]) + 1
                )

        rows: list[dict[str, Any]] = []
        for month in sorted(periods):
            period = periods[month]
            distance = float(period["distance"])
            energy = float(period["energy_used"])
            duration_seconds = int(period["duration_seconds"])
            average_consumption = (
                energy / distance * 100.0 if distance > 0.0 else 0.0
            )
            rows.append({
                "month": month,
                "distance_km": round(distance, 1),
                "trip_count": int(period["trip_count"]),
                "journey_count": int(period["journey_count"]),
                "driving_duration_seconds": duration_seconds,
                "driving_duration_hours": round(duration_seconds / 3600.0, 2),
                "energy_used_kwh": round(energy, 2),
                "average_consumption_kwh_100km": round(average_consumption, 1),
                "soc_used": round(float(period["soc_used"]), 1),
                "soc_recovered": round(float(period["soc_recovered"]), 1),
                "regenerated_energy_kwh": round(
                    float(period["regenerated_energy"]), 2
                ),
                "regen_trip_count": int(period["regen_trip_count"]),
            })

        filename = (
            "ford_triplog_driving_monthly_"
            + dt_util.now().strftime("%Y-%m-%d_%H-%M-%S")
            + ".csv"
        )
        output_file = self.export_path / filename
        await self.hass.async_add_executor_job(
            functools.partial(
                self._write_csv,
                output_file,
                rows,
                MONTHLY_DRIVING_EXPORT_FIELDS,
            )
        )

        return {
            "type": "driving_monthly",
            "record_count": len(rows),
            "filename": filename,
            "path": str(output_file),
            "start_date": rows[0]["month"] if rows else "",
            "end_date": rows[-1]["month"] if rows else "",
        }


    async def async_export_monthly_charging_statistics(
        self,
        charge_manager: Any,
    ) -> dict[str, Any]:
        """Export the complete charging history aggregated by calendar month."""

        charges = await charge_manager.async_get_charges(newest_first=False)
        site_storage = UserChargingSiteStorage(self.hass)
        await site_storage.async_setup()
        sites = await site_storage.async_load()

        periods: dict[str, dict[str, Any]] = {}

        def empty_period() -> dict[str, Any]:
            return {
                "home": {"energy": 0.0, "cost": 0.0, "count": 0},
                "work": {"energy": 0.0, "cost": 0.0, "count": 0},
                "external": {"energy": 0.0, "cost": 0.0, "count": 0},
                "currencies": set(),
                "energy_sources": {},
            }

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
            if not data.get("include_in_statistics", True):
                continue

            raw_start = data.get("start_time")
            if not raw_start:
                continue
            try:
                parsed = datetime.fromisoformat(
                    str(raw_start).replace("Z", "+00:00")
                )
                local_start = dt_util.as_local(parsed)
            except (TypeError, ValueError):
                continue

            month = local_start.strftime("%Y-%m")
            period = periods.setdefault(month, empty_period())
            category = _charge_site_type(data, sites)
            energy, source = _charge_energy_for_statistics(data)
            cost = _optional_float(data.get("cost_total")) or 0.0

            bucket = period[category]
            bucket["energy"] += energy
            bucket["cost"] += cost
            bucket["count"] += 1

            currency = str(data.get("currency") or "").strip().upper()
            if currency:
                period["currencies"].add(currency)
            period["energy_sources"][source] = (
                period["energy_sources"].get(source, 0) + 1
            )

        rows: list[dict[str, Any]] = []
        for month in sorted(periods):
            period = periods[month]
            home = period["home"]
            work = period["work"]
            external = period["external"]
            total_energy = home["energy"] + work["energy"] + external["energy"]
            total_cost = home["cost"] + work["cost"] + external["cost"]
            total_count = home["count"] + work["count"] + external["count"]
            currencies = sorted(period["currencies"])
            sources = period["energy_sources"]

            rows.append({
                "month": month,
                "home_energy_kwh": round(home["energy"], 2),
                "home_cost": round(home["cost"], 2),
                "home_charge_count": home["count"],
                "work_energy_kwh": round(work["energy"], 2),
                "work_cost": round(work["cost"], 2),
                "work_charge_count": work["count"],
                "external_energy_kwh": round(external["energy"], 2),
                "external_cost": round(external["cost"], 2),
                "external_charge_count": external["count"],
                "total_energy_kwh": round(total_energy, 2),
                "total_cost": round(total_cost, 2),
                "total_charge_count": total_count,
                "currency": currencies[0] if len(currencies) == 1 else ",".join(currencies),
                "billed_count": sources.get("billed", 0),
                "vehicle_count": sources.get("vehicle", 0),
                "charging_status_count": sources.get("charging_status", 0),
                "ford_last_charge_count": sources.get("ford_last_charge", 0),
                "soc_calculated_count": sources.get("soc_calculated", 0),
            })

        filename = (
            "ford_triplog_charging_monthly_"
            + dt_util.now().strftime("%Y-%m-%d_%H-%M-%S")
            + ".csv"
        )
        output_file = self.export_path / filename
        await self.hass.async_add_executor_job(
            functools.partial(
                self._write_csv,
                output_file,
                rows,
                MONTHLY_CHARGING_EXPORT_FIELDS,
            )
        )

        return {
            "type": "charging_monthly",
            "record_count": len(rows),
            "filename": filename,
            "path": str(output_file),
            "start_date": rows[0]["month"] if rows else "",
            "end_date": rows[-1]["month"] if rows else "",
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
