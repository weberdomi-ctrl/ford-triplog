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

Version 2.1 is planned as a larger storage architecture change.

The migration will be introduced gradually so the new SQLite backend can be compared directly with the existing JSON storage before it becomes the primary storage system.

## Phase 1 – 1:1 Database Mirror

- Introduce a local SQLite database
- Keep the existing JSON storage fully operational
- Create a corresponding database table for each existing JSON data type
- Preserve the current data structure as closely as possible
- Write new and changed data to JSON and SQLite in parallel
- Keep JSON as the production read source during the first migration phase
- Preserve existing IDs and relationships so JSON and database records can be compared directly
- Avoid premature schema normalization during the initial migration

The initial goal is simple:

**JSON record = database record**

## Phase 2 – Validation and Selectable Read Backend

- Continue parallel JSON and SQLite writes
- Add a selectable JSON or database read path for development and testing
- Compare stored records and calculated results between both backends
- Verify Trips, Charges, Journeys, Routes, pauses and related stored data
- Keep existing installations compatible throughout the transition

SQLite will not become the default until both storage paths produce equivalent results.

## Phase 3 – SQL Queries and Views

After the database mirror is proven reliable:

- Move suitable historical lookups and aggregations to SQL queries
- Introduce fixed database views for frequently used statistics where useful
- Use SQL for efficient filtering, grouping and aggregation
- Keep application-specific logic such as Home Assistant zone resolution and GPS clustering in Python
- Store resolved values needed for efficient database statistics

Potential views include:

- Trip statistics
- Journey statistics
- Charging statistics
- Top locations
- Top routes

## Phase 4 – Database as Primary Storage

After successful validation:

- Make SQLite the primary storage backend
- Retain JSON initially as a compatibility fallback and import/export format
- Provide a controlled migration path for existing JSON histories
- Evaluate making JSON storage optional only after the database backend is proven stable

The goal is not only database acceleration, but a maintainable storage layer that enables efficient long-term history and statistics without exposing large datasets through Home Assistant sensor attributes.

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
| 2.0.3 | In development | Translation cleanup, Top Locations, Top Routes, location resolution and 2.0.x consolidation |
| 2.1 | Planned | SQLite storage migration with parallel JSON/DB operation and SQL-based statistics |
| Future | Research | Multi-vehicle support, exports, maintenance tracking, long-term history |
