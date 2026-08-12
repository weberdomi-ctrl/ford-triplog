# Ford Triplog Roadmap

This roadmap describes planned development after the current Ford Triplog 2.0.x releases.

---

# Version 2.0.x

## Planned Features

### Trip History

Extend the existing date-based History views with direct access to individual historical trips.

Planned features:

- Browse previous trips
- Select trips by date or time period
- Display individual trip details
- Display recorded routes when Route Tracker data is available
- Efficient access to historical data without exposing large histories through sensor attributes

The existing Journey History, Route History and Charging History views remain available independently.

---

### Location Statistics

Add additional statistics based on historical trip and charging locations.

Planned statistics:

- Top starting locations
- Top destinations
- Top charging locations
- Number of visits / trips
- Charging sessions per location
- Charged energy per charging location
- Charging costs per charging location

Home and Work zones should be grouped consistently using the existing Ford Triplog location handling.

---

## Version 2.0.3 – Planned Maintenance

Planned technical cleanup and consolidation after the 2.0.2 release:

- Use English consistently as the internal base language and translation fallback
- Consolidate translation keys and entity naming
- General code cleanup after the 2.0.x feature expansion
- Continue improving statistics and dashboard integration where required

---

# Future Research

Potential future development areas include:

- Multi-vehicle support and improvements
- Data export options
- Maintenance tracking
- Long-term history improvements
- Optional SQLite acceleration for larger local histories

---

# Version Overview

| Version | Status   | Focus |
| ------- | -------- | ----- |
| 1.5 | Released | Charging locations, Smart Trip, documentation |
| 1.6 | Released | Automation, charging database improvements, dashboards |
| 1.7 | Released | Journey improvements, maintenance, charging integration |
| 1.8 | Released | Charging costs, energy tracking, reporting |
| 1.9 | Released | Pause management, receipts, charging site improvements |
| 2.0.0 | Released | GPS Route Tracker |
| 2.0.1 | Released | Daily History, Journey History, Route History, Charging History |
| 2.0.2 | Released | Top Statistics, Route Tracker improvements, optional OSRM route matching |
| 2.0.3 | Planned | Internal language/translation cleanup and 2.0.x consolidation |
| Future | Research | Multi-vehicle support, exports, maintenance tracking, long-term history |
