"""
Ford Triplog

Track your Ford.

Journey data model.

Version: 1.6.0
Release: 1.6a
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Final, Literal
from uuid import uuid4

from .const import GENERATOR, JOURNEY_SCHEMA_VERSION, VERSION

JourneyItemType = Literal["trip", "charge"]

_ITEM_TRIP: Final = "trip"
_ITEM_CHARGE: Final = "charge"
_VALID_ITEM_TYPES: Final = {_ITEM_TRIP, _ITEM_CHARGE}


def _as_float(value: Any, default: float = 0.0) -> float:
    """Return a value as float without raising conversion errors."""

    if value is None or isinstance(value, bool):
        return default

    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_int(value: Any, default: int = 0) -> int:
    """Return a value as integer without raising conversion errors."""

    if value is None or isinstance(value, bool):
        return default

    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _as_optional_float(value: Any) -> float | None:
    """Return an optional float value."""

    if value is None or isinstance(value, bool):
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_optional_string(value: Any) -> str | None:
    """Return an optional non-empty string."""

    if value is None:
        return None

    result = str(value).strip()
    return result or None


def _normalize_iso_datetime(value: Any) -> str | None:
    """Return an ISO datetime string when the value is usable."""

    if isinstance(value, datetime):
        return value.isoformat()

    return _as_optional_string(value)


def _date_from_datetime(value: str | None) -> str | None:
    """Return the ISO date part of an ISO datetime string."""

    if not value:
        return None

    try:
        return datetime.fromisoformat(value).date().isoformat()
    except ValueError:
        return value[:10] if len(value) >= 10 else None


@dataclass(slots=True)
class JourneyItem:
    """Reference to one trip or charging session inside a journey."""

    item_type: JourneyItemType
    item_id: str
    start_time: str | None = None
    end_time: str | None = None

    def __post_init__(self) -> None:
        """Validate and normalize the journey item."""

        if self.item_type not in _VALID_ITEM_TYPES:
            raise ValueError(
                f"Unsupported journey item type: {self.item_type}"
            )

        self.item_id = str(self.item_id).strip()
        if not self.item_id:
            raise ValueError("Journey item ID must not be empty")

        self.start_time = _normalize_iso_datetime(self.start_time)
        self.end_time = _normalize_iso_datetime(self.end_time)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the journey item."""

        return {
            "type": self.item_type,
            "id": self.item_id,
            "start_time": self.start_time,
            "end_time": self.end_time,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> JourneyItem:
        """Create a journey item from stored data."""

        return cls(
            item_type=str(data.get("type", "")).strip(),
            item_id=str(data.get("id", "")).strip(),
            start_time=data.get("start_time"),
            end_time=data.get("end_time"),
        )


@dataclass(slots=True)
class FordTriplogJourney:
    """Represent one daily journey containing trips and charges."""

    journey_id: str = field(
        default_factory=lambda: f"journey_{uuid4().hex}"
    )
    created: str = field(
        default_factory=lambda: datetime.now().astimezone().isoformat()
    )
    date: str | None = None

    start_time: str | None = None
    end_time: str | None = None

    start_address: str | None = None
    end_address: str | None = None

    start_latitude: float | None = None
    start_longitude: float | None = None
    end_latitude: float | None = None
    end_longitude: float | None = None

    trip_ids: list[str] = field(default_factory=list)
    charge_ids: list[str] = field(default_factory=list)
    items: list[JourneyItem] = field(default_factory=list)

    trip_count: int = 0
    charge_count: int = 0

    distance_km: float = 0.0
    driving_duration_seconds: int = 0
    charging_duration_seconds: int = 0
    total_duration_seconds: int = 0

    energy_used_kwh: float = 0.0
    energy_charged_kwh: float = 0.0
    average_consumption_kwh_100km: float = 0.0

    schema: int = JOURNEY_SCHEMA_VERSION
    generator: str = GENERATOR
    version: str = VERSION

    def __post_init__(self) -> None:
        """Normalize values and rebuild derived fields."""

        self.journey_id = str(self.journey_id).strip()
        if not self.journey_id:
            raise ValueError("Journey ID must not be empty")

        self.created = (
            _normalize_iso_datetime(self.created)
            or datetime.now().astimezone().isoformat()
        )
        self.start_time = _normalize_iso_datetime(self.start_time)
        self.end_time = _normalize_iso_datetime(self.end_time)

        self.start_address = _as_optional_string(self.start_address)
        self.end_address = _as_optional_string(self.end_address)

        self.start_latitude = _as_optional_float(self.start_latitude)
        self.start_longitude = _as_optional_float(self.start_longitude)
        self.end_latitude = _as_optional_float(self.end_latitude)
        self.end_longitude = _as_optional_float(self.end_longitude)

        self.distance_km = max(0.0, _as_float(self.distance_km))
        self.driving_duration_seconds = max(
            0,
            _as_int(self.driving_duration_seconds),
        )
        self.charging_duration_seconds = max(
            0,
            _as_int(self.charging_duration_seconds),
        )
        self.energy_used_kwh = max(
            0.0,
            _as_float(self.energy_used_kwh),
        )
        self.energy_charged_kwh = max(
            0.0,
            _as_float(self.energy_charged_kwh),
        )

        normalized_items: list[JourneyItem] = []
        for item in self.items:
            if isinstance(item, JourneyItem):
                normalized_items.append(item)
            elif isinstance(item, dict):
                normalized_items.append(JourneyItem.from_dict(item))
            else:
                raise TypeError(
                    "Journey items must be JourneyItem objects or dictionaries"
                )

        self.items = normalized_items
        self._rebuild_references()
        self.recalculate()

        if self.date is None:
            self.date = _date_from_datetime(self.start_time)

    def add_trip(
        self,
        trip_id: str,
        *,
        start_time: str | datetime | None = None,
        end_time: str | datetime | None = None,
        distance_km: float = 0.0,
        duration_seconds: int = 0,
        energy_used_kwh: float = 0.0,
        start_address: str | None = None,
        end_address: str | None = None,
        start_latitude: float | None = None,
        start_longitude: float | None = None,
        end_latitude: float | None = None,
        end_longitude: float | None = None,
    ) -> bool:
        """Add a trip reference and its aggregate values.

        Return False when the trip is already part of this journey.
        """

        normalized_id = str(trip_id).strip()
        if not normalized_id:
            raise ValueError("Trip ID must not be empty")

        if normalized_id in self.trip_ids:
            return False

        item = JourneyItem(
            item_type=_ITEM_TRIP,
            item_id=normalized_id,
            start_time=start_time,
            end_time=end_time,
        )
        self.items.append(item)

        self.distance_km += max(0.0, _as_float(distance_km))
        self.driving_duration_seconds += max(
            0,
            _as_int(duration_seconds),
        )
        self.energy_used_kwh += max(
            0.0,
            _as_float(energy_used_kwh),
        )

        self._apply_boundary_data(
            item=item,
            start_address=start_address,
            end_address=end_address,
            start_latitude=start_latitude,
            start_longitude=start_longitude,
            end_latitude=end_latitude,
            end_longitude=end_longitude,
        )
        self._rebuild_references()
        self.recalculate()
        return True

    def add_charge(
        self,
        charge_id: str,
        *,
        start_time: str | datetime | None = None,
        end_time: str | datetime | None = None,
        duration_seconds: int = 0,
        energy_charged_kwh: float = 0.0,
    ) -> bool:
        """Add a charging-session reference and its aggregate values.

        Return False when the charge is already part of this journey.
        """

        normalized_id = str(charge_id).strip()
        if not normalized_id:
            raise ValueError("Charge ID must not be empty")

        if normalized_id in self.charge_ids:
            return False

        self.items.append(
            JourneyItem(
                item_type=_ITEM_CHARGE,
                item_id=normalized_id,
                start_time=start_time,
                end_time=end_time,
            )
        )

        self.charging_duration_seconds += max(
            0,
            _as_int(duration_seconds),
        )
        self.energy_charged_kwh += max(
            0.0,
            _as_float(energy_charged_kwh),
        )

        self._rebuild_references()
        self.recalculate()
        return True

    def recalculate(self) -> None:
        """Recalculate all values derived from current journey data."""

        self.trip_count = len(self.trip_ids)
        self.charge_count = len(self.charge_ids)

        if self.items:
            first_item = self.items[0]
            last_item = self.items[-1]

            if first_item.start_time:
                self.start_time = first_item.start_time
            if last_item.end_time:
                self.end_time = last_item.end_time

        self.date = self.date or _date_from_datetime(self.start_time)

        self.total_duration_seconds = self._calculate_total_duration()

        if self.distance_km > 0:
            self.average_consumption_kwh_100km = round(
                self.energy_used_kwh / self.distance_km * 100,
                2,
            )
        else:
            self.average_consumption_kwh_100km = 0.0

        self.distance_km = round(self.distance_km, 3)
        self.energy_used_kwh = round(self.energy_used_kwh, 3)
        self.energy_charged_kwh = round(self.energy_charged_kwh, 3)

    def is_same_day(self) -> bool:
        """Return whether the journey starts and ends on the same date."""

        start_date = _date_from_datetime(self.start_time)
        end_date = _date_from_datetime(self.end_time)

        if start_date is None or end_date is None:
            return True

        return start_date == end_date

    def to_dict(self) -> dict[str, Any]:
        """Serialize the complete journey."""

        self._rebuild_references()
        self.recalculate()

        return {
            "schema": self.schema,
            "journey_id": self.journey_id,
            "created": self.created,
            "date": self.date,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "start_address": self.start_address,
            "end_address": self.end_address,
            "start_latitude": self.start_latitude,
            "start_longitude": self.start_longitude,
            "end_latitude": self.end_latitude,
            "end_longitude": self.end_longitude,
            "trip_ids": list(self.trip_ids),
            "charge_ids": list(self.charge_ids),
            "items": [item.to_dict() for item in self.items],
            "trip_count": self.trip_count,
            "charge_count": self.charge_count,
            "distance_km": self.distance_km,
            "driving_duration_seconds": self.driving_duration_seconds,
            "charging_duration_seconds": self.charging_duration_seconds,
            "total_duration_seconds": self.total_duration_seconds,
            "energy_used_kwh": self.energy_used_kwh,
            "energy_charged_kwh": self.energy_charged_kwh,
            "average_consumption_kwh_100km": (
                self.average_consumption_kwh_100km
            ),
            "generator": self.generator,
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FordTriplogJourney:
        """Create a journey from stored data."""

        if not isinstance(data, dict):
            raise TypeError("Journey data must be a dictionary")

        raw_items = data.get("items", [])
        items = raw_items if isinstance(raw_items, list) else []

        return cls(
            schema=_as_int(
                data.get("schema"),
                JOURNEY_SCHEMA_VERSION,
            ),
            journey_id=str(data.get("journey_id", "")).strip(),
            created=data.get("created"),
            date=_as_optional_string(data.get("date")),
            start_time=data.get("start_time"),
            end_time=data.get("end_time"),
            start_address=data.get("start_address"),
            end_address=data.get("end_address"),
            start_latitude=data.get("start_latitude"),
            start_longitude=data.get("start_longitude"),
            end_latitude=data.get("end_latitude"),
            end_longitude=data.get("end_longitude"),
            trip_ids=list(data.get("trip_ids", [])),
            charge_ids=list(data.get("charge_ids", [])),
            items=items,
            trip_count=_as_int(data.get("trip_count")),
            charge_count=_as_int(data.get("charge_count")),
            distance_km=_as_float(data.get("distance_km")),
            driving_duration_seconds=_as_int(
                data.get("driving_duration_seconds")
            ),
            charging_duration_seconds=_as_int(
                data.get("charging_duration_seconds")
            ),
            total_duration_seconds=_as_int(
                data.get("total_duration_seconds")
            ),
            energy_used_kwh=_as_float(data.get("energy_used_kwh")),
            energy_charged_kwh=_as_float(
                data.get("energy_charged_kwh")
            ),
            average_consumption_kwh_100km=_as_float(
                data.get("average_consumption_kwh_100km")
            ),
            generator=str(data.get("generator", GENERATOR)),
            version=str(data.get("version", VERSION)),
        )

    def _rebuild_references(self) -> None:
        """Rebuild ordered, duplicate-free trip and charge references."""

        trip_ids: list[str] = []
        charge_ids: list[str] = []
        seen: set[tuple[str, str]] = set()
        unique_items: list[JourneyItem] = []

        for item in self.items:
            key = (item.item_type, item.item_id)
            if key in seen:
                continue

            seen.add(key)
            unique_items.append(item)

            if item.item_type == _ITEM_TRIP:
                trip_ids.append(item.item_id)
            elif item.item_type == _ITEM_CHARGE:
                charge_ids.append(item.item_id)

        self.items = unique_items
        self.trip_ids = trip_ids
        self.charge_ids = charge_ids

    def _apply_boundary_data(
        self,
        *,
        item: JourneyItem,
        start_address: str | None,
        end_address: str | None,
        start_latitude: float | None,
        start_longitude: float | None,
        end_latitude: float | None,
        end_longitude: float | None,
    ) -> None:
        """Update journey start and end information from a trip."""

        if self.trip_count == 0:
            self.start_address = _as_optional_string(start_address)
            self.start_latitude = _as_optional_float(start_latitude)
            self.start_longitude = _as_optional_float(start_longitude)

            if item.start_time:
                self.start_time = item.start_time

        normalized_end_address = _as_optional_string(end_address)
        if normalized_end_address is not None:
            self.end_address = normalized_end_address

        normalized_end_latitude = _as_optional_float(end_latitude)
        if normalized_end_latitude is not None:
            self.end_latitude = normalized_end_latitude

        normalized_end_longitude = _as_optional_float(end_longitude)
        if normalized_end_longitude is not None:
            self.end_longitude = normalized_end_longitude

        if item.end_time:
            self.end_time = item.end_time

    def _calculate_total_duration(self) -> int:
        """Calculate elapsed journey duration from start to end."""

        if self.start_time and self.end_time:
            try:
                start = datetime.fromisoformat(self.start_time)
                end = datetime.fromisoformat(self.end_time)
                return max(0, int((end - start).total_seconds()))
            except (TypeError, ValueError):
                pass

        return (
            self.driving_duration_seconds
            + self.charging_duration_seconds
        )
