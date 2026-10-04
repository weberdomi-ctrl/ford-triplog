# Architecture

Ford Triplog is a local-first Home Assistant custom integration for automatic
Trip, charging, Journey and route history.

Ford Triplog remains Ford-focused, but version 2.5 uses an entity-based
multi-vehicle architecture. Ford Connect is the recommended source for Ford
vehicles. Compatible FordPass entities and other Home Assistant vehicle data
sources can also be used when they expose the required entities.

All persistent Triplog data is stored locally inside Home Assistant.

---

# Design Goals

Ford Triplog is designed around the following principles:

- Local-first
- Privacy-conscious
- Reliable recovery
- Minimal configuration
- Native Home Assistant integration
- Multi-vehicle isolation
- Low resource usage
- Backward-compatible storage migration
- Easy future expansion

---

# High-Level Architecture

```text
                 Home Assistant vehicle data sources
                Ford Connect / FordPass / compatible sources
                                  │
               ┌──────────────────┴──────────────────┐
               │                                     │
               ▼                                     ▼
        Vehicle ConfigEntry 1                 Vehicle ConfigEntry N
               │                                     │
               ▼                                     ▼
       Vehicle Runtime / Coordinator          Vehicle Runtime / Coordinator
               │                                     │
               └──────────────────┬──────────────────┘
                                  │
                         Shared Vehicle Context
                                  │
            ┌─────────────────────┼─────────────────────┐
            │                     │                     │
            ▼                     ▼                     ▼
      Trip Manager         Charging Manager       Route Tracker
            │                     │                     │
            └───────────────┬─────┴───────────────┬─────┘
                            ▼                     ▼
                     Journey Manager       Location Resolution
                            │                     │
                            └──────────┬──────────┘
                                       ▼
                              SQLite Storage
                         vehicle_id-scoped records
                                       │
                                       ▼
                       Shared Home Assistant entities
                    Vehicle selector / History / Sensors
```

Ford Triplog 2.5 keeps one shared dashboard entity set. Additional vehicle
ConfigEntries provide independent vehicle runtimes and data sources instead of
duplicating the complete public sensor set for every vehicle.

---

# Multi-Vehicle Runtime

Each configured vehicle receives its own Home Assistant ConfigEntry and a
stable internal `vehicle_id`.

Where the source integration exposes enough registry metadata, Ford Triplog can
discover vehicle identity information such as:

- VIN
- Display name
- Manufacturer
- Model
- Source integration

The vehicle identity is stored in SQLite and used to keep historical records
attached to the correct vehicle.

Operational state is kept separate per vehicle, including:

- Current Trip
- Last Trip
- Current charging session
- Last charging session
- Current Journey
- Last Journey
- Routes
- Statistics
- Vehicle-specific metadata

Existing pre-2.5 data is migrated to the original vehicle automatically.

---

# Shared Vehicle Context

Ford Triplog exposes one shared **Vehicle** selector for dashboard and History
context.

Changing the selected vehicle switches the data shown by the shared Ford
Triplog entities without changing their entity IDs.

The same vehicle context is used by vehicle-specific options and manual
maintenance actions.

Once an options flow has started, its vehicle context is locked for that flow
so a later dashboard vehicle change cannot make an already selected Trip,
charging session, receipt or pause resolve against another vehicle.

---

# Main Components

## Coordinator

Each vehicle runtime has its own coordinator.

The coordinator collects the configured vehicle data and evaluates state
changes. Depending on the configured source, this can include:

- Vehicle position
- Ignition
- Odometer
- State of Charge
- Charging state
- Last Charge information

For supported Ford Connect/FordPass devices, Ford Triplog can also discover a
physical EV plug-state entity automatically from the same Home Assistant
device. This source is runtime-only and is not exposed as a manual
configuration field.

Whenever relevant values change, the coordinator evaluates whether a Trip or
charging session has started, changed, paused, resumed or finished.

Temporary `unknown`, `unavailable`, unsupported or missing source states are
handled defensively and are not treated as real driving/charging transitions.

---

## Trip Manager

The Trip Manager controls the complete Trip lifecycle for one vehicle.

Responsibilities include:

- Detect Trip start
- Detect Trip end
- Smart Trip handling
- Distance calculation
- Duration calculation
- Average speed calculation
- SOC and energy estimation
- Recuperation handling
- Statistics update
- Start/end position handling
- Recovery after restart

Each completed Trip is written to SQLite with its `vehicle_id`.

---

## Route Tracker

The optional Route Tracker records a higher-resolution route from a separate
Home Assistant position source.

Supported source types include:

- ABRP latitude/longitude entities
- Home Assistant Companion App Geocoded Location
- Direct Home Assistant `device_tracker` GPS

Route data is linked to the corresponding Trip ID and vehicle.

Dense route traces can be kept in memory while active and are protected by
periodic SQLite snapshots. Important lifecycle transitions force an immediate
snapshot.

### Vehicle / auxiliary-GPS consistency guard

A phone tracker is only a valid vehicle route source while the phone is
actually travelling with the vehicle.

Ford Triplog 2.5 therefore compares the auxiliary Route Tracker with vehicle
GPS before accepting the completed route.

When both sources differ by more than 250 m:

- Vehicle GPS becomes authoritative.
- Auxiliary phone/device-tracker route points are discarded from the completed route.
- A provisional Trip start that was incorrectly replaced by the auxiliary source is restored to the original vehicle start.
- An implausible OSRM route is not accepted.

This prevents workshop or service movements from creating phantom routes when
the configured phone remains somewhere else.

When both sources remain geographically consistent, normal Route Tracker and
OSRM processing continues unchanged.

---

## Charging Manager

The Charging Manager records charging sessions independently for each vehicle.

It can record:

- Start time
- End time
- Start SOC
- End SOC
- Vehicle energy estimate
- Billed energy
- Charging duration
- Charging losses
- Charging location
- Charging provider
- Home tariff calculation
- Charging cost calculation
- Cost aggregation
- Receipt-derived values
- Last Charge reconciliation

### Physical plug-aware Ford sessions

For compatible Ford Connect/FordPass devices, an automatically discovered
physical plug state can distinguish a completed charging phase from a real
unplug event.

While the plug remains connected, transitions such as:

`IN_PROGRESS -> COMPLETED/READY -> IN_PROGRESS`

can remain one physical charging session. This covers later transfer segments
caused by preconditioning or battery management.

An explicit physical disconnect ends the session.

If plug-state support is unavailable, Ford Triplog retains the established
charging-state lifecycle for that vehicle source.

---

## Journey Manager

The Journey Manager groups related Trips and charging sessions for one vehicle
into a single Journey.

Responsibilities include:

- Automatic Journey creation
- Assignment of Trips and charging sessions
- Pause detection
- Journey completion detection
- Home-zone recognition
- Journey timeout handling
- Maximum Journey Gap handling
- Journey statistics
- Journey energy balance
- Journey charging-cost aggregation
- Average charging price calculation
- Journey rebuild and recovery

Journeys never mix records from different `vehicle_id` values.

---

## Charging Location Resolver

The Charging Location Resolver enriches charging sessions with known location
information.

The effective resolution chain is:

```text
Vehicle / Last Charge charging information
                    ↓
       User charging locations
                    ↓
       OpenStreetMap database
                    ↓
       Address / reverse-geocoding fallback
```

User-defined charging locations can override OSM matches. Unresolved charging
locations can be retained for later manual assignment.

---

## Storage Manager

Ford Triplog 2.5 uses SQLite as the sole productive Triplog datastore.

The JSON/SQLite transition from 2.1/2.2 was completed in 2.3. Legacy JSON data
is retained only as a migration/import source where applicable.

Responsibilities include:

- Save and load Trips
- Save and load charging sessions
- Save and load Journeys
- Save and load Routes
- Save current/last state
- Save statistics and diagnostics
- Save vehicle identity
- Save charging and pause metadata
- Save user-defined and pending charging locations
- Save user-defined Journey places
- Link receipts to charging sessions and Journey pauses
- Backend-neutral CSV export
- Maintenance and rebuild operations
- Migration and recovery

Most operational records are scoped by `vehicle_id`.

Home charging tariff periods are stored centrally in SQLite so the same tariff
table does not need to be duplicated across vehicle ConfigEntries.

Receipt files themselves remain on the Home Assistant filesystem; their
metadata and record links are stored by Ford Triplog.

---

## Receipt Management

Receipt management stores documents locally and links their metadata to the
corresponding Ford Triplog record.

Receipts can be associated with:

- Charging sessions
- Journey pauses

Multiple receipts can be linked to the same charging session or pause.

Charging receipts can optionally use OCR and parser profiles for automatic
billing-data extraction. Pause receipts do not require OCR.

When billing information is applied from a charging receipt, billed values
remain the preferred source for charging-cost calculations.

Dashboard access uses authenticated Home Assistant URLs instead of exposing
local filesystem paths.

---

## Export

Ford Triplog can export stored history through the Home Assistant options flow.

Supported exports include:

- Trips
- Journeys
- Charging sessions
- Monthly driving statistics
- Monthly charging statistics

Exports can be limited by date where supported and are generated from the local
SQLite data.

---

## Maintenance Operations

Ford Triplog includes guarded maintenance operations for stored history.

Examples include:

- Update or rebuild Journeys
- Delete selected Journeys while retaining source Trips/charges
- Delete clearly invalid charging sessions after confirmation
- Rebuild the latest Route
- Rebuild raw/failed Routes
- Rebuild all stored Routes

Maintenance runs in the selected vehicle context and does not mix vehicles.

Journey rebuild uses a central non-queuing guard so multiple rebuild operations
cannot run over one another.

Raw GPS route points remain preserved when OSRM geometry is rebuilt.

---

# Data Flow

## Trip Recording

```text
Ignition / vehicle state changes
              ↓
        Trip starts
              ↓
   Vehicle data monitored
              ↓
 Route Tracker records optional
      auxiliary GPS points
              ↓
       Smart Trip logic
              ↓
 Vehicle/route GPS validated
              ↓
         Trip finishes
              ↓
 SQLite record + vehicle_id
              ↓
 Journey/statistics refresh
```

---

## Charging Recording

```text
Charging detected
       ↓
Session starts
       ↓
SOC / energy monitored
       ↓
Charging may pause / complete
       ↓
Physical plug still connected?
   │                 │
  Yes               No / unsupported
   │                 │
Resume may stay       Existing lifecycle /
in same session       disconnect ends session
       └──────────────┬──────────────┘
                      ↓
       Location / cost reconciliation
                      ↓
        SQLite record + vehicle_id
```

---

## Vehicle Context Switching

```text
Vehicle selector changed
          ↓
selected_vehicle_id updated
          ↓
Shared runtime proxies resolve
the selected vehicle
          ↓
History / Last Trip / Last Charge /
Journey / Route / statistics refresh
```

---

# Local Storage

Ford Triplog stores its persistent history locally inside Home Assistant.

Typical SQLite-backed data includes:

- Vehicles and identity
- Trips
- Charging sessions
- Journeys
- GPS routes
- Current/last caches
- Statistics and diagnostics
- Charging locations
- Journey places
- Charging and pause metadata
- Receipt metadata and parser state
- Global home charging tariff periods
- Migration state

Additional local files include:

- Receipt documents
- Generated CSV exports
- OpenStreetMap charging databases

No external database server is required.

---

# Recovery

Recovery is designed to survive situations such as:

- Home Assistant restart
- Integration reload
- System reboot
- Power failure
- Temporary vehicle-source outage

Recovery includes vehicle-scoped restoration of active state and route
snapshots where available.

The source-health monitor distinguishes:

- Healthy
- Degraded
- Grace period
- Unavailable
- Unknown

A complete live-source outage is only declared after the configured 20-minute
grace behaviour used by Ford Triplog 2.4/2.5.

---

# Smart Trip

Smart Trip prevents short stops from unnecessarily fragmenting Trip history.

Example:

```text
Home
  ↓
Coffee stop
  ↓
Supermarket
  ↓
Office
```

Short ignition-off periods can be held as a paused Trip and resumed when the
vehicle continues within the configured timeout.

The resulting Trip is then assigned to the vehicle's Journey.

---

# Performance

Ford Triplog is designed for low runtime overhead.

Characteristics include:

- Event-driven Home Assistant entity listeners
- No independent high-frequency polling loop
- SQLite-only productive storage
- Vehicle-scoped SQL queries
- Cached location data where appropriate
- Coalesced coordinator updates
- Push-driven Home Assistant sensors
- Route snapshots instead of a SQLite write for every GPS point

---

# Privacy and External Communication

Trip, charging, Journey, Route, statistics and cost data is stored locally in
Home Assistant. Ford Triplog does not use a separate Triplog cloud backend.

External communication can still occur when a configured feature requires it:

- The selected vehicle integration communicates with its vehicle/backend.
- Reverse geocoding can send coordinates to OpenStreetMap Nominatim.
- OpenStreetMap charging databases can be downloaded on request.
- OSRM receives route coordinates when the user enables an OSRM service.
- OCR receives receipt content when the user enables and runs an OCR service.

Receipt files and generated CSV exports remain local unless the user explicitly
uses a configured external service or downloads them.

---

# Extensibility

The 2.5 architecture is prepared for further vehicle-aware features without
changing the established storage model.

Planned 2.6 development areas include:

- Vehicle operating-cost records
- Monthly and yearly total cost
- Cost per kilometre
- Vehicle-specific recurring and one-time costs
- Charging-cost integration using stored effective/billed costs
- Receipt support for vehicle costs
- Additional maintenance tracking and reporting

Longer-term research may further separate the Triplog core from
manufacturer-specific vehicle adapters.
