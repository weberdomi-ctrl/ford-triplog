"""
Ford Triplog

Coordinator

Version: 1.2.2
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.core import Event, HomeAssistant
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .geo import FordTriplogGeo
from .history import FordTriplogHistory
from .storage import FordTriplogStorage
from .trip import Trip
from .charge import Charge

from .const import SMART_TRIP_TIMEOUT

_LOGGER = logging.getLogger(__name__)

STABLE_INTERVAL = 2
STABLE_TIMEOUT = 20


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

        self.vehicle_state: dict[str, Any] = {}

        self.last_ignition = False
        self.last_charging = False

        self.remove_listener = None

        # Smart Trip
        self.trip_pause_time: float | None = None
        self.trip_pause_data: Trip | None = None
        self.smart_trip_timer: asyncio.TimerHandle | None = None

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
        self.vehicle_state = self._read_vehicle_state()
        ignition = str(self.vehicle_state.get("ignition")).lower() in (
            "on", "true", "1", "running"
        )

        charging_state = str(
            self.vehicle_state.get("charging")
        ).upper()

        charging = charging_state == "IN_PROGRESS"


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

    async def start_trip(self):
        
        # Smart Trip: Resume paused trip
        if self.trip_pause_data is not None:
            
            if self.smart_trip_timer:
                self.smart_trip_timer.cancel()
                self.smart_trip_timer = None

            self.current_trip = self.trip_pause_data    
            self.trip_pause_data = None
            self.trip_pause_time = None

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

        state = self._read_vehicle_state()
        address = await self._get_address(state)

        self.current_charge.finish(
            soc=state.get("soc"),
            latitude=state.get("latitude"),
            longitude=state.get("longitude"),
            address=address,
        )

        await self._finalize_charge(state)


    async def _finalize_trip(self, state):
        """Finalize and save trip."""

        if not self.current_trip:
            return

        trip = self.current_trip.to_dict()

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

        self.current_trip = None

    

        self.async_set_updated_data(state)

        _LOGGER.info("Trip saved successfully")


    async def _finalize_charge(self, state):
        """Finalize and save charging session."""

        if not self.current_charge:
            return

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

        _LOGGER.info("Charging session saved successfully")


    async def _smart_trip_timeout(self):
        """Finalize paused trip after timeout."""

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
        )

        await self._finalize_trip(state)
        self.current_trip = None
              
