# Ford Triplog 2.3.0

**Final release: Build 23048**

Ford Triplog 2.3 completes the SQLite storage migration and significantly
improves route recording, Journey reliability, charging-session recovery
and compatibility with current Home Assistant requirements.

The release keeps the local-first design: Trip, Journey, charging, route,
metadata and statistics data is stored locally in Home Assistant. Raw GPS
points remain preserved independently from OSRM-matched geometry, and OSRM
remains completely optional.

## 🗃️ SQLite-only production storage

SQLite is now the sole productive Ford Triplog storage backend.

Changes include:

-   new and changed Ford Triplog records are written to SQLite
-   parallel JSON production writes are removed
-   legacy JSON data remains available as a one-time migration/import source
-   persistent migration markers prevent completed imports from being
    scanned repeatedly after every Home Assistant restart
-   Trips, charging sessions, Journeys, Routes, caches, metadata and
    statistics are read from the local Ford Triplog database
-   receipt files remain on the Home Assistant filesystem and stay linked
    through stored receipt metadata

This completes the controlled JSON/SQLite migration that started in Ford
Triplog 2.1.

## 🚗 Vehicle data sources

Ford Triplog uses configurable Home Assistant entities as its vehicle data
sources.

For Ford Triplog 2.3, **Ford Connect is the recommended vehicle data
source**. Compatible FordPass entities can still be used where available.

FordPass is a community-maintained unofficial integration and was
temporarily affected by Ford backend changes in late August 2026. Ford
Triplog therefore does not assume that FordPass is the only possible Ford
vehicle source.

Source selectors also prevent Ford Triplog's own output entities from being
selected as inputs, avoiding accidental feedback configurations.

## 🛰️ Direct Home Assistant device tracker GPS

The Route Tracker can use a Home Assistant `device_tracker` entity directly
as a GPS source. This is especially useful with the Home Assistant Companion
App in high-accuracy location mode.

Supported Route Tracker source types include:

-   ABRP latitude/longitude entities
-   Home Assistant Companion App Geocoded Location
-   Home Assistant `device_tracker` GPS

The Route Tracker remains optional and independent from the Ford vehicle
tracker used for Trip detection and vehicle state.

## 💾 Active-route persistence

Dense high-accuracy traces are kept in memory for efficient recording and
are also protected by SQLite snapshots while a Trip is active.

-   active-route snapshots are written at most once per 60 seconds
-   a forced write occurs on Trip start
-   a forced write occurs on Smart Trip pause/resume
-   a forced write occurs during Home Assistant shutdown
-   the completed route is persisted when the Trip is finalized

This limits route loss after an unexpected Home Assistant interruption while
avoiding a database write for every individual GPS update.

## 📍 Improved Trip-end GPS selection

Route completion now compares the newest valid position from:

-   the configured Route Tracker source
-   the configured vehicle tracker

The freshest valid point is used as the authoritative endpoint. This
improves cases where the vehicle position is updated after ignition-off or
the phone tracker reaches the actual stopping point first.

A large difference between both sources is retained as a diagnostic warning
rather than automatically discarding the newer point.

## 🗺️ Dense OSRM route matching

High-accuracy tracking can produce hundreds or thousands of GPS points per
Trip. Ford Triplog 2.3 supports these traces by splitting them into
overlapping OSRM map-matching chunks below the common 100-coordinate request
limit.

-   chunks overlap to preserve continuous road geometry
-   each block is matched independently
-   successful geometries are merged into one route
-   the full original raw GPS trace is always preserved
-   OSRM requests use `tidy=false` so tracepoint diagnostics remain aligned
    with submitted GPS points

This fixes the previous HTTP 400 / `TooBig` failure for dense traces.

## 🧹 Route maintenance

Stored raw routes can be processed again through the currently configured
OSRM server. Available maintenance modes include:

-   rebuild the latest route
-   rebuild raw/failed routes
-   rebuild all stored routes

Raw GPS points are never removed by this workflow. Existing matched geometry
is replaced only after the new OSRM result passes the route plausibility
checks.

## 🧭 Last Tour and Last Route

The **Last Tour** view now represents the latest completed individual Trip
rather than duplicating a Journey/day aggregation.

The **Last Route** sensor follows the latest completed stored route and
refreshes safely through Home Assistant's event loop. Route attributes keep
raw-point information, geometry source, OSRM diagnostics and GeoJSON route
geometry.

The route entity's latitude/longitude values remain a map reference/centering
point; the actual driven line is provided by the GeoJSON geometry.

## ⚡ Charging-session recovery and Last Charge reconciliation

Charging recovery was strengthened for cases where Ford publishes final
charging information later than the local charging-state transition.

Ford Triplog 2.3 can:

-   recover stale/current charging sessions during startup
-   reconcile a delayed Last Charge dataset with an already archived session
-   repair matching archived sessions with exact Ford `plugInTime` and
    `plugOutTime` values
-   update start/end SOC and available session-energy values from the final
    Ford dataset
-   refresh dependent charging and Journey views after successful updates

This also fixes a Journey edge case where a locally recorded charging end
and the following Trip could overlap by only a few seconds. Exact Ford
timestamps are used where available and a small reconciliation tolerance is
applied when building the Journey timeline.

## 🔄 History and Journey refresh reliability

Several refresh paths were tightened so data appears without requiring a Home
Assistant restart or manual integration reload.

Improvements include:

-   Journey History refresh after stored Journey changes
-   Charging History refresh directly after charging data updates
-   automatic Journey rebuilding after relevant Trip/Charge changes
-   thread-safe Home Assistant update scheduling
-   thread-safe Top Charging refreshes

## 🧾 Receipt and OCR reliability

Receipt handling received additional runtime fixes:

-   synchronous OCR/parser exceptions are handled correctly
-   retry handling in the receipt workflow is more robust
-   OCR-derived charging-cost values can be identified with the appropriate
    cost source
-   translation placeholders used by the OCR workflow were corrected

## 🛡️ Home Assistant review fixes

Ford Triplog 2.3 also incorporates fixes identified during Home Assistant
review:

-   replaced external `async_timeout` usage with Python's built-in
    `asyncio.timeout()`
-   completed missing English configuration translations
-   normalized numeric entity values consistently, including `unknown` and
    `unavailable`
-   Trip energy calculations now use the configured usable battery capacity
    instead of a fixed 77 kWh value
-   remaining directory creation was moved away from the Home Assistant event
    loop
-   binary-sensor listener cleanup now follows the Home Assistant entity
    lifecycle and availability follows the coordinator
-   added missing UI metadata for `ford_triplog.rebuild_last_route`
-   removed documentation for entities that Ford Triplog does not provide
-   removed obsolete `trip_energy.py`
-   removed obsolete component-side `build_charging_database.py`; the
    maintained build utility remains under `tools/`

## 🐛 Final pre-release fixes through Build 23048

The final 2.3 testing cycle added several fixes discovered under real-world
Ford Connect, charging and receipt workflows.

-   Build 23040 fixed the Last Charge startup regression caused by remaining
    references to the removed `Charge._optional_float()` helper.
-   Temporary charging/ignition source states such as `unknown`,
    `unavailable`, `Unsupported` or missing values are ignored for transition
    handling so short Ford Connect outages do not fragment Trips or charging
    sessions.
-   Delayed Ford Last Charge data can correct the matching archived charging
    session even when it becomes available only after the normal completion
    reconciliation timeout.
-   Current German and English Electroverse receipts are parsed with a
    dedicated profile, including charging location, timestamps, billed energy
    and gross charging-session cost. Applied credit is retained separately
    from the actual charging cost.
-   Net recuperation is now included in Trip and lifetime energy statistics.
    A Trip whose SOC increases produces negative net battery energy instead of
    being clipped to 0 kWh, preventing systematic overstatement of average
    consumption.
-   Zero-distance Trips are excluded from distance-based energy/consumption
    statistics.
-   The default usable battery capacity is centralized at 77 kWh and written
    explicitly for new installations. Existing configured capacities are
    preserved.

The final release build is **23048**.


## 🧪 Real-world testing

The 2.3 pre-release has been exercised with extended real-world driving,
including:

-   long-distance driving days
-   multiple Alpine mountain-pass routes
-   multiple Trips within the same Journey
-   intermediate DC charging sessions
-   high-accuracy phone GPS traces containing thousands of points
-   chunked OSRM matching
-   Home Assistant restarts with existing SQLite data

The final Build 23048 completed everyday and real-world regression testing
before release.

## ⬆️ Upgrade notes

Ford Triplog 2.3 is designed to upgrade existing 2.1/2.2 installations
without manual database conversion.

Existing legacy JSON data remains available as a migration/import source, but
after migration normal Ford Triplog production storage is SQLite-only.

Existing raw GPS routes remain compatible and can be rebuilt later through
the Route maintenance workflow.

OSRM remains optional. Route recording continues to work without an OSRM
server.

Trip energy is calculated from SOC change and the configured **usable battery
capacity**. New installations default to 77 kWh. Existing installations keep
their configured value, so users upgrading from earlier versions should verify
that the stored capacity matches their vehicle if calculated kWh/100 km values
look implausible.

------------------------------------------------------------------------

------------------------------------------------------------------------

# Ford Triplog 2.2.0

Ford Triplog 2.2 focuses on practical data export, safer maintenance
tools and a more complete History workflow while retaining the parallel
JSON/SQLite storage architecture introduced in 2.1.

## 📤 CSV Export

Ford Triplog can now export the main stored history data directly from
the Home Assistant options flow.

Available exports include:

-   Trips
-   Journeys
-   Charging sessions

Each export supports an optional date range. If no date range is
selected, all available records are exported.

The generated CSV file can be downloaded directly through Home Assistant,
so users do not need to access the Home Assistant VM, container or
filesystem manually.

## 🚗 Configurable Vehicle Data Sources

Ford Triplog settings now allow the configured vehicle data-source
entities to be changed after initial setup.

This makes it possible to switch the Ford entities used by Ford Triplog
without reinstalling the integration or recreating the stored history.

## 🗑️ Invalid Charging Session Cleanup

A new guarded maintenance workflow can remove clearly invalid charging
sessions from the stored history.

Only suspicious sessions are offered for deletion, for example sessions
with zero vehicle energy or other strongly implausible data.

Before deletion, Ford Triplog shows the session details and requires
explicit confirmation.

After deletion:

-   dependent Journeys are rebuilt
-   statistics are recalculated
-   the stored last charging session is refreshed when required
-   existing receipt files are preserved

This avoids silently deleting documents while still allowing corrupted
or aborted charging records to be removed cleanly.

## ⏸️ Pause Receipt Management

Receipts can now be managed directly from a selected Journey pause.

Pause receipt features include:

-   direct PDF or image upload
-   multiple receipts per pause
-   optional receipt note
-   pause-specific receipt overview
-   open stored receipt
-   delete receipt with confirmation

OCR is intentionally not required for pause receipts. The receipt is
stored and linked directly to the selected pause.

## 🧾 Pause Receipts in History

Journey History now exposes pause receipts for the currently selected
History date.

Each pause receipt entry includes useful dashboard context such as:

-   pause title/category
-   start time
-   duration
-   location
-   pause costs
-   receipt filename/note
-   authenticated signed receipt URL

This allows dedicated Home Assistant dashboard cards for pause receipts,
similar to the existing charging-receipt History card.

Multiple receipts belonging to the same pause can be displayed together
without repeating the pause itself.

## 🕓 History Improvements

Ford Triplog 2.2 includes additional History reliability and display
improvements.

Changes include:

-   fixed Journey History date-selection/display issues
-   newest pauses are shown first
-   pause titles, notes and costs are available in Journey History
-   pause receipt data is synchronized with the selected History date
-   History selector refresh scheduling is safe with current Home
    Assistant thread-safety requirements

## 🌍 Translation and Options Flow Cleanup

The new export, maintenance and pause-receipt workflows are synchronized
across:

-   English fallback strings
-   English translation
-   German translation
-   Polish translation

Several dialog formatting, line-break and placeholder-validation issues
found during 2.2 testing were also corrected.

## ⚙️ Fixes and Reliability Improvements

-   Fixed thread-unsafe History selector refresh scheduling
-   Fixed Journey History date-selection/display issues
-   Fixed suspicious charging-session detection with stored Charge
    objects
-   Added complete SQLite deletion support for charging sessions
-   Fixed missing delete-dialog helpers and translation handlers
-   Fixed pause receipt detail navigation
-   Fixed pause receipt deletion flow
-   Fixed translation placeholder validation for charging-site database
    import
-   Preserved receipt files when invalid charging sessions are removed

## 🗃️ Storage Policy

Ford Triplog 2.2 continues the controlled storage transition introduced
in 2.1.

-   JSON and SQLite continue to be written in parallel
-   the selectable JSON/SQLite read backend remains available
-   JSON remains the compatibility and fallback path
-   no write-backend selector is introduced
-   the final SQLite-only production cutover remains planned for 2.3

## ⬆️ Upgrade Notes

Ford Triplog 2.2.0 is compatible with existing Ford Triplog 2.1.x
installations.

No manual storage migration is required.

Existing Trips, charging sessions, Journeys, Routes, receipts and
metadata remain compatible.

------------------------------------------------------------------------

# Ford Triplog 2.1.1

Ford Triplog 2.1.1 is a maintenance and bugfix release for the 2.1
storage release.

## 🐛 Fixes

-   Fixed the shared **History Date** selector not refreshing when new
    Journey or charging history becomes available while Home Assistant
    is running
-   New History dates now appear without requiring a Home Assistant
    restart or integration reload

## 🔧 Improvements

-   Pause management now lists the newest pauses first
-   Updated the Journey History dashboard example to display pause
    titles, notes and costs

## ⬆️ Upgrade Notes

Ford Triplog 2.1.1 is compatible with existing Ford Triplog 2.1
installations.

No storage migration or configuration change is required.

------------------------------------------------------------------------

# Ford Triplog 2.1.0

Ford Triplog 2.1 introduces a local SQLite storage backend and completes
the first major storage architecture migration of the project.

The existing JSON storage remains available during the transition.
Existing installations are not forced to change their read backend after
the update.

## 🗃️ SQLite Storage Backend

Ford Triplog now maintains a local SQLite database alongside the
existing JSON storage.

The new backend covers the main persistent Ford Triplog data, including:

-   Trips
-   Charging sessions
-   Journeys
-   Current and last Trip/Charge/Journey caches
-   GPS routes
-   User-defined charging locations
-   Pending charging locations
-   Charging metadata
-   Pause metadata
-   Charging receipts and OCR/parser state
-   User-created receipt parser profiles
-   Statistics and diagnostics

Existing IDs and stored data structures are preserved as closely as
possible so JSON and SQLite records remain comparable during the
migration period.

## 🔄 Parallel Storage and Safe Upgrade Path

Ford Triplog continues writing compatible data to JSON and SQLite during
the 2.1 transition.

Important upgrade behavior:

-   **JSON remains the default read backend after upgrading**
-   Existing users are not switched automatically to SQLite
-   SQLite can be enabled explicitly in Ford Triplog settings
-   Changing the backend reloads the integration
-   JSON remains available as a fallback while SQLite continues to be
    tested in normal use

This provides a controlled migration path without changing the storage
behavior of existing installations unexpectedly.

## ⚡ SQLite Read Mode

When SQLite is selected as the read backend, Ford Triplog reads
supported historical and configuration data directly from the local
database.

This includes:

-   Trip and charging history
-   Journey history
-   Route history
-   Charging and pause metadata
-   Receipts
-   User receipt parser profiles
-   User-defined charging locations
-   Statistics source data
-   Journey rebuild source data

SQLite-only testing no longer depends on archived Trip or Charge JSON
files for Journey rebuild or statistics calculation.

## 📊 SQL-backed Statistics

Frequently used Top Statistics can now use SQLite queries and database
views.

Database support includes:

-   Top Trip
-   Top Journey
-   Top Day
-   Top Charging
-   Top Departures & Destinations
-   Top Routes

Location-specific Home Assistant logic such as zones, charging-site
matching and GPS clustering remains in Python where appropriate.

## 🔧 Journey Rebuild

Journey maintenance has been made backend-independent.

Journey rebuild and update operations now load Trips and charging
sessions from the currently selected storage backend instead of
depending on archived JSON file paths.

This allows complete Journey rebuilding in SQLite read mode even when
archived JSON files are unavailable.

## 📈 Statistics Recalculation

Statistics are derived data and are now recalculated during integration
setup/reload from the currently selected read backend.

This prevents statistics from the previously selected backend remaining
active after switching between JSON and SQLite.

## 🧾 Receipt and Parser Storage

Receipt-related persistent metadata has been moved into dedicated SQLite
tables.

This includes:

-   Receipt metadata and OCR/parser results
-   Charging metadata
-   Pause metadata
-   User-created receipt parser profiles

Bundled parser profiles remain part of the Ford Triplog program files
and are not moved into the user database.

Existing user parser profiles are migrated into SQLite. New user parser
profiles are stored there when SQLite mode is active.

## 🛰️ Route Storage

GPS Route Tracker data is available from SQLite while preserving the
existing raw and matched route structure.

The route history and last-route reads can therefore operate without
requiring the archived JSON route files in SQLite mode.

## ⚙️ Improvements and Fixes

-   Added backend-neutral archive reads for Trips and charging sessions
-   Added incremental startup mirroring for Trips, Charges, Journeys and
    Routes
-   Unchanged JSON records are skipped instead of being written to
    SQLite again on every restart
-   SQLite-only archive records are preserved during compatibility
    mirroring
-   Added bulk mirror-index reads for Journey and Route startup
    comparison
-   Added a compact main-storage mirror snapshot to avoid repeated
    per-record SQLite lookups
-   Added a Home Assistant runtime guard for SQLite schema
    initialization
-   Added a shared initialization lock to prevent parallel duplicate
    schema setup
-   Reduced repeated metadata, charging-site and migration reads through
    runtime caching/guards
-   Cached user-defined charging locations after initial load instead of
    re-reading them for every location lookup
-   Added bulk Route lookups for multiple Trip IDs
-   Reduced redundant Top Statistics and Route History database access
-   Coalesced rapid coordinator update bursts before publishing sensor
    updates
-   Disabled redundant Home Assistant polling for push-driven Ford
    Triplog sensors
-   Fixed manual charging-cost editing when setting additional costs
    such as parking fees to `0`
-   Improved charging-cost recalculation consistency for stored home
    charging sessions
-   Fixed Journey rebuild returning zero source records in SQLite-only
    mode
-   Fixed statistics depending on the number of remaining JSON archive
    files
-   Added automatic statistics refresh after setup/reload
-   Added SQLite storage for user receipt parser profiles
-   Added SQLite storage for receipts, charging metadata and pause
    metadata
-   Added SQLite reads for user-defined charging locations
-   Added SQLite Journey and Route archive support
-   Reduced remaining hidden JSON-only read paths
-   Preserved JSON fallback behavior throughout the migration

## 🚀 Storage and Runtime Efficiency

The 2.1 storage migration also includes a number of startup and runtime
optimizations discovered during SQLite testing:

-   SQLite schema creation is performed only once per Home Assistant
    runtime
-   Journey and Route compatibility mirrors compare existing records
    before writing
-   Main Trip/Charge/cache mirroring skips unchanged records
-   Metadata migration checks run once per runtime
-   User-defined charging locations are cached after loading
-   Top Location and Top Route processing share cached location
    resolution data
-   Rapid FordPass entity-update bursts are published as a single
    coordinator update
-   Ford Triplog sensors use push updates instead of additional periodic
    Home Assistant polling

These changes substantially reduce unnecessary SQLite reads, writes and
repeated sensor recalculations during normal operation.

## ⬆️ Upgrade Notes

Ford Triplog 2.1 is designed to upgrade existing 2.0.x installations
without requiring an immediate storage-backend change.

After upgrading:

1.  Ford Triplog continues to use **JSON** as the read backend by
    default.
2.  Existing data is mirrored/migrated into the local SQLite database.
3.  Users who want to test or use the SQLite read performance can select
    **SQLite** in Ford Triplog settings.
4.  The integration reloads and recalculates statistics from the
    selected backend.
5.  JSON remains available as a fallback during the 2.1 transition.

The SQLite database is local to Home Assistant. No external database
server is required.

------------------------------------------------------------------------

# Ford Triplog 2.0.3

Ford Triplog 2.0.3 extends the Top Statistics introduced in 2.0.2,
improves location resolution and completes further translation and
storage-related cleanup.

## 📍 Top Departures & Destinations

A new **Top Departures & Destinations** sensor summarizes the most
frequently used trip start and destination locations.

Features include:

-   Top 5 departure locations
-   Top 5 destination locations
-   Trip count per location
-   Total distance associated with each location
-   GPS-based grouping to avoid duplicate entries caused by slightly
    different coordinates or address labels
-   Home Assistant zones are used as meaningful location names when
    available

## 🛣️ Top Routes

A new **Top Routes** sensor identifies the most frequently driven
directed routes.

Features include:

-   Top 5 routes by trip count
-   Direction-aware grouping, so A → B and B → A remain separate routes
-   Average distance per route
-   Average consumption where suitable trip data is available
-   Same-location routes are excluded from the ranking
-   Consumption averages only include individual trips of at least 10 km
    to avoid misleading short-trip values

## 🗺️ Improved Location Resolution

Top location statistics now use a common location resolution chain to
provide more meaningful and stable names.

Locations are resolved in the following order:

1.  Home Assistant zone
2.  User-defined Ford Triplog charging location
3.  Known OSM charging location
4.  50 m GPS cluster
5.  Stored address fallback

This allows locations such as Work, garages, shops and charging sites to
be grouped by their meaningful configured names instead of varying
street addresses.

The Home zone is stored as the stable language-neutral value `Home`.
Other Home Assistant zones use their user-defined zone names.

## ⚡ Charging Location Lookup

Known charging locations are now also available to Top Departures &
Destinations and Top Routes.

-   User-defined charging locations take priority over OSM charging
    locations
-   Custom charging-site radii are respected
-   Existing OSM charging-site lookup and configured lookup radius are
    reused
-   Charging-site location names can therefore be used even when no Home
    Assistant zone exists at that location

## 🌍 Translation and Naming Cleanup

Translation handling has been further standardized.

Improvements include:

-   English is used as the fallback language for untranslated entity
    names
-   German, English and Polish entity translations synchronized
-   New Top Departures & Destinations and Top Routes entity names
    translated
-   Language-specific labels removed from raw sensor attributes where
    possible
-   `Home` remains stable in raw attributes and can be localized by the
    dashboard
-   Entity names and stored/raw data are kept separate so changing the
    Home Assistant language does not alter underlying statistics data

## 🗃️ Recorder and Route History Cleanup

Large route attributes have been reduced to avoid Home Assistant
Recorder warnings caused by attributes exceeding the 16,384-byte storage
limit.

-   Route History no longer produces oversized Recorder attribute
    warnings
-   Route data remains available through Ford Triplog's persistent route
    storage
-   Existing stored Trip, Journey, Charge and Route data remains
    compatible

## 📊 Dashboard Examples

New Markdown dashboard examples are available for:

-   Top Departures & Destinations
-   Top Routes

The examples use the new sensor attributes directly and can localize the
stable `Home` value for display.

## ⚙️ Improvements and Fixes

-   Improved grouping of frequently visited locations
-   Added Home Assistant zone-aware location resolution
-   Added user-defined and OSM charging-site location resolution to trip
    statistics
-   Improved handling of varying geocoded addresses for the same
    physical location
-   Fixed missing regular-expression import used by location label
    scoring
-   Reduced misleading consumption statistics for very short routes
-   Removed same-location routes from Top Routes
-   Further standardized sensor names, translation keys and English
    fallbacks
-   Reduced Recorder warnings from large Route History attributes

## ⬆️ Upgrade Notes

Ford Triplog 2.0.3 is compatible with existing Ford Triplog 2.0.x stored
data.

No database or storage migration is required.

Existing Home Assistant zones and user-defined Ford Triplog charging
locations are used automatically by the new location statistics. Users
can adjust Home Assistant zone sizes where larger sites should be
treated as one location.

------------------------------------------------------------------------

# Ford Triplog 2.0.2

Ford Triplog 2.0.2 expands statistics, improves Route Tracker
reliability and road matching, and completes a number of dashboard and
translation refinements.

## 📊 Top Statistics

New native Top Statistics sensors provide quick access to notable
driving and charging records.

New statistics include:

-   **Top Trip** with distance, duration, energy use and consumption
-   **Top Journey** with Journey-level driving and energy information
-   **Top Day** aggregating all Journeys and trips of the same local
    calendar day
-   **Top Charging** with leading charging providers and locations
-   Largest charging session
-   Session count and remaining unknown-provider statistics
-   Charging costs and average price per kWh

Top Charging now refreshes automatically after stored charging data or
charging costs are changed. A Home Assistant or integration reload is no
longer required for updated cost statistics.

## 🛰️ Route Tracker Improvements

Route tracking introduced in Ford Triplog 2.0 has been refined for more
reliable everyday recording.

Improvements include:

-   Improved Route Tracker persistence and recovery
-   Better handling of trip start and end route points
-   Improved ABRP-based route recording
-   More reliable route completion and Trip ID association
-   Raw GPS route data remains preserved independently from matched
    route data

## 🗺️ OSRM Route Matching

Optional local OSRM map matching is now supported for recorded routes.

Features include:

-   Configurable local OSRM server
-   Configurable matching radius
-   Automatic road matching after trip completion
-   Raw and matched route data stored separately
-   Matching diagnostics
-   Manual rebuild of the latest route
-   DACH example configuration for Germany, Austria and Switzerland

OSRM remains completely optional. Without OSRM, Ford Triplog continues
to record and display the raw GPS route.

## 📅 Top Day

The new **Top Day** sensor aggregates driving activity by the Home
Assistant local calendar date.

It includes:

-   Total daily distance
-   Total and driving duration
-   Journey and trip counts
-   Charging information
-   Energy used and charged
-   Average consumption
-   Charging costs
-   Start and end locations
-   Associated Journey, Trip, Charge and Route IDs

This makes it possible to identify the longest recorded driving day even
when it consists of multiple Journeys.

## ⚡ Charging Statistics Improvements

Charging statistics now make better use of resolved charging locations
and providers.

Improvements include:

-   Home charging grouped as Home
-   Provider and location aggregation
-   User-defined charging locations included in statistics
-   Improved matching of charging locations
-   Unknown-provider sessions exposed separately
-   Immediate Top Charging recalculation after manual cost or stored
    charge changes

## 🌍 Translations and Entity Names

Entity naming and translations have been cleaned up and synchronized.

Improvements include:

-   German, English and Polish translation updates
-   Translatable **Charging History**
-   Translatable **Journey History**
-   Translatable **Route History**
-   Translatable shared **History Date** selector
-   Translatable **Trip Active**
-   Translation support for the new Top Statistics sensors
-   Removal of the redundant unavailable FordPass last-charge energy
    sensor

## ⚙️ Improvements and Fixes

-   Fixed Journey History aggregation when multiple separate Journeys
    exist on the same calendar date
    -   Distance, durations, energy, SoC and charging costs are now
        aggregated across all Journeys
    -   Journey timelines are merged chronologically instead of showing
        only the last Journey
    -   Average consumption and average charging price are recalculated
        from the aggregated totals
    -   Start SoC is taken from the first available Journey value and
        end SoC from the last available value
-   Improved Top Charging aggregation
-   Charging provider and location corrections are reflected in
    statistics
-   Manual charging cost changes can update Top Charging without
    reloading the integration
-   Reduced redundant sensor exposure
-   Existing Trip, Journey, Charge and Route storage remains compatible

## ⬆️ Upgrade Notes

Ford Triplog 2.0.2 is compatible with existing Ford Triplog 2.0.x stored
data.

No external database or storage migration is required.

OSRM is optional and only needs to be configured when local road
matching is desired.

------------------------------------------------------------------------

# Ford Triplog 2.0.1

Ford Triplog 2.0.1 extends the Route Tracker introduced in 2.0.0 with a
complete date-based History view for routes, Journeys, charging sessions
and charging receipts.

## 🕓 History

A shared History date selection is now available for reviewing stored
Ford Triplog data by day.

New capabilities include:

-   Shared History date selection
-   Daily Journey history
-   Daily route history
-   Daily charging history
-   Charging-only days are available in History
-   History sensors update together when the selected date changes

## 🗺️ Route History

Stored Route Tracker data can now be viewed for previously recorded
days.

Features include:

-   Native **Route History** sensor
-   Historical route loading from persistent route storage
-   Routes grouped by local Home Assistant calendar date
-   GeoJSON output for historical map visualization
-   Multiple routes from the selected day can be displayed together
-   Active and paused recovery routes are excluded from historical views
-   Existing Ford Triplog 2.0.0 route files remain compatible

## 🛣️ Journey History

The selected day can now be displayed as a complete Journey overview.

History data includes:

-   Journey summary
-   Distance and duration
-   Driving, pause and charging time
-   Energy consumption
-   Charged energy
-   Journey energy balance
-   Charging costs
-   Battery and SOC information
-   Complete Journey timeline with trips, pauses and charging sessions

## ⚡ Charging History

Charging sessions are now available for the selected History date.

History data includes:

-   Charging location
-   Charging times and duration
-   Start and end SOC
-   Charged and billed energy
-   Charging losses
-   Charging costs and price information
-   Charging source and provider information
-   Associated charging receipts

## 🧾 Receipt History

Charging receipts can now be accessed directly from the History
dashboard.

-   Receipts are linked to their charging session
-   Multiple receipts per charging session are supported
-   Receipt filename and media information are exposed to the dashboard
-   Authenticated signed receipt links are generated for dashboard
    access
-   Relative signed URLs allow the current Home Assistant host to be
    used
-   Receipt links can be opened directly from the dashboard

## 📊 Dashboard Examples

New ready-to-use History dashboard examples are included for:

-   History date selection
-   Journey history
-   Historical route map
-   Charging history
-   Charging receipts

The historical route map uses **Google Map Card** and **Config Template
Card** from HACS. The map example can be hidden automatically on days
without route data.

## ⚙️ Improvements

-   Reduced Journey diagnostic log noise
-   Improved synchronization of the History views
-   History uses the Home Assistant local timezone for date assignment
-   Existing trip, Journey, charging and route storage remains
    compatible

## ⬆️ Upgrade Notes

Ford Triplog 2.0.1 is compatible with existing Ford Triplog 2.0.0 route
data.

No external database or storage migration is required.

The new History dashboard examples are optional. Users who want to use
the historical route map need the **Google Map Card** and **Config
Template Card** custom cards installed through HACS.

------------------------------------------------------------------------

# Ford Triplog 2.0.0

Ford Triplog 2.0 introduced GPS route recording and optional local road
matching.

See the previous release notes for the complete 2.0.0 feature list.
