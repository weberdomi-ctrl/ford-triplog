# RELEASE_NOTES

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
