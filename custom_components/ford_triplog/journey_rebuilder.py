"""
Ford Triplog

Track your Ford.

Rebuild and update daily journeys from archived trips and charges.

Version: 1.6.1
Release: 1.6.1c
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Awaitable, Callable, Final, Literal, Mapping

from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import SIGNAL_LAST_JOURNEY_UPDATED
from .journey import FordTriplogJourney
from .journey_manager import FordTriplogJourneyManager
from .journey_storage import FordTriplogJourneyStorage
from .storage import FordTriplogStorage

_LOGGER = logging.getLogger(__name__)

JourneyRebuildMode = Literal["update", "rebuild", "delete"]
ProgressCallback = Callable[
    ["JourneyRebuildProgress"],
    Awaitable[None] | None,
]

_EVENT_TRIP: Final = "trip"
_EVENT_CHARGE: Final = "charge"


@dataclass(slots=True, frozen=True)
class JourneyRebuildProgress:
    """Progress information for task-status sensors and options flow."""

    mode: JourneyRebuildMode
    status: str
    processed: int
    total: int
    start_date: str | None = None
    end_date: str | None = None
    journeys_created: int = 0
    journeys_deleted: int = 0
    skipped_records: int = 0
    message: str | None = None

    @property
    def percentage(self) -> int:
        """Return progress as an integer percentage."""

        if self.total <= 0:
            return 100 if self.status == "completed" else 0

        return min(
            100,
            max(
                0,
                round(self.processed / self.total * 100),
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize progress for Home Assistant state attributes."""

        return {
            "mode": self.mode,
            "status": self.status,
            "processed": self.processed,
            "total": self.total,
            "percentage": self.percentage,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "journeys_created": self.journeys_created,
            "journeys_deleted": self.journeys_deleted,
            "skipped_records": self.skipped_records,
            "source_files_skipped": self.skipped_records,
            "message": self.message,
        }


@dataclass(slots=True, frozen=True)
class JourneyRebuildResult:
    """Final result of a journey maintenance operation."""

    mode: JourneyRebuildMode
    start_date: str | None
    end_date: str | None
    source_trips: int
    source_charges: int
    processed_records: int
    journeys_created: int
    journeys_deleted: int
    skipped_records: int
    affected_dates: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        """Serialize the result."""

        return {
            "mode": self.mode,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "source_trips": self.source_trips,
            "source_charges": self.source_charges,
            "processed_records": self.processed_records,
            "journeys_created": self.journeys_created,
            "journeys_deleted": self.journeys_deleted,
            "skipped_records": self.skipped_records,
            "source_files_skipped": self.skipped_records,
            "affected_dates": list(self.affected_dates),
        }


@dataclass(slots=True, frozen=True)
class _SourceEvent:
    """One chronological trip or charging source record."""

    event_type: Literal["trip", "charge"]
    timestamp: datetime
    data: dict[str, Any]


class FordTriplogJourneyRebuilder:
    """Maintain journeys from the independent trip and charge archives."""

    def __init__(
        self,
        source_storage: FordTriplogStorage,
        journey_storage: FordTriplogJourneyStorage,
        *,
        progress_callback: ProgressCallback | None = None,
    ) -> None:
        """Initialize journey maintenance."""

        self.source_storage = source_storage
        self.journey_storage = journey_storage
        self.progress_callback = progress_callback
        self.hass = journey_storage.hass

        self._lock = asyncio.Lock()

    async def async_update_journeys(
        self,
        *,
        start_date: date | str | None = None,
        end_date: date | str | None = None,
    ) -> JourneyRebuildResult:
        """Create missing journeys.

        Dates containing source records that are not referenced by an existing
        journey are rebuilt completely. Existing journeys on unaffected dates
        remain unchanged.
        """

        return await self._async_run(
            mode="update",
            start_date=start_date,
            end_date=end_date,
        )

    async def async_rebuild_journeys(
        self,
        *,
        start_date: date | str | None = None,
        end_date: date | str | None = None,
    ) -> JourneyRebuildResult:
        """Recalculate all journeys in an optional inclusive date range."""

        return await self._async_run(
            mode="rebuild",
            start_date=start_date,
            end_date=end_date,
        )

    async def async_delete_journeys(
        self,
        *,
        start_date: date | str | None = None,
        end_date: date | str | None = None,
    ) -> JourneyRebuildResult:
        """Delete all journeys or journeys in an inclusive date range."""

        return await self._async_run(
            mode="delete",
            start_date=start_date,
            end_date=end_date,
        )

    async def _async_run(
        self,
        *,
        mode: JourneyRebuildMode,
        start_date: date | str | None,
        end_date: date | str | None,
    ) -> JourneyRebuildResult:
        """Execute one serialized maintenance task."""

        async with self._lock:
            normalized_start = self._normalize_date(start_date)
            normalized_end = self._normalize_date(end_date)

            if (
                normalized_start is not None
                and normalized_end is not None
                and normalized_start > normalized_end
            ):
                raise ValueError(
                    "start_date must not be after end_date"
                )

            await self.source_storage.async_setup()
            await self.journey_storage.async_setup()

            await self._report(
                JourneyRebuildProgress(
                    mode=mode,
                    status="loading",
                    processed=0,
                    total=0,
                    start_date=self._date_string(normalized_start),
                    end_date=self._date_string(normalized_end),
                    message="Loading archived trips, charges and journeys",
                )
            )

            existing_journeys = (
                await self.journey_storage.get_all_journeys()
            )

            if mode == "delete":
                journeys_deleted = await self._delete_matching_journeys(
                    existing_journeys,
                    normalized_start,
                    normalized_end,
                    mode=mode,
                )

                await self._synchronize_last_journey()
                async_dispatcher_send(
                    self.hass,
                    SIGNAL_LAST_JOURNEY_UPDATED,
                )

                result = JourneyRebuildResult(
                    mode=mode,
                    start_date=self._date_string(normalized_start),
                    end_date=self._date_string(normalized_end),
                    source_trips=0,
                    source_charges=0,
                    processed_records=0,
                    journeys_created=0,
                    journeys_deleted=journeys_deleted,
                    skipped_records=0,
                    affected_dates=(),
                )

                await self._report(
                    JourneyRebuildProgress(
                        mode=mode,
                        status="completed",
                        processed=journeys_deleted,
                        total=journeys_deleted,
                        start_date=result.start_date,
                        end_date=result.end_date,
                        journeys_deleted=journeys_deleted,
                        message="Journey deletion completed",
                    )
                )
                return result

            trips, skipped_trips = await self._load_trips(
                normalized_start,
                normalized_end,
            )
            charges, skipped_charges = await self._load_charges(
                normalized_start,
                normalized_end,
            )

            source_dates = {
                self._event_date(event)
                for event in (*trips, *charges)
            }

            if mode == "update":
                affected_dates = self._find_missing_dates(
                    trips,
                    charges,
                    existing_journeys,
                )
            else:
                affected_dates = source_dates

            affected_dates = {
                current_date
                for current_date in affected_dates
                if self._date_in_range(
                    current_date,
                    normalized_start,
                    normalized_end,
                )
            }

            journeys_deleted = await self._delete_journeys_for_dates(
                existing_journeys,
                affected_dates,
                mode=mode,
            )

            events = sorted(
                (
                    event
                    for event in (*trips, *charges)
                    if self._event_date(event) in affected_dates
                ),
                key=self._event_sort_key,
            )

            total = len(events)
            skipped_records = skipped_trips + skipped_charges

            await self._report(
                JourneyRebuildProgress(
                    mode=mode,
                    status="running",
                    processed=0,
                    total=total,
                    start_date=self._date_string(normalized_start),
                    end_date=self._date_string(normalized_end),
                    journeys_deleted=journeys_deleted,
                    skipped_records=skipped_records,
                    message="Recalculating daily journeys",
                )
            )

            manager = FordTriplogJourneyManager(
                self.source_storage.hass,
                self.journey_storage,
            )
            await manager.async_setup()

            # A maintenance run must only use the selected archive data.
            manager.current_journey = None
            await self.journey_storage.clear_current_journey()

            journeys_created = 0
            processed = 0

            for event in events:
                if event.event_type == _EVENT_TRIP:
                    update = await manager.async_process_trip(
                        event.data
                    )
                else:
                    update = await manager.async_process_charge(
                        event.data
                    )

                if update.completed_journey is not None:
                    journeys_created += 1

                processed += 1

                await self._report(
                    JourneyRebuildProgress(
                        mode=mode,
                        status="running",
                        processed=processed,
                        total=total,
                        start_date=self._date_string(
                            normalized_start
                        ),
                        end_date=self._date_string(normalized_end),
                        journeys_created=journeys_created,
                        journeys_deleted=journeys_deleted,
                        skipped_records=skipped_records,
                        message="Recalculating daily journeys",
                    )
                )

            final_update = await manager.async_finalize_current(
                reason="maintenance_run_completed"
            )

            if final_update.completed_journey is not None:
                journeys_created += 1

            await self.journey_storage.clear_current_journey()
            await self._synchronize_last_journey()
            async_dispatcher_send(
                self.hass,
                SIGNAL_LAST_JOURNEY_UPDATED,
            )

            result = JourneyRebuildResult(
                mode=mode,
                start_date=self._date_string(normalized_start),
                end_date=self._date_string(normalized_end),
                source_trips=len(trips),
                source_charges=len(charges),
                processed_records=processed,
                journeys_created=journeys_created,
                journeys_deleted=journeys_deleted,
                skipped_records=skipped_records,
                affected_dates=tuple(
                    sorted(
                        current_date.isoformat()
                        for current_date in affected_dates
                    )
                ),
            )

            await self._report(
                JourneyRebuildProgress(
                    mode=mode,
                    status="completed",
                    processed=processed,
                    total=total,
                    start_date=result.start_date,
                    end_date=result.end_date,
                    journeys_created=journeys_created,
                    journeys_deleted=journeys_deleted,
                    skipped_records=skipped_records,
                    message="Journey maintenance completed",
                )
            )

            return result

    async def _load_trips(
        self,
        start_date: date | None,
        end_date: date | None,
    ) -> tuple[list[_SourceEvent], int]:
        """Load archived trips in the selected range."""

        events: list[_SourceEvent] = []
        skipped = 0

        for path in await self.source_storage.list_trips():
            data = await self.source_storage.load_trip_file(path)
            event = self._source_event(
                _EVENT_TRIP,
                data,
            )

            if event is None:
                skipped += 1
                continue

            if self._date_in_range(
                self._event_date(event),
                start_date,
                end_date,
            ):
                events.append(event)

        return events, skipped

    async def _load_charges(
        self,
        start_date: date | None,
        end_date: date | None,
    ) -> tuple[list[_SourceEvent], int]:
        """Load archived charges in the selected range."""

        events: list[_SourceEvent] = []
        skipped = 0

        for path in await self.source_storage.list_charges():
            data = await self.source_storage.load_charge_file(path)
            event = self._source_event(
                _EVENT_CHARGE,
                data,
            )

            if event is None:
                skipped += 1
                continue

            if self._date_in_range(
                self._event_date(event),
                start_date,
                end_date,
            ):
                events.append(event)

        return events, skipped

    @classmethod
    def _source_event(
        cls,
        event_type: Literal["trip", "charge"],
        data: Mapping[str, Any] | None,
    ) -> _SourceEvent | None:
        """Build a validated chronological source event."""

        if not isinstance(data, Mapping):
            return None

        identifier_key = (
            "trip_id"
            if event_type == _EVENT_TRIP
            else "charge_id"
        )

        if not str(data.get(identifier_key, "")).strip():
            return None

        start_time = data.get("start_time")
        end_time = data.get("end_time")

        if start_time is None or end_time is None:
            return None

        try:
            timestamp = cls._parse_datetime(start_time)
            cls._parse_datetime(end_time)
        except (TypeError, ValueError):
            return None

        return _SourceEvent(
            event_type=event_type,
            timestamp=timestamp,
            data=dict(data),
        )

    @staticmethod
    def _event_sort_key(
        event: _SourceEvent,
    ) -> tuple[datetime, int, str]:
        """Sort trips before charges when timestamps are identical."""

        priority = (
            0
            if event.event_type == _EVENT_TRIP
            else 1
        )
        identifier = str(
            event.data.get(
                "trip_id"
                if event.event_type == _EVENT_TRIP
                else "charge_id",
                "",
            )
        )

        return event.timestamp, priority, identifier

    @staticmethod
    def _event_date(event: _SourceEvent) -> date:
        """Return the source event's local calendar date."""

        return event.timestamp.date()

    @staticmethod
    def _journey_date(
        journey: FordTriplogJourney,
    ) -> date | None:
        """Return one stored journey date."""

        value = journey.date

        if value is None and journey.start_time:
            try:
                return FordTriplogJourneyRebuilder._parse_datetime(
                    journey.start_time
                ).date()
            except (TypeError, ValueError):
                return None

        if value is None:
            return None

        try:
            return date.fromisoformat(str(value))
        except ValueError:
            return None

    @classmethod
    def _find_missing_dates(
        cls,
        trips: list[_SourceEvent],
        charges: list[_SourceEvent],
        journeys: list[FordTriplogJourney],
    ) -> set[date]:
        """Find dates containing unreferenced source records."""

        referenced_trip_ids = {
            trip_id
            for journey in journeys
            for trip_id in journey.trip_ids
        }
        referenced_charge_ids = {
            charge_id
            for journey in journeys
            for charge_id in journey.charge_ids
        }

        missing_dates: set[date] = set()

        for event in trips:
            trip_id = str(event.data.get("trip_id", "")).strip()

            if trip_id not in referenced_trip_ids:
                missing_dates.add(cls._event_date(event))

        for event in charges:
            charge_id = str(
                event.data.get("charge_id", "")
            ).strip()

            if charge_id not in referenced_charge_ids:
                missing_dates.add(cls._event_date(event))

        return missing_dates

    async def _delete_matching_journeys(
        self,
        journeys: list[FordTriplogJourney],
        start_date: date | None,
        end_date: date | None,
        *,
        mode: JourneyRebuildMode,
    ) -> int:
        """Delete journeys matching an optional range."""

        matching = [
            journey
            for journey in journeys
            if (
                (journey_date := self._journey_date(journey))
                is not None
                and self._date_in_range(
                    journey_date,
                    start_date,
                    end_date,
                )
            )
        ]

        total = len(matching)
        deleted = 0

        for journey in matching:
            if await self.journey_storage.delete_journey(
                journey.journey_id
            ):
                deleted += 1

            await self._report(
                JourneyRebuildProgress(
                    mode=mode,
                    status="running",
                    processed=deleted,
                    total=total,
                    start_date=self._date_string(start_date),
                    end_date=self._date_string(end_date),
                    journeys_deleted=deleted,
                    message="Deleting journey data",
                )
            )

        if start_date is None and end_date is None:
            await self.journey_storage.clear_current_journey()

        return deleted

    async def _delete_journeys_for_dates(
        self,
        journeys: list[FordTriplogJourney],
        affected_dates: set[date],
        *,
        mode: JourneyRebuildMode,
    ) -> int:
        """Delete existing journeys on dates being recalculated."""

        matching = [
            journey
            for journey in journeys
            if self._journey_date(journey) in affected_dates
        ]

        deleted = 0

        for journey in matching:
            if await self.journey_storage.delete_journey(
                journey.journey_id
            ):
                deleted += 1

        if matching:
            _LOGGER.info(
                "Deleted %s existing journeys before %s",
                deleted,
                mode,
            )

        return deleted

    async def _synchronize_last_journey(self) -> None:
        """Update the last-journey cache after deletion or rebuilding."""

        journeys = await self.journey_storage.get_all_journeys()

        if not journeys:
            await self.journey_storage.clear_last_journey()
            return

        last_journey = max(
            journeys,
            key=lambda journey: (
                journey.end_time or journey.start_time or "",
                journey.journey_id,
            ),
        )

        await self.journey_storage.save_last_journey(
            last_journey
        )

    async def _report(
        self,
        progress: JourneyRebuildProgress,
    ) -> None:
        """Send optional task progress without blocking maintenance."""

        if self.progress_callback is None:
            return

        try:
            result = self.progress_callback(progress)

            if result is not None:
                await result
        except Exception:
            _LOGGER.exception(
                "Journey progress callback failed"
            )

    @staticmethod
    def _normalize_date(
        value: date | str | None,
    ) -> date | None:
        """Normalize one optional ISO date."""

        if value is None:
            return None

        if isinstance(value, datetime):
            return value.date()

        if isinstance(value, date):
            return value

        normalized = str(value).strip()

        if not normalized:
            return None

        return date.fromisoformat(normalized)

    @staticmethod
    def _date_in_range(
        value: date,
        start_date: date | None,
        end_date: date | None,
    ) -> bool:
        """Return whether a date is inside an inclusive range."""

        if start_date is not None and value < start_date:
            return False

        if end_date is not None and value > end_date:
            return False

        return True

    @staticmethod
    def _date_string(value: date | None) -> str | None:
        """Return an optional ISO date string."""

        return value.isoformat() if value is not None else None

    @staticmethod
    def _parse_datetime(value: datetime | str) -> datetime:
        """Parse an ISO datetime including trailing Z."""

        if isinstance(value, datetime):
            return value

        normalized = str(value).strip().replace(
            "Z",
            "+00:00",
        )

        if not normalized:
            raise ValueError("Datetime value must not be empty")

        return datetime.fromisoformat(normalized)
