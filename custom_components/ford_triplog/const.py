"""
Ford Triplog

Track your Ford.

Central constants used throughout the integration.

"""

from __future__ import annotations

from typing import Final

#
# Integration
#

DOMAIN: Final = "ford_triplog"
NAME: Final = "Ford Triplog"
GENERATOR: Final = "Ford Triplog"
VERSION: Final = "1.9.0"

#
# Storage
#

STORAGE_SCHEMA_VERSION: Final = 1
TRIP_SCHEMA_VERSION: Final = 1
CHARGE_SCHEMA_VERSION: Final = 3

STORAGE_DIR: Final = "ford_triplog"
TRIPS_DIR: Final = "trips"
CACHE_DIR: Final = "cache"

# User-defined charging sites (Phase 3)
USER_CHARGING_SITES_FILE: Final = "user_charging_sites.json"
USER_CHARGING_SITES_SCHEMA_VERSION: Final = 1
PENDING_CHARGING_SITES_FILE: Final = "pending_charging_sites.json"
PENDING_CHARGING_SITES_SCHEMA_VERSION: Final = 1
PENDING_CHARGING_SITE_DEDUP_RADIUS: Final = 100.0
DEFAULT_USER_CHARGING_SITE_RADIUS: Final = 50.0

CURRENT_TRIP_FILE: Final = "current_trip.json"
LAST_TRIP_FILE: Final = "last_trip.json"
STATISTICS_FILE: Final = "statistics.json"
DIAGNOSTICS_FILE: Final = "diagnostics.json"


#
# Journey
#

JOURNEY_SCHEMA_VERSION: Final = 2

JOURNEYS_DIR: Final = "journeys"

CURRENT_JOURNEY_FILE: Final = "current_journey.json"
LAST_JOURNEY_FILE: Final = "last_journey.json"

#
# Config Flow
#

CONF_IGNITION: Final = "ignition"
CONF_ODOMETER: Final = "odometer"
CONF_TRACKER: Final = "tracker"
CONF_SOC: Final = "soc"
CONF_CHARGING: Final = "charging"
CONF_LAST_CHARGE: Final = "last_charge"
CONF_BATTERY_CAPACITY: Final = "battery_capacity_kwh"


CONF_SMART_TRIP: Final = "smart_trip"
CONF_SMART_TRIP_TIMEOUT: Final = "smart_trip_timeout"


CONF_JOURNEY_HOME_ZONE: Final = "journey_home_zone"
CONF_JOURNEY_HOME_TIMEOUT: Final = "journey_home_timeout_minutes"
CONF_JOURNEY_MAX_GAP_HOURS: Final = "journey_max_gap_hours"

DEFAULT_JOURNEY_HOME_ZONE: Final = "zone.home"
DEFAULT_JOURNEY_HOME_TIMEOUT: Final = 15
DEFAULT_JOURNEY_MAX_GAP_HOURS: Final = 24

# Charging defaults

DEFAULT_CHARGE_MATCH_TIMEOUT: Final = 300  # 5 minutes
DEFAULT_CHARGE_MATCH_RADIUS: Final = 50.0  # meters
DEFAULT_LAST_CHARGE_STABLE_TIME: Final = 15  # seconds

#
# Events
#

EVENT_TRIP_STARTED: Final = "ford_triplog_trip_started"
EVENT_TRIP_FINISHED: Final = "ford_triplog_trip_finished"
EVENT_JOURNEY_STARTED: Final = "ford_triplog_journey_started"
EVENT_JOURNEY_FINISHED: Final = "ford_triplog_journey_finished"

#
# Sensor Unique IDs
#

SENSOR_LAST_TRIP: Final = "last_trip"
SENSOR_STATISTICS: Final = "statistics"
SENSOR_STATUS: Final = "triplog"
SENSOR_LAST_JOURNEY: Final = "last_journey"

#
# Common Trip Attributes
#

ATTR_TRIP_ID: Final = "trip_id"
ATTR_JOURNEY_ID: Final = "journey_id"

ATTR_START_TIME: Final = "start_time"
ATTR_END_TIME: Final = "end_time"

ATTR_START_ADDRESS: Final = "start_address"
ATTR_END_ADDRESS: Final = "end_address"

ATTR_START_ZONE: Final = "start_zone"
ATTR_END_ZONE: Final = "end_zone"

ATTR_START_LATITUDE: Final = "start_latitude"
ATTR_START_LONGITUDE: Final = "start_longitude"

ATTR_END_LATITUDE: Final = "end_latitude"
ATTR_END_LONGITUDE: Final = "end_longitude"

ATTR_START_ODOMETER: Final = "start_odometer"
ATTR_END_ODOMETER: Final = "end_odometer"

ATTR_DISTANCE: Final = "distance_km"
ATTR_DURATION: Final = "duration_seconds"

ATTR_START_SOC: Final = "start_soc"
ATTR_END_SOC: Final = "end_soc"

ATTR_VEHICLE: Final = "vehicle"
ATTR_TRIP_COUNT: Final = "trip_count"
ATTR_CHARGE_COUNT: Final = "charge_count"

#
# Status
#

STATUS_IDLE: Final = "idle"
STATUS_DRIVING: Final = "driving"
STATUS_READY: Final = "ready"

#
# Dispatcher Signals
#

SIGNAL_LAST_TRIP_UPDATED: Final = "ford_triplog_last_trip_updated"
SIGNAL_STATISTICS_UPDATED: Final = "ford_triplog_statistics_updated"
SIGNAL_STATUS_UPDATED: Final = "ford_triplog_status_updated"
SIGNAL_LAST_JOURNEY_UPDATED: Final = "ford_triplog_last_journey_updated"

#Smart Trip Timeout
SMART_TRIP_TIMEOUT: Final = 300  # 5 minutes