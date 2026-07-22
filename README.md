<p align="center">
  <img src="docs/images/banner.png" alt="Ford Triplog Banner" width="100%">
</p>

<h1 align="center">Ford Triplog</h1>

<p align="center">
<b>Complete Trip & Charging History for Ford vehicles in Home Assistant</b>
</p>

<p align="center">

![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2026.6+-41BDF5?logo=homeassistant)
![HACS Default](https://img.shields.io/badge/HACS-Default-41BDF5)
![Python](https://img.shields.io/badge/Python-3.12+-3776AB?logo=python)
![License](https://img.shields.io/badge/License-MIT-green)
![Version](https://img.shields.io/github/v/release/weberdomi-ctrl/ford-triplog)

</p>

<p align="center">

Automatic trip logging • Charging history • Smart statistics • Native Home Assistant integration

</p>

---

Ford Triplog extends the official FordPass integration by automatically recording every trip and charging session.

Designed specifically for Ford electric vehicles, it provides detailed trip history, charging history, energy statistics and native Home Assistant sensors while keeping **all data stored locally** inside Home Assistant.

No cloud services. No external database. Full control over your own driving history.
# Installation

## Requirements

Before installing Ford Triplog, make sure the following requirements are met:

| Requirement | Status |
| :---------- | :----: |
| Home Assistant 2026.6 or newer | ✅ |
| HACS installed | ✅ Recommended |
| FordPass Integration configured | ✅ Required |
| Supported Ford vehicle | ✅ |

> [!IMPORTANT]
> Ford Triplog extends the official FordPass integration and **does not replace it**.
>
> Install and configure the FordPass integration before adding Ford Triplog.

---

## Install with HACS (Recommended)

The easiest way to install Ford Triplog is through HACS.

[![Open your Home Assistant instance and open this repository in HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=weberdomi-ctrl&repository=ford-triplog)

### Steps

1. Open **HACS**
2. Search for **Ford Triplog**
3. Click **Download**
4. Restart Home Assistant
5. Go to **Settings → Devices & Services**
6. Click **Add Integration**
7. Select **Ford Triplog**

---

## Manual Installation

1. Download the latest release.
2. Copy

```
custom_components/ford_triplog
```

to

```
config/custom_components/
```

3. Restart Home Assistant.
4. Add the integration from **Devices & Services**.

---

## Initial Configuration

Ford Triplog automatically detects compatible FordPass entities.

Simply select:

- 🚗 Vehicle Tracker
- 🔑 Ignition Sensor
- 📏 Odometer Sensor
- 🔋 State of Charge Sensor

After completing the setup, Ford Triplog immediately starts recording trips and charging sessions.

---

## Configuration Options

| Option | Description |
| :------ | :---------- |
| Smart Trip | Merge short stops into one trip |
| Smart Trip Timeout | Time before a trip is finalized |
| Battery Capacity | Used for energy calculations |

---

# How It Works

Ford Triplog continuously monitors vehicle data provided by the FordPass integration.

Whenever the vehicle starts moving, a new trip is created automatically.

During the trip, Ford Triplog records:

- Start time
- End time
- Distance
- Driving duration
- Start & End SOC
- Energy consumption
- Start & Destination address

When charging is detected, a charging session is automatically created containing:

- Charging duration
- Charging location
- Start & End SOC
- Added energy
- Linked trip (when applicable)

Everything is stored locally in JSON format inside Home Assistant.

No external services are used.

---

# Smart Trip

Smart Trip prevents unnecessary trip splitting.

Instead of creating multiple short trips—for example when stopping briefly at a bakery, traffic light, parcel station or charging stop—Ford Triplog intelligently merges them into a single journey.

Benefits:

- Cleaner history
- More realistic trip statistics
- Better energy calculations
- Reduced fragmentation

The timeout is fully configurable in the integration options.

---

# Local Storage

Ford Triplog stores all information locally.

```
/config/.storage/ford_triplog/
```

This includes:

- Trip history
- Charging history
- Statistics
- Last trip
- Last charging session
- Active trip recovery
- Active charging recovery

> [!NOTE]
> Your driving history never leaves your Home Assistant installation.
# Sensors

Ford Triplog creates a comprehensive set of native Home Assistant sensors.

These sensors can be used in dashboards, automations, statistics, energy dashboards or custom cards.

---

# Last Trip

These sensors always represent the **most recently completed trip**.

| Sensor | Unit | Description |
| :------ | :--: | :---------- |
| Last Start Address | — | Human readable trip start address |
| Last Destination Address | — | Human readable destination |
| Last Distance | km | Trip distance |
| Last Driving Time | — | Formatted driving duration |
| Last Driving Time (Raw) | s | Duration in seconds |
| Last Average Speed | km/h | Average speed |
| Last Energy Used | kWh | Estimated energy consumption |
| Last Consumption | kWh/100 km | Average efficiency |
| Last Start SOC | % | Battery level at departure |
| Last End SOC | % | Battery level at arrival |
| Last SOC Used | % | Battery percentage consumed |
| Last Start Time | — | Trip start timestamp |
| Last End Time | — | Trip end timestamp |

> [!TIP]
> These sensors are perfect for Lovelace dashboards showing your latest drive.

---

# Last Charging Session

These sensors describe the latest completed charging session.

| Sensor | Unit | Description |
| :------ | :--: | :---------- |
| Last Charge Address | — | Charging location |
| Last Charge Duration | — | Formatted charging time |
| Last Charge Duration (Raw) | s | Charging time in seconds |
| Last Charge Start Time | — | Charging start |
| Last Charge End Time | — | Charging end |
| Last Charge Start SOC | % | Battery before charging |
| Last Charge End SOC | % | Battery after charging |
| Last Charge SOC Added | % | SOC gained |
| Last Energy Added | kWh | Estimated charged energy |

---

# Statistics

Ford Triplog continuously calculates long-term statistics.

| Sensor | Unit | Description |
| :------ | :--: | :---------- |
| Trip Count | trips | Total recorded trips |
| Charge Count | charges | Total charging sessions |
| Total Distance | km | Overall distance |
| Total Driving Time | — | Total driving duration |
| Total Energy Used | kWh | Overall consumption |
| Average Trip Distance | km | Average trip length |
| Average Trip Duration | — | Average driving time |
| Average Trip Energy | kWh | Average energy per trip |
| Average Consumption | kWh/100 km | Overall efficiency |
| Average Trip SOC Used | % | Average battery usage |
| Average Charge Duration | — | Average charging time |
| Average Charge Start SOC | % | Average charging start |
| Average Charge End SOC | % | Average charging end |
| Average Charge SOC Added | % | Average SOC gained |

---

# Dashboard Example

Ford Triplog integrates perfectly into Home Assistant dashboards.

Typical dashboard cards include:

- 🚗 Last Trip
- ⚡ Last Charging Session
- 📈 Lifetime Statistics
- 🔋 Battery Efficiency
- 🛣 Average Consumption
- 📍 Last Destination

Example:

```
┌─────────────────────────────┐
│ Ford Explorer EV            │
├─────────────────────────────┤
│ Last Trip                   │
│ 42.8 km                     │
│ 15.9 kWh/100 km             │
│ 68 min                      │
├─────────────────────────────┤
│ Last Charge                 │
│ 28 % → 80 %                 │
│ 41 min                      │
├─────────────────────────────┤
│ Total Distance              │
│ 18,452 km                   │
└─────────────────────────────┘
```

Dashboard layouts are fully customizable using standard Home Assistant cards.

---

# Performance

Ford Triplog has been optimized for long-term usage.

Recent versions introduced:

- Shared statistics cache
- Optimized JSON access
- Reduced disk I/O
- Faster sensor updates
- Improved coordinator synchronization

Even installations with thousands of recorded trips remain responsive.

---

# Data Storage

All information is stored locally.

```
/config/.storage/ford_triplog/
```

Folder structure:

```
ford_triplog/

├── active_trip.json
├── active_charge.json
├── last_trip.json
├── last_charge.json
├── statistics.json
├── trips/
└── charges/
```

No cloud service.

No telemetry.

No tracking.

Everything belongs to you.
# FordPass vs Ford Triplog

Ford Triplog is **not a replacement** for the official FordPass integration.

Instead, it builds on top of FordPass and adds the long-term history and statistics that many EV drivers are missing.

| Feature | FordPass | Ford Triplog |
| :------ | :------: | :----------: |
| Live vehicle status | ✅ | ✅ (via FordPass) |
| Vehicle location | ✅ | ✅ |
| Battery level | ✅ | ✅ |
| Trip history | ❌ | ✅ |
| Charging history | ❌ | ✅ |
| Smart Trip | ❌ | ✅ |
| Energy calculation | ❌ | ✅ |
| Driving statistics | ❌ | ✅ |
| Charging statistics | ❌ | ✅ |
| Home Assistant sensors | Limited | 30+ |
| Local JSON history | ❌ | ✅ |
| Recovery after restart | ❌ | ✅ |

> [!TIP]
> FordPass provides the live vehicle data.
>
> Ford Triplog transforms this data into a permanent trip and charging history.

---

# Privacy

Privacy was one of the primary design goals of Ford Triplog.

All trips, charging sessions and statistics remain inside your own Home Assistant installation.

Ford Triplog does **not**:

- upload trip history
- upload charging history
- use external databases
- send telemetry
- collect analytics
- require user accounts

Everything stays on your own system.

> [!IMPORTANT]
> Your driving history belongs to you.

---

# Backup & Restore

Backing up Ford Triplog is simple.

Copy the following folder:

```
/config/.storage/ford_triplog/
```

This folder contains:

- Complete trip history
- Complete charging history
- Statistics
- Last trip
- Last charging session
- Active trip
- Active charging session

## Restore

1. Install Ford Triplog.
2. Stop Home Assistant.
3. Copy the backup folder.
4. Start Home Assistant.

Ford Triplog automatically restores all data.

---

# Supported Vehicles

Ford Triplog currently focuses on modern Ford electric vehicles supported by the FordPass integration.

## Officially Tested

| Vehicle | Status |
| :------ | :----: |
| Ford Explorer EV | ✅ |

## Community Tested

| Vehicle | Status |
| :------ | :----: |
| Ford Capri EV | ✅ |
| Mustang Mach-E | 🧪 |
| Puma Gen-E | 🧪 |

> [!NOTE]
> Additional vehicles are welcome.
>
> Please open an issue if you successfully tested Ford Triplog with another Ford model.

---

# Frequently Asked Questions

<details>

<summary><strong>Does Ford Triplog replace FordPass?</strong></summary>

No.

FordPass is still required because it provides the live vehicle information.

Ford Triplog extends the integration with trip history, charging history and statistics.

</details>

<details>

<summary><strong>Where is my data stored?</strong></summary>

All data is stored locally inside your Home Assistant configuration.

No cloud storage is used.

</details>

<details>

<summary><strong>Can I export my trips?</strong></summary>

CSV and GPX export are planned for a future release.

</details>

<details>

<summary><strong>Does it support multiple vehicles?</strong></summary>

Not yet.

Multi vehicle support is planned.

</details>

<details>

<summary><strong>Can I lose my trip history?</strong></summary>

Not if you back up

```
/config/.storage/ford_triplog/
```

regularly.

</details>

---

# Roadmap

## Version 1.4

### Charging

- Smart Charge (Pause / Resume)
- Named charging locations
- AC / DC detection
- Charging provider lookup
- Improved charging statistics

---

## Version 1.5

### Dashboard

- Dashboard cards
- Interactive maps
- CSV export
- GPX export
- Monthly statistics

---

## Version 1.6

### Multi Vehicle

- Multiple Ford vehicles
- Vehicle selector
- Separate statistics
- Dashboard improvements

---

## Version 1.7

### Maintenance

- Charging costs
- Maintenance reminders
- Statistics rebuild
- Data maintenance tools

---

# Contributing

Contributions are welcome.

You can help by:

- Reporting bugs
- Suggesting new features
- Testing new releases
- Improving documentation
- Submitting pull requests

Please use the GitHub issue tracker for all bug reports and feature requests.

---

# Support

If Ford Triplog is useful to you and you would like to support future development, you can buy me a coffee.

<p align="center">

<a href="https://ko-fi.com/dompressor">
<img src="https://storage.ko-fi.com/cdn/kofi3.png?v=3" width="220">
</a>

</p>

Every contribution helps to improve the integration.

---

# License

Ford Triplog is released under the MIT License.

See the LICENSE file for details.

---

<p align="center">

Made with ❤️ for the Home Assistant community.

</p>
# Dashboard

Ford Triplog integrates seamlessly into Home Assistant dashboards.

Use the provided sensors with any standard Lovelace card or create your own custom dashboard.

## Example Dashboard

| Card | Description |
| :--- | :---------- |
| Last Trip | Shows the latest completed trip |
| Last Charging Session | Displays charging information |
| Vehicle Statistics | Overall driving statistics |
| Battery Efficiency | Consumption and energy usage |
| Lifetime Statistics | Total distance, trips and charging sessions |

---

## Example Layout

+------------------------------------------------------+
| 🚗 Ford Explorer EV                                  |
+------------------------------------------------------+

+----------------------+------------------------------+
| Last Trip            | Last Charging Session        |
| 42.8 km              | 65 % → 80 %                 |
| 15.9 kWh /100 km     | 34 minutes                  |
| 52 min               | 12.3 kWh                    |
+----------------------+------------------------------+

+------------------------------------------------------+
| Statistics                                           |
| Total Distance      18 452 km                        |
| Trips                  486                           |
| Charges                132                           |
| Average Consumption 16.3 kWh/100 km                  |
+------------------------------------------------------+

---

The dashboard shown above is only one possible layout.

Because Ford Triplog exposes native Home Assistant entities, you are free to create your own dashboard.

---

# Automations

Ford Triplog sensors can also be used inside Home Assistant automations.

Typical examples include:

- Notify when charging has finished
- Notify after every completed trip
- Calculate charging costs
- Weekly driving statistics
- Monthly energy report
- Vehicle maintenance reminders

Example:

```yaml
alias: Notify after Trip

trigger:

- platform: state
entity_id: sensor.ford_triplog_last_distance

action:

- service: notify.mobile_app
data:
message: >
Trip completed:
{{ states('sensor.ford_triplog_last_distance') }} km
```

---

# Energy Calculations

Ford Triplog estimates energy consumption using:

- usable battery capacity
- State of Charge difference
- driven distance

Estimated values include:

- Energy Used (kWh)
- Energy Added (kWh)
- Consumption (kWh /100 km)

Battery capacity can be configured in the integration options.

---

# Storage Structure

Ford Triplog keeps everything organized in simple JSON files.

```
ford_triplog/

statistics.json

last_trip.json

last_charge.json

active_trip.json

active_charge.json

trips/

2026/

07/

trip_20260721_083012.json

trip_20260721_175401.json

charges/

2026/

07/

charge_20260720_201155.json
```

Advantages:

- Easy backup
- Human readable
- No database required
- Fast recovery
- Future proof

---

# Recovery

Unexpected Home Assistant restart?

No problem.

Ford Triplog automatically restores:

- active trips
- active charging sessions
- statistics cache

The integration continues automatically without losing data.

---

# Performance

Ford Triplog was designed for long-term usage.

Optimizations include:

✔ Shared statistics cache

✔ Atomic JSON writes

✔ Reduced disk access

✔ Optimized coordinator updates

✔ Native Home Assistant coordinator

✔ Efficient sensor refresh

This keeps CPU and disk usage low even after years of recorded trips.

---

# Planned Features

The roadmap focuses on practical features requested by the community.

### Charging

- Smart Charge Pause / Resume
- AC / DC recognition
- Charging provider
- Named charging locations

### Dashboard

- Dashboard cards
- Interactive maps
- Monthly reports

### Statistics

- Charging costs
- Cost per kilometer
- Yearly statistics
- Export

### Fleet

- Multiple vehicles
- Vehicle comparison
- Combined statistics

---

# Project Philosophy

Ford Triplog follows four simple principles.

## Local First

Everything stays inside Home Assistant.

## Privacy First

No tracking.

No analytics.

No cloud.

## Home Assistant Native

No additional database.

No external services.

No custom frontend required.

## Reliability

The integration is designed to recover automatically after unexpected restarts without losing trip or charging data.

---

# Credits

Developed by

Dominik Weber

Community testing by Ford EV owners.

Special thanks to everyone reporting bugs, testing beta versions and suggesting new features.

---

# Support Development

If Ford Triplog saves you time or provides useful insights into your vehicle, consider supporting future development.

☕

Ko-fi

https://ko-fi.com/dompressor

Every coffee helps improving Ford Triplog.

---

# Star the Project

If you like Ford Triplog,

⭐ Star the repository on GitHub.

It helps other Ford owners discover the project.
# Troubleshooting

Most issues can be resolved with a few simple checks.

---

## No trips are recorded

Verify that the following entities are correctly configured:

- Vehicle Tracker
- Odometer Sensor
- Ignition Sensor
- State of Charge Sensor

Also verify that the FordPass integration is updating correctly.

---

## No charging sessions are recorded

Charging detection requires:

- Vehicle connected to a charger
- FordPass reports charging status
- State of Charge sensor updating

Charging sessions are finalized automatically after charging stops.

---

## Incorrect distance

Ford Triplog uses the odometer provided by FordPass.

If the odometer sensor reports incorrect values, the calculated trip distance will also be incorrect.

---

## Incorrect energy calculation

Energy calculations depend on the configured usable battery capacity.

Check:

Settings

↓

Devices & Services

↓

Ford Triplog

↓

Configure

↓

Usable Battery Capacity

---

## Statistics seem incorrect

Statistics are updated automatically after every completed trip and charging session.

If you imported or manually edited data, a future version will provide a statistics rebuild tool.

---

# Architecture

Ford Triplog is intentionally simple.

```

FordPass Integration

↓

Vehicle Data

↓

Ford Triplog Coordinator

↓

Trip Detection

↓

Charging Detection

↓

History Engine

↓

Statistics Engine

↓

Home Assistant Sensors

```

The integration relies entirely on native Home Assistant components.

No additional services are required.

---

# Design Goals

Ford Triplog follows a few core principles.

## Simplicity

Easy installation.

No complex setup.

---

## Reliability

Automatic recovery after restart.

Atomic file storage.

Duplicate protection.

---

## Performance

Optimized storage access.

Shared statistics cache.

Minimal disk I/O.

---

## Privacy

100% local.

No telemetry.

No analytics.

No cloud.

---

# Version History

| Version | Highlights |
| :------ | :--------- |
| 1.0 | Initial trip logging |
| 1.1 | Smart Trip |
| 1.2 | Charging support |
| 1.3 | Statistics, energy calculation, recovery, trip ↔ charge linking |
| 1.4 | Planned charging improvements |
| 1.5 | Planned dashboard enhancements |
| 1.6 | Planned multi vehicle support |

---

# Community

Ford Triplog is developed in spare time.

Community feedback directly influences future releases.

Feature requests are always welcome.

---

# Reporting Bugs

When reporting an issue, please include:

- Home Assistant version
- Ford Triplog version
- FordPass version
- Vehicle model
- Relevant log entries
- Steps to reproduce

This helps diagnosing problems much faster.

---

# Feature Requests

Ideas are welcome.

Please describe:

- the use case
- the expected behaviour
- why the feature would be useful

The more information provided, the easier it is to evaluate and implement.

---

# Release Cycle

Ford Triplog follows semantic versioning.

Patch Release

1.3.1

- Bug fixes
- Stability improvements

Minor Release

1.4

- New functionality
- Backwards compatible

Major Release

2.0

- Larger architectural improvements
- New concepts

---

# Acknowledgements

Ford Triplog would not exist without:

- Home Assistant
- HACS
- FordPass Integration
- OpenStreetMap
- The Home Assistant Community
- All beta testers

Thank you for making this project possible.

---

# Disclaimer

Ford Triplog is an independent community project.

It is not affiliated with or endorsed by Ford Motor Company.

Ford®, FordPass® and related trademarks belong to their respective owners.

---

<p align="center">

## Drive.

## Charge.

## Analyze.

### Ford Triplog

Made for the Home Assistant Community

⭐ If you enjoy the project, consider starring it on GitHub.

</p>
