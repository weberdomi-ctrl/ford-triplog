# Ford Triplog Roadmap

This roadmap summarizes completed development and outlines the next planned Ford Triplog releases.

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

# Version 2.2 – Reliability & Export

Version 2.2 focuses on Trip/Route reliability and practical data export while retaining the 2.1 parallel-storage architecture.

## Planned – Trip End Position Validation

Improve Trip end-position reliability by comparing the Ford-provided end GPS position with the latest Route Tracker position.

Planned behavior:

- Compare the Ford API end position with the last available Route Tracker GPS point
- Detect implausible distance differences or stale Ford position data
- Prefer the latest plausible Route Tracker point as the Trip end position when appropriate
- Support Route Tracker sources such as ABRP and Home Assistant position data
- Preserve the existing Ford position when no better Route Tracker point is available

## Planned – CSV Export

Provide straightforward CSV exports for the main historical data sets:

- Trips
- Charging sessions
- Journeys
- Routes

Exports should use useful, flattened columns rather than exposing internal JSON payloads directly.

Typical exported information includes timestamps, distances, durations, SOC values, energy data, consumption, charging provider/location, charging costs and related record IDs.

Route export should keep route metadata practical for tabular use. Detailed GPS track data may be handled separately where appropriate.

The export feature is intended to cover common user requirements. Advanced or custom analysis can be performed directly against the local SQLite database with external SQLite tools.

## Storage Policy for 2.2

- JSON and SQLite continue to be written in parallel
- The selectable read backend remains available
- SQLite continues to receive real-world validation
- No write-backend selector is planned
- Storage architecture remains compatible with 2.1 throughout this release

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
| 2.2 | Planned | Trip/Route reliability, CSV exports, continued JSON/SQLite validation |
| 2.3 | Planned | SQLite-only production storage, end of parallel JSON writes |
| Future | Research | Multi-vehicle support, maintenance tracking, long-term history and additional reporting |
