\
<p align="center">
  <img src="docs/images/banner.png" alt="Ford Triplog Banner" width="100%">
</p>

<h1 align="center">Ford Triplog</h1>

<p align="center">
Automatic Trip & Energy Logging for Ford vehicles in Home Assistant
</p>

<p align="center">
  <a href="#"><img src="https://img.shields.io/badge/Home%20Assistant-2026.6%2B-41BDF5?logo=homeassistant" alt="HA"></a>
  <a href="#"><img src="https://img.shields.io/badge/HACS-Coming%20Soon-41BDF5" alt="HACS"></a>
  <a href="#"><img src="https://img.shields.io/badge/Version-1.2.0--beta-blue" alt="Version"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-green" alt="MIT"></a>
  <a href="#"><img src="https://img.shields.io/badge/Python-3.12+-3776AB?logo=python" alt="Python"></a>
</p>

---

## Contents

- [Overview](#overview)
- [Features](#features)
- [Screenshots](#screenshots)
- [Installation](#installation)
- [Sensors](#sensors)
- [What's New](#whats-new-in-120)
- [Roadmap](#roadmap)
- [FAQ](#faq)
- [Support](#support)

---

# Overview

Ford Triplog extends the FordPass integration by automatically recording every completed trip and exposing detailed driving statistics through native Home Assistant sensors.

Unlike FordPass, the integration keeps a persistent trip history including:

- Distance
- Driving time
- Average speed
- Battery usage (SOC)
- Energy consumption
- Efficiency
- Start & destination addresses
- Long-term statistics

All data remains **local** in Home Assistant.

---

# Features

| 🚗 Trip Logging | ⚡ Energy | 📊 Statistics | 🏠 Home Assistant |
|---|---|---|---|
| Automatic trip detection | Consumption (kWh) | Total distance | Config Flow |
| Smart Trip | Efficiency | Total energy | Options Flow |
| Start & destination | SOC usage | Average consumption | Native sensors |
| Driving time | Average speed | Trip history | Local branding |

---

# Screenshots

> Replace placeholders before the public release.

| Integration | Dashboard |
|-------------|-----------|
| ![](docs/images/integration.png) | ![](docs/images/dashboard.png) |

| Trip History | Statistics |
|--------------|------------|
| ![](docs/images/history.png) | ![](docs/images/statistics.png) |

---

# Installation

## HACS *(coming soon)*

1. Add the repository.
2. Install **Ford Triplog**.
3. Restart Home Assistant.
4. Add the integration.

## Manual

```text
custom_components/
└── ford_triplog/
```

Restart Home Assistant and add the integration.

---

# Sensors

## Last Trip

| Sensor | Unit |
|---|---|
| Last Start Address | — |
| Last End Address | — |
| Last Distance | km |
| Last Driving Time | formatted |
| Last Duration (Raw) | s |
| Last SOC Used | % |
| Last Consumption | kWh |
| Last Efficiency | kWh/100 km |
| Last Average Speed | km/h |

## Statistics

| Sensor | Unit |
|---|---|
| Trip Count | trips |
| Total Distance | km |
| Total Energy | kWh |
| Average Consumption | kWh/100 km |
| Total Driving Time | formatted |
| Total Duration (Raw) | s |

---

# What's New in 1.2.0

### New

- Last Consumption sensor
- Last Efficiency sensor
- Last Average Speed sensor
- Total Energy sensor
- Average Consumption sensor

### Improved

- SensorStateClass support
- Long-term statistics
- Dashboard compatibility

---

# Roadmap

### Version 1.2

- Charging history
- Charging statistics
- More analytics

### Future

- Multi vehicle support
- GPX export
- CSV export
- Dashboard cards
- Maintenance tracking

---

# FAQ

**Does Ford Triplog replace FordPass?**

No. It extends the FordPass integration with trip logging and statistics.

**Where is my data stored?**

Everything is stored locally inside Home Assistant.

**Does it support multiple vehicles?**

Not yet.

---

# Support

Ford Triplog is developed in my spare time.

If you enjoy using it, consider supporting future development:

☕ https://ko-fi.com/dompressor

---

# Contributing

Bug reports, feature requests and pull requests are welcome.

---

# License

MIT License
