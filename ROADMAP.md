# Ford Triplog Roadmap

This roadmap describes planned development after the current Ford Triplog 2.0.x releases.

---

# Version 2.0.x

## Trip History

Extend the existing date-based History views with direct access to individual historical trips.

Planned features:

- Browse previous trips
- Select trips by date or time period
- Display individual trip details
- Display recorded routes when Route Tracker data is available
- Efficient access to historical data without exposing large histories through sensor attributes

The existing Journey History, Route History and Charging History views remain available independently.

---

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

## Transition Policy

SQLite is available as an explicit read option in 2.1, but JSON remains the default for upgraded installations.

This allows the SQLite backend to be tested under normal use without silently changing storage behavior for existing users.

A later release can make SQLite the default once the migration path has been proven across a wider range of installations.

---

# Future Research

Potential future development areas include:

- Multi-vehicle support and improvements
- Data export options
- Maintenance tracking
- Long-term history improvements
- Additional database-backed reporting and export options

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
| 2.1 | In development | SQLite storage backend, selectable JSON/SQLite reads, migration validation and SQL-based statistics |
| Future | Research | Multi-vehicle support, exports, maintenance tracking, long-term history |
