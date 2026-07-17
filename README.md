
<p align="center">
  <img src="docs/images/banner.png" alt="Ford Triplog Banner" width="100%">
</p>

<h1 align="center">Ford Triplog</h1>

<p align="center">
<b>Automatic Trip & Energy Logging for Ford vehicles in Home Assistant</b>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Home%20Assistant-2026.6%2B-41BDF5?logo=homeassistant" alt="HA">
  <img src="https://img.shields.io/badge/HACS-Coming%20Soon-41BDF5" alt="HACS">
  <img src="https://img.shields.io/badge/Version-1.2.0--beta-blue" alt="Version">
  <img src="https://img.shields.io/badge/License-MIT-green" alt="MIT">
  <img src="https://img.shields.io/badge/Python-3.12+-3776AB?logo=python" alt="Python">
</p>

---

## Why Ford Triplog?

The official FordPass integration provides vehicle data, but it does not maintain a complete trip history.

**Ford Triplog extends FordPass** by automatically recording every journey and exposing detailed trip statistics through native Home Assistant entities.

### Highlights

- 🚗 Automatic trip detection
- 📍 Start & destination addresses
- ⚡ Energy consumption (kWh)
- 🔋 Battery usage (SOC)
- 📈 Efficiency (kWh/100 km)
- 📊 Long-term statistics
- 🏠 100% local data storage
- 🔧 Native Home Assistant integration

---

# Screenshots

## Integration

![Integration](docs/images/integration.png)

*Ford Triplog integrates seamlessly into Home Assistant through Config Flow.*

## Options

![Options](docs/images/options.png)

*Smart Trip automatically merges short stops into a single trip.*

## Sensors

![Sensors](docs/images/sensors.png)

*Native Home Assistant sensors provide detailed information about your last trip and overall driving statistics.*

---

# Features

| Trip Logging | Energy | Statistics | Home Assistant |
|---|---|---|---|
| Automatic trip detection | Consumption (kWh) | Total distance | Config Flow |
| Smart Trip | Efficiency | Total energy | Options Flow |
| Start & End Address | SOC usage | Average consumption | Native Sensors |
| Driving Time | Average Speed | Trip History | Local Branding |

---

# Installation

## HACS *(coming soon)*

1. Add the Ford Triplog repository.
2. Install **Ford Triplog**.
3. Restart Home Assistant.
4. Add the integration from **Settings → Devices & Services**.

## Manual Installation

```text
custom_components/
└── ford_triplog/
```

Copy the folder into your Home Assistant configuration directory and restart Home Assistant.

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

### Added

- Last Consumption sensor
- Last Efficiency sensor
- Last Average Speed sensor
- Total Energy sensor
- Average Consumption sensor

### Improved

- Home Assistant SensorStateClass support
- Long-term statistics compatibility
- Dashboard compatibility

---

# Roadmap

### Next

- Charging history
- Charging statistics
- More trip analytics

### Future

- Multi-vehicle support
- GPX export
- CSV export
- Dashboard cards
- Maintenance tracking

---

# FAQ

### Does Ford Triplog replace FordPass?

No. It extends the official FordPass integration with comprehensive trip logging and statistics.

### Where is my data stored?

All trip data remains stored locally inside your Home Assistant instance.

### Does it support multiple vehicles?

Not yet. Multi-vehicle support is planned.

---

# Support

Ford Triplog is developed in my spare time.

If you enjoy using the integration and would like to support future development:

**☕ Ko-fi**

https://ko-fi.com/dompressor

Every contribution helps improve the project.

---

# Contributing

Bug reports, feature requests and pull requests are welcome.

---

# License

Released under the MIT License.
