# Version 2.0

## Planned Features

### Route Tracker

Introduce an optional and fully independent route tracking subsystem.

The Route Tracker will operate separately from the existing Trip and Journey processing and will not modify the current trip detection logic.

Planned features:

- Automatic route tracking using the existing IGNITION ON/OFF signals
- Separate route storage using dedicated JSON files
- Separate Route Tracker sensors
- Direct association of recorded routes with the corresponding Trip ID
- Route visualization in Home Assistant
- Journey route generation by combining the routes of individual trips
- Optional route tracking that does not affect normal Triplog operation if disabled or unavailable

#### Position Sources

Route tracking will use an extensible source adapter architecture.

Initial supported source types:

- ABRP using separate latitude and longitude entities
- Home Assistant Companion App using Geocoded Location data

All position sources will internally be normalized to:

- Timestamp
- Latitude
- Longitude

The adapter architecture allows additional position sources to be added later without changing the Route Tracker itself.

Potential future sources include:

- Ford / FordPass location data
- Home Assistant device trackers
- Traccar
- MQTT based GPS trackers
- Other vehicle integrations

---

### Trip History

Provide access to historical trip information directly from the Home Assistant dashboard.

Planned features:

- Browse previous trips
- Select trips by date or time period
- Display trip details
- Display recorded routes when Route Tracker data is available
- Efficient access to historical data without exposing large histories through sensor attributes

---

### Location Statistics

Add statistics based on historical trip and charging locations.

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

# Version Overview

| Version | Status      | Focus                                                   |
| ------- | ----------- | ------------------------------------------------------- |
| 1.5     | Released    | Charging locations, Smart Trip, documentation           |
| 1.6     | Released    | Automation, charging database improvements, dashboards  |
| 1.7     | Released    | Journey improvements, maintenance, charging integration |
| 1.8     | Released    | Charging costs, energy tracking, reporting              |
| 1.9     | Released    | Pause management, receipts, charging site improvements  |
| 2.0     | Development | Route tracking, trip history, location statistics       |
| Future  | Research    | Multi-vehicle support, exports, maintenance tracking    |