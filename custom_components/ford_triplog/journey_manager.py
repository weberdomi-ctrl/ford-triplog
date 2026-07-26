"""
Ford Triplog

Track your Ford.

Daily journey lifecycle and matching manager.

Version: 1.6.0
Release: 1.6f
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from math import asin, cos, radians, sin, sqrt
from typing import Any, Mapping

from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import SIGNAL_LAST_JOURNEY_UPDATED
from .journey import FordTriplogJourney, JourneyItem
from .journey_storage import FordTriplogJourneyStorage

_LOGGER = logging.getLogger(__name__)

DEFAULT_TRIP_TO_CHARGE_TIMEOUT_SECONDS = 2 * 60 * 60
DEFAULT_CHARGE_TO_TRIP_TIMEOUT_SECONDS = 12 * 60 * 60
DEFAULT_CHARGE_TO_CHARGE_TIMEOUT_SECONDS = 2 * 60 * 60
DEFAULT_LOCATION_MATCH_RADIUS_METERS = 500.0


@dataclass(slots=True, frozen=True)
class JourneyUpdateResult:
    """Describe the result of processing one trip or charging session."""

    action: str
    journey: FordTriplogJourney | None = None
    completed_journey: FordTriplogJourney | None = None
    reason: str | None = None


class FordTriplogJourneyManager:
    """Build daily journeys without changing trip or charge records."""

    def __init__(
        self,
        hass: HomeAssistant,
        storage: FordTriplogJourneyStorage,
        *,
        trip_to_charge_timeout_seconds: int = (
            DEFAULT_TRIP_TO_CHARGE_TIMEOUT_SECONDS
        ),
        charge_to_trip_timeout_seconds: int = (
            DEFAULT_CHARGE_TO_TRIP_TIMEOUT_SECONDS
        ),
        charge_to_charge_timeout_seconds: int = (
            DEFAULT_CHARGE_TO_CHARGE_TIMEOUT_SECONDS
        ),
        location_match_radius_meters: float = (
            DEFAULT_LOCATION_MATCH_RADIUS_METERS
        ),
    ) -> None:
        """Initialize the daily journey manager."""

        self.hass = hass
        self.storage = storage

        self.trip_to_charge_timeout_seconds = max(
            0,
            int(trip_to_charge_timeout_seconds),
        )
        self.charge_to_trip_timeout_seconds = max(
            0,
            int(charge_to_trip_timeout_seconds),
        )
        self.charge_to_charge_timeout_seconds = max(
            0,
            int(charge_to_charge_timeout_seconds),
        )
        self.location_match_radius_meters = max(
            0.0,
            float(location_match_radius_meters),
        )

        self.current_journey: FordTriplogJourney | None = None
        self.last_journey: FordTriplogJourney | None = None

        self._trip_data: dict[str, dict[str, Any]] = {}
        self._charge_data: dict[str, dict[str, Any]] = {}

    async def async_setup(self) -> None:
        """Initialize storage and restore saved journey state."""

        await self.storage.async_setup()

        self.current_journey = (
            await self.storage.load_current_journey()
        )
        self.last_journey = await self.storage.load_last_journey()

        if (
            self.current_journey is not None
            and not self.current_journey.is_same_day()
        ):
            await self.async_finalize_current(
                reason="restored_journey_crosses_day_boundary"
            )

    async def async_process_trip(
        self,
        trip: Mapping[str, Any] | Any,
    ) -> JourneyUpdateResult:
        """Process one completed trip."""

        data = self._as_dict(trip)
        trip_id = self._required_id(data, "trip_id")
        start_time = self._required_datetime(data, "start_time")
        end_time = self._required_datetime(data, "end_time")

        if self._date_key(start_time) != self._date_key(end_time):
            return JourneyUpdateResult(
                action="ignored",
                reason="trip_crosses_day_boundary",
            )

        self._trip_data[trip_id] = data

        completed: FordTriplogJourney | None = None

        if self.current_journey is not None:
            if not self._same_journey_day(
                self.current_journey,
                start_time,
            ):
                completed = await self._finish_or_discard_current(
                    reason="day_changed"
                )

        if self.current_journey is None:
            journey = self._new_journey_from_trip(data)
            self.current_journey = journey
            await self.storage.save_current_journey(journey)

            return JourneyUpdateResult(
                action="started",
                journey=journey,
                completed_journey=completed,
            )

        last_item = self._last_item(self.current_journey)

        if last_item is None:
            journey = self._new_journey_from_trip(data)
            self.current_journey = journey
            await self.storage.save_current_journey(journey)

            return JourneyUpdateResult(
                action="restarted",
                journey=journey,
                completed_journey=completed,
                reason="current_journey_has_no_items",
            )

        if last_item.item_type == "charge":
            charge_data = self._charge_data.get(
                last_item.item_id
            )

            if charge_data is None:
                completed = await self._finish_or_discard_current(
                    reason="missing_charge_source_data"
                )
                journey = self._new_journey_from_trip(data)
                self.current_journey = journey
                await self.storage.save_current_journey(journey)

                return JourneyUpdateResult(
                    action="restarted",
                    journey=journey,
                    completed_journey=completed,
                    reason="missing_charge_source_data",
                )

            matches, reason = self._charge_matches_next_trip(
                charge_data,
                data,
            )

            if matches:
                self._add_trip(self.current_journey, data)
                await self.storage.save_current_journey(
                    self.current_journey
                )

                return JourneyUpdateResult(
                    action="updated",
                    journey=self.current_journey,
                    completed_journey=completed,
                    reason=reason,
                )

            completed = await self._finish_or_discard_current(
                reason=reason
            )
            journey = self._new_journey_from_trip(data)
            self.current_journey = journey
            await self.storage.save_current_journey(journey)

            return JourneyUpdateResult(
                action="restarted",
                journey=journey,
                completed_journey=completed,
                reason=reason,
            )

        completed = await self._finish_or_discard_current(
            reason="trip_without_intermediate_charge"
        )
        journey = self._new_journey_from_trip(data)
        self.current_journey = journey
        await self.storage.save_current_journey(journey)

        return JourneyUpdateResult(
            action="restarted",
            journey=journey,
            completed_journey=completed,
            reason="trip_without_intermediate_charge",
        )

    async def async_process_charge(
        self,
        charge: Mapping[str, Any] | Any,
    ) -> JourneyUpdateResult:
        """Process one completed charging session."""

        data = self._as_dict(charge)
        charge_id = self._required_id(data, "charge_id")
        start_time = self._required_datetime(data, "start_time")
        end_time = self._required_datetime(data, "end_time")

        if self._date_key(start_time) != self._date_key(end_time):
            completed = await self._finish_or_discard_current(
                reason="charge_crosses_day_boundary"
            )
            return JourneyUpdateResult(
                action="ignored",
                completed_journey=completed,
                reason="charge_crosses_day_boundary",
            )

        self._charge_data[charge_id] = data

        if self.current_journey is None:
            return JourneyUpdateResult(
                action="ignored",
                reason="charge_without_previous_trip",
            )

        if not self._same_journey_day(
            self.current_journey,
            start_time,
        ):
            completed = await self._finish_or_discard_current(
                reason="day_changed"
            )
            return JourneyUpdateResult(
                action="ignored",
                completed_journey=completed,
                reason="charge_without_previous_trip",
            )

        last_item = self._last_item(self.current_journey)

        if last_item is None:
            return JourneyUpdateResult(
                action="ignored",
                journey=self.current_journey,
                reason="charge_without_previous_item",
            )

        if last_item.item_type == "trip":
            trip_data = self._trip_data.get(last_item.item_id)

            if trip_data is None:
                return JourneyUpdateResult(
                    action="ignored",
                    journey=self.current_journey,
                    reason="missing_trip_source_data",
                )

            matches, reason = self._trip_matches_charge(
                trip_data,
                data,
            )
        elif last_item.item_type == "charge":
            previous_charge = self._charge_data.get(last_item.item_id)

            if previous_charge is None:
                return JourneyUpdateResult(
                    action="ignored",
                    journey=self.current_journey,
                    reason="missing_previous_charge_source_data",
                )

            matches, reason = self._charge_matches_charge(
                previous_charge,
                data,
            )
        else:
            return JourneyUpdateResult(
                action="ignored",
                journey=self.current_journey,
                reason="unsupported_previous_item_type",
            )

        if not matches:
            completed = await self._finish_or_discard_current(
                reason=reason
            )
            return JourneyUpdateResult(
                action="ignored",
                completed_journey=completed,
                reason=reason,
            )

        self._add_charge(self.current_journey, data)
        await self.storage.save_current_journey(
            self.current_journey
        )

        return JourneyUpdateResult(
            action="updated",
            journey=self.current_journey,
            reason=reason,
        )

    async def async_finalize_current(
        self,
        *,
        reason: str = "manual",
    ) -> JourneyUpdateResult:
        """Finalize or discard the current daily journey."""

        completed = await self._finish_or_discard_current(
            reason=reason
        )

        if completed is None:
            return JourneyUpdateResult(
                action="discarded",
                reason=reason,
            )

        return JourneyUpdateResult(
            action="completed",
            completed_journey=completed,
            reason=reason,
        )

    async def async_finalize_if_day_changed(
        self,
        reference_time: datetime | str,
    ) -> JourneyUpdateResult:
        """Finalize the current journey when a new local day starts."""

        if self.current_journey is None:
            return JourneyUpdateResult(
                action="unchanged",
                reason="no_current_journey",
            )

        reference = self._parse_datetime(reference_time)

        if self._same_journey_day(
            self.current_journey,
            reference,
        ):
            return JourneyUpdateResult(
                action="unchanged",
                journey=self.current_journey,
                reason="same_day",
            )

        return await self.async_finalize_current(
            reason="day_changed"
        )

    @staticmethod
    def is_complete_journey(
        journey: FordTriplogJourney,
    ) -> bool:
        """Return whether a journey contains Trip-Charge-Trip."""

        if journey.trip_count < 2 or journey.charge_count < 1:
            return False

        item_types = [
            item.item_type
            for item in journey.items
        ]

        if (
            not item_types
            or item_types[0] != "trip"
            or item_types[-1] != "trip"
        ):
            return False

        # Consecutive charging sessions are valid. This occurs, for example,
        # when the vehicle reaches a configured SOC limit and charging is then
        # restarted without an intervening trip. Consecutive trips still split
        # journeys because a charge is required between journey legs.
        return all(
            not (current == following == "trip")
            for current, following in zip(
                item_types,
                item_types[1:],
            )
        )

    async def _finish_or_discard_current(
        self,
        *,
        reason: str,
    ) -> FordTriplogJourney | None:
        """Archive a valid journey or discard an incomplete candidate."""

        journey = self.current_journey
        self.current_journey = None

        if journey is None:
            return None

        await self.storage.clear_current_journey()

        self._remove_cached_source_data(journey)

        if not self.is_complete_journey(journey):
            _LOGGER.debug(
                "Discarded incomplete journey %s: %s",
                journey.journey_id,
                reason,
            )
            return None

        journey.recalculate()
        await self.storage.save_completed_journey(journey)

        self.last_journey = journey

        async_dispatcher_send(
            self.hass,
            SIGNAL_LAST_JOURNEY_UPDATED,
            journey.to_dict(),
        )

        _LOGGER.info(
            "Completed journey %s with %s trips and %s charges: %s",
            journey.journey_id,
            journey.trip_count,
            journey.charge_count,
            reason,
        )

        return journey

    def _new_journey_from_trip(
        self,
        trip: Mapping[str, Any],
    ) -> FordTriplogJourney:
        """Create a new daily journey candidate from one trip."""

        journey = FordTriplogJourney()
        self._add_trip(journey, trip)
        return journey

    @staticmethod
    def _last_item(
        journey: FordTriplogJourney,
    ) -> JourneyItem | None:
        """Return the last journey item."""

        if not journey.items:
            return None

        return journey.items[-1]

    @staticmethod
    def _as_dict(
        value: Mapping[str, Any] | Any,
    ) -> dict[str, Any]:
        """Convert a supported trip or charge object to a dictionary."""

        if isinstance(value, Mapping):
            return dict(value)

        to_dict = getattr(value, "to_dict", None)
        if callable(to_dict):
            data = to_dict()
            if isinstance(data, Mapping):
                return dict(data)

        raise TypeError(
            "Trip or charge value must be a mapping or provide to_dict()"
        )

    @staticmethod
    def _required_id(
        data: Mapping[str, Any],
        key: str,
    ) -> str:
        """Return one required identifier."""

        value = str(data.get(key, "")).strip()
        if not value:
            raise ValueError(f"Missing required field: {key}")

        return value

    @classmethod
    def _required_datetime(
        cls,
        data: Mapping[str, Any],
        key: str,
    ) -> datetime:
        """Return one required datetime field."""

        value = data.get(key)
        if value is None:
            raise ValueError(f"Missing required field: {key}")

        return cls._parse_datetime(value)

    @staticmethod
    def _parse_datetime(
        value: datetime | str,
    ) -> datetime:
        """Parse one ISO datetime value."""

        if isinstance(value, datetime):
            return value

        normalized = str(value).strip().replace(
            "Z",
            "+00:00",
        )
        if not normalized:
            raise ValueError("Datetime value must not be empty")

        return datetime.fromisoformat(normalized)

    @staticmethod
    def _date_key(value: datetime) -> str:
        """Return the local date represented by a datetime."""

        return value.date().isoformat()

    @classmethod
    def _same_journey_day(
        cls,
        journey: FordTriplogJourney,
        value: datetime,
    ) -> bool:
        """Return whether a datetime belongs to the journey date."""

        journey_date = journey.date

        if journey_date is None and journey.start_time:
            journey_date = cls._date_key(
                cls._parse_datetime(journey.start_time)
            )

        return journey_date == cls._date_key(value)

    def _trip_matches_charge(
        self,
        trip: Mapping[str, Any],
        charge: Mapping[str, Any],
    ) -> tuple[bool, str]:
        """Check whether a charge follows a trip."""

        trip_id = str(trip.get("trip_id", "")).strip()
        charge_id = str(charge.get("charge_id", "")).strip()

        linked_charge_id = str(
            trip.get("next_charge_id") or ""
        ).strip()
        previous_trip_id = str(
            charge.get("previous_trip_id") or ""
        ).strip()

        if linked_charge_id:
            if linked_charge_id != charge_id:
                return False, "trip_links_different_charge"
            return True, "matched_by_trip_link"

        if previous_trip_id:
            if previous_trip_id != trip_id:
                return False, "charge_links_different_trip"
            return True, "matched_by_charge_link"

        trip_end = self._required_datetime(
            trip,
            "end_time",
        )
        charge_start = self._required_datetime(
            charge,
            "start_time",
        )

        gap = (charge_start - trip_end).total_seconds()

        if gap < 0:
            return False, "charge_starts_before_trip_ends"

        if gap > self.trip_to_charge_timeout_seconds:
            return False, "trip_to_charge_timeout"

        if not self._locations_match(
            trip.get("end_latitude"),
            trip.get("end_longitude"),
            charge.get("start_latitude"),
            charge.get("start_longitude"),
        ):
            return False, "trip_and_charge_locations_do_not_match"

        return True, "matched_by_time_and_location"


    def _charge_matches_charge(
        self,
        previous_charge: Mapping[str, Any],
        charge: Mapping[str, Any],
    ) -> tuple[bool, str]:
        """Check whether another charge continues at the same stop."""

        previous_end = self._required_datetime(
            previous_charge,
            "end_time",
        )
        charge_start = self._required_datetime(
            charge,
            "start_time",
        )

        gap = (charge_start - previous_end).total_seconds()

        if gap < 0:
            return False, "charge_starts_before_previous_charge_ends"

        if gap > self.charge_to_charge_timeout_seconds:
            return False, "charge_to_charge_timeout"

        if not self._locations_match(
            previous_charge.get("end_latitude"),
            previous_charge.get("end_longitude"),
            charge.get("start_latitude"),
            charge.get("start_longitude"),
        ):
            return False, "consecutive_charge_locations_do_not_match"

        return True, "matched_consecutive_charge_by_time_and_location"

    def _charge_matches_next_trip(
        self,
        charge: Mapping[str, Any],
        trip: Mapping[str, Any],
    ) -> tuple[bool, str]:
        """Check whether a trip follows a charge.

        ``charge.trip_id`` belongs to the trip that preceded the charging
        session. It must not be interpreted as a link to the following trip.
        The next trip is therefore matched by chronology and location.
        """

        charge_end = self._required_datetime(
            charge,
            "end_time",
        )
        trip_start = self._required_datetime(
            trip,
            "start_time",
        )

        gap = (trip_start - charge_end).total_seconds()

        if gap < 0:
            return False, "trip_starts_before_charge_ends"

        if gap > self.charge_to_trip_timeout_seconds:
            return False, "charge_to_trip_timeout"

        if not self._locations_match(
            charge.get("end_latitude"),
            charge.get("end_longitude"),
            trip.get("start_latitude"),
            trip.get("start_longitude"),
        ):
            return False, "charge_and_trip_locations_do_not_match"

        return True, "matched_by_time_and_location"

    def _locations_match(
        self,
        first_latitude: Any,
        first_longitude: Any,
        second_latitude: Any,
        second_longitude: Any,
    ) -> bool:
        """Compare two locations.

        Missing coordinates are treated as unknown rather than as a mismatch.
        Existing trip/charge links and chronological checks still protect the
        journey sequence.
        """

        coordinates = (
            first_latitude,
            first_longitude,
            second_latitude,
            second_longitude,
        )

        if any(value is None for value in coordinates):
            return True

        try:
            distance = self._distance_meters(
                float(first_latitude),
                float(first_longitude),
                float(second_latitude),
                float(second_longitude),
            )
        except (TypeError, ValueError):
            return True

        return distance <= self.location_match_radius_meters

    @staticmethod
    def _distance_meters(
        first_latitude: float,
        first_longitude: float,
        second_latitude: float,
        second_longitude: float,
    ) -> float:
        """Calculate the great-circle distance between two coordinates."""

        earth_radius_meters = 6_371_000.0

        latitude_1 = radians(first_latitude)
        latitude_2 = radians(second_latitude)
        latitude_delta = radians(
            second_latitude - first_latitude
        )
        longitude_delta = radians(
            second_longitude - first_longitude
        )

        haversine = (
            sin(latitude_delta / 2) ** 2
            + cos(latitude_1)
            * cos(latitude_2)
            * sin(longitude_delta / 2) ** 2
        )

        return (
            2
            * earth_radius_meters
            * asin(sqrt(haversine))
        )

    @staticmethod
    def _duration_seconds(
        data: Mapping[str, Any],
    ) -> int:
        """Return stored or calculated duration."""

        raw_duration = data.get("duration_seconds")

        if raw_duration is not None:
            try:
                return max(
                    0,
                    int(float(raw_duration)),
                )
            except (TypeError, ValueError):
                pass

        start_time = data.get("start_time")
        end_time = data.get("end_time")

        if start_time is None or end_time is None:
            return 0

        try:
            start = FordTriplogJourneyManager._parse_datetime(
                start_time
            )
            end = FordTriplogJourneyManager._parse_datetime(
                end_time
            )
        except (TypeError, ValueError):
            return 0

        return max(
            0,
            int((end - start).total_seconds()),
        )

    @staticmethod
    def _float_value(
        data: Mapping[str, Any],
        key: str,
    ) -> float:
        """Return one non-negative float value."""

        value = data.get(key)

        if value is None:
            return 0.0

        try:
            return max(
                0.0,
                float(value),
            )
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _address_value(value: Any) -> str | None:
        """Return a readable address value."""

        if value is None:
            return None

        if isinstance(value, str):
            normalized = value.strip()
            return normalized or None

        if isinstance(value, Mapping):
            for key in (
                "display",
                "display_name",
                "formatted",
                "address",
                "name",
            ):
                candidate = value.get(key)
                if candidate:
                    return str(candidate).strip() or None

            return None

        return str(value).strip() or None

    def _add_trip(
        self,
        journey: FordTriplogJourney,
        trip: Mapping[str, Any],
    ) -> None:
        """Add one trip to a journey."""

        journey.add_trip(
            self._required_id(trip, "trip_id"),
            start_time=trip.get("start_time"),
            end_time=trip.get("end_time"),
            distance_km=self._float_value(
                trip,
                "distance_km",
            ),
            duration_seconds=self._duration_seconds(trip),
            energy_used_kwh=self._float_value(
                trip,
                "energy_used_kwh",
            ),
            start_address=self._address_value(
                trip.get("start_address")
            ),
            end_address=self._address_value(
                trip.get("end_address")
            ),
            start_latitude=trip.get("start_latitude"),
            start_longitude=trip.get("start_longitude"),
            end_latitude=trip.get("end_latitude"),
            end_longitude=trip.get("end_longitude"),
        )

    def _add_charge(
        self,
        journey: FordTriplogJourney,
        charge: Mapping[str, Any],
    ) -> None:
        """Add one charging session to a journey."""

        journey.add_charge(
            self._required_id(charge, "charge_id"),
            start_time=charge.get("start_time"),
            end_time=charge.get("end_time"),
            duration_seconds=self._duration_seconds(charge),
            energy_charged_kwh=self._float_value(
                charge,
                "energy_added_kwh",
            ),
        )

    def _remove_cached_source_data(
        self,
        journey: FordTriplogJourney,
    ) -> None:
        """Remove source snapshots belonging to a finished candidate."""

        for trip_id in journey.trip_ids:
            self._trip_data.pop(trip_id, None)

        for charge_id in journey.charge_ids:
            self._charge_data.pop(charge_id, None)
