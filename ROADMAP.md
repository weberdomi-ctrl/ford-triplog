# Ford Triplog Roadmap

This roadmap summarizes completed 2.0.x / 2.1 development and outlines the next planned Ford Triplog releases.

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

# Version 2.3
---

# Version 2.3 – SQLite Primary Storage

Version 2.3 completes the storage migration started in 2.1.

## Planned – SQLite-only Writes

- SQLite becomes the sole productive Ford Triplog storage backend
- New data is written only to SQLite
- Parallel JSON writes are removed
- No user-selectable write backend is planned
- Existing JSON data remains usable as a migration/import source
- Compatibility mirror code is removed or reduced to dedicated migration/import paths
- Runtime complexity from maintaining two synchronized storage formats is reduced

## Data Access and Portability

Ford Triplog will continue to provide standard export functions for common use cases.

Users requiring specialized queries, reporting or additional export formats can access the SQLite database directly with external SQLite tools.

JSON may remain useful as an import/export format, but no longer as a continuously maintained parallel production database.

## Implemented – Runtime and Startup Optimization

- Incremental Trip and Charge compatibility mirror
- Incremental Journey compatibility mirror
- Incremental Route compatibility mirror
- Existing identical records are skipped instead of rewritten
- SQLite-only archive records remain untouched by the JSON compatibility mirror
- Bulk mirror-index reads for Journey and Route comparison
- Combined main-storage mirror snapshot for Trip, Charge and cache comparison
- SQLite schema setup guarded to run only once per Home Assistant runtime
- Parallel database initialization protected by an asynchronous lock
- Metadata and legacy migration checks guarded against repeated execution
- User-defined charging locations cached after initial load
- Bulk Route reads for multiple Trip IDs
- Shared Top Location / Top Route location cache
- Coordinator update bursts coalesced before sensor publication
- Redundant periodic polling disabled for push-driven Ford Triplog sensors

---

# Future Research

Potential future development areas include:

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
| 2.3 | Planned | SQLite-only production storage, end of parallel JSON writes |
| Future | Research | Multi-vehicle support, maintenance tracking, long-term history and additional reporting |
