# Sensors

Ford Triplog creates a comprehensive set of native Home Assistant sensors.

All sensors are automatically updated whenever a trip or charging session is completed.

The sensors can be used in:

- Dashboards
- Automations
- Statistics
- Energy dashboards
- Notifications
- Custom Lovelace cards

---

# Last Trip

These sensors always represent the **most recently completed trip**.

| Sensor | Unit | Description |
| :------ | :--: | :---------- |
| Last Start Address | — | Human readable start location |
| Last Destination | — | Human readable destination |
| Last Start Time | — | Trip start timestamp |
| Last End Time | — | Trip end timestamp |
| Last Distance | km | Distance travelled |
| Last Energy Used | kWh | Estimated energy consumption |
| Last Consumption | kWh/100 km | Average consumption |
| Last Average Speed | km/h | Average speed |
| Last Driving Time | — | Formatted driving time |
| Last Duration | s | Driving time in seconds |
| Last Trip Start SOC | % | Battery level at departure |
| Last Trip End SOC | % | Battery level at arrival |
| Last Trip SOC Used | % | Battery percentage used |

---

# Last Charging Session

These sensors describe the most recently completed charging session.

| Sensor | Unit | Description |
| :------ | :--: | :---------- |
| Last Charging Location | — | Human readable charging location |
| Last Charge Start Time | — | Charging start |
| Last Charge End Time | — | Charging end |
| Last Charge Duration | — | Formatted charging duration |
| Last Charge Duration (Raw) | s | Charging time in seconds |
| Last Charge Start SOC | % | Battery level before charging |
| Last Charge End SOC | % | Battery level after charging |
| Last Charge SOC Added | % | Added battery percentage |
| Last Energy Added | kWh | Estimated charged energy |

---

# Lifetime Statistics

These sensors summarize all recorded trips and charging sessions.

| Sensor | Unit | Description |
| :------ | :--: | :---------- |
| Trip Count | trips | Total recorded trips |
| Charge Count | charges | Total charging sessions |
| Total Distance | km | Overall driven distance |
| Total Energy Used | kWh | Total estimated energy consumption |
| Total Driving Time | — | Formatted driving time |
| Total Duration | s | Total driving time in seconds |
| Average Consumption | kWh/100 km | Overall average consumption |
| Average Trip Distance | km | Average distance per trip |
| Average Trip Duration | — | Average formatted trip duration |
| Average Trip Energy | kWh | Average energy per trip |
| Average Trip Consumption | kWh/100 km | Average trip consumption |
| Average Trip SOC Used | % | Average battery usage |
| Average Charge Duration | — | Average formatted charging duration |
| Average Charge Start SOC | % | Average SOC before charging |
| Average Charge End SOC | % | Average SOC after charging |
| Average Charge SOC Added | % | Average added battery percentage |

---

# Using Sensors

Every sensor behaves like a standard Home Assistant entity.

Examples:

- Dashboard cards
- Gauge cards
- History graphs
- Statistics cards
- Tile cards

No custom cards are required.

---

# Typical Automations

Ford Triplog sensors are ideal for automations.

Examples include:

- Notify after every completed trip
- Notify when charging finishes
- Weekly driving summary
- Monthly charging report
- Battery efficiency monitoring

---

# Estimated Values

Some values are calculated rather than measured directly.

These include:

- Energy Used
- Energy Added
- Consumption

Calculations are based on:

- Vehicle battery capacity
- State of Charge difference
- Driven distance

This provides realistic estimates without requiring charger data.

---

# Translation

All sensors use Home Assistant's native translation system.

Sensor names automatically appear in the selected Home Assistant language.

Currently available translations include:

- English
- German

Additional translations can easily be added in future releases.

---

# Performance

Ford Triplog is optimized for long-term operation.

Sensor updates use:

- Shared statistics cache
- Optimized JSON access
- Reduced disk I/O
- Native Coordinator updates

Even installations containing thousands of trips remain responsive.

---

# Next Step

Learn how to build dashboards using Ford Triplog sensors.

➡ **[Dashboard Examples](dashboard.md)**