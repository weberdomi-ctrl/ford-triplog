# Sensors

Ford Triplog provides a comprehensive set of native Home Assistant sensors.

The available entities are automatically created after the integration has been configured.

They provide real-time information, the latest recorded trip and charging session, as well as lifetime statistics.

---

# Overview

Ford Triplog sensors are grouped into four categories:

- Last Trip
- Last Charging Session
- Statistics
- Status

All sensors update automatically.

---

# Last Trip

The Last Trip sensors provide information about the most recently completed journey.

## Distance

```
Last Trip Distance
```

Displays the travelled distance.

Example:

```
42.6 km
```

---

## Duration

```
Last Trip Duration
```

Displays the total driving time.

Example:

```
00:37:15
```

---

## Average Speed

```
Last Trip Average Speed
```

Calculated from:

```
Distance / Driving Time
```

Example:

```
68 km/h
```

---

## Start State of Charge

```
Last Trip Start SOC
```

Example:

```
82 %
```

---

## End State of Charge

```
Last Trip End SOC
```

Example:

```
64 %
```

---

## SOC Used

```
Last Trip SOC Used
```

Example:

```
18 %
```

---

## Estimated Energy Consumption

```
Last Trip Energy
```

Estimated using the configured usable battery capacity.

Example:

```
14.2 kWh
```

---

## Average Consumption

```
Last Trip Consumption
```

Example:

```
16.8 kWh/100 km
```

---

## Start Time

```
Last Trip Started
```

Timestamp of the trip start.

---

## End Time

```
Last Trip Finished
```

Timestamp of the completed trip.

---

# Last Charging Session

These sensors describe the latest completed charging session.

---

## Charging Duration

```
Last Charging Duration
```

Example:

```
01:14:32
```

---

## Start State of Charge

```
Last Charging Start SOC
```

---

## End State of Charge

```
Last Charging End SOC
```

---

## SOC Gained

```
Last Charging SOC Gained
```

Example:

```
42 %
```

---

## Charged Energy

```
Last Charged Energy
```

Estimated using the configured usable battery capacity.

Example:

```
33.2 kWh
```

---

## Charging Location

```
Last Charging Location
```

Example:

```
IONITY Neuenkirch
```

---

## Charging Provider

```
Last Charging Provider
```

Example:

```
IONITY
```

---

## Charging Network

```
Last Charging Network
```

Example:

```
IONITY
```

---

# Lifetime Statistics

Ford Triplog continuously updates lifetime statistics.

---

## Total Trips

```
Total Trips
```

Displays the total number of completed trips.

---

## Total Distance

```
Total Distance
```

Displays the cumulative distance.

---

## Total Driving Time

```
Total Driving Time
```

Displays the accumulated driving time.

---

## Total Energy Consumption

```
Total Energy Consumption
```

Estimated total energy used for driving.

---

## Average Consumption

```
Average Consumption
```

Average lifetime efficiency.

Example:

```
17.4 kWh/100 km
```

---

## Total Charging Sessions

Displays the number of recorded charging sessions.

---

## Total Charged Energy

Estimated total charged energy.

---

## Total Charging Time

Accumulated charging duration.

---

# Status Sensors

Additional sensors provide information about the integration itself.

Examples include:

- Current Trip Active
- Current Charging Active
- Smart Trip Active
- Charging Database Status
- Charging Database Country

The available sensors may vary depending on the configured options.

---

# Entity Naming

Ford Triplog follows Home Assistant naming conventions.

Example:

```
sensor.ford_triplog_last_trip_distance
```

This makes entities easy to identify in dashboards, automations and templates.

---

# Updating

All sensors update automatically.

Typical update events include:

- Vehicle movement
- Trip completion
- Charging completion
- Configuration changes
- Home Assistant restart

No manual refresh is required.

---

# Dashboard Usage

The sensors are designed to work directly with native Home Assistant dashboard cards.

Typical cards include:

- Entity Card
- Tile Card
- Statistics Card
- History Graph
- Gauge
- Markdown Card

Example dashboards are available in:

```
docs/dashboard.md
```

---

# Automations

Every sensor can be used in Home Assistant automations.

Examples:

- Notify when charging has finished.
- Notify when arriving home.
- Display the last trip on a dashboard.
- Track monthly driving distance.
- Calculate energy costs (future versions).

Example automations are provided in:

```
docs/automation_examples.md
```

---

# Availability

Sensors remain available after:

- Home Assistant restart
- Integration restart
- HACS update

Previously recorded trips and charging sessions remain accessible because all data is stored locally.

---

# Future Sensors

Future releases will introduce additional entities, including:

- Charging costs
- Home charging costs
- Monthly statistics
- Yearly statistics
- Charging efficiency
- Vehicle usage summaries

The existing entity names will remain stable whenever possible to avoid breaking dashboards and automations.