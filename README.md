# Ford Triplog

A Home Assistant integration that automatically records trips for Ford vehicles using the FordPass integration.

![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2026.6%2B-blue.svg)
![Version](https://img.shields.io/badge/version-1.1.0-green.svg)
![License](https://img.shields.io/badge/license-MIT-blue.svg)

---

## Features

- Automatic trip detection
- Smart Trip (merge short stops)
- Start and destination address
- GPS coordinates
- Odometer tracking
- State of Charge (SOC)
- Home Assistant Config Flow
- Options Flow
- Local storage
- Home Assistant Brands API support
- German and English translations

---

## Requirements

- Home Assistant Core **2026.6** or newer
- FordPass Home Assistant Integration
- A working FordPass vehicle

---

## Installation

### HACS

Coming soon.

### Manual Installation

Copy the folder

```
custom_components/ford_triplog
```

to

```
config/custom_components/
```

Restart Home Assistant.

---

## Configuration

After restarting Home Assistant:

Settings

→ Devices & Services

→ Add Integration

→ **Ford Triplog**

Configure the following entities:

| Setting | Required |
|----------|----------|
| Ignition Sensor | ✅ |
| Odometer Sensor | ✅ |
| Device Tracker | ✅ |
| State of Charge (SOC) | Optional |

---

## Smart Trip

Smart Trip automatically combines short stops into a single trip.

Example:

Home → Bakery → Gas Station → Work

instead of

3 individual trips

Ford Triplog records

Home → Work

if the stop time is shorter than the configured timeout.

---

## Current Features

- Automatic trip logging
- Start / End time
- Duration
- Distance
- Odometer
- GPS coordinates
- Reverse Geocoding
- Start address
- Destination address
- SOC
- Smart Trip

---

## Roadmap

### Version 1.2

- Charging History
- AC/DC Detection
- Charging Locations
- Energy Statistics

### Version 1.3

- CSV Export
- GPX Export
- Dashboard Cards
- Advanced Statistics

### Version 1.4

- Multi Vehicle Support
- Cloud Backup
- Maintenance Tracking

---

## Screenshots

*(coming soon)*

---

## Support

GitHub Issues

https://github.com/weberdomi-ctrl/ford-triplog/issues

---

## License

MIT License

---

## Credits

Developed by

**Dominik Weber**

Special thanks to all beta testers for their valuable feedback.