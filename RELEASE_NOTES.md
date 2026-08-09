# Ford Triplog 2.0.0

Ford Triplog 2.0 introduces GPS route recording and optional local road matching.

This release adds a separate Route Tracker that records the driven route for individual trips, stores it persistently and makes the latest route available to Home Assistant as GeoJSON.

## 🛰️ Route Tracker

New capabilities include:

- Optional GPS route recording for individual trips
- Automatic start and stop together with Ford Triplog trips
- Route association using the Ford Triplog Trip ID
- Support for ABRP latitude/longitude entities
- Support for Home Assistant Companion App position data
- Persistent route storage
- Smart Trip pause and resume support
- Automatic recovery after Home Assistant or integration restart
- Trip start and end GPS points used as route endpoints
- Native **Last Route** sensor
- GeoJSON output for Home Assistant map visualization
- Raw GPS points are always preserved

The Route Tracker operates independently from the normal Ford vehicle tracker and can be enabled only when required.

## 🗺️ Optional OSRM Route Matching

Ford Triplog can now optionally use a local OSRM server to match recorded GPS points to the road network.

Features include:

- Configurable OSRM server URL
- Configurable matching radius
- Automatic matching when a route is finalized
- Raw and matched route data stored separately
- Route matching diagnostics
- Raw and matched point counts
- Route distance
- Matching confidence
- Unmatched tracepoint information
- Manual rebuild of the latest route

OSRM is optional. Raw GPS route recording continues to work without an OSRM server.

For regular use, a local OSRM instance is recommended instead of relying on a public routing service.

## 🐳 Local OSRM / DACH Example

Documentation and an example workflow are provided for building a combined Germany, Austria and Switzerland (DACH) OSRM dataset.

For large datasets, preprocessing can require substantial memory. Building the dataset on a PC or server with sufficient RAM and SSD/NVMe storage and copying the finished files to the production Docker host is recommended.

The example is available under:

`examples/osrm/`

## ⚙️ Reliability Improvements

- Improved synchronization of separate ABRP latitude and longitude updates
- Added debounce handling for position updates
- Protection against mismatched latitude/longitude timestamps
- Improved handling of stale GPS coordinates at trip start and trip end
- Active and paused routes are persisted continuously
- Route recording survives Smart Trip pauses
- Route recovery after Home Assistant restart or integration reload

## 🔒 Privacy

Route data remains local.

Ford Triplog does not require a cloud routing backend. When a local OSRM server is configured, route recording and road matching can remain entirely inside the local network.

## ⬆️ Upgrade Notes

Route tracking and OSRM are optional.

Existing trip, charging and Journey data remain compatible and no migration to an external database is required.

---

# Ford Triplog 1.9.2

### Fixed

- Fixed a race condition that could create duplicate Journey files during automatic Journey rebuilds.
- Reduced the size of the **Last Journey Overview** sensor attributes to stay below Home Assistant Recorder limits and avoid recorder warnings.

### Improvements

- Added a helpful note to the receipt viewer explaining a Home Assistant browser limitation when opening receipts. If direct opening does not work, users can open the receipt via **Open link in new tab**.


# Ford Triplog 1.9.1

### OpenStreetMap charging-site database

- Added manual import of Ford Triplog charging-site databases (`charging_sites_*.json`).
- Country databases can now be downloaded from the Ford Triplog GitHub repository and imported directly from the Home Assistant options flow.
- Imported databases are validated automatically (format, version, country and data integrity) before replacing the existing database.
- Existing databases are backed up automatically before import.
- Added a direct GitHub download link to the import dialog using Home Assistant translation placeholders.

# Ford Triplog 1.9.0

This release focuses on charging management, receipt handling, pause management, internationalization, and a significantly improved configuration interface.

## ✨ New Features

### Charging Cost Management
- Added a complete charging cost editor.
- Supports:
  - billed energy
  - energy costs
  - session fees
  - time-based fees
  - blocking fees
  - parking fees
  - other costs
- Automatic calculation of:
  - charging losses
  - effective price per kWh
  - energy price per kWh

### Receipt Management
- Upload PDF and image receipts directly from Home Assistant.
- Multiple receipts per charging session supported.
- Receipt overview and management dialogs.
- Open stored receipts directly from Home Assistant.
- Delete receipts individually.

### OCR Integration
- Optional connection to a local OCR service.
- Built-in connection test.
- Automatic OCR processing after receipt upload.
- Manual OCR reprocessing.
- OCR status and processing information.
- User parser profiles for custom receipt formats.

### Pause Management
- Edit detected pauses.
- Add:
  - title
  - category
  - location
  - notes
  - costs
- Clear manually entered pause information.

### Journey Management
- Improved journey rebuild workflow.
- Improved journey update workflow.
- Better management dialogs.

### Charging Location Management
- Download charging location databases directly from OpenStreetMap.
- Import charging location databases.
- Improved custom charging location management.

## 🌍 Internationalization

- German translations updated.
- English translations completely revised.
- Polish translations updated.
- Improved wording and consistency throughout the configuration interface.

## 🎨 User Interface

- New structured options menu.
- Improved configuration dialogs.
- Better charging session overview.
- Improved charging cost editor.
- Improved receipt dialogs.
- More consistent terminology.
- Cleaner English user interface.

## ⚙ Improvements

- Added HTTP dependency to the integration manifest.
- Improved translation structure.
- Updated configuration menus.
- Improved charging session details.
- Improved charging statistics presentation.
- Improved OCR configuration workflow.

## 🛠 Fixes

- Fixed translation validation issues reported by Hassfest.
- Removed obsolete translation entries.
- Updated translations to the latest Home Assistant format.
- Fixed manifest validation.
- Fixed configuration menu structure.
- Improved overall translation consistency.

## ✅ Validation

- Hassfest validation passed.
- Updated German translations.
- Updated English translations.
- Updated Polish translations.

---

**Ford Triplog 1.9** continues to evolve into a complete trip, charging and energy management solution for Ford electric vehicles within Home Assistant.

# Ford Triplog 1.8

## 🚀 Major New Features

### 💰 Comprehensive Charging Cost Management

Ford Triplog now includes complete charging cost tracking.

New capabilities:

- Manual charging cost editor
- Automatic total cost calculation
- Energy costs
- Session fees
- Time-based fees
- Blocking fees
- Parking fees
- Additional costs
- Cost verification
- Receipt support
- Currency support

### 🏠 Automatic Home Charging Tariffs

Charging sessions inside the configured Home zone can now be priced automatically.

Features include:

- Two configurable seasonal electricity tariffs
- Configurable summer and winter date ranges
- Automatic tariff selection based on charging date
- Automatic charging cost calculation

### ⚡ Advanced Energy Tracking

Charging sessions now distinguish between:

- Energy stored in the battery
- Energy billed by the charging provider
- Charging losses
- Effective charging price
- Energy source tracking

### 🚗 Extended Journey Statistics

Journeys now provide additional energy and charging information:

- Charging cost total
- Energy cost
- Additional charging costs
- Average charging price
- Battery energy balance
- Battery energy delta
- Total battery energy flow
- Billed charging energy

### 📊 Improved Dashboard Support

The included Markdown dashboard examples have been extended with:

- Journey charging costs
- Average charging price
- Billed charging energy
- Improved Last Charge dashboard
- Improved Journey dashboard
- Unified location display

---

## ✨ Improvements

- Unified charging location display
- Home Assistant zones now have highest location priority
- Improved Journey timeline
- Richer Journey sensor attributes
- Richer Last Charge sensor attributes
- Better charging location handling
- Improved charging cost calculations
- Cleaner dashboard presentation

---

## 🛠 Fixes

- Correct average charging price calculation using billed energy when available
- Improved Journey charging cost aggregation
- Better handling of manually entered charging costs
- Invalid charging sessions are ignored automatically
- Improved handling of unavailable SOC values
- Multiple charging session stability improvements

---

## 🌍 Translations

Updated translations for:

- 🇬🇧 English
- 🇩🇪 German
- 🇵🇱 Polish

including all new charging cost management and home tariff functionality.

---


# Ford Triplog 1.7.0

Ford Triplog 1.7.0 is a major feature release focused on the new Journey experience.

Trips, charging sessions and pauses are now combined into a complete journey timeline, providing a much clearer overview of daily vehicle usage while significantly improving dashboard integration.

------------------------------------------------------------------------

# Highlights

## Enhanced Journey Management

Journey management has been significantly expanded.

New features include:

- Automatic Journey rebuild after trip completion
- Complete Journey timeline
- Trips, pauses and charging sessions in chronological order
- Local timezone support
- Rich Journey metadata for dashboards
- Improved Journey synchronization

------------------------------------------------------------------------

### Added

- Extended **Last Journey Overview** sensor.
- Timeline now includes:
  - Journey start
  - Trips
  - Pauses
  - Charging sessions
  - Journey end
- Added trip metrics:
  - Distance
  - Duration
  - Energy consumption
  - Consumption (kWh/100 km)
  - Start / End SOC
- Added charging metrics:
  - Charging duration
  - Charged energy
  - Start / End SOC
  - SOC increase

------------------------------------------------------------------------

## Improved Location Recognition

Journey locations are now resolved using multiple prioritized sources.

Priority order:

1. Home Assistant zones
2. FordPass charging information
3. Offline OpenStreetMap charging database
4. Address fallback

Location information is now available for:

- Trip start
- Trip destination
- Charging sessions
- Pauses

------------------------------------------------------------------------

## Dashboard Improvements

The Journey sensor now exposes significantly more information for Home Assistant dashboards.

New dashboard attributes include:

- Timeline events
- Journey statistics
- Driving metrics
- Charging metrics
- Pause information
- Location names
- Formatted timestamps

This allows rich Markdown dashboards without additional template logic.

------------------------------------------------------------------------

## Home Assistant Improvements

- Automatic Journey rebuild after trips are saved.
- Correct local timezone handling.
- Improved Smart Trip synchronization.
- Improved GPS freshness detection.
- Better Journey consistency after charging sessions.

------------------------------------------------------------------------

# Privacy

Ford Triplog remains a local-first integration.

- No cloud backend
- Local JSON storage
- Offline charging database
- Full user control over data

------------------------------------------------------------------------

# Compatibility

- Home Assistant 2026.6 or newer
- Python 3.12 or newer
- Community FordPass integration
- HACS

------------------------------------------------------------------------

# Upgrade Notes

Existing installations are upgraded automatically.

Existing Journey data can be rebuilt using the new Journey engine.

No manual migration is required.

------------------------------------------------------------------------

# Known Limitations

- Journey energy balance planned for Version 1.8
- Charging cost calculation planned for Version 1.8
- JSON remains the default storage backend
- Multi-vehicle support planned for a future release

------------------------------------------------------------------------

# Looking Ahead

Upcoming development focuses on:

- Journey energy balance
- Charging cost calculation
- Home charging tariffs
- Maintenance and rebuild tools
- Extended statistics
- Optional database backend

See `ROADMAP.md` for additional information.

------------------------------------------------------------------------

Thank you to everyone who tests Ford Triplog, reports issues and contributes to the project.


# Ford Triplog 1.6.0

Ford Triplog 1.6.0 is the second major public release and introduces
comprehensive Journey Management together with significantly enhanced
charging location recognition, diagnostics and configuration.

------------------------------------------------------------------------

# Highlights

## Journey Management

Version 1.6 introduces automatic Journey management.

A Journey combines multiple trips and charging sessions into one
complete outing.

Features include:

-   Automatic Journey creation
-   Multiple trips per Journey
-   Multiple charging sessions per Journey
-   Automatic Journey completion
-   Home-zone based Journey detection
-   Journey rebuild and maintenance tools

------------------------------------------------------------------------

### Added
- New "Last Journey Overview" sensor for Home Assistant dashboards.
- Provides a structured journey timeline including start, trips, pauses, charging sessions and destination.
- Includes summarized driving, charging and pause durations for easier dashboard visualization.

------------------------------------------------------------------------

## Improved Charging Location Recognition

Charging locations are now resolved using multiple prioritized data
sources:

1.  FordPass charging information
2.  User-defined charging locations
3.  Local OpenStreetMap charging database
4.  Reverse geocoding

This provides accurate charging provider and location recognition while
allowing complete user customization.

------------------------------------------------------------------------

## OpenStreetMap Charging Database

The offline charging database has been expanded with:

-   Country-specific downloads
-   Simple import and update
-   Fast geohash lookups
-   Offline operation
-   Charging provider recognition

------------------------------------------------------------------------

## User Charging Locations

Create and manage custom charging locations such as:

-   Home
-   Workplace
-   Public chargers
-   Private locations

Custom locations always take priority over automatically detected
locations.

------------------------------------------------------------------------

## Home Assistant Integration

New and improved features include:

-   Journey sensor
-   Extended diagnostics
-   Improved Configuration Flow
-   Improved Options Flow
-   English, German and Polish translations
-   HACS support

------------------------------------------------------------------------

# Privacy

Ford Triplog remains a local-first integration.

-   No cloud backend
-   Local JSON storage
-   Offline charging database
-   Full user control over data

------------------------------------------------------------------------

# Compatibility

-   Home Assistant 2026.6 or newer
-   Python 3.12 or newer
-   Community FordPass integration
-   HACS

------------------------------------------------------------------------

# Upgrade Notes

Existing installations are migrated automatically.

No manual migration is required.

------------------------------------------------------------------------

# Known Limitations

-   Charging cost calculation planned for Version 1.7
-   JSON remains the default storage backend
-   Multi-vehicle support planned for a future release

------------------------------------------------------------------------

# Looking Ahead

Upcoming development focuses on:

-   Charging cost calculation
-   Home charging tariffs
-   Maintenance tools
-   Extended statistics
-   Optional database backend

See `ROADMAP.md` for additional information.

------------------------------------------------------------------------

Thank you to everyone who tests Ford Triplog, reports issues and
contributes to the project.
