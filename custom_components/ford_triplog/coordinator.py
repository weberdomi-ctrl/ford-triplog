"""
Ford Triplog

Coordinator

Version: 1.3.0
"""

from __future__ import annotations

import asyncio
import logging
import math
from typing import Any

from homeassistant.core import Event, HomeAssistant
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .geo import FordTriplogGeo
from .history import FordTriplogHistory
from .storage import FordTriplogStorage
from .trip import Trip
from .charge import Charge

from .const import SMART_TRIP_TIMEOUT

_LOGGER = logging.getLogger(__name__)

STABLE_INTERVAL = 2
STABLE_TIMEOUT = 20

MAX_LINK_TIME_SECONDS = 1800
MAX_LINK_DISTANCE_METERS = 300


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

        # Battery capacity (kWh)
        self.battery_capacity = float(config.get("battery_capacity_kwh", 77))

        self.smart_trip_timeout = int(
        config.get("smart_trip_timeout", SMART_TRIP_TIMEOUT)
)


        self.current_trip: Trip | None = None
        self.current_charge: Charge | None = None
        self.last_completed_trip: Trip | None = None

        self.vehicle_state: dict[str, Any] = {}

        self.last_ignition = False
        self.last_charging = False

        self.remove_listener = None

        # Serialize state transitions. Home Assistant can deliver several
        # entity updates within a few seconds (SOC, tracker, ignition, charging).
        # Without a lock, two callbacks can start or finalize the same event.
        self._transition_lock = asyncio.Lock()
        self._trip_finalizing = False
        self._charge_finalizing = False

        # Smart Trip
        self.trip_pause_time: float | None = None
        self.trip_pause_data: Trip | None = None
        self.smart_trip_timer: asyncio.TimerHandle | None = None
        self.trip_end_time = None
       

    async def async_setup(self):
        await self.storage.async_setup()

        data = await self.storage.load_current_trip()
        if data:
            self.current_trip = Trip.from_dict(data)

          
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
            ) if e
        ]

        # Seed edge-detection state before registering the listener. This avoids
        # interpreting the first unrelated entity update as a fresh ignition or
        # charging transition after a Home Assistant restart.
        self.vehicle_state = self._read_vehicle_state()
        self.last_ignition = str(
            self.vehicle_state.get("ignition")
        ).lower() in ("on", "true", "1", "running")
        self.last_charging = str(
            self.vehicle_state.get("charging")
        ).upper() == "IN_PROGRESS"

        self.remove_listener = async_track_state_change_event(
            self.hass, entities, self._state_changed
        )

    def _read_vehicle_state(self):
        data = {}

        for key in (
            "ignition",
            "odometer",
            "soc",
            "charging",    
        ):
            entity_id = self.config.get(key)
            st = self.hass.states.get(entity_id) if entity_id else None
            data[key] = st.state if st else None




        tracker = self.hass.states.get(self.config.get("tracker"))
        data["latitude"] = tracker.attributes.get("latitude") if tracker else None
        data["longitude"] = tracker.attributes.get("longitude") if tracker else None
        return data




    async def _state_changed(self, event: Event):
        """Process vehicle state changes in a strictly serialized order."""
        async with self._transition_lock:
            self.vehicle_state = self._read_vehicle_state()

            ignition = str(
                self.vehicle_state.get("ignition")
            ).lower() in ("on", "true", "1", "running")

            charging = str(
                self.vehicle_state.get("charging")
            ).upper() == "IN_PROGRESS"

            # Charging has priority over ignition. The vehicle may report
            # ignition=on while the driver is sitting in the car during a charge.
            # That must not create a new trip with a mid-charge SOC value.
            if charging:
                if not self.last_charging:
                    await self.start_charge()

                self.last_charging = True
                # Treat ignition as inactive for trip edge detection while
                # charging. If ignition is still on when charging ends, the
                # following event starts the trip with the final charging SOC.
                self.last_ignition = False

                self.async_set_updated_data(self.vehicle_state)
                return

            # Charging has just ended. Finalize it before considering a new trip
            # so the stabilized post-charge SOC is used for both records.
            if self.last_charging:
                await self.finish_charge()

            self.last_charging = False

            # Normal trip edge handling only when no charging session is active.
            if ignition and not self.last_ignition:
                await self.start_trip()
            elif not ignition and self.last_ignition:
                await self.finish_trip()

            self.last_ignition = ignition
            self.async_set_updated_data(self.vehicle_state)

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
        """Link the current charge to the last completed trip when plausible."""
        if self.current_charge is None:
            return

        trip = self.last_completed_trip
        if trip is None:
            _LOGGER.debug("No completed trip available for charge linking")
            return

        if not trip.trip_id or not trip.end_time:
            _LOGGER.debug(
                "Last completed trip has no ID or end time; charge not linked"
            )
            return

        trip_end = dt_util.parse_datetime(trip.end_time)
        charge_start = dt_util.parse_datetime(
            self.current_charge.start_time or ""
        )

        if trip_end is None or charge_start is None:
            _LOGGER.debug(
                "Trip or charge timestamp could not be parsed; charge not linked"
            )
            return

        time_difference = (charge_start - trip_end).total_seconds()

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
            trip.end_latitude,
            trip.end_longitude,
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
                float(trip.end_latitude),
                float(trip.end_longitude),
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

        self.current_charge.trip_id = trip.trip_id
        self.current_charge.previous_trip_id = trip.trip_id

        _LOGGER.info(
            "Linked charge %s to trip %s (%.0fs, %.0fm)",
            self.current_charge.charge_id,
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
           
            await self.storage.save_current_trip(
                self.current_trip.to_dict()
            )           

            self.async_set_updated_data(
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

        await self.storage.save_current_trip(self.current_trip.to_dict())

    async def finish_trip(self):
        if not self.current_trip:
            return

        _LOGGER.info("Waiting for stable vehicle state...")


        if self.smart_trip_timer:
            self.smart_trip_timer.cancel()
            self.smart_trip_timer = None
        
        # Smart Trip
        self.trip_pause_data = self.current_trip
        
        await self.storage.save_current_trip(
           self.current_trip.to_dict()
        )

        self.current_trip = None
        
        self.trip_pause_time = self.hass.loop.time()
        self.trip_end_time = dt_util.now()

        _LOGGER.debug(
        "Trip paused - waiting %s seconds",
        self.smart_trip_timeout,
        )

        self.smart_trip_timer = self.hass.loop.call_later(
            self.smart_trip_timeout,
            lambda: self.hass.async_create_task(
                self._smart_trip_timeout()
            ),
        )


        _LOGGER.info(
            "Trip paused for Smart Trip (%ss)",
            self.smart_trip_timeout,
)

    async def start_charge(self):
        """Start charging session."""
    
        if self.current_charge:
            return

        state = self._read_vehicle_state()
        address = await self._get_address(state)

        self.current_charge = Charge()


        self.current_charge.start(
            soc=state.get("soc"),
            latitude=state.get("latitude"),
            longitude=state.get("longitude"),
            address=address,
        )

        await self._try_link_charge_to_trip(state)

        await self.storage.save_current_charge(
            self.current_charge.to_dict()
        )

        _LOGGER.info(
            "Charging started at %s%%",
            state.get("soc"),
        )

        self.async_set_updated_data(state)


    async def finish_charge(self):
        """Finish charging session."""

        if not self.current_charge:
            return

        state = await self._wait_for_stable_vehicle_state()
        _LOGGER.info(
            "Charge end: soc=%s charging=%s lat=%s lon=%s",
            state.get("soc"),
            state.get("charging"),
            state.get("latitude"),
            state.get("longitude"),
        )

        address = await self._get_address(state)

        self.current_charge.finish(
            soc=state.get("soc"),
            latitude=state.get("latitude"),
            longitude=state.get("longitude"),
            address=address,
        )

        await self._finalize_charge(state)


    async def _finalize_trip(self, state):
        """Finalize and save trip exactly once."""

        if not self.current_trip or self._trip_finalizing:
            return

        self._trip_finalizing = True
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
        await self.storage.delete_current_trip()

        self.last_completed_trip = trip_obj

        _LOGGER.debug(
            "Stored last completed trip %s",
            trip_obj.trip_id,
        )

        self.current_trip = None

    

        self.async_set_updated_data(state)

        self._trip_finalizing = False
        _LOGGER.info("Trip saved successfully")


    async def _finalize_charge(self, state):
        """Finalize and save charging session exactly once."""

        if not self.current_charge or self._charge_finalizing:
            return

        self._charge_finalizing = True
        charge = self.current_charge.to_dict()

        start_soc = float(charge.get("start_soc") or 0)
        end_soc = float(charge.get("end_soc") or 0)
        soc_delta = max(0, end_soc - start_soc)

        charge["energy_added_kwh"] = round(
            (soc_delta / 100) * self.battery_capacity,
            2,
        )

        await self.storage.save_charge(charge)
        await self.storage.save_last_charge(charge)

        await self.storage.delete_current_charge()

        self.current_charge = None

        self.async_set_updated_data(state)

        self._charge_finalizing = False
        _LOGGER.info("Charging session saved successfully")


    async def _smart_trip_timeout(self):
        """Finalize a paused trip after timeout without racing a resume."""
        async with self._transition_lock:
            await self._smart_trip_timeout_locked()

    async def _smart_trip_timeout_locked(self):
        """Locked Smart Trip timeout implementation."""

        _LOGGER.info("Smart Trip timeout reached")

        if not self.trip_pause_data:
            return

        if self.current_trip:
            _LOGGER.debug(
                "Smart Trip cancelled - trip already resumed"
            )
            return

        self.current_trip = self.trip_pause_data
        self.trip_pause_data = None

        state = await self._wait_for_stable_vehicle_state()

        self.current_trip.finish(
            odometer=state.get("odometer"),
            soc=state.get("soc"),
            latitude=state.get("latitude"),
            longitude=state.get("longitude"),
            address=await self._get_address(state),
            end_time=self.trip_end_time,
        )

        await self._finalize_trip(state)
        self.trip_end_time = None
        self.current_trip = None