# CHANGELOG

All notable changes to Ford Triplog are documented in this file.

The project follows the principles of [Semantic Versioning](https://semver.org/).

---

# [1.5.0] - Initial Public Release

## Added

### Smart Trip

- Added Smart Trip functionality.
- Automatically merges short stops into a single journey.
- Configurable timeout.
- Prevents unnecessary trip splitting.

### Trip Recording

- Automatic trip detection.
- Improved trip start detection based on actual vehicle movement.
- Automatic trip completion.
- Trip duration calculation.
- Distance calculation.
- Average speed calculation.
- Energy consumption estimation.
- Lifetime trip statistics.

### Charging Sessions

- Automatic charging session detection.
- Charging history.
- Estimated charged energy.
- Charging duration.
- Charging statistics.
- Trip and charging session linking.

### Charging Location Resolver

Implemented a prioritized charging location resolver.

Priority:

1. FordPass charging location
2. User charging locations
3. OpenStreetMap charging database
4. Reverse geocoding

### User Charging Locations

Added support for manually managed charging locations.

Features:

- Home charging locations
- Work charging locations
- Public charging locations
- Custom names
- Configurable matching radius
- Manual editing
- Manual deletion

### OpenStreetMap Charging Database

Added local charging database support.

Features:

- Country-specific databases
- Offline operation
- Fast local lookup
- Brand recognition
- Operator recognition
- Network recognition
- Connector information
- Charging power
- Charging point count

### Statistics

Added cumulative statistics including:

- Total trips
- Total distance
- Total charged energy
- Total charging sessions
- Average consumption
- Lifetime statistics

### Sensors

Added Home Assistant entities for:

- Last trip
- Last charging session
- Charging statistics
- Trip statistics
- Energy statistics
- Charging locations
- Runtime status

### Storage

Implemented persistent local storage.

Features:

- JSON storage
- Automatic migration
- Automatic recovery
- Backup compatible
- Human-readable files

### Configuration

Added complete configuration flow including:

- Vehicle Tracker selection
- Ignition entity selection
- Odometer selection
- State of Charge selection
- Smart Trip configuration
- Battery capacity configuration
- Charging database selection

### Documentation

Added comprehensive project documentation.

Included:

- Installation Guide
- Configuration Guide
- Architecture
- Smart Trip
- Charging Sessions
- Charging Locations
- Charging Database
- Sensors
- Dashboard Examples
- Storage
- Privacy
- Troubleshooting
- Automation Examples
- FAQ
- Roadmap

### Home Assistant

- Native Home Assistant integration
- HACS support
- Config Flow
- Options Flow
- Diagnostics support
- Translations
- Device information

---

## Changed

- Improved trip detection accuracy.
- Improved charging detection.
- Improved charging location matching.
- Improved configuration interface.
- Improved storage reliability.
- Improved startup recovery.
- Improved Home Assistant entity naming.
- Improved translation coverage.

---

## Performance

- Optimized startup time.
- Optimized storage access.
- Optimized charging database lookup.
- Reduced unnecessary recalculations.
- Improved memory usage.

---

## Privacy

- Local-first architecture.
- No cloud backend.
- Local JSON storage.
- Offline charging database lookup.
- User-controlled backups.

---

## Known Limitations

- One active OpenStreetMap charging database at a time.
- Charging costs are not yet calculated.
- JSON storage is used as the default backend.
- Multi-vehicle support is not yet available.

---

## Future

See `ROADMAP.md` for planned features and future development.