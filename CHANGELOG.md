# Changelog

## Version 1.2.0

### Added
- New sensors:
  - Last Trip Start Time
  - Last Trip End Time
- Human-readable trip timestamps ("Heute", "Gestern", Datum/Uhrzeit).

### Changed
- Improved local time handling using Home Assistant's timezone utilities.
- Trip timestamps are now correctly converted from UTC to the configured Home Assistant timezone.
- Internal date/time formatting moved to a shared utility function.

### Fixed
- Fixed incorrect UTC display for trip start and end times.
- Improved consistency of date and time formatting across all trip sensors.

## 1.1.0

### Added
- Config Flow
- Options Flow
- Smart Trip
- Smart Trip timeout
- Home Assistant Brands Proxy API
- German and English translations

### Improved
- Modernized integration architecture
- Automatic reload after option changes
- Improved configuration handling

### Fixed
- Config Flow issues
- Options handling
- Home Assistant 2026.6 compatibility
