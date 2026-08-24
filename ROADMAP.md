# Ford Triplog Roadmap

This roadmap summarizes completed 2.0.x / 2.1 / 2.2 development, the current 2.3 test release and the next planned Ford Triplog releases.

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

Status: **In testing**

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

# Version 2.4 – Route Data Portability & GPS Enrichment

Version 2.4 is planned to make recorded routes more useful outside Home
Assistant and to retain additional GPS information when a source can
provide it.

## Planned – Route Export for Third-party Applications

Export stored route data through the Home Assistant options flow.

Candidate exports:

- Raw GPS points as CSV
- Raw GPS tracks as GPX
- Raw or OSRM-matched geometry as GeoJSON
- Direct Home Assistant download
- Export of the latest route, selected routes or a date range

Raw and OSRM-matched data should remain clearly separated so external
tools can choose between the original trace and the road-matched
geometry.

## Planned – Enriched GPS Point Storage

When the selected Route Tracker source provides additional attributes,
Ford Triplog may store optional metadata together with each raw GPS
point.

Candidate fields:

- altitude
- GPS accuracy
- speed
- course / bearing

Latitude, longitude and timestamp remain the required common route
fields.

Sources that do not expose the additional metadata remain fully
compatible. Existing stored routes must continue to load without a data
migration that requires those optional values.

Possible later uses include:

- elevation profiles
- route-quality diagnostics
- speed profiles
- more detailed third-party exports

## Planned – Charging Metadata Enrichment

When FordPass/Ford Connect last-charge data exposes additional
attributes, Ford Triplog may automatically generate a compact optional
memo without changing the structured charging-session fields.

Example information can include:

- charger type
- start/end SOC
- SOC delta
- average charging power
- distance added
- configured charge target

Only attributes that are actually available from the configured source
should be included.

---

# Version 3.x – Manufacturer-neutral Research

Longer-term research may separate the Triplog core from individual
vehicle integrations.

Potential direction:

- Manufacturer-neutral Triplog core
- Vehicle-specific read-only adapters
- Ford adapter based on the current Ford data-source model
- Research into additional vehicle backends where stable read-only data
  access is technically feasible
- Continued investigation of a possible JAC adapter/API source

Additional future development areas include:

- Multi-vehicle support and improvements
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
| 2.3 | In testing | SQLite-only storage, direct device-tracker GPS, improved trip-end GPS, dense OSRM matching and Route maintenance |
| 2.4 | Planned | Route export, enriched GPS point metadata and charging metadata enrichment |
| 3.x | Research | Manufacturer-neutral Triplog core and vehicle adapters |
