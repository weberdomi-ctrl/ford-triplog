# Changelog

## 2.3.0

### Added

-   SQLite is now the sole productive Ford Triplog storage backend.
-   Added one-time legacy JSON import paths with persistent migration
    markers so already migrated legacy data is not scanned again on every
    Home Assistant restart.
-   Added direct Home Assistant `device_tracker` support as a Route
    Tracker GPS source.
-   Added active-route SQLite snapshots while a trip is running. Dense
    route data is persisted at most once per 60 seconds and is force-saved
    on trip start, Smart Trip pause/resume, shutdown and trip completion.
-   Added Route maintenance actions for rebuilding the latest route,
    raw/failed routes or all stored routes through the configured OSRM
    server.
-   Added OSRM chunked map matching for dense GPS traces that exceed the
    common OSRM limit of 100 trace coordinates per request.
-   Added service metadata for `ford_triplog.rebuild_last_route`.

### Improved

-   Trip-end GPS selection now compares the latest valid point from the
    configured Route Tracker source with the vehicle tracker and uses the
    point with the newest timestamp after the Smart Trip timeout.
-   Home Assistant Companion App high-accuracy `device_tracker` data can
    be recorded directly without going through the slower Geocoded
    Location sensor.
-   OSRM matching now processes long traces in overlapping chunks while
    preserving the original raw GPS points.
-   OSRM requests use `tidy=false` so returned tracepoints stay aligned
    with the submitted GPS points and matching diagnostics remain
    meaningful.
-   The Last Route sensor now follows the latest completed stored route
    and refreshes safely through Home Assistant's event loop.
-   The public **Last Tour** view now represents the latest completed
    individual Trip rather than a complete Journey/day aggregation.
-   Route rebuilds preserve the original raw trace and replace matched
    route geometry only after a successful plausibility check.
-   Source selectors now prevent Ford Triplog's own entities from being
    selected as vehicle or Route Tracker input sources.
-   Charging-session recovery now handles stale/current charging records
    more robustly during startup and can reconcile delayed Ford Last Charge
    data after the session has already been archived.
-   Matching Last Charge data can repair archived charging sessions with
    the exact Ford `plugInTime`, `plugOutTime`, start/end SOC and available
    session energy data.
-   Journey rebuilding and History sensors refresh more reliably after
    completed trips, charging sessions and charging-cost changes.
-   Charging History now refreshes directly when stored charging data is
    updated.
-   Receipt/OCR retry handling and OCR-derived charging-cost metadata were
    improved.
-   Numeric vehicle states are normalized consistently, including
    `unknown` and `unavailable` values.
-   Trip energy calculations now use the configured usable battery
    capacity instead of a fixed battery value.
-   Charging and ignition transition handling now ignores temporary
    `unknown`, `unavailable`, `Unsupported` and missing source states instead
    of interpreting them as real start/stop transitions.
-   Completed charging sessions can be corrected later when delayed Ford
    Last Charge data becomes available after the local session was already
    archived.
-   Electroverse receipt parsing now supports current German and English
    receipt layouts, including provider, charging location, start/end time,
    billed energy, gross session cost and applied credit.
-   Trip and lifetime consumption statistics now use the signed net battery
    energy derived from SOC change so Trips with net recuperation reduce the
    calculated energy balance instead of being clipped to zero.
-   Zero-distance Trips no longer contribute energy to distance-based
    consumption statistics.
-   The usable battery-capacity default is centralized at 77 kWh and is
    written explicitly for new installations; existing configured values
    remain unchanged.
-   English configuration strings were completed to match the German and
    Polish translation coverage.
-   Remaining filesystem work and entity listener handling were aligned
    with current Home Assistant event-loop and lifecycle requirements.
-   Removed remaining normal-runtime dependency on parallel JSON/SQLite
    production storage.

### Fixed

-   Fixed duplicate Trip start/end processing caused by closely spaced
    vehicle state changes.
-   Fixed stale or early route endpoints when the vehicle tracker received
    a newer GPS fix after ignition-off.
-   Fixed OSRM `TooBig` failures for dense Route Tracker traces with more
    than 100 GPS points.
-   Fixed false OSRM rejection caused by `tidy=true` changing the
    tracepoint/input alignment.
-   Fixed thread-unsafe Last Route, Charging History and Top Charging
    refresh scheduling.
-   Fixed OCR handling when a synchronous parser raised an exception.
-   Fixed delayed Last Charge publication not updating the matching
    archived charging session.
-   Fixed Journey loss caused by small timestamp overlaps between the end
    of a charging session and the following Trip by using exact charging
    timestamps where available and a small reconciliation tolerance.
-   Fixed Trip finalization failures when SOC or odometer entities were
    temporarily `unavailable`.
-   Fixed the Build 23039 runtime regression where Last Charge
    reconciliation still referenced the removed `Charge._optional_float()`
    helper. Build 23040 uses the shared numeric normalization helper
    consistently.
-   Fixed repeated legacy migration scans after successful SQLite
    migration.
-   Fixed configuration paths that could allow Ford Triplog output
    entities to be selected as their own input source.
-   Fixed binary-sensor listener cleanup and coordinator-based availability
    handling.
-   Fixed sensor documentation that listed entities not provided by Ford
    Triplog.
-   Fixed temporary Ford Connect outages fragmenting charging sessions or
    producing false charging/ignition transitions.
-   Fixed delayed Last Charge data not correcting an already archived
    charging session after the reconciliation timeout.
-   Fixed Electroverse receipts being matched by a generic MOVE profile or
    returning missing charging location/start/end values.
-   Fixed Electroverse receipt costs so the gross charging-session amount is
    used while applied credit remains separate.
-   Fixed average consumption being overstated because Trips with net SOC
    gain from recuperation were previously stored as 0 kWh instead of
    negative net battery energy.
-   Fixed distance-based consumption statistics being distorted by
    zero-distance Trips carrying energy values.

### Cleanup

-   Removed obsolete `trip_energy.py`; Trip energy uses the configured
    battery capacity directly.
-   Removed the obsolete component-side `build_charging_database.py`; the
    maintained charging-database build workflow remains in `tools/`.
-   Replaced the external `async_timeout` usage with Python's built-in
    `asyncio.timeout()`.

### Vehicle Data Sources

-   Ford Triplog remains entity-based and can use compatible Ford vehicle
    entities supplied by Home Assistant integrations.
-   Ford Connect is the recommended vehicle data source for Ford Triplog
    2.3.
-   FordPass remains usable where available, but it is an unofficial
    integration and was temporarily affected by Ford backend changes in
    late August 2026.

### Storage Notes

-   Existing JSON data remains usable as a migration/import source and
    backup, but it is no longer maintained as a parallel production
    datastore.
-   Receipts remain stored as files and their metadata remains linked
    through Ford Triplog storage.
-   Raw GPS route points remain preserved independently from OSRM-matched
    route geometry.
-   Ford Triplog 2.3.0 final is released as Build 23048.

## 2.2.0

### Added

-   Added CSV export for stored Trips, Journeys and charging sessions.
-   Added direct CSV download through the Home Assistant options flow so
    exported files do not need to be retrieved manually from the Home
    Assistant filesystem.
-   Added configurable vehicle data-source entities in Ford Triplog
    settings, allowing the tracked Ford entities to be changed without
    reinstalling the integration.
-   Added a guarded workflow for deleting clearly invalid charging
    sessions, such as zero-energy or otherwise implausible sessions.
-   Added pause-specific receipt management with direct receipt upload,
    listing, opening and deletion.
-   Added pause receipts to Journey History sensor attributes with signed
    receipt URLs for dashboard access.

### Improved

-   Journey History now includes pause titles, notes, costs and receipt
    data for the selected History date.
-   Pause management keeps the newest pauses first.
-   Pause receipt views now show pause-specific context instead of
    charging-only fields.
-   Multiple receipts can be linked to one pause and displayed together
    in dashboards.
-   Invalid charging-session deletion rebuilds dependent Journey and
    statistics data and refreshes the stored last charging session when
    required.
-   Existing receipt files are preserved when an invalid charging
    session is deleted.
-   Export and deletion dialogs were cleaned up and synchronized across
    German, English and Polish translations.

### Fixed

-   Fixed Journey History date-selection and display issues affecting
    archived Journey data.
-   Fixed thread-unsafe refresh scheduling in the History date selector.
-   Fixed charging-session deletion compatibility with stored Charge
    objects and the SQLite backend.
-   Fixed missing charging-session delete formatting and translation
    handlers in the options flow.
-   Fixed translation placeholder validation for charging-site database
    import.
-   Fixed pause receipt detail navigation and delete-action handling.

## 2.1.1

### Fixed

-   Fixed the shared **History Date** selector not refreshing when new
    Journey or charging history becomes available while Home Assistant
    is running.
-   New History dates now appear without requiring a Home Assistant
    restart or integration reload.

### Improved

-   Pause management now lists the newest pauses first.
-   Updated the Journey History dashboard example to display pause
    titles, notes and costs.

## 2.1.0

### Added

-   Local SQLite storage backend alongside the existing JSON storage.
-   Configurable JSON or SQLite read backend, with JSON remaining the
    default after upgrade.
-   SQLite storage and reads for Trips, charging sessions, Journeys,
    Routes, caches, charging and pause metadata, receipts, user receipt
    parser profiles, charging locations, statistics and diagnostics.
-   SQL-backed support for Top Trip, Top Journey, Top Day, Top Charging,
    Top Departures & Destinations and Top Routes.

### Improved

-   Journey rebuild now loads Trips and charging sessions from the
    selected storage backend.
-   Statistics are recalculated during setup/reload from the selected
    backend.
-   Added incremental startup mirroring and comparison to avoid
    unnecessary SQLite writes.
-   Added runtime guards and locking for SQLite schema initialization
    and metadata migration.
-   Cached user-defined charging locations and reduced repeated
    metadata/database reads.
-   Added bulk Route lookups and reduced redundant Top Statistics and
    Route History database access.
-   Coalesced rapid coordinator update bursts and disabled redundant
    polling for push-driven sensors.
-   Preserved JSON fallback behavior throughout the 2.1 migration.

### Fixed

-   Fixed manual charging-cost editing when additional costs such as
    parking fees are set to `0`.
-   Improved charging-cost recalculation consistency for stored home
    charging sessions.
-   Fixed Journey rebuild returning zero source records in SQLite-only
    mode.
-   Fixed statistics depending on the number of remaining JSON archive
    files.
-   Added automatic statistics refresh after setup/reload.

## 2.0.0

### Added

-   Route Tracker for recording the driven route independently from the
    normal Ford vehicle tracker
-   Support for ABRP latitude/longitude entities as a Route Tracker
    position source
-   Support for Home Assistant Companion App Geocoded Location as a
    Route Tracker position source
-   Persistent route storage linked to the corresponding Trip ID
-   Automatic route recovery after Home Assistant or integration restart
-   Smart Trip pause and resume support for route recording
-   Trip start and end GPS points as authoritative route endpoints
-   Native Last Route sensor with GeoJSON route data
-   Optional local OSRM integration for road-based route matching
-   Configurable OSRM server URL and matching radius
-   Automatic OSRM matching when a route is finalized
-   Raw GPS points are always preserved independently from the matched
    route
-   `ford_triplog.rebuild_last_route` service to rebuild the latest
    route using the configured OSRM server
-   Route matching diagnostics including raw/matched point counts, route
    distance, confidence and unmatched tracepoints

### Improved

-   ABRP latitude and longitude synchronization using debounce handling
-   Protection against mismatched latitude/longitude update timestamps
-   Protection against stale GPS coordinates at trip start and trip end
-   Route recording survives Smart Trip pauses without losing previously
    collected points
-   Active and paused routes are persisted continuously instead of only
    when a trip ends
-   Route storage remains independent from Trip and Journey storage
-   Local-first route processing with no external routing service
    required when using a local OSRM instance

### Notes

-   Route Tracker is optional and does not replace the existing Ford
    Triplog vehicle tracker.
-   OSRM route matching is optional. Raw GPS route recording works
    without OSRM.
-   A local OSRM server is recommended for regular route matching.
-   OSRM preprocessing can require substantial memory for large map
    regions. Building large datasets on a PC/server and running the
    finished dataset on a smaller Docker host is recommended.

## 1.9.2

### Fixed

-   Fixed a race condition that could create duplicate Journey files
    during automatic Journey rebuilds.
-   Reduced the size of the **Last Journey Overview** sensor attributes
    to stay below the Home Assistant Recorder attribute limit and
    prevent recorder warnings.

### Improved

-   Added a helpful note to the receipt viewer explaining a Home
    Assistant browser limitation when opening receipts. If direct
    opening does not work, users can open the receipt via **Open link in
    new tab**.

------------------------------------------------------------------------

## 1.9.1

### Added

-   Manual import of pre-generated OpenStreetMap charging-site
    databases.
-   Official GitHub charging-site database repository for supported
    countries.

### Improved

-   Improved charging-site database management.
-   Extended translations and documentation.
-   Added fallback workflow when automatic OpenStreetMap downloads are
    not possible.

------------------------------------------------------------------------

## 1.9.0

### Added

-   Pause management with editable categories, titles, notes and
    locations.
-   Receipt management for charging sessions and pauses.
-   OCR integration for automatic receipt processing.
-   Receipt parser profiles.
-   Charging receipt management within the charging session workflow.
-   Manual charging cost management with detailed cost breakdown.
-   User-defined charging locations.

### Improved

-   Charging workflow.
-   Options flow.
-   Journey timeline.
-   Charging cost calculation.
-   Local storage and metadata handling.

------------------------------------------------------------------------

## 1.8.0

### Added

-   Complete Journey energy balance.
-   Journey battery statistics.
-   Automatic home charging cost calculation.
-   Seasonal home electricity tariffs.
-   Journey charging cost statistics.
-   Extended Journey dashboard sensors.

### Improved

-   Journey calculations.
-   Energy calculations.
-   Charging statistics.
-   Dashboard support.

------------------------------------------------------------------------

## 1.7.0

### Added

-   Automatic Journey rebuild after completed trips.
-   Journey timeline with local timestamps.
-   Charging and pause locations.
-   Journey maintenance tools.
-   Extended dashboard examples.

### Improved

-   Journey generation.
-   Timeline formatting.
-   GPS location handling.
-   Translation coverage.

### Fixed

-   UTC time display in Journey timeline.
-   Journey rebuild reliability.
-   GPS freshness handling.
-   Various Journey stability improvements.

------------------------------------------------------------------------

## 1.6.0

### Added

-   Journey management.
-   Journey update, rebuild and delete.
-   Journey history and native Journey sensor.
-   OpenStreetMap charging-site database download and import.
-   User-defined charging locations.
-   Intelligent charging-site recognition.
-   Configurable Journey home zone, timeout and maximum gap.
-   Polish translations.

### Improved

-   Trip detection.
-   Charging detection.
-   Multi-trip and multi-charge Journey handling.
-   Configuration flow.
-   Options flow.
-   Translation coverage.
-   Diagnostics and local storage.

### Fixed

-   Multi-day Journey handling.
-   Home detection reliability.
-   Journey rebuild behaviour.
-   Translation validation.
-   Various stability and reliability improvements.
