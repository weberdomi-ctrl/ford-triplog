# Ford Triplog 2.1.0

Ford Triplog 2.1 introduces a local SQLite storage backend and completes the first major storage architecture migration of the project.

The existing JSON storage remains available during the transition. Existing installations are not forced to change their read backend after the update.

## 🗃️ SQLite Storage Backend

Ford Triplog now maintains a local SQLite database alongside the existing JSON storage.

The new backend covers the main persistent Ford Triplog data, including:

- Trips
- Charging sessions
- Journeys
- Current and last Trip/Charge/Journey caches
- GPS routes
- User-defined charging locations
- Pending charging locations
- Charging metadata
- Pause metadata
- Charging receipts and OCR/parser state
- User-created receipt parser profiles
- Statistics and diagnostics

Existing IDs and stored data structures are preserved as closely as possible so JSON and SQLite records remain comparable during the migration period.

## 🔄 Parallel Storage and Safe Upgrade Path

Ford Triplog continues writing compatible data to JSON and SQLite during the 2.1 transition.

Important upgrade behavior:

- **JSON remains the default read backend after upgrading**
- Existing users are not switched automatically to SQLite
- SQLite can be enabled explicitly in Ford Triplog settings
- Changing the backend reloads the integration
- JSON remains available as a fallback while SQLite continues to be tested in normal use

This provides a controlled migration path without changing the storage behavior of existing installations unexpectedly.

## ⚡ SQLite Read Mode

When SQLite is selected as the read backend, Ford Triplog reads supported historical and configuration data directly from the local database.

This includes:

- Trip and charging history
- Journey history
- Route history
- Charging and pause metadata
- Receipts
- User receipt parser profiles
- User-defined charging locations
- Statistics source data
- Journey rebuild source data

SQLite-only testing no longer depends on archived Trip or Charge JSON files for Journey rebuild or statistics calculation.

## 📊 SQL-backed Statistics

Frequently used Top Statistics can now use SQLite queries and database views.

Database support includes:

- Top Trip
- Top Journey
- Top Day
- Top Charging
- Top Departures & Destinations
- Top Routes

Location-specific Home Assistant logic such as zones, charging-site matching and GPS clustering remains in Python where appropriate.

## 🔧 Journey Rebuild

Journey maintenance has been made backend-independent.

Journey rebuild and update operations now load Trips and charging sessions from the currently selected storage backend instead of depending on archived JSON file paths.

This allows complete Journey rebuilding in SQLite read mode even when archived JSON files are unavailable.

## 📈 Statistics Recalculation

Statistics are derived data and are now recalculated during integration setup/reload from the currently selected read backend.

This prevents statistics from the previously selected backend remaining active after switching between JSON and SQLite.

## 🧾 Receipt and Parser Storage

Receipt-related persistent metadata has been moved into dedicated SQLite tables.

This includes:

- Receipt metadata and OCR/parser results
- Charging metadata
- Pause metadata
- User-created receipt parser profiles

Bundled parser profiles remain part of the Ford Triplog program files and are not moved into the user database.

Existing user parser profiles are migrated into SQLite. New user parser profiles are stored there when SQLite mode is active.

## 🛰️ Route Storage

GPS Route Tracker data is available from SQLite while preserving the existing raw and matched route structure.

The route history and last-route reads can therefore operate without requiring the archived JSON route files in SQLite mode.

## ⚙️ Improvements and Fixes

- Added backend-neutral archive reads for Trips and charging sessions
- Added incremental startup mirroring for Trips, Charges, Journeys and Routes
- Unchanged JSON records are skipped instead of being written to SQLite again on every restart
- SQLite-only archive records are preserved during compatibility mirroring
- Added bulk mirror-index reads for Journey and Route startup comparison
- Added a compact main-storage mirror snapshot to avoid repeated per-record SQLite lookups
- Added a Home Assistant runtime guard for SQLite schema initialization
- Added a shared initialization lock to prevent parallel duplicate schema setup
- Reduced repeated metadata, charging-site and migration reads through runtime caching/guards
- Cached user-defined charging locations after initial load instead of re-reading them for every location lookup
- Added bulk Route lookups for multiple Trip IDs
- Reduced redundant Top Statistics and Route History database access
- Coalesced rapid coordinator update bursts before publishing sensor updates
- Disabled redundant Home Assistant polling for push-driven Ford Triplog sensors
- Fixed manual charging-cost editing when setting additional costs such as parking fees to `0`
- Improved charging-cost recalculation consistency for stored home charging sessions
- Fixed Journey rebuild returning zero source records in SQLite-only mode
- Fixed statistics depending on the number of remaining JSON archive files
- Added automatic statistics refresh after setup/reload
- Added SQLite storage for user receipt parser profiles
- Added SQLite storage for receipts, charging metadata and pause metadata
- Added SQLite reads for user-defined charging locations
- Added SQLite Journey and Route archive support
- Reduced remaining hidden JSON-only read paths
- Preserved JSON fallback behavior throughout the migration

## 🚀 Storage and Runtime Efficiency

The 2.1 storage migration also includes a number of startup and runtime optimizations discovered during SQLite testing:

- SQLite schema creation is performed only once per Home Assistant runtime
- Journey and Route compatibility mirrors compare existing records before writing
- Main Trip/Charge/cache mirroring skips unchanged records
- Metadata migration checks run once per runtime
- User-defined charging locations are cached after loading
- Top Location and Top Route processing share cached location resolution data
- Rapid FordPass entity-update bursts are published as a single coordinator update
- Ford Triplog sensors use push updates instead of additional periodic Home Assistant polling

These changes substantially reduce unnecessary SQLite reads, writes and repeated sensor recalculations during normal operation.

## ⬆️ Upgrade Notes

Ford Triplog 2.1 is designed to upgrade existing 2.0.x installations without requiring an immediate storage-backend change.

After upgrading:

1. Ford Triplog continues to use **JSON** as the read backend by default.
2. Existing data is mirrored/migrated into the local SQLite database.
3. Users who want to test or use the SQLite read performance can select **SQLite** in Ford Triplog settings.
4. The integration reloads and recalculates statistics from the selected backend.
5. JSON remains available as a fallback during the 2.1 transition.

The SQLite database is local to Home Assistant. No external database server is required.

---

# Ford Triplog 2.0.3

Ford Triplog 2.0.3 extends the Top Statistics introduced in 2.0.2, improves location resolution and completes further translation and storage-related cleanup.

## 📍 Top Departures & Destinations

A new **Top Departures & Destinations** sensor summarizes the most frequently used trip start and destination locations.

Features include:

- Top 5 departure locations
- Top 5 destination locations
- Trip count per location
- Total distance associated with each location
- GPS-based grouping to avoid duplicate entries caused by slightly different coordinates or address labels
- Home Assistant zones are used as meaningful location names when available

## 🛣️ Top Routes

A new **Top Routes** sensor identifies the most frequently driven directed routes.

Features include:

- Top 5 routes by trip count
- Direction-aware grouping, so A → B and B → A remain separate routes
- Average distance per route
- Average consumption where suitable trip data is available
- Same-location routes are excluded from the ranking
- Consumption averages only include individual trips of at least 10 km to avoid misleading short-trip values

## 🗺️ Improved Location Resolution

Top location statistics now use a common location resolution chain to provide more meaningful and stable names.

Locations are resolved in the following order:

1. Home Assistant zone
2. User-defined Ford Triplog charging location
3. Known OSM charging location
4. 50 m GPS cluster
5. Stored address fallback

This allows locations such as Work, garages, shops and charging sites to be grouped by their meaningful configured names instead of varying street addresses.

The Home zone is stored as the stable language-neutral value `Home`. Other Home Assistant zones use their user-defined zone names.

## ⚡ Charging Location Lookup

Known charging locations are now also available to Top Departures & Destinations and Top Routes.

- User-defined charging locations take priority over OSM charging locations
- Custom charging-site radii are respected
- Existing OSM charging-site lookup and configured lookup radius are reused
- Charging-site location names can therefore be used even when no Home Assistant zone exists at that location

## 🌍 Translation and Naming Cleanup

Translation handling has been further standardized.

Improvements include:

- English is used as the fallback language for untranslated entity names
- German, English and Polish entity translations synchronized
- New Top Departures & Destinations and Top Routes entity names translated
- Language-specific labels removed from raw sensor attributes where possible
- `Home` remains stable in raw attributes and can be localized by the dashboard
- Entity names and stored/raw data are kept separate so changing the Home Assistant language does not alter underlying statistics data

## 🗃️ Recorder and Route History Cleanup

Large route attributes have been reduced to avoid Home Assistant Recorder warnings caused by attributes exceeding the 16,384-byte storage limit.

- Route History no longer produces oversized Recorder attribute warnings
- Route data remains available through Ford Triplog's persistent route storage
- Existing stored Trip, Journey, Charge and Route data remains compatible

## 📊 Dashboard Examples

New Markdown dashboard examples are available for:

- Top Departures & Destinations
- Top Routes

The examples use the new sensor attributes directly and can localize the stable `Home` value for display.

## ⚙️ Improvements and Fixes

- Improved grouping of frequently visited locations
- Added Home Assistant zone-aware location resolution
- Added user-defined and OSM charging-site location resolution to trip statistics
- Improved handling of varying geocoded addresses for the same physical location
- Fixed missing regular-expression import used by location label scoring
- Reduced misleading consumption statistics for very short routes
- Removed same-location routes from Top Routes
- Further standardized sensor names, translation keys and English fallbacks
- Reduced Recorder warnings from large Route History attributes

## ⬆️ Upgrade Notes

Ford Triplog 2.0.3 is compatible with existing Ford Triplog 2.0.x stored data.

No database or storage migration is required.

Existing Home Assistant zones and user-defined Ford Triplog charging locations are used automatically by the new location statistics. Users can adjust Home Assistant zone sizes where larger sites should be treated as one location.

---

# Ford Triplog 2.0.2

Ford Triplog 2.0.2 expands statistics, improves Route Tracker reliability and road matching, and completes a number of dashboard and translation refinements.

## 📊 Top Statistics

New native Top Statistics sensors provide quick access to notable driving and charging records.

New statistics include:

- **Top Trip** with distance, duration, energy use and consumption
- **Top Journey** with Journey-level driving and energy information
- **Top Day** aggregating all Journeys and trips of the same local calendar day
- **Top Charging** with leading charging providers and locations
- Largest charging session
- Session count and remaining unknown-provider statistics
- Charging costs and average price per kWh

Top Charging now refreshes automatically after stored charging data or charging costs are changed. A Home Assistant or integration reload is no longer required for updated cost statistics.

## 🛰️ Route Tracker Improvements

Route tracking introduced in Ford Triplog 2.0 has been refined for more reliable everyday recording.

Improvements include:

- Improved Route Tracker persistence and recovery
- Better handling of trip start and end route points
- Improved ABRP-based route recording
- More reliable route completion and Trip ID association
- Raw GPS route data remains preserved independently from matched route data

## 🗺️ OSRM Route Matching

Optional local OSRM map matching is now supported for recorded routes.

Features include:

- Configurable local OSRM server
- Configurable matching radius
- Automatic road matching after trip completion
- Raw and matched route data stored separately
- Matching diagnostics
- Manual rebuild of the latest route
- DACH example configuration for Germany, Austria and Switzerland

OSRM remains completely optional. Without OSRM, Ford Triplog continues to record and display the raw GPS route.

## 📅 Top Day

The new **Top Day** sensor aggregates driving activity by the Home Assistant local calendar date.

It includes:

- Total daily distance
- Total and driving duration
- Journey and trip counts
- Charging information
- Energy used and charged
- Average consumption
- Charging costs
- Start and end locations
- Associated Journey, Trip, Charge and Route IDs

This makes it possible to identify the longest recorded driving day even when it consists of multiple Journeys.

## ⚡ Charging Statistics Improvements

Charging statistics now make better use of resolved charging locations and providers.

Improvements include:

- Home charging grouped as Home
- Provider and location aggregation
- User-defined charging locations included in statistics
- Improved matching of charging locations
- Unknown-provider sessions exposed separately
- Immediate Top Charging recalculation after manual cost or stored charge changes

## 🌍 Translations and Entity Names

Entity naming and translations have been cleaned up and synchronized.

Improvements include:

- German, English and Polish translation updates
- Translatable **Charging History**
- Translatable **Journey History**
- Translatable **Route History**
- Translatable shared **History Date** selector
- Translatable **Trip Active**
- Translation support for the new Top Statistics sensors
- Removal of the redundant unavailable FordPass last-charge energy sensor

## ⚙️ Improvements and Fixes

- Fixed Journey History aggregation when multiple separate Journeys exist on the same calendar date
  - Distance, durations, energy, SoC and charging costs are now aggregated across all Journeys
  - Journey timelines are merged chronologically instead of showing only the last Journey
  - Average consumption and average charging price are recalculated from the aggregated totals
  - Start SoC is taken from the first available Journey value and end SoC from the last available value
- Improved Top Charging aggregation
- Charging provider and location corrections are reflected in statistics
- Manual charging cost changes can update Top Charging without reloading the integration
- Reduced redundant sensor exposure
- Existing Trip, Journey, Charge and Route storage remains compatible

## ⬆️ Upgrade Notes

Ford Triplog 2.0.2 is compatible with existing Ford Triplog 2.0.x stored data.

No external database or storage migration is required.

OSRM is optional and only needs to be configured when local road matching is desired.

---

# Ford Triplog 2.0.1

Ford Triplog 2.0.1 extends the Route Tracker introduced in 2.0.0 with a complete date-based History view for routes, Journeys, charging sessions and charging receipts.

## 🕓 History

A shared History date selection is now available for reviewing stored Ford Triplog data by day.

New capabilities include:

- Shared History date selection
- Daily Journey history
- Daily route history
- Daily charging history
- Charging-only days are available in History
- History sensors update together when the selected date changes

## 🗺️ Route History

Stored Route Tracker data can now be viewed for previously recorded days.

Features include:

- Native **Route History** sensor
- Historical route loading from persistent route storage
- Routes grouped by local Home Assistant calendar date
- GeoJSON output for historical map visualization
- Multiple routes from the selected day can be displayed together
- Active and paused recovery routes are excluded from historical views
- Existing Ford Triplog 2.0.0 route files remain compatible

## 🛣️ Journey History

The selected day can now be displayed as a complete Journey overview.

History data includes:

- Journey summary
- Distance and duration
- Driving, pause and charging time
- Energy consumption
- Charged energy
- Journey energy balance
- Charging costs
- Battery and SOC information
- Complete Journey timeline with trips, pauses and charging sessions

## ⚡ Charging History

Charging sessions are now available for the selected History date.

History data includes:

- Charging location
- Charging times and duration
- Start and end SOC
- Charged and billed energy
- Charging losses
- Charging costs and price information
- Charging source and provider information
- Associated charging receipts

## 🧾 Receipt History

Charging receipts can now be accessed directly from the History dashboard.

- Receipts are linked to their charging session
- Multiple receipts per charging session are supported
- Receipt filename and media information are exposed to the dashboard
- Authenticated signed receipt links are generated for dashboard access
- Relative signed URLs allow the current Home Assistant host to be used
- Receipt links can be opened directly from the dashboard

## 📊 Dashboard Examples

New ready-to-use History dashboard examples are included for:

- History date selection
- Journey history
- Historical route map
- Charging history
- Charging receipts

The historical route map uses **Google Map Card** and **Config Template Card** from HACS. The map example can be hidden automatically on days without route data.

## ⚙️ Improvements

- Reduced Journey diagnostic log noise
- Improved synchronization of the History views
- History uses the Home Assistant local timezone for date assignment
- Existing trip, Journey, charging and route storage remains compatible

## ⬆️ Upgrade Notes

Ford Triplog 2.0.1 is compatible with existing Ford Triplog 2.0.0 route data.

No external database or storage migration is required.

The new History dashboard examples are optional. Users who want to use the historical route map need the **Google Map Card** and **Config Template Card** custom cards installed through HACS.

---

# Ford Triplog 2.0.0

Ford Triplog 2.0 introduced GPS route recording and optional local road matching.

See the previous release notes for the complete 2.0.0 feature list.
