# Ford Triplog

![Ford Triplog Banner](docs/images/banner.png)

<p align="center">
<b>Automatic Trip & Charging History for Ford EVs in Home Assistant</b>
</p>

<p align="center">

![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2026.6+-41BDF5?logo=homeassistant)
![HACS Default](https://img.shields.io/badge/HACS-Default-41BDF5)
![Python](https://img.shields.io/badge/Python-3.12+-3776AB?logo=python)
![License](https://img.shields.io/badge/License-MIT-green)
![Version](https://img.shields.io/github/v/release/weberdomi-ctrl/ford-triplog)

</p>

<p align="center">

**Automatic Trip Logging • Journey Management • Charging History • Smart Statistics • Intelligent Charging Location Recognition**


------------------------------------------------------------------------

Ford Triplog is a Home Assistant custom integration that automatically
records every trip and charging session of your Ford electric vehicle.

Built on top of the community-maintained FordPass integration, it
creates a permanent local driving history including detailed trip
statistics, charging history, energy calculations and charging location
recognition.

All data is stored locally inside Home Assistant.

No cloud backend.

No external database.

Your data always remains under your control.

------------------------------------------------------------------------

# Features

## 🚗 Automatic Trip Logging

-   Automatic trip detection
-   Start and end timestamps
-   Distance travelled
-   Driving duration
-   Average speed
-   State of Charge (SOC) consumption
-   Estimated energy consumption
-   Smart Trip support

## 🛣️ Journey Management

Ford Triplog automatically combines related trips and charging sessions into a single Journey.

Features include:

- Automatic Journey creation
- Multiple trips per Journey
- Multiple charging sessions per Journey
- Home-zone based Journey completion
- Configurable timeout and maximum gap
- Native Journey sensor


------------------------------------------------------------------------

## 🔋 Charging History

Automatically records every charging session including:

-   Charging duration
-   Start and end SOC
-   Estimated charged energy
-   Charging location
-   Charging provider
-   Linked trip (when available)

------------------------------------------------------------------------

## 📍 Intelligent Charging Location Recognition

Charging locations are resolved automatically using multiple sources.

Priority order:

1.  FordPass charging information
2.  User-defined charging locations
3.  Local OpenStreetMap charging database
4.  Reverse geocoding

This provides highly reliable charging location detection while allowing
complete user customization.

------------------------------------------------------------------------

## 🗺️ OpenStreetMap Charging Database

Ford Triplog includes an offline charging location database based on
OpenStreetMap.

Features include:

-   Offline operation
-   Country-specific databases
-   Automatic download
-   Geohash indexing
-   Fast local lookups
-   No internet required during normal operation

------------------------------------------------------------------------

## 📊 Statistics

Ford Triplog continuously maintains:

-   Trip statistics
-   Charging statistics
-   Lifetime statistics
-   Energy consumption
-   Average efficiency
-   Native Home Assistant sensors

------------------------------------------------------------------------

## 🏠 Home Assistant Integration

Designed specifically for Home Assistant.

Features include:

-   Native entities
-   Device diagnostics
-   Configuration Flow
-   Options Flow
-   Automatic recovery
-   Persistent local storage
-   HACS support

------------------------------------------------------------------------

## 🔒 Privacy

Privacy is one of the core design goals.

Ford Triplog never uploads:

-   Trip history
-   Charging history
-   Vehicle statistics
-   Location history

Everything remains inside your Home Assistant installation.

------------------------------------------------------------------------

# Documentation

  -------------------------------------------------------------------------------
  Documentation                                Description
  -------------------------------------------- ----------------------------------
  [Installation](docs/installation.md)         Install Ford Triplog using HACS

  [Configuration](docs/configuration.md)       Configure the integration

  [Architecture](docs/architecture.md)         Internal architecture and data
                                               flow

  [Smart Trip](docs/smart_trip.md)             Smart Trip functionality

  [Journeys](docs/journeys.md)                 Journey management and history |

  [Charging Sessions](docs/charging.md)        Charging session documentation

  [Charging                                    User charging locations and
  Locations](docs/charging_locations.md)       recognition

  [Charging                                    OpenStreetMap charging database
  Database](docs/charging_database.md)         

  [Sensors](docs/sensors.md)                   Complete entity reference

  [Dashboard Examples](docs/dashboard.md)      Example Home Assistant dashboards

  [Storage](docs/storage.md)                   Local storage structure

  [Privacy](docs/privacy.md)                   Privacy information

  [Automatation](docs/automation_examples.md)   Automation examples
     
  -------------------------------------------------------------------------------

------------------------------------------------------------------------

# Supported Vehicles

## Officially Tested

  Vehicle             Status
  ------------------ --------
  Ford Explorer EV      ✅

## Community Tested

  Vehicle           Status
  ---------------- --------
  Ford Capri EV       ✅
  Mustang Mach-E      🧪
  Puma Gen-E          🧪

Additional Ford electric vehicles are welcome.

------------------------------------------------------------------------

# Requirements

-   Home Assistant 2026.6 or newer
-   HACS
-   FordPass Home Assistant integration
-   Python 3.12+

------------------------------------------------------------------------

# Installation

Ford Triplog is installed through HACS.

See the complete installation guide:

➡ **[Installation Guide](docs/installation.md)**

------------------------------------------------------------------------

# Screenshots

Screenshots of dashboards, charging history and configuration are
available in the documentation.

➡ **[Dashboard Examples](docs/dashboard.md)**

------------------------------------------------------------------------

## What's new in Version 1.6.0

Version 1.6.0 is the largest Ford Triplog update so far and introduces
comprehensive journey management together with major charging-location
improvements.

### New features

-   Journey management with automatic Journey creation
-   Journey update, rebuild and delete tools
-   Home-zone based Journey completion
-   Configurable Journey home zone, timeout and maximum gap
-   OpenStreetMap charging-site database download and import
-   User-defined charging locations
-   Intelligent charging-site recognition with multiple data sources
-   Native Journey sensor
-   Improved configuration and options flow
-   Complete English, German and Polish translations

### Improvements

-   More reliable trip and charging detection
-   Improved multi-trip and multi-charge Journey handling
-   Improved Home Assistant integration
-   Better diagnostics and local storage handling

------------------------------------------------------------------------

# Roadmap

## Version 1.7

-   Charging cost calculation
-   Home charging tariffs
-   Seasonal electricity tariffs
-   Extended maintenance tools
-   Additional dashboard examples

## Version 1.8

-   Automatic charging database country switching
-   Optional database backend
-   Extended statistics
-   Long-term history
-   Multi-vehicle enhancements

Complete roadmap:

➡ **[ROADMAP.md](ROADMAP.md)**

------------------------------------------------------------------------

# Contributing

Bug reports, feature requests and pull requests are welcome.

Contribution guide:

➡ **[CONTRIBUTING.md](CONTRIBUTING.md)**

------------------------------------------------------------------------

# Support

If Ford Triplog is useful to you, consider supporting future
development.

```{=html}
<p align="center">
```
`<a href="https://ko-fi.com/dompressor">`{=html}
`<img src="https://storage.ko-fi.com/cdn/kofi3.png?v=3" width="220">`{=html}
`</a>`{=html}

```{=html}
</p>
```
Every contribution helps improving the project.

------------------------------------------------------------------------

# Changelog

See:

➡ **[CHANGELOG.md](CHANGELOG.md)**

Release information:

➡ **[RELEASE_NOTES.md](RELEASE_NOTES.md)**

------------------------------------------------------------------------

# License

Ford Triplog is released under the MIT License.

See **LICENSE** for details.

------------------------------------------------------------------------

# Disclaimer

Ford Triplog is an independent community project.

It is not affiliated with or endorsed by Ford Motor Company.

Ford®, FordPass® and all related trademarks belong to their respective
owners.

------------------------------------------------------------------------

```{=html}
<p align="center">
```
Made for the Home Assistant Community ❤️

If you like Ford Triplog, consider giving the project a ⭐ on GitHub.

```{=html}
</p>
```
