# RELEASE_NOTES

## Ford Triplog 1.5.0

Ford Triplog 1.5.0 is the first public release of the integration.

This release introduces a complete trip and charging history solution for Home Assistant with a strong focus on local data processing, privacy and seamless integration with the existing FordPass integration.

---

# Highlights

## Automatic Trip Recording

Trips are recorded automatically using vehicle telemetry from the FordPass integration.

Each completed trip includes:

- Distance
- Duration
- Average speed
- State of Charge (SOC)
- Estimated energy consumption
- Start and destination locations

---

## Smart Trip

The new Smart Trip feature prevents short stops from splitting a journey into multiple trips.

Typical use cases include:

- Coffee breaks
- Shopping stops
- Picking up passengers
- Brief charging stops

The timeout is fully configurable.

---

## Automatic Charging Sessions

Charging sessions are detected automatically without any user interaction.

Each charging session records:

- Start and end time
- Charging duration
- State of Charge
- Estimated charged energy
- Charging location
- Charging provider (when available)

---

## Charging Location Resolver

Ford Triplog now identifies charging locations using a prioritized resolver.

Priority order:

1. FordPass charging information
2. User-defined charging locations
3. OpenStreetMap charging database
4. Reverse geocoding

This provides reliable charging location recognition while allowing users to override locations whenever necessary.

---

## User Charging Locations

Create your own charging locations for:

- Home
- Work
- Public chargers

Each location supports:

- Custom names
- Configurable matching radius
- Address information
- Charging operator
- Charging network
- Connector information

User-defined locations always take precedence over the OpenStreetMap database.

---

## OpenStreetMap Charging Database

Version 1.5 introduces optional offline charging databases.

Benefits include:

- Fast local lookups
- Offline operation
- Charging provider recognition
- Network information
- Connector types
- Charging power
- Number of charging points

Country-specific databases can be downloaded directly from the integration.

---

## Trip and Charging Linking

Charging sessions are automatically associated with the corresponding trip whenever possible.

Trips and charging sessions remain separate records while providing a connected driving history.

---

## Local Storage

All data is stored locally inside Home Assistant.

Stored information includes:

- Trips
- Charging sessions
- Statistics
- User charging locations
- Configuration

No external database server is required.

---

## Home Assistant Integration

Ford Triplog integrates seamlessly into Home Assistant.

Features include:

- Native Config Flow
- Options Flow
- Diagnostics support
- HACS installation
- Device information
- Translation support
- Dashboard compatibility

---

## Documentation

Version 1.5 includes comprehensive documentation covering:

- Installation
- Configuration
- Architecture
- Smart Trip
- Charging sessions
- Charging locations
- Charging database
- Sensors
- Dashboard examples
- Storage
- Privacy
- Troubleshooting
- Automation examples
- FAQ

---

# Privacy

Ford Triplog follows a local-first architecture.

- No cloud backend
- Local JSON storage
- Offline charging database lookups
- User-controlled backups

Your driving history always remains under your control.

---

# Compatibility

- Home Assistant 2026.6 or newer
- Python 3.12 or newer
- Community FordPass integration
- HACS

---

# Upgrade Notes

This is the initial public release.

No migration steps are required for new installations.

Future releases will automatically migrate stored data whenever necessary.

---

# Known Limitations

Current limitations include:

- One active charging database at a time
- Charging cost calculation is not yet available
- JSON is the default storage backend
- Multi-vehicle support is planned for a future release

---

# Looking Ahead

Development continues with planned improvements including:

- Automatic charging database switching
- Additional dashboard templates
- Charging cost calculation
- Maintenance tools
- Enhanced statistics
- Optional database backend for large installations

See `ROADMAP.md` for additional information.

---

Thank you to everyone who tests, reports issues, suggests new ideas and contributes to the Ford Triplog project.