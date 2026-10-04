# Configuration

Ford Triplog 2.5 is configured through Home Assistant ConfigEntries.

Each configured vehicle has its own Ford Triplog ConfigEntry and its own vehicle
data sources. The integration keeps the recorded history separated by a stable
internal `vehicle_id`.

Ford Connect is the recommended source for Ford vehicles. Compatible FordPass
entities and other Home Assistant vehicle sources can also be used when they
expose the required entities.

---

# Initial Configuration

Navigate to:

```text
Settings
→ Devices & Services
→ Add Integration
→ Ford Triplog
```

Create one Ford Triplog ConfigEntry for each vehicle you want to record.

The initial setup asks for the core vehicle entities plus Smart Trip settings.

---

# Vehicle Source Entities

## Required entities

Three entities are required during initial setup.

### Ignition

The ignition source determines when the vehicle starts and stops.

Typical source:

```text
sensor.explorer_ignition
```

Ford Triplog expects a compatible vehicle-state sensor and normalizes supported
source values internally.

### Odometer

The odometer is the authoritative source for travelled distance.

Example:

```text
sensor.explorer_odometer
```

The value should increase normally while the vehicle is driven.

### Vehicle Tracker

The vehicle tracker provides the vehicle's own position.

Example:

```text
device_tracker.ford_explorer
```

It is used for:

- Trip start/end position
- Charging position
- Location recognition
- GPS plausibility checks
- Reverse geocoding fallback

Do not use a phone tracker here. A phone tracker belongs in the optional Route
Tracker configuration.

---

## Optional entities

### State of Charge (SOC)

SOC improves:

- Trip energy estimation
- Consumption statistics
- Recuperation calculation
- Charging-session data

Example:

```text
sensor.explorer_soc
```

The integration can still be configured without SOC, but energy-related values
will naturally be limited.

### Charging State

A charging-state entity enables automatic charging-session detection.

Example:

```text
sensor.explorer_charging
```

The exact raw values depend on the selected vehicle integration and are
normalized by Ford Triplog.

### Last Charge

Last Charge is configured later under **Settings → Vehicle sensors** when the
vehicle source provides such an entity.

Ford sources can use Last Charge to reconcile delayed or more accurate session
information after the local charging session has already completed.

---

# Source Selection Rules

Select input entities from the vehicle integration itself.

Do **not** select Ford Triplog's own output entities as inputs. Ford Triplog
filters its own entities from the normal selectors to reduce accidental
feedback configurations.

For one ConfigEntry, all selected vehicle entities should belong to the same
physical vehicle.

---

# Vehicle Identity and Multi-Vehicle Setup

Ford Triplog 2.5 attempts to discover vehicle identity from Home Assistant
registry/device information where available.

Detected information can include:

- VIN
- Vehicle name
- Manufacturer
- Model
- Source integration

The identity is used to create or recover the vehicle's stable internal
`vehicle_id`.

To add another vehicle, add **Ford Triplog** again under Home Assistant
Integrations and select the entities of that vehicle.

If the same VIN is already configured, Ford Triplog detects the duplicate.
Normal installations should not create a second ConfigEntry for the same
physical vehicle.

---

# Vehicle Selector

Ford Triplog exposes one shared **Vehicle** selector.

The selector changes which vehicle is shown by the shared Ford Triplog
dashboard and History entities.

This avoids creating a complete duplicate sensor set for every configured
vehicle.

The currently selected vehicle also becomes the default context when opening
vehicle-specific manual actions from the options flow.

An options flow locks its vehicle context when it starts so a later dashboard
selector change cannot move an in-progress edit to another vehicle.

---

# Smart Trip

Smart Trip prevents short stops from unnecessarily splitting a drive.

The initial configuration enables Smart Trip by default.

Default timeout:

```text
300 seconds
```

Allowed setup range:

```text
30–900 seconds
```

A shorter timeout finalizes Trips sooner. A longer timeout allows longer stops
to remain part of the same Trip.

---

# Ford Triplog Settings

Open:

```text
Settings
→ Devices & Services
→ Ford Triplog
→ Configure
```

The main options menu shows the currently selected vehicle context.

The settings area contains:

- General settings
- Home charging tariffs
- Vehicle settings
- Vehicle sensors
- Route Tracker
- OSRM
- OCR

---

# General Settings

General settings are stored for the selected vehicle where applicable.

Available settings include:

- Smart Trip enabled/disabled
- Smart Trip timeout
- Charging-site country
- Usable battery capacity
- Journey home zone
- Home tariff enabled/disabled
- Home tariff currency
- Journey home timeout
- Maximum Journey gap

---

# Battery Capacity

The usable battery capacity is used for SOC-based energy calculations.

Default for new configurations:

```text
77 kWh
```

Change this value to the actual usable capacity of the configured vehicle.

An incorrect capacity directly scales calculated:

- Trip energy
- kWh/100 km
- SOC-derived recuperation
- Some charging estimates

Each vehicle can therefore use its own battery capacity.

---

# Vehicle Settings

**Vehicle settings** shows the detected identity of the selected vehicle and
allows its Ford Triplog display name to be changed.

Identity information can include:

- Internal `vehicle_id`
- VIN
- Source integration
- Detected vehicle name/model

Changing the display name does not change historical ownership or the internal
vehicle ID.

---

# Vehicle Sensors

**Vehicle sensors** allows the source entities of the selected vehicle to be
changed without deleting its Triplog history.

Configurable sources are:

- Ignition — required
- Odometer — required
- Vehicle tracker — required
- SOC — optional
- Charging state — optional
- Last Charge — optional

Optional sources can also be cleared later.

---

# Physical Plug State

There is no manual plug-state field in the Ford Triplog configuration.

For compatible Ford Connect/FordPass devices, Ford Triplog 2.5 automatically
looks for a supported EV plug-state entity on the same Home Assistant device.

When a valid physical plug state is available:

- A completed/ready phase does not necessarily end the physical session.
- A later `IN_PROGRESS` phase can continue the same session while still plugged in.
- An explicit physical disconnect ends the session.
- Temporary unavailable/unsupported plug values retain the last valid physical state.

Vehicle sources without this capability continue to use the normal
charging-state lifecycle.

---

# Route Tracker

The optional Route Tracker is separate from the vehicle tracker.

It can provide denser GPS traces while driving.

Supported sources:

- ABRP latitude and longitude entities
- Home Assistant Companion App Geocoded Location
- Direct Home Assistant `device_tracker` GPS

The Route Tracker can be enabled or disabled per vehicle.

## Phone / vehicle GPS guard

A phone tracker is only valid while the phone is travelling with the selected
vehicle.

At Trip completion, Ford Triplog compares the auxiliary route source with
vehicle GPS.

If the two sources differ by more than 250 m:

- Vehicle GPS wins.
- Auxiliary route points are discarded from the completed route.
- An incorrectly replaced provisional start position is restored to the vehicle start.
- Implausible OSRM geometry is not accepted.

This prevents a vehicle being moved in a workshop while the owner's phone is
somewhere else from creating a false long-distance route.

---

# OSRM

Ford Triplog can optionally use an OSRM server to match recorded GPS traces to
the road network.

Per-vehicle settings include:

- Enable/disable OSRM
- OSRM server URL
- Matching radius

Default matching radius:

```text
15 m
```

The configuration flow tests the OSRM connection when it is enabled.

OSRM is optional. Raw route recording continues without it.

---

# Home Charging Tariffs

Ford Triplog 2.5 stores home charging tariff periods centrally in SQLite.

This prevents the same tariff table from being duplicated for every vehicle
ConfigEntry.

Tariff periods contain:

- Year
- Valid from
- Valid to
- Price per kWh
- Currency

Periods within the same year may not overlap.

Typical example:

```text
Year:       2027
Valid from: 01.01
Valid to:   31.12
Price:      0.2735 CHF/kWh
```

The tariff table can be used by multiple configured vehicles.

The **Home tariff enabled** setting still determines whether automatic home
charging cost calculation is used for the selected vehicle.

Where legacy summer/winter tariff settings still exist and no new tariff
periods have been created, the options flow can offer a legacy tariff import.

---

# Charging Location Database

Ford Triplog can use an offline OpenStreetMap charging-site database.

Benefits include:

- Charging location recognition
- Provider/network information
- Charger metadata
- Local lookup after the database has been created

The charging-site country is configured in General settings.

---

## Download Database

Open the Ford Triplog options menu and select the charging-site database
workflow.

A country database can be downloaded from OpenStreetMap and processed locally.

Depending on country size and Home Assistant hardware, processing can take
several minutes.

A pre-generated Ford Triplog charging-site JSON database can also be imported.

---

# User Charging Locations

Custom charging locations can be created and managed directly in Ford Triplog.

Typical examples:

- Home
- Work
- Company parking
- Dealer
- Hotel
- Public charging site

Stored fields can include:

- Name
- Address
- Coordinates
- Matching radius
- Type
- Brand/provider
- Operator
- Network
- Connectors
- Maximum charging power
- Number of charging points
- Notes

User-defined locations take priority over OSM charging-site matches.

Unknown charging locations can be retained as pending locations for later
assignment.

---

# User-Defined Journey Places

Reusable Journey places can be configured independently from charging
locations.

A place can contain:

- Name
- Category
- Description
- Latitude/longitude
- Matching radius
- Optional MDI icon

These places can automatically enrich later Journey pauses in the same area.

Manual pause edits retain priority.

---

# Charging Location Recognition

The effective charging location resolution chain is:

1. Vehicle / Last Charge charging information, when usable
2. User-defined charging location
3. OpenStreetMap charging database
4. Address / reverse-geocoding fallback

The exact available fields depend on the vehicle source.

---

# Storage

Ford Triplog 2.5 uses SQLite as the sole productive history datastore.

There is no JSON/SQLite read-backend selector in current releases.

The parallel JSON/SQLite migration phase from 2.1/2.2 ended with version 2.3.

Existing legacy JSON data can still be used as a migration/import source where
supported, but new productive Triplog records are stored in SQLite.

Existing 2.4 data is migrated automatically to the multi-vehicle schema. No
manual database conversion is required.

---

# Export

Ford Triplog can export:

- Trips
- Journeys
- Charging sessions
- Monthly driving statistics
- Monthly charging statistics

Exports are generated from local storage and can be downloaded through Home
Assistant.

Date filtering is available where supported by the export type.

---

# History and Maintenance

Ford Triplog provides guarded maintenance functions for the selected vehicle.

Available workflows include:

- Update Journeys
- Rebuild Journeys
- Delete Journeys
- Edit charging costs
- Delete clearly invalid charging sessions
- Manage pause metadata
- Manage receipts
- Rebuild Routes through OSRM

Maintenance actions remain scoped to the selected vehicle context.

---

# Receipt and OCR Configuration

Receipts can be uploaded for charging sessions and Journey pauses.

Charging receipts can optionally be analyzed by an OCR service.

OCR settings include:

- Enable OCR
- OCR service URL
- API key
- Timeout

The OCR connection is optional. All normal Triplog recording continues without
OCR.

Receipt files remain stored locally in Home Assistant.

---

# Diagnostics

Diagnostic information can be downloaded through Home Assistant.

Navigate to:

```text
Settings
→ Devices & Services
→ Ford Triplog
```

Diagnostics are intended to help identify configuration/runtime problems
without requiring manual access to the Triplog database.

---

# Local Data

Ford Triplog keeps its persistent history locally in Home Assistant.

This includes:

- Vehicle identities
- Trips
- Journeys
- Charging sessions
- Routes
- Statistics
- Charging locations
- Journey places
- Charging and pause metadata
- Receipt metadata
- Home tariff periods
- Migration state

Receipt files, generated exports and downloaded charging-site databases also
remain local files.

Reverse geocoding, vehicle-source access, optional OSRM and optional OCR can
communicate with the respective configured services.

---

# Updating Configuration

Settings can be changed later without deleting recorded history.

Vehicle-specific changes apply to the currently selected vehicle.

Changing source entities or the vehicle display name does not move existing
history to another vehicle.

Adding a second vehicle should be done by creating another Ford Triplog
ConfigEntry rather than replacing the first vehicle's sources.

---

# Best Practices

For the most reliable results:

- Use Ford Connect for Ford vehicles where available.
- Select all core vehicle entities from the same physical vehicle.
- Never use Ford Triplog output entities as Ford Triplog inputs.
- Use the vehicle's own tracker as **Vehicle Tracker**.
- Configure a phone only as the optional **Route Tracker**.
- Enter the correct usable battery capacity for each vehicle.
- Configure the correct home zone and Journey timeouts.
- Maintain current home charging tariff periods when automatic home charging costs are used.
- Add frequently used charging locations such as Home and Work.
- Use local OSRM only when route matching is desired.
- Keep Home Assistant and the selected vehicle-source integration up to date.
