<p align="center">
  <img src="docs/images/banner.png" alt="Ford Triplog Banner" width="100%">
</p>

<h1 align="center">Ford Triplog</h1>

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

Automatic Trip Logging • Charging History • Smart Statistics • Local Storage

</p>

---

Ford Triplog extends the **FordPass** integration maintained by the Home Assistant GitHub community (https://github.com/marq24/ha-fordpass) by automatically recording every trip and charging session.

Designed for modern Ford electric vehicles, it creates a permanent driving history with detailed statistics, energy calculations and native Home Assistant sensors while keeping **all data stored locally** inside your Home Assistant installation.

No cloud services. No external database. Your data always remains under your control.

---

# Features

✔ Automatic trip detection

✔ Automatic charging history

✔ Smart Trip (merge short stops)

✔ Trip & charging statistics

✔ Automatic Charging-Site Recognition

✔ Local OpenStreetMap charging-site database

✔ Native Home Assistant sensors

✔ Energy consumption calculations

✔ Local JSON storage

✔ Automatic recovery after Home Assistant restart

✔ Privacy-first design



---

# Architecture

Detailed documentation of the integration architecture, component design, data flow, and internal processing.

➡ **[Architecture](docs/architecture.md)**


---

# Installation

Ford Triplog is available through **HACS**.

See the complete installation guide:

➡ **[Installation Guide](docs/installation.md)**

---

# Configuration

After installation simply select:

- Vehicle Tracker
- Ignition Sensor
- Odometer Sensor
- State of Charge Sensor

Optional settings include:

- Smart Trip
- Smart Trip Timeout
- Battery Capacity
- Charging-site country

Charging-site databases can be downloaded directly from the integration options.

Full configuration guide:

➡ **[Configuration](docs/configuration.md)**

---

# Smart Trip

Smart Trip intelligently merges short stops into a single journey.

Instead of creating multiple trips for short breaks, Ford Triplog automatically combines them into one continuous trip, resulting in cleaner statistics and a more realistic driving history.

More information:

➡ **[Smart Trip Documentation](docs/smart_trip.md)**

---

# Charging History

Charging sessions are detected automatically.

Ford Triplog records:

- Charging duration
- Estimated charged energy
- Start & End State of Charge
- Charging location
- Charging-site recognition
- Charging provider information
- Linked trip (when applicable)

More information:

➡ **[Charging Documentation](docs/charging.md)**

---

# Sensors

Ford Triplog exposes a comprehensive set of native Home Assistant entities including:

- Last Trip
- Last Charging Session
- Lifetime Statistics
- Energy Consumption
- Driving Statistics
- Battery Statistics

Complete sensor reference:

➡ **[Sensor Documentation](docs/sensors.md)**

---

# Dashboard

All sensors are designed for native Home Assistant dashboards.

Example dashboards and automation ideas are available here:

➡ **[Dashboard Examples](docs/dashboard.md)**

---

# Local Storage

All trips, charging sessions and statistics are stored locally.

```
/config/.storage/ford_triplog/
```

Backup and storage details:

➡ **[Storage Documentation](docs/storage.md)**

---

# Privacy

Privacy is one of the core design goals.

Ford Triplog never uploads:

- Trip history
- Charging history
- Statistics
- Vehicle data

Everything stays inside your Home Assistant installation.

More information:

➡ **[Privacy](docs/privacy.md)**

---

# Supported Vehicles

Officially tested:

| Vehicle | Status |
| :------ | :----: |
| Ford Explorer EV | ✅ |

Community tested:

| Vehicle | Status |
| :------ | :----: |
| Ford Capri EV | ✅ |
| Mustang Mach-E | 🧪 |
| Puma Gen-E | 🧪 |

Additional vehicles are welcome.

---

# FAQ

Frequently asked questions are available here:

➡ **[FAQ](FAQ.md)**

---

# Roadmap

Upcoming features include:

- Smart Charge (Pause / Resume)
- Charging Cost Calculation
- AC/DC Detection
- Multi Vehicle Support
- Journey timeline (combine trips and charging sessions)

Complete roadmap:

➡ **[ROADMAP.md](ROADMAP.md)**

---

# Contributing

Bug reports, feature requests and pull requests are always welcome.

Contribution guidelines:

➡ **[CONTRIBUTING.md](CONTRIBUTING.md)**

---

# Support

If Ford Triplog is useful to you, consider supporting future development.

<p align="center">

<a href="https://ko-fi.com/dompressor">
<img src="https://storage.ko-fi.com/cdn/kofi3.png?v=3" width="220">
</a>

</p>

Every contribution helps improving the project.

---

# License

Ford Triplog is released under the MIT License.

See **LICENSE** for details.

---

# Disclaimer

Ford Triplog is an independent community project.

It is not affiliated with or endorsed by Ford Motor Company.

Ford®, FordPass® and related trademarks belong to their respective owners.

---

<p align="center">

Made for the Home Assistant Community ❤️

If you like Ford Triplog, consider ⭐ starring the repository on GitHub.

</p>
