# Dashboard Examples

Ford Triplog is designed to work seamlessly with native Home Assistant dashboards.

All entities can be used with standard Lovelace cards without requiring custom frontend components.

This document presents several dashboard ideas that can be adapted to your own installation.

---

# Vehicle Overview

A simple dashboard showing the current vehicle status.

Recommended cards:

- Tile Card
- Entity Card
- Gauge Card

Suggested entities:

- Current State of Charge
- Vehicle Location
- Odometer
- Last Trip Distance
- Last Charging Session
- Charging Database Status

Example:

```
+----------------------------------+
| Ford Explorer EV                 |
|                                  |
| SOC                74 %          |
| Odometer       24,618 km         |
| Last Trip         43.7 km        |
| Last Charge       Yesterday      |
+----------------------------------+
```

---

# Last Trip

Display detailed information about the most recently completed trip.

Suggested entities:

- Last Trip Distance
- Last Trip Duration
- Average Speed
- Energy Consumption
- Consumption (kWh/100 km)
- Start SOC
- End SOC

Example:

```
Last Trip

Distance            42.8 km

Duration            00:38

Average Speed       67 km/h

SOC

82 %

↓

64 %

Consumption

17.1 kWh/100 km
```

---

# Last Charging Session

Display information about the most recent charging session.

Suggested entities:

- Charging Duration
- Charged Energy
- Start SOC
- End SOC
- Charging Location
- Charging Provider

Example:

```
Last Charging

Location

IONITY Neuenkirch

Start SOC

18 %

End SOC

82 %

Charged Energy

51.4 kWh

Duration

00:29
```

---

# Lifetime Statistics

A dashboard showing accumulated statistics.

Recommended cards:

- Statistics Card
- Tile Card
- Entity Card

Typical entities:

- Total Trips
- Total Distance
- Total Driving Time
- Average Consumption
- Total Charging Sessions
- Total Charged Energy

Example:

```
Statistics

Trips

248

Distance

18,642 km

Charging Sessions

92

Average Consumption

17.4 kWh/100 km
```

---

# Charging Overview

Create a dedicated charging dashboard.

Suggested entities:

- Last Charging Location
- Charging Provider
- Charging Network
- Charged Energy
- Charging Duration
- Charging Database Status

This dashboard is particularly useful for users who frequently use public charging infrastructure.

---

# Energy Dashboard

Ford Triplog integrates well with the Home Assistant Energy Dashboard.

Recommended entities include:

- Estimated charged energy
- Estimated trip energy consumption

Future versions will expand support for charging cost calculations.

---

# Mobile Dashboard

For phones and tablets, a compact dashboard is recommended.

Suggested layout:

```
SOC

↓

Last Trip

↓

Last Charge

↓

Statistics
```

Only the most important entities should be displayed to keep the interface clean.

---

# Tablet Dashboard

Larger displays allow additional information.

Example layout:

```
+----------------+----------------+

Vehicle Status   Last Trip

+----------------+----------------+

Charging         Statistics

+----------------+----------------+

Map              History

+---------------------------------+
```

---

# History Dashboard

Combine Home Assistant history cards with Ford Triplog sensors.

Useful examples include:

- State of Charge history
- Odometer history
- Trip distance history
- Charging energy history

This provides a visual overview of long-term vehicle usage.

---

# Map Dashboard

Combine the Home Assistant Map Card with:

- Vehicle Tracker
- Charging Locations

This allows the current vehicle position to be viewed together with known charging locations.

---

# Automation Dashboard

A dedicated dashboard can display automation status.

Examples:

- Charging Finished Notification
- Vehicle Arrived Home
- Vehicle Left Home
- Smart Trip Active

This is useful for debugging automations.

---

# Recommended Layout

A good overall dashboard might look like this:

```
Vehicle

↓

Current Status

↓

Last Trip

↓

Last Charging Session

↓

Lifetime Statistics

↓

History Graphs
```

This layout provides quick access to the most frequently used information while keeping the dashboard easy to read.

---

# Native Home Assistant

All examples in this documentation use only standard Home Assistant cards.

No custom Lovelace cards are required.

Users are free to enhance their dashboards using community cards such as Mushroom or Bubble Card, but Ford Triplog does not depend on them.

---

# Future Dashboard Templates

Future releases will include ready-to-import dashboard templates.

Planned examples include:

- Vehicle Overview
- Last Trip
- Last Charging Session
- Lifetime Statistics
- Charging History
- Complete Vehicle Dashboard

These templates will use stable Ford Triplog entities to ensure compatibility across future releases.