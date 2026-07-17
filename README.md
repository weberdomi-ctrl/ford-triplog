# Ford Triplog

<p align="center">
  <img src="docs/images/banner.png" alt="Ford Triplog" width="900">
</p>

<p align="center">
Automatic trip logging for Ford vehicles in Home Assistant.
</p>

> **Status:** Beta 1.2.0

---

# Overview

Ford Triplog is a Home Assistant custom integration that automatically records every journey using the FordPass integration. Every completed trip is stored with detailed information and exposed through native Home Assistant sensors.

## Highlights

- Automatic trip detection
- Smart Trip support
- Start & destination addresses
- Distance and driving time
- Average speed
- Battery usage (SOC)
- Energy consumption (kWh)
- Efficiency (kWh/100 km)
- Trip history
- Statistics
- Native Home Assistant sensors
- Config Flow
- Options Flow
- English & German translations
- Local branding

---

# Screenshots

> Screenshots will be added before the first public release.

- Integration setup
- Sensors
- Dashboard example
- Trip history

---

# Available Sensors

## Last Trip

| Sensor | Unit | Description |
|--------|------|-------------|
| Last Start Address | - | Trip start |
| Last End Address | - | Trip destination |
| Last Distance | km | Distance of last trip |
| Last Driving Time | - | Formatted duration |
| Last Duration (Raw) | s | Raw duration |
| Last SOC Used | % | Battery used |
| Last Consumption | kWh | Energy consumed |
| Last Efficiency | kWh/100 km | Average consumption |
| Last Average Speed | km/h | Average speed |

## Statistics

| Sensor | Unit | Description |
|--------|------|-------------|
| Trip Count | Trips | Recorded trips |
| Total Distance | km | Overall distance |
| Total Energy | kWh | Overall energy |
| Average Consumption | kWh/100 km | Fleet average |
| Total Driving Time | - | Formatted time |
| Total Duration (Raw) | s | Raw duration |

---

# Installation

## HACS (planned)

1. Add the Ford Triplog repository.
2. Install the integration.
3. Restart Home Assistant.
4. Add Ford Triplog from **Settings → Devices & Services**.

## Manual

Copy the `custom_components/ford_triplog` folder into your Home Assistant configuration directory and restart Home Assistant.

---

# Requirements

- Home Assistant 2026.6+
- FordPass Integration

---

# What's New in Version 1.2

## New

- Last Consumption sensor
- Last Efficiency sensor
- Last Average Speed sensor
- Total Energy sensor
- Average Consumption sensor

## Improved

- Home Assistant SensorStateClass support
- Improved long-term statistics
- Better dashboard compatibility

---

# Roadmap

## Version 1.2

- Charging history
- Charging statistics
- More trip analytics

## Future

- GPX export
- CSV export
- Multi-vehicle support
- Dashboard cards
- Maintenance tracking

---

# FAQ

### Does Ford Triplog replace FordPass?

No. Ford Triplog extends the FordPass integration with trip logging and statistics.

### Does it support multiple vehicles?

Not yet. Planned for a future release.

### Is internet access required?

Ford Triplog relies on the FordPass integration.

---

# Contributing

Bug reports, feature requests and pull requests are welcome.

---

# Support

Ford Triplog is developed in my spare time and released free of charge.

If you enjoy using the integration, consider supporting future development:

**Ko-fi**

https://ko-fi.com/dompressor

Every contribution helps improve Ford Triplog.

---

# License

Released under the MIT License.
