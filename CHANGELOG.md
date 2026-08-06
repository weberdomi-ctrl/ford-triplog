# Changelog

## 1.9.2

### Fixed

- Fixed a race condition that could create duplicate Journey files during automatic Journey rebuilds.
- Reduced the size of the **Last Journey Overview** sensor attributes to stay below the Home Assistant Recorder attribute limit and prevent recorder warnings.

### Improved

- Added a helpful note to the receipt viewer explaining a Home Assistant browser limitation when opening receipts. If direct opening does not work, users can open the receipt via **Open link in new tab**.

---

## 1.9.1

### Added

- Manual import of pre-generated OpenStreetMap charging-site databases.
- Official GitHub charging-site database repository for supported countries.

### Improved

- Improved charging-site database management.
- Extended translations and documentation.
- Added fallback workflow when automatic OpenStreetMap downloads are not possible.

---

## 1.9.0

### Added

- Pause management with editable categories, titles, notes and locations.
- Receipt management for charging sessions and pauses.
- OCR integration for automatic receipt processing.
- Receipt parser profiles.
- Charging receipt management within the charging session workflow.
- Manual charging cost management with detailed cost breakdown.
- User-defined charging locations.

### Improved

- Charging workflow.
- Options flow.
- Journey timeline.
- Charging cost calculation.
- Local storage and metadata handling.

---

## 1.8.0

### Added

- Complete Journey energy balance.
- Journey battery statistics.
- Automatic home charging cost calculation.
- Seasonal home electricity tariffs.
- Journey charging cost statistics.
- Extended Journey dashboard sensors.

### Improved

- Journey calculations.
- Energy calculations.
- Charging statistics.
- Dashboard support.

---

## 1.7.0

### Added

- Automatic Journey rebuild after completed trips.
- Journey timeline with local timestamps.
- Charging and pause locations.
- Journey maintenance tools.
- Extended dashboard examples.

### Improved

- Journey generation.
- Timeline formatting.
- GPS location handling.
- Translation coverage.

### Fixed

- UTC time display in Journey timeline.
- Journey rebuild reliability.
- GPS freshness handling.
- Various Journey stability improvements.

---

## 1.6.0

### Added

- Journey management.
- Journey update, rebuild and delete.
- Journey history and native Journey sensor.
- OpenStreetMap charging-site database download and import.
- User-defined charging locations.
- Intelligent charging-site recognition.
- Configurable Journey home zone, timeout and maximum gap.
- Polish translations.

### Improved

- Trip detection.
- Charging detection.
- Multi-trip and multi-charge Journey handling.
- Configuration flow.
- Options flow.
- Translation coverage.
- Diagnostics and local storage.

### Fixed

- Multi-day Journey handling.
- Home detection reliability.
- Journey rebuild behaviour.
- Translation validation.
- Various stability and reliability improvements.