# Configuration

After installing Ford Triplog, the integration must be configured once.

The configuration process only requires selecting the existing entities provided by the FordPass integration.

Additional options can be changed at any time without losing recorded trips or charging history.

---

# Initial Configuration

Navigate to:

```
Settings
→ Devices & Services
→ Ford Triplog
```

Select **Configure**.

---

# Required Entities

Four entities are required.

## Vehicle Tracker

The vehicle tracker is used to determine the current vehicle location.

Example:

```
device_tracker.ford_explorer
```

The tracker is also used for:

- Trip start detection
- Trip end detection
- Charging location recognition
- Reverse geocoding

---

## Ignition

The ignition entity determines when the vehicle starts and stops.

Typical entity:

```
binary_sensor.explorer_ignition
```

Ford Triplog uses this together with the tracker to avoid false trip detection.

---

## Odometer

The odometer is used to calculate the travelled distance.

Example:

```
sensor.explorer_odometer
```

The value should increase continuously while driving.

---

## State of Charge (SOC)

The battery state of charge is required for:

- Energy calculations
- Charging session detection
- Charging statistics

Example:

```
sensor.explorer_soc
```

---

# Smart Trip

Smart Trip prevents unnecessary trip fragmentation.

Without Smart Trip:

```
Home
↓

Bakery

↓

Fuel Station

↓

Office
```

would create three individual trips.

With Smart Trip enabled:

```
Home
↓

Bakery

↓

Fuel Station

↓

Office
```

becomes one continuous journey.

---

## Smart Trip Timeout

Defines how long a stop may last before a trip is finalized.

Recommended value:

```
180 seconds
```

Typical settings:

| Value | Description |
|--------|-------------|
| 60 s | Aggressive merging |
| 180 s | Recommended |
| 300 s | Longer stops remain part of the trip |

---

# Battery Capacity

The usable battery capacity is used to estimate energy consumption.

Example:

```
79 kWh
```

Providing the correct value improves:

- Energy calculations
- Consumption statistics
- Charging efficiency estimates

---

# Charging Location Database

Ford Triplog can use an offline OpenStreetMap charging database.

Benefits:

- Faster charging location recognition
- Charging provider detection
- Charger information
- Offline operation

---

## Country Selection

Select the country that matches where the vehicle is normally charged.

The country can be changed later at any time.

Future versions will support automatic country switching.

---

## Download Database

Open the options menu and select:

```
Download Charging Database
```

Choose the desired country.

The integration downloads and installs the database automatically.

---

# User Charging Locations

Ford Triplog allows creating custom charging locations.

Typical examples:

- Home
- Workplace
- Company parking
- Dealer
- Hotel
- Favourite public charger

User-defined locations always have priority over the OpenStreetMap database.

---

## Creating a Charging Location

Open:

```
Settings
→ Devices & Services
→ Ford Triplog
→ Configure
```

Select:

```
Manage Charging Locations
```

Then choose:

```
Add Charging Location
```

Enter the available information.

Typical fields include:

- Name
- Type
- Brand
- Operator
- Network
- Connectors
- Maximum charging power
- Number of charging points
- Matching radius
- Notes

Only the relevant information needs to be entered.

---

## Charging Location Types

Supported types include:

- Public
- Home
- Work
- Private
- Hotel
- Dealer
- Other

Home and Work locations automatically receive suitable default names, which can be changed if desired.

---

# Charging Location Recognition

Ford Triplog resolves charging locations using the following priority:

1. FordPass charging information
2. User-defined charging locations
3. OpenStreetMap charging database
4. Reverse geocoding

This combination provides reliable recognition while allowing complete user customization.

---

# Diagnostics

Diagnostic information can be downloaded directly from Home Assistant.

Navigate to:

```
Settings
→ Devices & Services
→ Ford Triplog
```

Select:

```
Download Diagnostics
```

The diagnostics file helps identify configuration problems without exposing personal trip history.

---

# Local Storage

All data is stored locally inside Home Assistant.

This includes:

- Trips
- Charging sessions
- Statistics
- Charging locations
- Charging databases

No trip or charging history is uploaded to external services.

---

# Updating Configuration

All settings can be modified later.

Changing configuration options does **not** delete:

- Trip history
- Charging history
- Statistics
- Charging locations

Only the selected option is updated.

---

# Best Practices

For the best experience:

- Use accurate FordPass entities.
- Enter the correct usable battery capacity.
- Download the charging database for your country.
- Add frequently used charging locations such as Home and Work.
- Keep Home Assistant and FordPass up to date.

These recommendations provide the most accurate trip statistics and charging location recognition.