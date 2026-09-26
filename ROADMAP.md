# Ford Triplog Roadmap

This roadmap summarizes completed Ford Triplog releases and the next planned development areas.

---

# Version 2.0.x

## Version 2.0.3 – Maintenance and Statistics

Ford Triplog 2.0.3 focuses on technical cleanup, statistics and location resolution:

- Use English consistently as the internal base language and translation fallback
- Consolidate translation keys and entity naming
- Top Departures & Destinations
- Top Routes
- Home Assistant zone-aware location statistics
- User-defined charging-location lookup for trip statistics
- OpenStreetMap charging-location lookup for trip statistics
- 50 m GPS clustering where no known location is available
- Address fallback where no better location can be resolved
- Recorder and Route History cleanup
- Additional dashboard examples and statistics
- General code cleanup after the 2.0.x feature expansion

Location statistics use the following resolution priority:

1. Home Assistant zone
2. User-defined Ford Triplog charging location
3. Known OpenStreetMap charging location
4. 50 m GPS cluster
5. Stored address fallback

---

# Version 2.1 – SQLite Storage Migration

Version 2.1 implements the first production-capable SQLite storage backend while keeping JSON available as a compatibility and fallback path.

## Implemented – Database Mirror

- Local SQLite database
- Existing JSON data mirrored/migrated into corresponding database tables
- Parallel JSON and SQLite writes for the transition period
- Existing IDs and record structures preserved where possible
- Non-destructive migration behavior
- JSON remains available for compatibility and recovery

## Implemented – Selectable Read Backend

- Selectable JSON or SQLite read backend
- JSON remains the default after upgrade
- SQLite must be enabled explicitly by the user
- Backend selection persists in Home Assistant options
- Integration reloads when storage options change
- Statistics are recalculated from the selected backend after setup/reload

## Implemented – SQLite-backed Data

SQLite-backed reads are available for:

- Trips
- Charges
- Journeys
- Routes
- Current and last caches
- User-defined charging locations
- Pending charging locations
- Charging metadata
- Pause metadata
- Receipts and OCR/parser state
- User-created receipt parser profiles
- Statistics and diagnostics

Bundled receipt parser profiles remain program data and are not migrated into user storage.

## Implemented – Backend-independent Maintenance

- Journey rebuild reads Trips and Charges from the selected backend
- Journey rebuild no longer depends on archived JSON file paths in SQLite mode
- Statistics read their source archives from the selected backend
- Derived statistics are refreshed after integration setup/reload
- JSON and SQLite can therefore be compared without carrying statistics from the previously selected backend

## Implemented – SQL Queries and Views

SQLite views and queries are used where they provide a clear benefit, including support for:

- Top Trip
- Top Journey
- Top Day
- Top Charging
- Top locations
- Top routes

Application-specific logic such as Home Assistant zone resolution, charging-site matching and GPS clustering remains in Python.

## Implemented – Runtime and Startup Optimization

- Incremental startup mirroring for Trips and Charges
- Incremental startup mirroring for Journeys and Routes
- Existing identical records are skipped instead of being rewritten to SQLite
- SQLite-only archive records are preserved during compatibility mirroring
- Bulk mirror-index reads for Journey and Route comparison
- Combined main-storage snapshot for efficient Trip, Charge and cache comparison
- SQLite schema initialization runs only once per Home Assistant runtime
- Parallel database initialization is protected by an asynchronous lock
- Metadata and legacy migration checks are guarded against repeated execution
- User-defined charging locations are cached after initial loading
- Bulk Route reads are used for multiple Trip IDs
- Top Locations and Top Routes share cached location resolution data
- Rapid coordinator update bursts are coalesced before sensor publication
- Redundant periodic polling is disabled for push-driven Ford Triplog sensors

## Transition Policy

SQLite is available as an explicit read option in 2.1, but JSON remains the default for upgraded installations.

This allows the SQLite backend to be tested under normal use without silently changing storage behavior for existing users.

Version 2.2 continues the parallel JSON/SQLite transition so the SQLite backend can gain further real-world testing before the final storage cutover.

---

# Version 2.2 – Reliability, Export & Maintenance

Version 2.2 completes the next practical feature layer on top of the
2.1 parallel JSON/SQLite storage architecture.

## Implemented – CSV Export

Ford Triplog now provides CSV export for:

- Trips
- Journeys
- Charging sessions

Exports support optional date ranges and can be downloaded directly
through the Home Assistant options flow.

The export format uses practical flattened columns instead of exposing
internal JSON payloads directly.

## Implemented – Configurable Vehicle Data Sources

- Vehicle data-source entities can be changed from Ford Triplog settings
- Existing stored Triplog data is preserved
- The integration can be pointed to different compatible Ford entities
  without reinstalling Ford Triplog

## Implemented – Invalid Charging Session Cleanup

- Suspicious charging sessions are filtered before deletion is offered
- Explicit confirmation is required
- Dependent Journeys and statistics are rebuilt after deletion
- The stored last charging session is refreshed when required
- Existing receipt files are preserved

## Implemented – Pause Receipt Workflow

- Direct receipt upload from a selected pause
- Multiple receipts per pause
- Optional receipt notes
- Open and delete pause receipts
- Pause-specific receipt detail views
- Pause receipts exposed in Journey History with signed dashboard URLs
- Dedicated dashboard cards can display pause duration, location, costs
  and all receipts linked to the pause
- OCR is not required for pause receipts

## Implemented – History Reliability

- Fixed Journey History date-selection/display issues
- Newest pauses are shown first
- Pause titles, notes and costs are exposed in Journey History
- History selector refresh scheduling follows Home Assistant thread-safety
  requirements
- Pause receipts follow the shared selected History date

## Storage Policy for 2.2

- JSON and SQLite continue to be written in parallel
- The selectable read backend remains available
- SQLite continues to receive real-world validation
- No write-backend selector is planned
- Storage architecture remains compatible with 2.1 throughout this release

---

# Version 2.3 – SQLite Primary Storage & Route Reliability

Version 2.3 completes the storage migration started in 2.1 and expands
the Route Tracker for dense Home Assistant Companion App GPS data.

Status: **Released**

## Implemented – SQLite-only Production Storage

- SQLite is the sole productive Ford Triplog storage backend
- Parallel JSON production writes are removed
- Existing JSON data remains available as a migration/import source
- Persistent migration markers prevent already completed legacy imports
  from being scanned again after every Home Assistant restart
- Runtime complexity from maintaining two synchronized production
  formats is removed
- Receipts remain stored as files and linked through persistent metadata

## Implemented – Safer Source Configuration

- Vehicle source entities remain configurable
- Ford Triplog's own output entities cannot be selected as their own
  source
- Route Tracker source selection uses the same self-reference protection
- Obsolete configuration paths were removed during the 2.3 cleanup

## Implemented – Home Assistant Device Tracker Route Source

Route Tracker position sources now include:

- ABRP latitude/longitude sensors
- Home Assistant Companion App Geocoded Location
- Direct Home Assistant `device_tracker` GPS

The direct tracker source reads latitude/longitude from the entity
attributes and uses the Home Assistant update timestamp.

This enables dense high-accuracy Companion App traces without depending
on the slower Geocoded Location sensor.

## Implemented – Trip-end GPS Selection

At Smart Trip timeout Ford Triplog compares the newest valid point from:

- the configured Route Tracker source
- the configured vehicle tracker

The point with the newest timestamp is used as the authoritative route
endpoint.

This prevents an older route-source point from winning merely because it
is geographically close to an earlier ignition-off snapshot.

## Implemented – Dense OSRM Map Matching

- Long traces are split into chunks below the common OSRM 100-coordinate
  matching limit
- Chunks overlap to preserve continuity
- Matched chunk geometries are merged into one route
- OSRM matching uses `tidy=false` to keep tracepoints aligned with the
  submitted GPS points
- Raw GPS points are always retained independently
- Match diagnostics include raw/matched counts, unmatched tracepoints,
  distance and confidence

## Implemented – Route Maintenance

Stored routes can be reprocessed through the configured OSRM server.

Maintenance modes include:

- latest route
- raw/failed routes
- all routes

Existing raw data is preserved and matched geometry is replaced only
after a successful plausibility check.

## Implemented – Last Tour / Last Route Reliability

- Last Tour represents the latest completed individual Trip
- Last Route resolves the latest completed stored route
- Last Route refresh scheduling follows Home Assistant thread-safety
  requirements
- Route map entities continue to expose a separate map-centre coordinate
  and GeoJSON geometry

---

# Version 2.4 – Charging Reliability, Statistics, Journey Places & Source Health

Status: **Released**

Version 2.4 consolidates charging-data reliability improvements, new energy/statistics reporting, reusable Journey places, safer historical Journey maintenance and vehicle-source health monitoring.

## Implemented – Charging Source Reconciliation

- AC/DC charging type handling
- Delayed Start-SOC stabilization
- Live charging snapshots for SOC, charging type and charger energy
- Preservation of the last valid live snapshot when Ford clears values after a manual stop
- Completion snapshot for available end-SOC, charging type and charger energy
- Separate storage of technical charging-energy sources
- Ford Last Charge reconciliation for already completed sessions
- Billed receipt energy has highest priority for charging-cost calculations
- Improved charging-energy provenance and session transparency

## Implemented – Recuperation and Monthly Driving Statistics

- Trip fields `soc_recovered` and `regenerated_energy_kwh`
- SOC-based net recuperation statistics
- Total recovered SOC
- Total net recuperated energy
- Recuperation-trip count
- Average recuperation
- Top recuperation Trip
- Monthly driving distance
- Monthly Trip and Journey counts
- Monthly driving time
- Monthly net battery energy
- Monthly average consumption
- Monthly recuperation values
- Monthly driving-statistics CSV export

## Implemented – Monthly Charging Statistics

- Home / Work / External classification
- Energy, cost and session count per category
- Current-month totals
- Rolling monthly history
- Yearly summaries
- Monthly charging-statistics CSV export
- Energy-source selection aligned with stored charging-session provenance

## Implemented – User-defined Places

- Reusable places for automatic Journey pause assignment
- Name, category and description
- Latitude / longitude and configurable radius
- Optional MDI icon
- Direct creation from an existing Journey pause
- Duplicate protection for near-identical places
- Home Assistant zone → user-defined place → existing location/address display priority
- Manual pause edits retain priority

## Implemented – Journey Maintenance Reliability

- Full rebuild runs as a Home Assistant background task
- Central non-queuing maintenance guard
- Duplicate/queued rebuild requests are rejected
- Deterministic filtering of near-identical historical duplicate Trips
- Maintenance-only reconciliation of short historical Trip/charging timestamp overlaps when locations match
- Normal live Journey matching remains unchanged

## Implemented – Vehicle-source Health Monitoring

- Health states: healthy, degraded, grace period, unavailable and unknown
- Connectivity binary sensor
- Translated dashboard/badge status sensor
- Dynamic health-state icons
- 20-minute grace period before declaring a complete source outage
- One Home Assistant Persistent Notification per continuous outage
- Recovery resets the notification state
- Ford Last Charge excluded from live-source outage detection

## Deferred beyond 2.4

The following earlier 2.4 ideas were not required for the final 2.4 release and remain candidates for later Ford Triplog development:

- Route export for third-party applications
- Raw GPS export with timestamps
- GPX / GeoJSON route export
- Optional enriched GPS point metadata such as altitude, accuracy, speed and course
- Further charging metadata presentation improvements

---

# Version 2.5 – Multi-Vehicle Architecture

Status: **Pre-release testing**

Version 2.5 introduces vehicle-aware storage and a shared vehicle context so multiple vehicles can be used inside one Ford Triplog installation without mixing their historical data.

## Implemented – Vehicle-aware SQLite Storage

- Persistent internal `vehicle_id`
- Vehicle-aware Trips and current/last Trip state
- Vehicle-aware charging sessions and current/last Charge state
- Vehicle-aware Journeys and current/last Journey state
- Vehicle-aware Routes
- Vehicle-aware statistics and diagnostics
- Vehicle-aware charging and pause metadata
- Vehicle-aware receipt metadata
- Existing SQLite history is migrated automatically
- A pre-2.5 SQLite backup is created automatically before schema migration

## Implemented – Shared Vehicle Selection

Ford Triplog exposes a shared vehicle-selection entity:

`select.ford_triplog_fahrzeug`

The selected vehicle controls the shared Ford Triplog views and statistics.

Vehicle changes refresh the relevant shared entities so one Dashboard can be used with more than one configured vehicle.

## Implemented – Vehicle-context Reliability

- Shared Dashboard entities follow the selected vehicle
- History reads follow the selected vehicle
- Top Statistics follow the selected vehicle
- Last Trip, Last Journey and Last Route refresh after vehicle changes
- Top Journey stale-value handling fixed during the 2.5 test cycle
- Additional vehicle-context and SQLite-isolation fixes from multi-vehicle testing

## Implemented – Tariff Import Duplicate Protection

Tariff imports no longer treat a changed external source ID by itself as a new tariff period.

Equivalent tariff data can therefore be imported repeatedly without creating duplicate tariff entries solely because the source generated different IDs.

---

# Version 2.6+ – Planned

Potential Ford-focused development areas:

- Route export and route-data portability
- Optional enriched GPS point metadata
- Additional database-backed reporting
- Maintenance tracking
- Further charging and energy reporting improvements
- Further multi-vehicle refinements

---

# Version 3.x – Manufacturer-neutral Research

Longer-term research may separate the Triplog processing core from individual vehicle data sources.

Potential direction:

- Manufacturer-neutral Triplog core
- Vehicle-specific read-only adapters
- Ford adapter based on the current configurable Ford data-source model
- Stable interface between vehicle integrations and Triplog processing
- Shared Trip, charging, Journey, statistics and reporting logic

Ford Triplog remains Ford-focused during the current 2.x development line.

The JAC Home Assistant connector is developed as a separate project and is not part of Ford Triplog. Experience from additional vehicle integrations may later help define a manufacturer-neutral adapter interface.

Additional future development areas include:

- Maintenance tracking
- Long-term history improvements
- Additional database-backed reporting options

---

# Version Overview

| Version | Status | Focus |
| ------- | ------ | ----- |
| 1.5 | Released | Charging locations, Smart Trip, documentation |
| 1.6 | Released | Automation, charging database improvements, dashboards |
| 1.7 | Released | Journey improvements, maintenance, charging integration |
| 1.8 | Released | Charging costs, energy tracking, reporting |
| 1.9 | Released | Pause management, receipts, charging site improvements |
| 2.0.0 | Released | GPS Route Tracker |
| 2.0.1 | Released | Daily History, Journey History, Route History, Charging History |
| 2.0.2 | Released | Top Statistics, Route Tracker improvements, optional OSRM route matching |
| 2.0.3 | Released | Translation cleanup, Top Locations, Top Routes, location resolution and 2.0.x consolidation |
| 2.1 | Released | SQLite storage backend, selectable JSON/SQLite reads, migration validation, SQL-based statistics and runtime optimization |
| 2.2 | Released | CSV exports, maintenance tools, pause receipts, History reliability and continued JSON/SQLite validation |
| 2.3 | Released | SQLite-only storage, direct device-tracker GPS, improved trip-end GPS, dense OSRM matching and Route maintenance |
| 2.4 | Released | Charging reliability, recuperation/monthly statistics, user-defined places, Journey rebuild reliability and vehicle-source health |
| 2.5 | Pre-release | Multi-vehicle architecture, vehicle-aware SQLite storage, shared vehicle selection and tariff-import reliability |
| 2.6+ | Planned | Route portability, enriched GPS metadata, reporting and further Ford-focused improvements |
| 3.x | Research | Manufacturer-neutral Triplog core and vehicle adapters |
