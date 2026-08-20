"""
Ford Triplog

Coordinator

Version: 2.1.0
Phase: 
Build: 

Changes:
- Route Tracker uses Trip start GPS as first route point and finalized fresh Trip end GPS as last route point.
- Smart Trip pauses route capture without discarding collected ABRP points.
- Persists Smart Trip pause recovery data inside current_trip.json.
- Restores the paused Trip, captured end state and remaining timeout after
  a Home Assistant or integration reload.
- Finalizes immediately when the original Smart Trip timeout has already
  expired during the reload.
- Keeps the existing Trip, Journey and Route Tracker flow unchanged.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from homeassistant.core import Event, HomeAssistant, State
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .geo import FordTriplogGeo
from .history import FordTriplogHistory
from .storage import FordTriplogStorage
from .trip import Trip
from .charge import Charge
from .charging_costs import FordTriplogChargingCostCalculator
from .charging_location_resolver import ChargingLocationResolver
from .pending_charging_site_storage import PendingChargingSiteStorage
from .user_charging_site_storage import UserChargingSiteStorage
from .charging_site_lookup import (
    ChargingSiteDatabaseError,
    ChargingSiteLookup,
)

from .const import (
    CONF_JOURNEY_HOME_ZONE,
    CONF_LAST_CHARGE,
    DEFAULT_CHARGE_MATCH_TIMEOUT,
    DEFAULT_LAST_CHARGE_STABLE_TIME,
    SMART_TRIP_TIMEOUT,
)

_LOGGER = logging.getLogger(__name__)

STABLE_INTERVAL = 2
STABLE_TIMEOUT = 20
GPS_UPDATE_TIMEOUT = 60
TRIP_END_GPS_MAX_DISTANCE_METERS = 250

MAX_LINK_TIME_SECONDS = 1800
MAX_LINK_DISTANCE_METERS = 300

DEFAULT_CHARGING_SITE_RADIUS_METERS = 10
CHARGING_SITE_DATABASE_DIRECTORY = "charging_sites"
CHARGING_SITE_GENERATED_DIRECTORY = "generated"
DEFAULT_CHARGING_SITE_COUNTRY = "CH"
CONF_CHARGING_SITE_COUNTRY = "charging_site_country"

CONF_HOME_TARIFF_ENABLED = "home_tariff_enabled"
CONF_HOME_TARIFF_SUMMER_PRICE = "home_tariff_summer_price"
CONF_HOME_TARIFF_WINTER_PRICE = "home_tariff_winter_price"
CONF_HOME_TARIFF_CURRENCY = "home_tariff_currency"

DEFAULT_HOME_ZONE_ENTITY_ID = "zone.home"
DEFAULT_HOME_TARIFF_SUMMER_PRICE = 0.28
DEFAULT_HOME_TARIFF_WINTER_PRICE = 0.38
DEFAULT_HOME_TARIFF_CURRENCY = "CHF"


class FordTriplogCoordinator(DataUpdateCoordinator):
    def __init__(self, hass: HomeAssistant,
                 storage: FordTriplogStorage,
                 config: dict[str, Any],
                 geo: FordTriplogGeo) -> None:
        super().__init__(hass, _LOGGER, name="Ford Triplog")
        self.hass = hass
        self.storage = storage
        self.history = FordTriplogHistory(storage)
        self.config = config
        self.geo = geo
        self.charging_cost_calculator = FordTriplogChargingCostCalculator(
            hass,
            config,
        )

        self.user_charging_site_storage = UserChargingSiteStorage(hass)
        self.pending_charging_site_storage = PendingChargingSiteStorage(hass)

        self.charging_location_resolver = ChargingLocationResolver(
            hass,
            config,
            self.user_charging_site_storage,
            self.pending_charging_site_storage,
        )

        self.charging_site_radius = int(
            config.get(
                "charging_site_radius",
                DEFAULT_CHARGING_SITE_RADIUS_METERS,
            )
        )
        self.charging_site_lookup: ChargingSiteLookup | None = None

        # Battery capacity (kWh)
        self.battery_capacity = float(config.get("battery_capacity_kwh", 77))

        # Automatic home charging cost infrastructure.
        self.home_tariff_enabled = bool(
            config.get(CONF_HOME_TARIFF_ENABLED, False)
        )
        self.home_zone_entity_id = str(
            config.get(
                CONF_JOURNEY_HOME_ZONE,
                DEFAULT_HOME_ZONE_ENTITY_ID,
            )
            or DEFAULT_HOME_ZONE_ENTITY_ID
        ).strip()
        self.home_tariff_summer_price = max(
            0.0,
            float(
                config.get(
                    CONF_HOME_TARIFF_SUMMER_PRICE,
                    DEFAULT_HOME_TARIFF_SUMMER_PRICE,
                )
            ),
        )
        self.home_tariff_winter_price = max(
            0.0,
            float(
                config.get(
                    CONF_HOME_TARIFF_WINTER_PRICE,
                    DEFAULT_HOME_TARIFF_WINTER_PRICE,
                )
            ),
        )
        self.home_tariff_currency = str(
            config.get(
                CONF_HOME_TARIFF_CURRENCY,
                DEFAULT_HOME_TARIFF_CURRENCY,
            )
            or DEFAULT_HOME_TARIFF_CURRENCY
        ).strip().upper()

        self.smart_trip_timeout = int(
        config.get("smart_trip_timeout", SMART_TRIP_TIMEOUT)
)


        self.current_trip: Trip | None = None
        self.current_charge: Charge | None = None
        self.last_completed_trip: Trip | None = None

        self.vehicle_state: dict[str, Any] = {}

        self.last_ignition = False
        self.last_charging = False

        # FordPass 'Last Charge' sensor (Version 1.5 preparation).
        self.last_charge_entity: str | None = config.get(CONF_LAST_CHARGE)
        self.last_charge_snapshot: dict[str, Any] | None = None
        self.last_charge_signature: str | None = None

        # Last Charge stabilization infrastructure.
        # Phase 3 waits for the complete Last Charge dataset to stabilize
        # before the charging session is finalized.
        self.waiting_for_last_charge = False
        self.last_charge_stable_time = int(
            config.get(
                "last_charge_stable_time",
                DEFAULT_LAST_CHARGE_STABLE_TIME,
            )
        )
        self.last_charge_timer: asyncio.TimerHandle | None = None
        self.last_charge_match_timeout = int(
            config.get(
                "charge_match_timeout",
                DEFAULT_CHARGE_MATCH_TIMEOUT,
            )
        )
        self.last_charge_timeout_timer: asyncio.TimerHandle | None = None

        self.remove_listener = None

        # Prevent overlapping charge handlers from changing current_charge
        # while another handler is awaiting Home Assistant or file I/O.
        self._charge_lock = asyncio.Lock()

        # Defensive guard against finalizing the same charging session twice.
        self._charge_finalizing = False
        self._trip_finishing = False

        # Coalesce rapid coordinator publishes. FordPass/Home Assistant can
        # update several watched entities within a few milliseconds. The
        # transition handling still runs for every event, but sensors only
        # need the latest resulting vehicle state once per burst.
        self._publish_delay_seconds = 0.25
        self._publish_handle: asyncio.TimerHandle | None = None
        self._pending_publish_data: dict[str, Any] | None = None


        # Smart Trip
        self.trip_pause_time: float | None = None
        self.trip_pause_data: Trip | None = None
        self.smart_trip_timer: asyncio.TimerHandle | None = None
        self.trip_end_time = None
        self.trip_end_state: dict[str, Any] | None = None

        # Issue #14: signal tracker updates while a paused trip is waiting
        # for a fresh final GPS position.
        self._gps_update_event = asyncio.Event()

        # Issue #15: assigned during integration setup after the Journey
        # infrastructure has been initialized.
        self.journey_rebuilder: Any | None = None
        self.route_tracker: Any | None = None
       

    def _schedule_coordinator_update(
        self,
        data: dict[str, Any],
    ) -> None:
        """Publish only the latest coordinator state from a rapid update burst."""

        self._pending_publish_data = dict(data)

        if self._publish_handle is not None:
            self._publish_handle.cancel()

        self._publish_handle = self.hass.loop.call_later(
            self._publish_delay_seconds,
            self._publish_coordinator_update,
        )

    def _publish_coordinator_update(self) -> None:
        """Publish the most recently queued coordinator state."""

        self._publish_handle = None
        data = self._pending_publish_data
        self._pending_publish_data = None

        if data is None:
            return

        self.async_set_updated_data(data)

    async def async_setup(self):
        await self.storage.async_setup()
        await self.user_charging_site_storage.async_setup()
        await self.pending_charging_site_storage.async_setup()
        await self._async_setup_charging_site_lookup()

        data = await self.storage.load_current_trip()
        if data:
            recovery = data.pop("_smart_trip_recovery", None)
            self.current_trip = Trip.from_dict(data)

            if isinstance(recovery, dict) and recovery.get("paused"):
                self._restore_smart_trip_recovery(recovery)

          
        data = await self.storage.load_current_charge()
        if data:
            self.current_charge = Charge.from_dict(data)        


        entities = [
            e for e in (
                self.config.get("ignition"),
                self.config.get("odometer"),
                self.config.get("tracker"),
                self.config.get("soc"),
                self.config.get("charging"),
                self.last_charge_entity,
            ) if e
        ]

        self.remove_listener = async_track_state_change_event(
            self.hass, entities, self._state_changed
        )

        if self.last_charge_entity:
            last_charge = self.hass.states.get(self.last_charge_entity)
            self.last_charge_snapshot = self._last_charge_to_snapshot(
                last_charge
            )
            self.last_charge_signature = self._last_charge_to_signature(
                last_charge
            )

        # Resume a pending completed charging session from recovery. The
        # timeout is measured from the recorded charge end time, so a Home
        # Assistant restart cannot restart the full waiting period or leave
        # current_charge.json pending indefinitely.
        if (
            self.current_charge is not None
            and self.current_charge.fordpass_pending
            and self.current_charge.end_time
        ):
            self._resume_pending_charge_from_recovery()

    def _smart_trip_recovery_payload(self) -> dict[str, Any] | None:
        """Return JSON-safe Smart Trip pause recovery metadata."""

        if (
            self.trip_pause_data is None
            or self.trip_end_state is None
            or self.trip_end_time is None
        ):
            return None

        end_state = dict(self.trip_end_state)

        end_time_value = end_state.get("end_time")
        if isinstance(end_time_value, datetime):
            end_state["end_time"] = end_time_value.isoformat()

        gps_updated_at = end_state.get("gps_updated_at")
        if isinstance(gps_updated_at, datetime):
            end_state["gps_updated_at"] = gps_updated_at.isoformat()

        deadline = self.trip_end_time + timedelta(
            seconds=self.smart_trip_timeout
        )

        return {
            "paused": True,
            "deadline": deadline.isoformat(),
            "end_state": end_state,
        }

    def _restore_smart_trip_recovery(
        self,
        recovery: dict[str, Any],
    ) -> None:
        """Restore a paused Smart Trip after HA/integration reload."""

        if self.current_trip is None:
            return

        raw_end_state = recovery.get("end_state")
        raw_deadline = recovery.get("deadline")

        if not isinstance(raw_end_state, dict):
            _LOGGER.warning(
                "Smart Trip recovery ignored: end-state snapshot missing"
            )
            return

        deadline = dt_util.parse_datetime(str(raw_deadline or ""))
        end_time = dt_util.parse_datetime(
            str(raw_end_state.get("end_time") or "")
        )

        if deadline is None or end_time is None:
            _LOGGER.warning(
                "Smart Trip recovery ignored: timestamps are invalid"
            )
            return

        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=dt_util.UTC)
        if end_time.tzinfo is None:
            end_time = end_time.replace(tzinfo=dt_util.UTC)

        restored_end_state = dict(raw_end_state)
        restored_end_state["end_time"] = end_time

        self.trip_pause_data = self.current_trip
        self.current_trip = None
        self.trip_end_state = restored_end_state
        self.trip_end_time = end_time

        now = dt_util.now()
        remaining = max(0.0, (deadline - now).total_seconds())
        elapsed = max(
            0.0,
            float(self.smart_trip_timeout) - remaining,
        )
        self.trip_pause_time = self.hass.loop.time() - elapsed

        self.smart_trip_timer = self.hass.loop.call_later(
            remaining,
            lambda: self.hass.async_create_task(
                self._smart_trip_timeout()
            ),
        )

        if remaining <= 0:
            _LOGGER.info(
                "Recovered paused Smart Trip; original timeout already "
                "expired, finalizing now"
            )
        else:
            _LOGGER.info(
                "Recovered paused Smart Trip; %.1fs remaining",
                remaining,
            )

    async def async_shutdown(self) -> None:
        """Stop listeners, timers and pending coordinator work."""

        if self.remove_listener is not None:
            self.remove_listener()
            self.remove_listener = None

        if self.smart_trip_timer is not None:
            self.smart_trip_timer.cancel()
            self.smart_trip_timer = None

        self._cancel_last_charge_timer()
        self._cancel_last_charge_timeout_timer()

        if self._publish_handle is not None:
            self._publish_handle.cancel()
            self._publish_handle = None
        self._pending_publish_data = None

        self._gps_update_event.set()

        _LOGGER.debug("Ford Triplog coordinator shut down")

    def _resolve_charging_site_database(self) -> Path:
        """Return the configured country's charging-site database path."""

        country_code = str(
            self.config.get(
                CONF_CHARGING_SITE_COUNTRY,
                DEFAULT_CHARGING_SITE_COUNTRY,
            )
            or DEFAULT_CHARGING_SITE_COUNTRY
        ).strip().upper()

        # ISO 3166-1 alpha-2 uses GB. Accept UK as a defensive alias.
        if country_code == "UK":
            country_code = "GB"

        if len(country_code) != 2 or not country_code.isalpha():
            _LOGGER.warning(
                "Invalid charging-site country '%s'; using %s",
                country_code,
                DEFAULT_CHARGING_SITE_COUNTRY,
            )
            country_code = DEFAULT_CHARGING_SITE_COUNTRY

        database_directory = Path(
            self.hass.config.path(
                ".storage",
                "ford_triplog",
                CHARGING_SITE_DATABASE_DIRECTORY,
            )
        )
        generated_directory = (
            database_directory / CHARGING_SITE_GENERATED_DIRECTORY
        )
        generated_directory.mkdir(parents=True, exist_ok=True)

        database_filename = (
            f"charging_sites_{country_code.lower()}.json"
        )
        database_path = generated_directory / database_filename

        if database_path.is_file():
            return database_path

        # Migrate the previous persistent Swiss database into generated/.
        if country_code == "CH":
            legacy_database_path = (
                database_directory / "charging_sites_ch.json"
            )

            if legacy_database_path.is_file():
                shutil.copy2(legacy_database_path, database_path)
                _LOGGER.info(
                    "Legacy Swiss charging-site database copied to %s",
                    database_path,
                )
                return database_path

            bundled_database_path = Path(__file__).with_name(
                "charging_sites_ch.json"
            )

            if bundled_database_path.is_file():
                shutil.copy2(bundled_database_path, database_path)
                _LOGGER.info(
                    "Initial Swiss charging-site database copied to %s",
                    database_path,
                )
                return database_path

        raise ChargingSiteDatabaseError(
            "Charging-site database for country "
            f"{country_code} is missing: {database_path}. "
            "Generate or import this country database in the "
            "Ford Triplog options."
        )

    async def _async_setup_charging_site_lookup(self) -> None:
        """Load the configured country charging-site database."""

        try:
            database_path = await self.hass.async_add_executor_job(
                self._resolve_charging_site_database
            )

            self.charging_site_lookup = (
                await self.hass.async_add_executor_job(
                    ChargingSiteLookup,
                    database_path,
                )
            )
        except ChargingSiteDatabaseError as error:
            self.charging_site_lookup = None
            _LOGGER.warning(
                "Charging-site database unavailable: %s",
                error,
            )
            return
        except (OSError, ValueError) as error:
            self.charging_site_lookup = None
            _LOGGER.warning(
                "Charging-site lookup could not be initialized: %s",
                error,
            )
            return

        _LOGGER.info(
            "Charging-site database loaded from %s: %s searchable sites, "
            "%s geohash cells, radius %sm",
            database_path,
            self.charging_site_lookup.searchable_site_count,
            self.charging_site_lookup.index_cell_count,
            self.charging_site_radius,
        )

    async def _get_charging_site(
        self,
        state: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Resolve vehicle coordinates to a charging site."""

        if self.charging_site_lookup is None:
            return None

        latitude = state.get("latitude")
        longitude = state.get("longitude")

        if latitude is None or longitude is None:
            return None

        try:
            return await self.hass.async_add_executor_job(
                self.charging_site_lookup.find,
                float(latitude),
                float(longitude),
                float(self.charging_site_radius),
            )
        except (TypeError, ValueError) as error:
            _LOGGER.debug(
                "Charging-site lookup skipped because coordinates are invalid: %s",
                error,
            )
            return None

    def _apply_charging_site(
        self,
        site: dict[str, Any] | None,
    ) -> None:
        """Store a resolved charging site on the active charging session."""

        if self.current_charge is None or site is None:
            return

        self.current_charge.charging_site_id = site.get("site_id")
        self.current_charge.charging_site_name = site.get("name")
        self.current_charge.charging_site_brand = site.get("brand")
        self.current_charge.charging_site_operator = site.get("operator")
        self.current_charge.charging_site_network = site.get("network")
        self.current_charge.charging_site_power_kw = list(
            site.get("power_kw") or []
        )
        self.current_charge.charging_site_capacity = list(
            site.get("capacity") or []
        )
        self.current_charge.charging_site_connectors = list(
            site.get("connectors") or []
        )
        self.current_charge.charging_site_quality = site.get("quality")
        self.current_charge.charging_site_distance_m = site.get("distance_m")

        _LOGGER.info(
            "Charging site detected: %s (%s, %.1fm)",
            (
                self.current_charge.charging_site_name
                or self.current_charge.charging_site_brand
                or self.current_charge.charging_site_operator
                or self.current_charge.charging_site_id
            ),
            self.current_charge.charging_site_id,
            self.current_charge.charging_site_distance_m or 0.0,
        )

    def _read_vehicle_state(self):
        data = {}

        for key in (
            "ignition",
            "odometer",
            "soc",
            "charging",
            CONF_LAST_CHARGE,
        ):
            entity_id = self.config.get(key)
            st = self.hass.states.get(entity_id) if entity_id else None
            data[key] = st.state if st else None




        tracker = self.hass.states.get(self.config.get("tracker"))
        data["latitude"] = tracker.attributes.get("latitude") if tracker else None
        data["longitude"] = tracker.attributes.get("longitude") if tracker else None
        data["gps_updated_at"] = (
            tracker.last_updated.isoformat() if tracker else None
        )
        return data




    async def _state_changed(self, event: Event):
        if event.data.get("entity_id") == self.config.get("tracker"):
            self._gps_update_event.set()

        self.vehicle_state = self._read_vehicle_state()
        ignition = str(self.vehicle_state.get("ignition")).lower() in (
            "on", "true", "1", "running"
        )

        charging_state = str(
            self.vehicle_state.get("charging")
        ).upper()

        charging = charging_state == "IN_PROGRESS"

        if (
            self.last_charge_entity
            and event.data.get("entity_id") == self.last_charge_entity
        ):
            self._handle_last_charge_state_change(
                event.data.get("new_state")
            )

        # Trip handling
        if not self.last_ignition and ignition:
            await self.start_trip()

        elif self.last_ignition and not ignition:
            await self.finish_trip()

        # Charge handling
        if not self.last_charging and charging:
            await self.start_charge()

        elif self.last_charging and not charging:
            await self.finish_charge()

        self.last_ignition = ignition
        self.last_charging = charging

        self._schedule_coordinator_update(self.vehicle_state)

    @staticmethod
    def _last_charge_to_snapshot(
        state: State | None,
    ) -> dict[str, Any] | None:
        """Return the complete Last Charge dataset."""

        if state is None:
            return None

        return {
            "state": state.state,
            "attributes": dict(state.attributes),
        }

    @classmethod
    def _last_charge_to_signature(
        cls,
        state: State | None,
    ) -> str:
        """Return a stable comparison value for state and all attributes."""

        snapshot = cls._last_charge_to_snapshot(state)

        return json.dumps(
            snapshot,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )

    def _handle_last_charge_state_change(
        self,
        new_state: State | None,
    ) -> None:
        """Observe changes of the complete configured Last Charge entity."""

        new_signature = self._last_charge_to_signature(new_state)

        if new_signature == self.last_charge_signature:
            return

        previous_snapshot = self.last_charge_snapshot
        self.last_charge_snapshot = self._last_charge_to_snapshot(new_state)
        self.last_charge_signature = new_signature

        _LOGGER.debug(
            "Last Charge dataset changed: previous=%s current=%s",
            previous_snapshot,
            self.last_charge_snapshot,
        )

        if not self.waiting_for_last_charge:
            return

        if self.current_charge is None:
            return

        if (
            new_signature
            == self.current_charge.last_charge_baseline_signature
        ):
            return

        self._restart_last_charge_timer()

    def _start_waiting_for_last_charge(
        self,
        timeout_seconds: float | None = None,
    ) -> None:
        """Wait for a new matching FordPass dataset with a hard timeout."""

        self.waiting_for_last_charge = True
        self._cancel_last_charge_timer()
        self._cancel_last_charge_timeout_timer()

        timeout = (
            float(self.last_charge_match_timeout)
            if timeout_seconds is None
            else max(0.0, float(timeout_seconds))
        )

        self.last_charge_timeout_timer = self.hass.loop.call_later(
            timeout,
            self._last_charge_match_timed_out,
        )

        # A dataset that was already present when charging started is stale.
        # Only start stabilization if FordPass has produced a new signature.
        if (
            self.current_charge is not None
            and self.last_charge_signature
            != self.current_charge.last_charge_baseline_signature
        ):
            self._restart_last_charge_timer()

        _LOGGER.info(
            "Waiting up to %.0fs for a new matching FordPass Last Charge dataset",
            timeout,
        )

    def _resume_pending_charge_from_recovery(self) -> None:
        """Resume or immediately expire a pending recovered charge."""

        charge = self.current_charge
        if charge is None or not charge.end_time:
            return

        end_time = self._parse_fordpass_datetime(charge.end_time)
        if end_time is None:
            _LOGGER.warning(
                "Recovered charge %s has an invalid end time; finalizing locally",
                charge.charge_id,
            )
            self.waiting_for_last_charge = True
            self.hass.async_create_task(
                self._async_last_charge_match_timed_out()
            )
            return

        now = dt_util.now()
        elapsed = max(0.0, (now - end_time).total_seconds())
        remaining = max(
            0.0,
            float(self.last_charge_match_timeout) - elapsed,
        )

        _LOGGER.info(
            "Recovered pending charge %s: %.0fs elapsed, %.0fs timeout remaining",
            charge.charge_id,
            elapsed,
            remaining,
        )

        self._start_waiting_for_last_charge(remaining)

    def _stop_waiting_for_last_charge(self) -> None:
        """Stop Last Charge matching and cancel all associated timers."""

        self.waiting_for_last_charge = False
        self._cancel_last_charge_timer()
        self._cancel_last_charge_timeout_timer()

        _LOGGER.debug("Stopped waiting for Last Charge dataset")

    def _restart_last_charge_timer(self) -> None:
        """Restart the Last Charge stabilization timer."""

        self._cancel_last_charge_timer()

        self.last_charge_timer = self.hass.loop.call_later(
            self.last_charge_stable_time,
            self._last_charge_stabilized,
        )

        _LOGGER.debug(
            "Last Charge stabilization timer started for %ss",
            self.last_charge_stable_time,
        )

    def _cancel_last_charge_timer(self) -> None:
        """Cancel the Last Charge stabilization timer if active."""

        if self.last_charge_timer is None:
            return

        self.last_charge_timer.cancel()
        self.last_charge_timer = None

        _LOGGER.debug("Last Charge stabilization timer cancelled")

    def _cancel_last_charge_timeout_timer(self) -> None:
        """Cancel the overall FordPass matching timeout."""

        if self.last_charge_timeout_timer is None:
            return

        self.last_charge_timeout_timer.cancel()
        self.last_charge_timeout_timer = None

    def _last_charge_stabilized(self) -> None:
        """Schedule validation after the Last Charge dataset is stable."""

        self.last_charge_timer = None

        _LOGGER.debug(
            "Last Charge dataset stable for %ss",
            self.last_charge_stable_time,
        )

        self.hass.async_create_task(
            self._async_last_charge_stabilized()
        )

    def _last_charge_match_timed_out(self) -> None:
        """Schedule local finalization after the overall timeout."""

        self.last_charge_timeout_timer = None
        self.hass.async_create_task(
            self._async_last_charge_match_timed_out()
        )

    @staticmethod
    def _snapshot_attribute(
        snapshot: dict[str, Any] | None,
        *path: str,
    ) -> Any:
        """Read a nested attribute from a Last Charge snapshot."""

        value: Any = (
            snapshot.get("attributes", {})
            if snapshot is not None
            else {}
        )

        for key in path:
            if not isinstance(value, dict):
                return None
            value = value.get(key)

        return value

    @staticmethod
    def _parse_fordpass_datetime(value: Any) -> datetime | None:
        """Return a timezone-aware datetime from a local or FordPass value."""

        if isinstance(value, datetime):
            parsed = value
        elif isinstance(value, str) and value:
            parsed = dt_util.parse_datetime(value)
        else:
            return None

        if parsed is None:
            return None

        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt_util.UTC)

        return parsed

    def _last_charge_matches_current_charge(
        self,
        snapshot: dict[str, Any] | None,
    ) -> bool:
        """Return whether the FordPass dataset belongs to the local charge."""

        charge = self.current_charge
        if charge is None or snapshot is None:
            return False

        if (
            self.last_charge_signature
            == charge.last_charge_baseline_signature
        ):
            return False

        local_start = self._parse_fordpass_datetime(charge.start_time)
        local_end = self._parse_fordpass_datetime(charge.end_time)

        if local_start is None or local_end is None:
            _LOGGER.warning(
                "Cannot match Last Charge dataset because local charge "
                "timestamps are unavailable"
            )
            return False

        ford_start = self._parse_fordpass_datetime(
            self._snapshot_attribute(
                snapshot,
                "energyTransferDuration",
                "begin",
            )
            or self._snapshot_attribute(
                snapshot,
                "plugDetails",
                "plugInTime",
            )
        )
        ford_end = self._parse_fordpass_datetime(
            self._snapshot_attribute(
                snapshot,
                "energyTransferDuration",
                "end",
            )
            or self._snapshot_attribute(
                snapshot,
                "plugDetails",
                "plugOutTime",
            )
            or self._snapshot_attribute(snapshot, "timeStamp")
        )

        # If FordPass does not expose usable times, the new signature remains
        # the fallback freshness check.
        if ford_start is None and ford_end is None:
            return True

        tolerance_seconds = 900
        tolerance = timedelta(seconds=tolerance_seconds)

        if ford_start is None:
            ford_start = ford_end
        if ford_end is None:
            ford_end = ford_start

        matches = (
            ford_start <= local_end + tolerance
            and ford_end >= local_start - tolerance
        )

        if not matches:
            _LOGGER.debug(
                "Ignoring non-matching Last Charge dataset: "
                "local=%s..%s fordpass=%s..%s",
                local_start,
                local_end,
                ford_start,
                ford_end,
            )

        return matches

    async def _async_last_charge_stabilized(self) -> None:
        """Validate and apply a stable FordPass Last Charge dataset."""

        async with self._charge_lock:
            if not self.waiting_for_last_charge:
                return

            if self.current_charge is None:
                self._stop_waiting_for_last_charge()
                return

            if not self._last_charge_matches_current_charge(
                self.last_charge_snapshot
            ):
                # Keep waiting. A later FordPass update can still match.
                return

            self.current_charge.fordpass_last_charge = (
                dict(self.last_charge_snapshot)
                if self.last_charge_snapshot is not None
                else None
            )
            self.current_charge.data_source = "fordpass"
            self.current_charge.fordpass_pending = False

            state = self._read_vehicle_state()

            await self.storage.save_current_charge(
                self.current_charge.to_dict()
            )

            self._stop_waiting_for_last_charge()
            await self._finalize_charge(state)

    async def _async_last_charge_match_timed_out(self) -> None:
        """Finalize with local data when FordPass provides no matching record."""

        _LOGGER.info(
            "FordPass Last Charge hard timeout reached; finalizing locally"
        )

        async with self._charge_lock:
            if not self.waiting_for_last_charge:
                return

            if self.current_charge is None:
                self._stop_waiting_for_last_charge()
                return

            charge_id = self.current_charge.charge_id
            self.current_charge.fordpass_last_charge = None
            self.current_charge.fordpass_pending = False
            self.current_charge.data_source = "local"

            state = self._read_vehicle_state()

            await self.storage.save_current_charge(
                self.current_charge.to_dict()
            )

            self._stop_waiting_for_last_charge()
            await self._finalize_charge(state)

            _LOGGER.info(
                "No matching FordPass Last Charge data received within %ss; "
                "charging session %s saved with local data",
                self.last_charge_match_timeout,
                charge_id,
            )

    async def _wait_for_stable_vehicle_state(self):
        last = None
        stable = 0
        elapsed = 0

        while elapsed < STABLE_TIMEOUT:
            current = self._read_vehicle_state()

            key = (
                current.get("odometer"),
                current.get("soc"),
                current.get("latitude"),
                current.get("longitude"),
            )

            _LOGGER.debug("Vehicle state check %s", key)

            if key == last:
                stable += 1
            else:
                stable = 0

            if stable >= 1:
                _LOGGER.debug("Vehicle state stabilized after %ss", elapsed)
                return current

            last = key
            await asyncio.sleep(STABLE_INTERVAL)
            elapsed += STABLE_INTERVAL

        _LOGGER.warning("Vehicle state timeout reached")
        return self._read_vehicle_state()

    async def _get_address(self, state):
        return await self.geo.reverse_geocode(
            state.get("latitude"),
            state.get("longitude"),
        )

    @staticmethod
    def _distance_meters(
        latitude_1: float,
        longitude_1: float,
        latitude_2: float,
        longitude_2: float,
    ) -> float:
        """Return the distance between two coordinates in meters."""
        earth_radius_m = 6_371_000

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
            math.sqrt(value),
            math.sqrt(1 - value),
        )

    async def _try_link_charge_to_trip(
        self,
        state: dict[str, Any],
    ) -> None:
        """Link the current charge to a plausible preceding trip."""

        charge = self.current_charge
        if charge is None:
            return

        trip: Trip | None = None
        trip_end_time = None
        trip_end_latitude = None
        trip_end_longitude = None
        trip_source = None

        # A charge commonly starts before the Smart Trip timeout has expired.
        # In that case the preceding trip is paused and its real end values are
        # held in trip_end_state rather than in the Trip object itself.
        if self.trip_pause_data is not None and self.trip_end_state is not None:
            trip = self.trip_pause_data
            trip_end_time = self.trip_end_state.get("end_time")
            trip_end_latitude = self.trip_end_state.get("latitude")
            trip_end_longitude = self.trip_end_state.get("longitude")
            trip_source = "paused"
        elif self.last_completed_trip is not None:
            trip = self.last_completed_trip
            trip_end_time = trip.end_time
            trip_end_latitude = trip.end_latitude
            trip_end_longitude = trip.end_longitude
            trip_source = "completed"

        if trip is None:
            _LOGGER.debug("No preceding trip available for charge linking")
            return

        if not trip.trip_id or not trip_end_time:
            _LOGGER.debug(
                "Preceding trip has no ID or end time; charge not linked"
            )
            return

        if isinstance(trip_end_time, datetime):
            parsed_trip_end = trip_end_time
        else:
            parsed_trip_end = dt_util.parse_datetime(str(trip_end_time))

        charge_start = dt_util.parse_datetime(charge.start_time or "")

        if parsed_trip_end is None or charge_start is None:
            _LOGGER.debug(
                "Trip or charge timestamp could not be parsed; charge not linked"
            )
            return

        time_difference = (charge_start - parsed_trip_end).total_seconds()

        if time_difference < 0:
            _LOGGER.debug(
                "Charge started before trip ended (%ss); charge not linked",
                round(time_difference),
            )
            return

        if time_difference > MAX_LINK_TIME_SECONDS:
            _LOGGER.debug(
                "Trip link rejected: time difference %ss exceeds %ss",
                round(time_difference),
                MAX_LINK_TIME_SECONDS,
            )
            return

        coordinates = (
            trip_end_latitude,
            trip_end_longitude,
            state.get("latitude"),
            state.get("longitude"),
        )

        if any(value is None for value in coordinates):
            _LOGGER.debug(
                "Trip or charge coordinates missing; charge not linked"
            )
            return

        try:
            distance = self._distance_meters(
                float(trip_end_latitude),
                float(trip_end_longitude),
                float(state["latitude"]),
                float(state["longitude"]),
            )
        except (TypeError, ValueError):
            _LOGGER.debug(
                "Trip or charge coordinates invalid; charge not linked"
            )
            return

        if distance > MAX_LINK_DISTANCE_METERS:
            _LOGGER.debug(
                "Trip link rejected: distance %.0fm exceeds %sm",
                distance,
                MAX_LINK_DISTANCE_METERS,
            )
            return

        charge.trip_id = trip.trip_id
        charge.previous_trip_id = trip.trip_id

        trip.next_charge_id = charge.charge_id
        trip.next_charge_start = charge.start_time

        # Keep recovery data synchronized while the Smart Trip timer is still
        # running. The final archived trip will retain the same references.
        if trip_source == "paused":
            await self.storage.save_current_trip(trip.to_dict())

        _LOGGER.info(
            "Linked charge %s to %s trip %s (%.0fs, %.0fm)",
            charge.charge_id,
            trip_source,
            trip.trip_id,
            time_difference,
            distance,
        )

    async def start_trip(self):
        
        # Smart Trip: Resume paused trip
        if self.trip_pause_data is not None:
            
            if self.smart_trip_timer:
                self.smart_trip_timer.cancel()
                self.smart_trip_timer = None

            self.current_trip = self.trip_pause_data
            self.trip_pause_data = None
            self.trip_pause_time = None
            self.trip_end_time = None
            self.trip_end_state = None
           
            if self.route_tracker is not None and self.current_trip.trip_id:
                await self.route_tracker.async_start(
                    self.current_trip.trip_id
                )

            await self.storage.save_current_trip(
                self.current_trip.to_dict()
            )           

            self._schedule_coordinator_update(
                self._read_vehicle_state()
            )

            _LOGGER.info("Smart Trip resumed")
            return
    
        if self.current_trip:
                return

        state = self._read_vehicle_state()
        addr = await self._get_address(state)

        self.current_trip = Trip()
        self.current_trip.start(
            odometer=state.get("odometer"),
            soc=state.get("soc"),
            latitude=state.get("latitude"),
            longitude=state.get("longitude"),
            address=addr,
        )

        if self.route_tracker is not None and self.current_trip.trip_id:
            await self.route_tracker.async_start(
                self.current_trip.trip_id,
                start_latitude=state.get("latitude"),
                start_longitude=state.get("longitude"),
                start_timestamp=self.current_trip.start_time,
            )

        await self.storage.save_current_trip(self.current_trip.to_dict())

    async def finish_trip(self):
        """Pause the trip and capture its end state immediately."""

        if self._trip_finishing:
            _LOGGER.debug("Trip finalization already in progress")
            return

        trip = self.current_trip
        if trip is None:
            return

        if self.route_tracker is not None:
            await self.route_tracker.async_pause()

        self._trip_finishing = True

        try:
            if self.smart_trip_timer:
                self.smart_trip_timer.cancel()
                self.smart_trip_timer = None

            _LOGGER.info("Capturing stable trip end state")

            state = await self._wait_for_stable_vehicle_state()
            end_time = dt_util.now()
            address = await self._get_address(state)

            # The trip may have been changed while awaiting FordPass data.
            # Never finalize a different or already-cleared trip.
            if self.current_trip is not trip:
                _LOGGER.debug(
                    "Trip changed while capturing end state; snapshot discarded"
                )
                return

            self.trip_end_state = {
                "odometer": state.get("odometer"),
                "soc": state.get("soc"),
                "latitude": state.get("latitude"),
                "longitude": state.get("longitude"),
                "address": address,
                "end_time": end_time,
                "gps_updated_at": state.get("gps_updated_at"),
            }

            # Smart Trip pauses the captured trip object. The timeout only
            # decides whether this snapshot is finalized or discarded.
            self.trip_pause_data = trip
            self.trip_pause_time = self.hass.loop.time()
            self.trip_end_time = end_time

            recovery_data = trip.to_dict()
            recovery_payload = self._smart_trip_recovery_payload()
            if recovery_payload is not None:
                recovery_data["_smart_trip_recovery"] = recovery_payload

            await self.storage.save_current_trip(recovery_data)

            self.current_trip = None

            _LOGGER.info(
                "Trip paused for Smart Trip (%ss), end SOC=%s, odometer=%s",
                self.smart_trip_timeout,
                self.trip_end_state.get("soc"),
                self.trip_end_state.get("odometer"),
            )

            self.smart_trip_timer = self.hass.loop.call_later(
                self.smart_trip_timeout,
                lambda: self.hass.async_create_task(
                    self._smart_trip_timeout()
                ),
            )
        finally:
            self._trip_finishing = False

    async def start_charge(self):
        """Start charging session."""

        async with self._charge_lock:
            # A new IN_PROGRESS event permanently closes a previous session
            # that was still waiting for delayed FordPass data.
            if self.waiting_for_last_charge and self.current_charge:
                previous_charge_id = self.current_charge.charge_id
                self._stop_waiting_for_last_charge()
                self.current_charge.fordpass_pending = False

                await self._finalize_charge(
                    self._read_vehicle_state()
                )

                _LOGGER.info(
                    "Previous charging session %s finalized because a new "
                    "charging session started",
                    previous_charge_id,
                )

            if self.current_charge:
                return

            state = self._read_vehicle_state()
            address = await self._get_address(state)

            self.current_charge = Charge()
            self.current_charge.last_charge_baseline_signature = (
                self.last_charge_signature
            )

            self.current_charge.start(
                soc=state.get("soc"),
                latitude=state.get("latitude"),
                longitude=state.get("longitude"),
                address=address,
            )

            charging_site = await self._get_charging_site(state)
            self._apply_charging_site(charging_site)

            await self._try_link_charge_to_trip(state)

            await self.storage.save_current_charge(
                self.current_charge.to_dict()
            )

            _LOGGER.info(
                "Charging started at %s%%",
                state.get("soc"),
            )

            self._schedule_coordinator_update(state)

    async def finish_charge(self):
        """Finish charging locally and wait for stable FordPass data."""

        async with self._charge_lock:
            if not self.current_charge:
                return

            if self.waiting_for_last_charge:
                return

            charge = self.current_charge

            state = await self._wait_for_stable_vehicle_state()
            _LOGGER.info(
                "Charge end: soc=%s charging=%s lat=%s lon=%s",
                state.get("soc"),
                state.get("charging"),
                state.get("latitude"),
                state.get("longitude"),
            )

            if self.current_charge is not charge:
                _LOGGER.debug(
                    "Charging session changed while finishing; "
                    "aborting stale handler"
                )
                return

            address = await self._get_address(state)

            charge.finish(
                soc=state.get("soc"),
                latitude=state.get("latitude"),
                longitude=state.get("longitude"),
                address=address,
            )

            # Retry charging-site detection at the end of the session if the
            # start coordinates did not produce a match.
            if not charge.charging_site_id:
                charging_site = await self._get_charging_site(state)
                self._apply_charging_site(charging_site)

            if self.last_charge_entity:
                charge.fordpass_pending = True
                charge.data_source = "local"

                await self.storage.save_current_charge(
                    charge.to_dict()
                )

                self._start_waiting_for_last_charge()

                _LOGGER.info(
                    "Charging completed; waiting for stable FordPass "
                    "Last Charge data"
                )
                return

            await self._finalize_charge(state)

    async def _finalize_trip(self, state):
        """Finalize and save trip."""

        if not self.current_trip:
            return

        trip_obj = self.current_trip
        trip = trip_obj.to_dict()

        # Energy calculation
        start_soc = float(trip.get("start_soc") or 0)
        end_soc = float(trip.get("end_soc") or 0)
        soc_delta = max(0, start_soc - end_soc)

        trip["energy_used_kwh"] = round(
            (soc_delta / 100) * self.battery_capacity,
            2,
        )

        await self.storage.save_trip(trip)
        await self.storage.save_last_trip(trip)
        await self.history.refresh_statistics()

        # Issue #15: rebuild only the local calendar day affected by the
        # newly archived trip. Journey maintenance failures must never undo
        # or block an otherwise successful trip save.
        if self.journey_rebuilder is not None:
            try:
                start_time = dt_util.parse_datetime(
                    str(trip.get("start_time") or "")
                )

                if start_time is None:
                    raise ValueError(
                        "Saved trip has no valid start_time"
                    )

                if start_time.tzinfo is None:
                    start_time = start_time.replace(
                        tzinfo=dt_util.UTC
                    )

                journey_date = dt_util.as_local(start_time).date()

                await self.journey_rebuilder.async_rebuild_journeys(
                    start_date=journey_date,
                    end_date=journey_date,
                )

                _LOGGER.info(
                    "Journey rebuilt automatically for %s after trip %s",
                    journey_date,
                    trip.get("trip_id"),
                )
            except Exception:  # noqa: BLE001
                _LOGGER.exception(
                    "Automatic Journey rebuild failed after trip %s",
                    trip.get("trip_id"),
                )

        await self.storage.delete_current_trip()

        self.last_completed_trip = trip_obj

        _LOGGER.debug(
            "Stored last completed trip %s",
            trip_obj.trip_id,
        )

        self.current_trip = None

    

        self._schedule_coordinator_update(state)

        _LOGGER.info("Trip saved successfully")


    async def _apply_home_charging_costs(
        self,
        charge: Charge,
    ) -> bool:
        """Apply central automatic charging-cost calculation."""

        return self.charging_cost_calculator.recalculate(
            charge,
            allow_automatic_tariff=True,
        )

    async def _finalize_charge(self, state):
        """Finalize and save charging session exactly once."""

        if self.current_charge is None:
            return

        if self._charge_finalizing:
            _LOGGER.debug(
                "Charging finalization already in progress; duplicate request ignored"
            )
            return

        self._charge_finalizing = True
        charge_obj = self.current_charge

        try:
            charge_obj = await self.charging_location_resolver.async_resolve(
                charge_obj
            )
            charge = charge_obj.to_dict()

            start_soc = float(charge.get("start_soc") or 0)
            end_soc = float(charge.get("end_soc") or 0)
            soc_delta = max(0, end_soc - start_soc)

            energy_calculated = round(
                (soc_delta / 100) * self.battery_capacity,
                2,
            )

            energy_fordpass = None
            fordpass_snapshot = charge.get("fordpass_last_charge")

            if isinstance(fordpass_snapshot, dict):
                attributes = fordpass_snapshot.get("attributes")

                if isinstance(attributes, dict):
                    raw_energy = attributes.get("energyConsumed")

                    try:
                        if raw_energy is not None:
                            energy_fordpass = round(float(raw_energy), 2)
                    except (TypeError, ValueError):
                        _LOGGER.debug(
                            "FordPass energyConsumed is not numeric: %r",
                            raw_energy,
                        )

            charge["energy_added_kwh_calculated"] = energy_calculated
            charge["energy_added_kwh_fordpass"] = energy_fordpass

            # FordPass energyConsumed is strongly rounded and may differ
            # from the value shown in the FordPass app.
            charge["energy_added_kwh"] = energy_calculated
            charge["energy_source"] = "calculated"

            # Keep the Charge object synchronized for automatic cost logic.
            charge_obj.energy_added_kwh_calculated = energy_calculated
            charge_obj.energy_added_kwh_fordpass = energy_fordpass
            charge_obj.energy_added_kwh = energy_calculated
            charge_obj.energy_source = "calculated"

            await self._apply_home_charging_costs(charge_obj)
            charge = charge_obj.to_dict()

            archive_saved = await self.storage.save_charge(charge)
            cache_saved = await self.storage.save_last_charge(charge)

            if not archive_saved or not cache_saved:
                _LOGGER.error(
                    "Charging session %s could not be saved completely; "
                    "recovery data retained",
                    charge.get("charge_id"),
                )
                return

            await self.history.refresh_statistics()

            if self.current_charge is charge_obj:
                await self.storage.delete_current_charge()
                self.current_charge = None

            self._schedule_coordinator_update(state)

            _LOGGER.info("Charging session saved successfully")

        finally:
            self._charge_finalizing = False


    @staticmethod
    def _gps_timestamp_is_newer(
        current_value: Any,
        baseline_value: Any,
    ) -> bool:
        """Return whether the tracker timestamp is newer than the baseline."""

        current = dt_util.parse_datetime(str(current_value or ""))
        baseline = dt_util.parse_datetime(str(baseline_value or ""))

        if current is None:
            return False

        if baseline is None:
            return True

        return current > baseline

    async def _select_trip_end_position(
        self,
        fresh_gps_state: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Return the most plausible final Trip GPS position."""

        route_point = None
        if self.route_tracker is not None:
            route_point = self.route_tracker.get_last_point()

        if fresh_gps_state is None:
            if route_point is None:
                _LOGGER.warning(
                    "Trip-end GPS unavailable: no fresh vehicle GPS and no route point"
                )
                return {
                    "latitude": None,
                    "longitude": None,
                    "address": None,
                    "gps_updated_at": None,
                }

            route_state = {
                "latitude": route_point.get("latitude"),
                "longitude": route_point.get("longitude"),
                "gps_updated_at": route_point.get("timestamp"),
            }
            route_state["address"] = await self._get_address(route_state)
            _LOGGER.warning(
                "No fresh vehicle trip-end GPS; using last route tracker point"
            )
            return route_state

        if route_point is None:
            _LOGGER.info(
                "Trip-end GPS validation skipped: no route tracker point; using vehicle GPS"
            )
            return fresh_gps_state

        try:
            distance = self._distance_meters(
                float(fresh_gps_state["latitude"]),
                float(fresh_gps_state["longitude"]),
                float(route_point["latitude"]),
                float(route_point["longitude"]),
            )
        except (KeyError, TypeError, ValueError):
            _LOGGER.warning(
                "Trip-end GPS validation failed because coordinates are invalid; using vehicle GPS"
            )
            return fresh_gps_state

        if distance <= TRIP_END_GPS_MAX_DISTANCE_METERS:
            _LOGGER.info(
                "Trip-end GPS validation: vehicle-route distance=%.0fm; using vehicle GPS",
                distance,
            )
            return fresh_gps_state

        route_state = {
            "latitude": route_point.get("latitude"),
            "longitude": route_point.get("longitude"),
            "gps_updated_at": route_point.get("timestamp"),
        }
        route_state["address"] = await self._get_address(route_state)

        _LOGGER.warning(
            "Trip-end GPS validation: vehicle-route distance=%.0fm exceeds %sm; using route tracker GPS",
            distance,
            TRIP_END_GPS_MAX_DISTANCE_METERS,
        )
        return route_state


    async def _wait_for_fresh_trip_end_gps(
        self,
        baseline_timestamp: Any,
    ) -> dict[str, Any] | None:
        """Wait for a tracker update newer than the captured trip-end GPS."""

        deadline = self.hass.loop.time() + GPS_UPDATE_TIMEOUT

        while True:
            state = self._read_vehicle_state()

            if self._gps_timestamp_is_newer(
                state.get("gps_updated_at"),
                baseline_timestamp,
            ):
                latitude = state.get("latitude")
                longitude = state.get("longitude")

                if latitude is not None and longitude is not None:
                    state["address"] = await self._get_address(state)
                    _LOGGER.info(
                        "Fresh trip-end GPS received: %s, %s (%s)",
                        latitude,
                        longitude,
                        state.get("gps_updated_at"),
                    )
                    return state

                _LOGGER.debug(
                    "Tracker timestamp changed but coordinates are unavailable"
                )

            remaining = deadline - self.hass.loop.time()
            if remaining <= 0:
                _LOGGER.warning(
                    "No fresh trip-end GPS received within %ss",
                    GPS_UPDATE_TIMEOUT,
                )
                return None

            # Clear before the second read to avoid missing an update between
            # the initial check and waiting on the event.
            self._gps_update_event.clear()

            state = self._read_vehicle_state()
            if self._gps_timestamp_is_newer(
                state.get("gps_updated_at"),
                baseline_timestamp,
            ):
                continue

            try:
                await asyncio.wait_for(
                    self._gps_update_event.wait(),
                    timeout=remaining,
                )
            except asyncio.TimeoutError:
                _LOGGER.warning(
                    "No fresh trip-end GPS received within %ss",
                    GPS_UPDATE_TIMEOUT,
                )
                return None

    async def _smart_trip_timeout(self):
        """Finalize a paused trip after refreshing its final GPS position."""

        _LOGGER.info("Smart Trip timeout reached")
        self.smart_trip_timer = None

        if not self.trip_pause_data:
            return

        if self.current_trip:
            _LOGGER.debug(
                "Smart Trip cancelled - trip already resumed"
            )
            return

        if not self.trip_end_state:
            _LOGGER.error(
                "Cannot finalize paused trip: trip end-state snapshot missing"
            )
            return

        self.current_trip = self.trip_pause_data
        self.trip_pause_data = None

        end_state = self.trip_end_state
        self.trip_end_state = None

        fresh_gps_state = await self._wait_for_fresh_trip_end_gps(
            end_state.get("gps_updated_at")
        )

        final_position = await self._select_trip_end_position(
            fresh_gps_state
        )
        end_state["latitude"] = final_position.get("latitude")
        end_state["longitude"] = final_position.get("longitude")
        end_state["address"] = final_position.get("address")
        end_state["gps_updated_at"] = final_position.get(
            "gps_updated_at"
        )

        self.current_trip.finish(
            odometer=end_state.get("odometer"),
            soc=end_state.get("soc"),
            latitude=end_state.get("latitude"),
            longitude=end_state.get("longitude"),
            address=end_state.get("address"),
            end_time=end_state.get("end_time"),
        )

        if self.route_tracker is not None:
            await self.route_tracker.async_finalize(
                end_latitude=end_state.get("latitude"),
                end_longitude=end_state.get("longitude"),
                end_timestamp=end_state.get("end_time"),
            )

        await self._finalize_trip(end_state)

        self.trip_pause_time = None
        self.trip_end_time = None
        self.current_trip = None

