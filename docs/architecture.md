# Architecture

Ford Triplog is designed as a lightweight extension for the Home Assistant FordPass integration.

The integration continuously monitors vehicle state changes and automatically creates a permanent local history of trips and charging sessions.

All processing is performed locally inside Home Assistant.

---

# Design Goals

Ford Triplog was designed with the following principles:

- Local-first
- Privacy-first
- Reliable recovery
- Minimal configuration
- Native Home Assistant integration
- Low resource usage
- Easy future expansion

---

# High-Level Architecture

```
                     FordPass Integration
                             │
                             │
        ┌────────────────────┴────────────────────┐
        │                                         │
        ▼                                         ▼
 Vehicle Sensors                         Device Tracker
        │                                         │
        └────────────────────┬────────────────────┘
                             │
                             ▼
                        Coordinator
                             │
         ┌───────────────────┼───────────────────┐
         │                   │                   │
         ▼                   ▼                   ▼
    Trip Manager      Charging Manager      Location Resolver
         │                   │                   │
         └───────────────┬───┴───────────────────┘
                         ▼
                   Journey Manager
                         │
                         ▼
                   Storage Manager
                         │
             ┌───────────┴───────────┐
             ▼                       ▼
      JSON + SQLite           Home Assistant
        Storage                   Sensors
```

---

# Main Components

## Coordinator

The coordinator is responsible for collecting all required vehicle data.

It monitors:

- Vehicle position
- Ignition
- Odometer
- State of Charge

Whenever one of these values changes, the coordinator evaluates whether a trip or charging session has started, changed or finished.

---

## Trip Manager

The Trip Manager controls the complete trip lifecycle.

Responsibilities include:

- Detect trip start
- Detect trip end
- Smart Trip handling
- Distance calculation
- Duration calculation
- Average speed calculation
- Energy estimation
- Statistics update

Each completed trip is written immediately to local storage.

---

## Charging Manager

The Charging Manager detects charging sessions independently from trips.

It records:

- Start time
- End time
- Start SOC
- End SOC
- Charged energy
- Billed energy
- Charging duration
- Charging losses
- Home tariff calculation
- Charging cost calculation
- Cost aggregation

Whenever possible, charging sessions are linked to the previous trip.

---


## Journey Manager

The Journey Manager groups related trips and charging sessions into a single Journey.

Responsibilities include:

- Automatic Journey creation
- Assignment of trips and charging sessions
- Journey completion detection
- Home-zone recognition
- Journey timeout handling
- Maximum Journey Gap handling
- Journey statistics
- Journey energy balance
- Journey charging cost aggregation
- Average charging price calculation
- Journey rebuild and recovery

A Journey may contain multiple trips and charging sessions, providing a complete view of a driving session.

---

## Charging Location Resolver

The Charging Location Resolver determines where a charging session occurred.

The resolver uses the following priority:

```
FordPass

↓

User Charging Locations

↓

OpenStreetMap Database

↓

Reverse Geocoding
```

This priority allows FordPass information to be used whenever available while still providing reliable fallback methods.

---

## Storage Manager

The Storage Manager provides a backend-independent interface for persistent local storage.

Ford Triplog 2.1 supports JSON and SQLite as local read backends. During the 2.1 transition, compatible data is written to both formats. JSON remains the default read backend after an upgrade; SQLite can be enabled explicitly in Ford Triplog settings.

Responsibilities:

- Save and load trips, charging sessions and Journeys
- Save and load route history
- Save statistics and diagnostics
- Save charging and pause metadata
- Save receipts and user receipt parser profiles
- Save user-defined and pending charging locations
- Data migration and mirroring
- Recovery

Backend-neutral archive access allows statistics and Journey rebuild operations to use the selected read backend without depending on JSON archive files.

---

# Data Flow

## Trip Recording

```
Ignition ON

↓

Vehicle starts moving

↓

Trip starts

↓

Vehicle position updates

↓

Distance calculated

↓

Statistics updated

↓

Trip finished

↓

Trip stored
```

---

## Charging Recording

```
Charging detected

↓

Charging starts

↓

SOC monitored

↓

Charging ends

↓

Energy calculated

↓

Charging location resolved

↓

Charging stored
```

---


## Journey Recording

```
Trip starts

↓

Journey created

↓

Trips added

↓

Charging sessions added

↓

Vehicle returns home
or timeout expires

↓

Journey completed

↓

Journey stored
```

---

# Charging Location Resolution

```
FordPass Location
        │
        ▼
Available?

Yes ─────────► Use FordPass

No

↓

User Charging Locations

↓

Match?

Yes ─────────► Use User Location

No

↓

OSM Database

↓

Match?

Yes ─────────► Use OSM

No

↓

Reverse Geocoding
```

---

# Local Storage

Ford Triplog stores its persistent data locally inside Home Assistant.

Version 2.1 introduces a local SQLite database alongside the existing JSON storage.

Typical data includes:

- Journeys
- Trips
- Charging sessions
- GPS routes
- Statistics and diagnostics
- Charging locations
- Charging and pause metadata
- Receipts and OCR/parser state
- User-created receipt parser profiles
- OpenStreetMap databases
- Configuration

## Storage Backends

JSON remains the default read backend after upgrading to 2.1. Existing users are not switched automatically to SQLite.

Users who want SQLite reads can enable the backend explicitly in Ford Triplog settings. Changing the backend reloads the integration.

During the 2.1 migration period:

- Compatible data is written to JSON and SQLite
- Existing data is migrated or mirrored into SQLite
- Historical Trips, Charges, Journeys and Routes can be read from SQLite
- Journey rebuild uses the selected backend
- Statistics are recalculated from the selected backend after setup or reload
- JSON remains available as a compatibility and fallback path

The SQLite database is local to Home Assistant. No external database server is required.

---

# Recovery

Recovery has been designed to survive unexpected situations such as:

- Home Assistant restart
- System reboot
- Power failure
- FordPass temporary outage

When Home Assistant starts again, Ford Triplog restores its previous state and continues recording without losing historical data.

Recovery also includes:

- Active Journey restoration
- Journey reconstruction after restart

---

# Smart Trip

Smart Trip prevents unnecessary fragmentation of journeys.

Example:

```
Home

↓

Coffee Stop (2 min)

↓

Supermarket (4 min)

↓

Office
```

Instead of creating multiple short trips, Smart Trip merges short stops into a single trip.

That trip is then automatically assigned to a Journey together with any subsequent trips and charging sessions.

The timeout is fully configurable.

---

# Performance

Ford Triplog has been designed for minimal system load.

Characteristics:

- Event-driven architecture
- No continuous polling
- Local JSON and SQLite storage
- Backend-neutral historical reads
- SQL-backed queries and views for frequently used statistics
- Fast geohash-based charging lookup
- Minimal memory usage
- Native Home Assistant coordinator pattern

Under normal operation, CPU and memory usage remain very low.

---

# Privacy

All processing happens locally.

Nothing is uploaded except the communication already performed by the FordPass integration itself.

Ford Triplog never transmits:

- Trip history
- Charging history
- Statistics
- Charging locations
- User-defined charging locations

This makes the integration suitable for users who prefer complete local control over their driving history.

---

# Extensibility

The architecture has been designed to support future features without major structural changes.

Planned extensions include:

- Automatic charging database switching
- Dashboard templates
- Multi-vehicle support
- Further SQL-based statistics and aggregation
- Additional route validation and GPS plausibility checks

Because the core components are separated into dedicated managers, future functionality can be added with minimal impact on the existing architecture.
