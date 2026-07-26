# RELEASE_NOTES

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
