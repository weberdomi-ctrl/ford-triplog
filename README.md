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

Ford Triplog automatically combines related trips and charging sessions into a single Journey

Features include:

- Automatic Journey creation
- Automatic Journey rebuild
- Complete Journey timeline
- Multiple trips per Journey
- Multiple charging sessions per Journey
- Pause detection
- Home-zone based Journey completion
- Configurable timeout and maximum gap
- Native Journey sensor
- Local timezone support
- Rich dashboard attributes
- Journey energy balance
- Start and end battery state
- Battery energy flow calculation
- Charging cost summary
- Average charging price

------------------------------------------------------------------------

## ⏸️ Pause Management

Detected pauses can be enriched with additional information.

Features include:

- Title
- Category
- Location
- Notes
- Costs
- Manual editing
- Journey timeline integration

------------------------------------------------------------------------

## 🔋 Charging History

Automatically records every charging session including:

-   Charging duration
-   Start and end SOC
-   Estimated charged energy
-   Charging location
-   Charging provider
-   Linked trip (when available)
-   Journey integration
-   Charging station recognition
-   Manual charging cost editor
-   Seasonal home charging tariffs
-   Energy billed by charging provider
-   Charging loss calculation
-   Energy delivered vs. billed
-   Detailed charging cost breakdown
-   Automatic home charging cost calculation
-   Receipt management
-   Multiple receipts per charging session
-   PDF and image receipt upload
-   Optional OCR support
-   OCR parser profiles

------------------------------------------------------------------------


## 🧾 Receipt Management

Ford Triplog can manage charging receipts directly inside Home Assistant.

Features include:

- PDF and image receipt upload
- Multiple receipts per charging session
- Receipt browser
- Open stored receipts
- Delete receipts
- OCR integration (optional)
- User parser profiles
- Automatic charging data extraction

------------------------------------------------------------------------


## 📍 Intelligent Charging Location Recognition

Charging locations are resolved automatically using multiple sources.

Priority order:

1.  Home Assistant zones
2.  FordPass charging information
3.  Local OpenStreetMap charging database
4.  Address fallback

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

### Additional countries

The list of supported countries is defined in `countries.py`.

Advanced users can add additional countries manually by extending the `COUNTRIES` dictionary and generating the corresponding charging-site database.

------------------------------------------------------------------------

## 📊 Statistics

Ford Triplog continuously maintains:

-   Trip statistics
-   Charging statistics
-   Lifetime statistics
-   Energy consumption
-   Average efficiency
-   Native Home Assistant sensors
-   Journey energy balance
-   Journey charging costs
-   Average charging price
-   Battery energy delta
-   Total battery energy flow

------------------------------------------------------------------------

## 🏠 Home Assistant Integration

Designed specifically for Home Assistant.

Features include:

-   Native entities
-   Device diagnostics
-   Configuration Flow
-   Options Flow
-   Automatic recovery
-   Journey overview sensor
-   Rich Journey timeline attributes
-   Native Last Charge sensor
-   Native Journey overview sensor
-   Charging cost attributes
-   Journey energy attributes
-   Ready-to-use Markdown dashboard examples
-   Persistent local storage
-   HACS support
-   Receipt management
-   OCR configuration
-   Charging session editor
-   Pause editor
-   User charging location manager


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

  [OCR](docs/ocr.md)   OCR Receipt Recognition
     

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

## Features

- 🚗 Automatic trip detection using FordPass vehicle data
- 🧠 Smart Trip mode merges short stops into a single journey
- 🛣️ Journey Management with complete trip timelines
- ⚡ Automatic charging session detection
- 📍 Intelligent location recognition using:
  - Home Assistant zones
  - FordPass charging information
  - Offline OpenStreetMap charging database
  - Address fallback
- 🔋 Detailed trip metrics:
  - Distance
  - Duration
  - Energy consumption
  - Consumption (kWh/100 km)
  - Start and end State of Charge (SOC)
- ⚡ Detailed charging metrics:
  - Charged energy
  - Charging duration
  - SOC before and after charging
  - Energy billed by charger
  - Charging losses
  - Manual charging costs
  - Seasonal home charging tariffs
  - Charging cost breakdown
  - Effective charging price
- 📊 Journey statistics for Home Assistant dashboards
- 🧾 Receipt management
- 📄 PDF and image receipt support
- 🔍 Optional OCR integration
- ✏️ Pause management
- 💵 Charging cost editor
- 🧮 Charging loss calculation
- ⚖️ Journey energy balance
- 💰 Journey charging costs
- 🗺️ Offline charging station database
- 🌍 Multi-language support (English, German and Polish)
- 🔒 Local-first architecture with local JSON storage
- 🏠 Full Home Assistant integration
- 📦 HACS compatible

------------------------------------------------------------------------

## Dashboard Examples

Ready-to-use Home Assistant dashboard examples are available in:

Examples include:

- Vehicle overview
- Last Trip
- Last Charge
- Last Journey
- Journey timeline
- Charging history
- Charging cost overview
- Journey energy balance

`docs/examples/`

Simply copy the content into a Home Assistant Markdown card and adjust the entity IDs to match your installation.

------------------------------------------------------------------------

# Roadmap

## Version 2.x

- Route tracking
- Advanced journey editing
- Additional dashboard examples
- Multi-vehicle enhancements
- Optional database backend
- Long-term history improvements

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

➡ **[Buy me a Coffee](https://ko-fi.com/dompressor)**

Every contribution helps improving the project.

------------------------------------------------------------------------

# Changelog

See:

➡ **[CHANGELOG.md](CHANGELOG.md)**

Release information:

➡ **[RELEASE_NOTES.md](RELEASE_NOTES.md)**

------------------------------------------------------------------------

# Help translate Ford Triplog

Want to see Ford Triplog in your native language?

New translations and improvements to existing ones are always welcome. Simply submit a Pull Request with your translation files.

Every contribution helps make Ford Triplog more accessible to the Home Assistant community. Thank you!

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

# Made for the Home Assistant Community ❤️

If you like Ford Triplog, consider giving the project a ⭐ on GitHub.

