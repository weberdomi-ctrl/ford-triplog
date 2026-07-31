"""
Ford Triplog

Track your Ford.

Daily journey lifecycle and matching manager.

Version: 1.7.3
Release: 1.7.3
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from math import asin, cos, radians, sin, sqrt
from typing import Any, Callable, Mapping

from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_call_later

from .const import (
    DEFAULT_JOURNEY_HOME_TIMEOUT,
    DEFAULT_JOURNEY_HOME_ZONE,
    DEFAULT_JOURNEY_MAX_GAP_HOURS,
    SIGNAL_LAST_JOURNEY_UPDATED,
)
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
        journey_max_gap_hours: int = DEFAULT_JOURNEY_MAX_GAP_HOURS,
        home_zone_entity_id: str = DEFAULT_JOURNEY_HOME_ZONE,
        home_timeout_minutes: int = DEFAULT_JOURNEY_HOME_TIMEOUT,
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
        self.journey_max_gap_seconds = max(
            1,
            int(journey_max_gap_hours),
        ) * 60 * 60
        self.home_zone_entity_id = (
            str(home_zone_entity_id).strip() or DEFAULT_JOURNEY_HOME_ZONE
        )
        self.home_timeout_seconds = max(
            0,
            int(home_timeout_minutes),
        ) * 60

        self.current_journey: FordTriplogJourney | None = None
        self.last_journey: FordTriplogJourney | None = None

        self._trip_data: dict[str, dict[str, Any]] = {}
        self._charge_data: dict[str, dict[str, Any]] = {}

        self._home_arrival_time: datetime | None = None
        self._home_timeout_cancel: Callable[[], None] | None = None
        self._home_timeout_journey_id: str | None = None
        self._home_timeout_reason: str | None = None

    async def async_setup(self) -> None:
        """Initialize storage and restore saved journey state."""

        await self.storage.async_setup()

        self.current_journey = (
            await self.storage.load_current_journey()
        )
        self.last_journey = await self.storage.load_last_journey()


    async def async_process_trip(
        self,
        trip: Mapping[str, Any] | Any,
    ) -> JourneyUpdateResult:
        """Process one completed trip."""

        data = self._as_dict(trip)
        trip_id = self._required_id(data, "trip_id")
        start_time = self._required_datetime(data, "start_time")
        end_time = self._required_datetime(data, "end_time")

        _LOGGER.info(
            "Journey debug: process trip %s (%s -> %s), current=%s, items=%s",
            trip_id,
            start_time.isoformat(),
            end_time.isoformat(),
            self.current_journey.journey_id if self.current_journey else None,
            self._item_summary(self.current_journey),
        )

        # A new trip cancels a pending minimum-stay timer. When no timer was
        # active, its start position can still confirm that the previous
        # journey had already returned home.
        had_pending_home_timeout = self._home_timeout_cancel is not None
        self._cancel_home_timeout(reason="new_trip_started")

        self._trip_data[trip_id] = data

        completed: FordTriplogJourney | None = None

        if (
            not had_pending_home_timeout
            and self.current_journey is not None
            and self._can_complete_at_last_trip(self.current_journey)
            and self._trip_start_confirms_home(data)
        ):
            last_trip = self._last_trip_source_data(self.current_journey)
            if last_trip is not None:
                previous_end = self._required_datetime(last_trip, "end_time")
                home_stay = (start_time - previous_end).total_seconds()

                if home_stay >= self.home_timeout_seconds:
                    if not self._trim_current_to_last_trip():
                        _LOGGER.warning(
                            "Journey could not be trimmed to its last trip: %s",
                            self.current_journey.journey_id,
                        )
                    completed = await self._finish_or_discard_current(
                        reason="returned_to_home_zone_next_trip"
                    )
                    journey = self._new_journey_from_trip(data)
                    self.current_journey = journey
                    await self.storage.save_current_journey(journey)

                    return JourneyUpdateResult(
                        action="restarted",
                        journey=journey,
                        completed_journey=completed,
                        reason="returned_to_home_zone_next_trip",
                    )

                _LOGGER.info(
                    "Journey home confirmation by next trip ignored because "
                    "minimum stay was not reached: journey=%s stay=%.1fs "
                    "required=%ss",
                    self.current_journey.journey_id,
                    home_stay,
                    self.home_timeout_seconds,
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
            _LOGGER.info(
                "Journey debug: charge %s -> trip %s match=%s reason=%s",
                last_item.item_id,
                trip_id,
                matches,
                reason,
            )

            if matches:
                self._add_trip(self.current_journey, data)

                completed = await self._async_handle_home_arrival(
                    self.current_journey,
                    data,
                    reason="returned_to_home_zone_trip",
                )
                if completed is not None:
                    return JourneyUpdateResult(
                        action="completed",
                        completed_journey=completed,
                        reason="returned_to_home_zone_trip",
                    )

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

        previous_trip = self._trip_data.get(last_item.item_id)
        if previous_trip is None:
            completed = await self._finish_or_discard_current(
                reason="missing_previous_trip_source_data"
            )
            journey = self._new_journey_from_trip(data)
            self.current_journey = journey
            await self.storage.save_current_journey(journey)
            return JourneyUpdateResult(
                action="restarted",
                journey=journey,
                completed_journey=completed,
                reason="missing_previous_trip_source_data",
            )

        matches, reason = self._trip_matches_trip(previous_trip, data)
        _LOGGER.info(
            "Journey debug: trip %s -> trip %s match=%s reason=%s",
            last_item.item_id,
            trip_id,
            matches,
            reason,
        )

        if matches:
            self._add_trip(self.current_journey, data)

            completed = await self._async_handle_home_arrival(
                self.current_journey,
                data,
                reason="returned_to_home_zone_trip",
            )
            if completed is not None:
                return JourneyUpdateResult(
                    action="completed",
                    completed_journey=completed,
                    reason="returned_to_home_zone_trip",
                )

            await self.storage.save_current_journey(self.current_journey)
            return JourneyUpdateResult(
                action="updated",
                journey=self.current_journey,
                completed_journey=completed,
                reason=reason,
            )

        completed = await self._finish_or_discard_current(reason=reason)
        journey = self._new_journey_from_trip(data)
        self.current_journey = journey
        await self.storage.save_current_journey(journey)
        return JourneyUpdateResult(
            action="restarted",
            journey=journey,
            completed_journey=completed,
            reason=reason,
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

        _LOGGER.info(
            "Journey debug: process charge %s (%s -> %s), previous_trip_id=%s, current=%s, items=%s",
            charge_id,
            start_time.isoformat(),
            end_time.isoformat(),
            data.get("previous_trip_id") or data.get("trip_id"),
            self.current_journey.journey_id if self.current_journey else None,
            self._item_summary(self.current_journey),
        )

        self._charge_data[charge_id] = data

        if self.current_journey is None:
            return JourneyUpdateResult(
                action="ignored",
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
            _LOGGER.info(
                "Journey debug: trip %s -> charge %s match=%s reason=%s, trip.next_charge_id=%s, charge.previous_trip_id=%s",
                last_item.item_id,
                charge_id,
                matches,
                reason,
                trip_data.get("next_charge_id"),
                data.get("previous_trip_id") or data.get("trip_id"),
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
            _LOGGER.info(
                "Journey debug: charge %s -> charge %s match=%s reason=%s",
                last_item.item_id,
                charge_id,
                matches,
                reason,
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

        if (
            self.is_complete_journey(self.current_journey)
            and self._charge_confirms_home(data)
        ):
            last_trip = self._last_trip_source_data(self.current_journey)
            if last_trip is not None:
                completed = await self._async_confirm_home(
                    self.current_journey,
                    last_trip,
                    reason="returned_to_home_zone_charge",
                )
                if completed is not None:
                    return JourneyUpdateResult(
                        action="completed",
                        completed_journey=completed,
                        reason="returned_to_home_zone_charge",
                    )

                await self.storage.save_current_journey(
                    self.current_journey
                )
                return JourneyUpdateResult(
                    action="updated",
                    journey=self.current_journey,
                    reason="home_confirmation_pending_charge",
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
        """Keep journeys open across calendar-day boundaries."""

        return JourneyUpdateResult(
            action="unchanged",
            journey=self.current_journey,
            reason="calendar_day_boundary_ignored",
        )

    @staticmethod
    def is_complete_journey(
        journey: FordTriplogJourney,
    ) -> bool:
        """Return whether a journey starts and ends with at least two trips."""

        if journey.trip_count < 2:
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

        # Both consecutive trips and consecutive charging sessions are valid.
        return all(item_type in {"trip", "charge"} for item_type in item_types)

    async def _finish_or_discard_current(
        self,
        *,
        reason: str,
    ) -> FordTriplogJourney | None:
        """Archive a valid journey or discard an incomplete candidate."""

        self._cancel_home_timeout(reason="journey_finished")

        journey = self.current_journey
        self.current_journey = None

        if journey is None:
            return None

        await self.storage.clear_current_journey()

        self._remove_cached_source_data(journey)

        if not self.is_complete_journey(journey):
            _LOGGER.info(
                "Journey debug: discarded incomplete journey %s: reason=%s, trips=%s, charges=%s, items=%s",
                journey.journey_id,
                reason,
                journey.trip_count,
                journey.charge_count,
                self._item_summary(journey),
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
    def _item_summary(
        journey: FordTriplogJourney | None,
    ) -> str:
        """Return a compact journey item list for diagnostics."""

        if journey is None:
            return "[]"

        return "[" + ", ".join(
            f"{item.item_type}:{item.item_id}"
            for item in journey.items
        ) + "]"

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


    async def _async_handle_home_arrival(
        self,
        journey: FordTriplogJourney,
        trip: Mapping[str, Any],
        *,
        reason: str,
    ) -> FordTriplogJourney | None:
        """Finish or schedule completion after a trip reaches home."""

        if not self.is_complete_journey(journey):
            return None

        if not self._trip_end_confirms_home(trip):
            return None

        return await self._async_confirm_home(
            journey,
            trip,
            reason=reason,
        )

    async def _async_confirm_home(
        self,
        journey: FordTriplogJourney,
        last_trip: Mapping[str, Any],
        *,
        reason: str,
    ) -> FordTriplogJourney | None:
        """Finish immediately or schedule completion from the last trip end."""

        arrival_time = self._required_datetime(last_trip, "end_time")

        if self.home_timeout_seconds <= 0:
            _LOGGER.info(
                "Journey home confirmed: journey=%s reason=%s, "
                "completing immediately",
                journey.journey_id,
                reason,
            )
            return await self._finish_or_discard_current(reason=reason)

        now = datetime.now(tz=arrival_time.tzinfo)
        elapsed = max(0.0, (now - arrival_time).total_seconds())
        if elapsed >= self.home_timeout_seconds:
            _LOGGER.info(
                "Journey home confirmed: journey=%s reason=%s stay=%.1fs, "
                "minimum stay already reached",
                journey.journey_id,
                reason,
                elapsed,
            )
            return await self._finish_or_discard_current(reason=reason)

        self._schedule_home_timeout(
            journey,
            arrival_time,
            reason=reason,
        )
        return None

    def _schedule_home_timeout(
        self,
        journey: FordTriplogJourney,
        arrival_time: datetime,
        *,
        reason: str,
    ) -> None:
        """Schedule journey completion after the minimum stay at home."""

        self._cancel_home_timeout(reason="home_timeout_rescheduled")

        self._home_arrival_time = arrival_time
        self._home_timeout_journey_id = journey.journey_id
        self._home_timeout_reason = reason

        now = datetime.now(tz=arrival_time.tzinfo)
        elapsed = max(0.0, (now - arrival_time).total_seconds())
        delay = max(0.0, self.home_timeout_seconds - elapsed)

        async def _async_finish_after_home_timeout(_now: datetime) -> None:
            expected_journey_id = self._home_timeout_journey_id
            completion_reason = self._home_timeout_reason or reason
            self._home_timeout_cancel = None
            self._home_timeout_journey_id = None
            self._home_timeout_reason = None
            self._home_arrival_time = None

            if (
                self.current_journey is None
                or self.current_journey.journey_id != expected_journey_id
            ):
                return

            await self._finish_or_discard_current(
                reason=f"{completion_reason}_timeout_elapsed"
            )

        self._home_timeout_cancel = async_call_later(
            self.hass,
            delay,
            _async_finish_after_home_timeout,
        )

        _LOGGER.info(
            "Journey home timeout started: journey=%s arrival=%s "
            "delay=%.1fs reason=%s",
            journey.journey_id,
            arrival_time.isoformat(),
            delay,
            reason,
        )

    def _cancel_home_timeout(self, *, reason: str) -> None:
        """Cancel and clear a pending home-stay timeout."""

        had_pending_timeout = self._home_timeout_cancel is not None

        if self._home_timeout_cancel is not None:
            self._home_timeout_cancel()

        self._home_timeout_cancel = None
        self._home_timeout_journey_id = None
        self._home_timeout_reason = None
        self._home_arrival_time = None

        if had_pending_timeout:
            _LOGGER.info(
                "Journey home timeout cancelled: reason=%s",
                reason,
            )

    def _can_complete_at_last_trip(
        self,
        journey: FordTriplogJourney,
    ) -> bool:
        """Return whether a journey can be completed at its last trip."""

        trip_items = [
            item for item in journey.items if item.item_type == "trip"
        ]
        return (
            len(trip_items) >= 2
            and bool(journey.items)
            and journey.items[0].item_type == "trip"
        )

    def _trim_current_to_last_trip(self) -> bool:
        """Remove trailing charges by rebuilding through the last trip."""

        journey = self.current_journey
        if journey is None or not journey.items:
            return False

        last_trip_index = -1
        for index, item in enumerate(journey.items):
            if item.item_type == "trip":
                last_trip_index = index

        if last_trip_index < 0:
            return False
        if last_trip_index == len(journey.items) - 1:
            return True

        rebuilt = FordTriplogJourney(
            journey_id=journey.journey_id,
            created=journey.created,
        )

        for item in journey.items[: last_trip_index + 1]:
            if item.item_type == "trip":
                source = self._trip_data.get(item.item_id)
                if source is None:
                    return False
                self._add_trip(rebuilt, source)
            elif item.item_type == "charge":
                source = self._charge_data.get(item.item_id)
                if source is None:
                    return False
                self._add_charge(rebuilt, source)

        self.current_journey = rebuilt
        _LOGGER.info(
            "Journey trailing charges removed before home completion: "
            "journey=%s items=%s",
            rebuilt.journey_id,
            self._item_summary(rebuilt),
        )
        return True

    def _last_trip_source_data(
        self,
        journey: FordTriplogJourney,
    ) -> dict[str, Any] | None:
        """Return source data for the last trip in a journey."""

        for item in reversed(journey.items):
            if item.item_type == "trip":
                return self._trip_data.get(item.item_id)

        return None

    def _trip_end_confirms_home(
        self,
        trip: Mapping[str, Any],
    ) -> bool:
        """Return whether a trip end lies inside the home zone."""

        latitude, longitude = self._coordinates_from_data(
            trip,
            prefix="end",
        )
        return self._is_location_inside_home(
            latitude,
            longitude,
            source="trip_end",
            item_id=trip.get("trip_id"),
        )

    def _trip_start_confirms_home(
        self,
        trip: Mapping[str, Any],
    ) -> bool:
        """Return whether a trip start lies inside the home zone."""

        latitude, longitude = self._coordinates_from_data(
            trip,
            prefix="start",
        )
        return self._is_location_inside_home(
            latitude,
            longitude,
            source="trip_start",
            item_id=trip.get("trip_id"),
        )

    def _charge_confirms_home(
        self,
        charge: Mapping[str, Any],
    ) -> bool:
        """Return whether a charge start or end lies inside the home zone."""

        for prefix in ("start", "end"):
            latitude, longitude = self._coordinates_from_data(
                charge,
                prefix=prefix,
            )
            if self._is_location_inside_home(
                latitude,
                longitude,
                source=f"charge_{prefix}",
                item_id=charge.get("charge_id"),
            ):
                return True

        return False

    @staticmethod
    def _coordinates_from_data(
        data: Mapping[str, Any],
        *,
        prefix: str,
    ) -> tuple[Any, Any]:
        """Return coordinates from direct fields or a nested address."""

        latitude = data.get(f"{prefix}_latitude")
        longitude = data.get(f"{prefix}_longitude")
        address = data.get(f"{prefix}_address")

        if isinstance(address, Mapping):
            if latitude is None:
                latitude = address.get("latitude")
            if longitude is None:
                longitude = address.get("longitude")

        return latitude, longitude

    def _is_location_inside_home(
        self,
        latitude: Any,
        longitude: Any,
        *,
        source: str,
        item_id: Any,
    ) -> bool:
        """Return whether one coordinate lies inside the configured home zone."""

        zone_state = self.hass.states.get(self.home_zone_entity_id)
        if zone_state is None:
            _LOGGER.debug(
                "Journey home-zone check skipped: %s not found",
                self.home_zone_entity_id,
            )
            return False

        zone_latitude = zone_state.attributes.get("latitude")
        zone_longitude = zone_state.attributes.get("longitude")
        zone_radius = zone_state.attributes.get("radius")

        coordinates = (
            latitude,
            longitude,
            zone_latitude,
            zone_longitude,
            zone_radius,
        )
        if any(value is None for value in coordinates):
            _LOGGER.debug(
                "Journey home-zone check skipped: source=%s item=%s "
                "coordinates or radius missing",
                source,
                item_id,
            )
            return False

        try:
            distance = self._distance_meters(
                float(latitude),
                float(longitude),
                float(zone_latitude),
                float(zone_longitude),
            )
            radius = max(0.0, float(zone_radius))
        except (TypeError, ValueError):
            return False

        inside_home = distance <= radius
        _LOGGER.info(
            "Journey home-zone check: source=%s item=%s zone=%s "
            "distance=%.1fm radius=%.1fm inside=%s",
            source,
            item_id,
            self.home_zone_entity_id,
            distance,
            radius,
            inside_home,
        )
        return inside_home

    def _trip_matches_trip(
        self,
        previous_trip: Mapping[str, Any],
        trip: Mapping[str, Any],
    ) -> tuple[bool, str]:
        """Check whether a trip continues the current journey."""

        previous_end = self._required_datetime(previous_trip, "end_time")
        trip_start = self._required_datetime(trip, "start_time")
        gap = (trip_start - previous_end).total_seconds()

        if gap < 0:
            return False, "trip_starts_before_previous_trip_ends"
        if gap > self.journey_max_gap_seconds:
            return False, "journey_max_gap_exceeded"

        if not self._locations_match(
            previous_trip.get("end_latitude"),
            previous_trip.get("end_longitude"),
            trip.get("start_latitude"),
            trip.get("start_longitude"),
        ):
            return True, "matched_by_time_location_changed"

        return True, "matched_by_time"

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

        # A trip stores only one next_charge_id. If several charging
        # sessions follow the same trip, a later session may overwrite that
        # field. Therefore the charge's previous_trip_id is authoritative
        # whenever it is present.
        if previous_trip_id:
            if previous_trip_id != trip_id:
                return False, "charge_links_different_trip"
            if linked_charge_id == charge_id:
                return True, "matched_by_both_links"
            if linked_charge_id:
                return True, "matched_by_charge_link_trip_points_to_later_charge"
            return True, "matched_by_charge_link"

        if linked_charge_id:
            if linked_charge_id != charge_id:
                return False, "trip_links_different_charge"
            return True, "matched_by_trip_link"

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

        if gap > self.journey_max_gap_seconds:
            return False, "journey_max_gap_exceeded"

        if not self._locations_match(
            trip.get("end_latitude"),
            trip.get("end_longitude"),
            charge.get("start_latitude"),
            charge.get("start_longitude"),
        ):
            return True, "matched_by_time_location_changed"

        return True, "matched_by_time"


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

        if gap > self.journey_max_gap_seconds:
            return False, "journey_max_gap_exceeded"

        if not self._locations_match(
            previous_charge.get("end_latitude"),
            previous_charge.get("end_longitude"),
            charge.get("start_latitude"),
            charge.get("start_longitude"),
        ):
            return True, "matched_by_time_location_changed"

        return True, "matched_by_time"

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

        if gap > self.journey_max_gap_seconds:
            return False, "journey_max_gap_exceeded"

        if not self._locations_match(
            charge.get("end_latitude"),
            charge.get("end_longitude"),
            trip.get("start_latitude"),
            trip.get("start_longitude"),
        ):
            return True, "matched_by_time_location_changed"

        return True, "matched_by_time"

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
    def _optional_float_value(
        data: Mapping[str, Any],
        key: str,
    ) -> float | None:
        """Return one optional float value without converting missing data to zero."""

        value = data.get(key)
        if value is None:
            return None

        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _resolve_zone_name(
        self,
        latitude: Any,
        longitude: Any,
    ) -> str | None:
        """Resolve coordinates against all configured Home Assistant zones."""

        try:
            item_latitude = float(latitude)
            item_longitude = float(longitude)
        except (TypeError, ValueError):
            return None

        matching_zone: tuple[float, str] | None = None

        for zone_state in self.hass.states.async_all("zone"):
            zone_latitude = zone_state.attributes.get("latitude")
            zone_longitude = zone_state.attributes.get("longitude")
            zone_radius = zone_state.attributes.get("radius", 100)

            try:
                distance = self._distance_meters(
                    item_latitude,
                    item_longitude,
                    float(zone_latitude),
                    float(zone_longitude),
                )
                radius = max(0.0, float(zone_radius))
            except (TypeError, ValueError):
                continue

            if distance > radius:
                continue

            zone_name = str(
                zone_state.attributes.get(
                    "friendly_name",
                    zone_state.name,
                )
            ).strip()
            if not zone_name:
                continue

            if matching_zone is None or distance < matching_zone[0]:
                matching_zone = (distance, zone_name)

        return matching_zone[1] if matching_zone else None

    @staticmethod
    def _fordpass_location(
        charge: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Return the FordPass charging location snapshot when available."""

        snapshot = charge.get("fordpass_last_charge")
        if not isinstance(snapshot, Mapping):
            return {}

        attributes = snapshot.get("attributes")
        if not isinstance(attributes, Mapping):
            return {}

        location = attributes.get("location")
        return dict(location) if isinstance(location, Mapping) else {}

    @classmethod
    def _fordpass_address(
        cls,
        location: Mapping[str, Any],
    ) -> str | None:
        """Return a readable address from a FordPass location."""

        address = location.get("address")
        if not isinstance(address, Mapping):
            return cls._address_value(address)

        address_1 = cls._address_value(address.get("address1"))
        postcode = cls._address_value(address.get("postalCode"))
        city = cls._address_value(address.get("city"))

        locality = " ".join(
            part for part in (postcode, city) if part
        )

        if address_1 and locality:
            return f"{address_1}, {locality}"
        return address_1 or locality or None

    def _resolve_trip_location(
        self,
        trip: Mapping[str, Any],
        *,
        prefix: str,
    ) -> tuple[str | None, str | None, Any, Any, str | None]:
        """Resolve one trip boundary using zone before address."""

        latitude, longitude = self._coordinates_from_data(
            trip,
            prefix=prefix,
        )
        address = self._address_value(trip.get(f"{prefix}_address"))
        zone_name = self._resolve_zone_name(latitude, longitude)

        if zone_name:
            return zone_name, address, latitude, longitude, "zone"
        if address:
            return address, address, latitude, longitude, "address"

        return None, None, latitude, longitude, None

    def _resolve_charge_location(
        self,
        charge: Mapping[str, Any],
    ) -> tuple[str | None, str | None, Any, Any, str | None]:
        """Resolve a charging location.

        Priority: Home Assistant zone, FordPass, OSM, address.
        """

        fordpass_location = self._fordpass_location(charge)

        latitude = (
            fordpass_location.get("latitude")
            or charge.get("start_latitude")
            or charge.get("end_latitude")
        )
        longitude = (
            fordpass_location.get("longitude")
            or charge.get("start_longitude")
            or charge.get("end_longitude")
        )

        zone_name = self._resolve_zone_name(latitude, longitude)
        fordpass_name = self._address_value(
            fordpass_location.get("name")
        )
        fordpass_address = self._fordpass_address(fordpass_location)

        osm_name = next(
            (
                self._address_value(charge.get(key))
                for key in (
                    "charging_site_name",
                    "charging_site_brand",
                    "charging_site_operator",
                    "charging_site_network",
                )
                if self._address_value(charge.get(key))
                and str(charge.get(key)).strip().upper() != "UNKNOWN"
            ),
            None,
        )

        stored_address = self._address_value(
            charge.get("start_address")
        )
        address = fordpass_address or stored_address

        if zone_name:
            return zone_name, address, latitude, longitude, "zone"
        if fordpass_name:
            return (
                fordpass_name,
                address,
                latitude,
                longitude,
                "fordpass",
            )
        if osm_name:
            return osm_name, address, latitude, longitude, "osm"
        if address:
            return address, address, latitude, longitude, "address"

        return None, None, latitude, longitude, None

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
        """Add one trip with metrics and resolved boundary locations."""

        (
            start_location,
            start_address,
            start_latitude,
            start_longitude,
            start_location_source,
        ) = self._resolve_trip_location(trip, prefix="start")

        (
            end_location,
            end_address,
            end_latitude,
            end_longitude,
            end_location_source,
        ) = self._resolve_trip_location(trip, prefix="end")

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
            start_soc=self._optional_float_value(
                trip,
                "start_soc",
            ),
            end_soc=self._optional_float_value(
                trip,
                "end_soc",
            ),
            start_location=start_location,
            start_address=start_address,
            start_latitude=start_latitude,
            start_longitude=start_longitude,
            start_location_source=start_location_source,
            end_location=end_location,
            end_address=end_address,
            end_latitude=end_latitude,
            end_longitude=end_longitude,
            end_location_source=end_location_source,
        )

    def _add_charge(
        self,
        journey: FordTriplogJourney,
        charge: Mapping[str, Any],
    ) -> None:
        """Add one charging session with metrics and resolved location."""

        (
            location,
            address,
            latitude,
            longitude,
            location_source,
        ) = self._resolve_charge_location(charge)

        journey.add_charge(
            self._required_id(charge, "charge_id"),
            start_time=charge.get("start_time"),
            end_time=charge.get("end_time"),
            duration_seconds=self._duration_seconds(charge),
            energy_charged_kwh=self._float_value(
                charge,
                "energy_added_kwh",
            ),
            start_soc=self._optional_float_value(
                charge,
                "start_soc",
            ),
            end_soc=self._optional_float_value(
                charge,
                "end_soc",
            ),
            location=location,
            address=address,
            latitude=latitude,
            longitude=longitude,
            location_source=location_source,
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
