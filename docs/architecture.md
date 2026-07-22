# Architecture

Ford Triplog is built around Home Assistant's recommended integration architecture.

The integration follows an event-driven design and uses a single coordinator to manage all trip detection, charging detection, storage and sensor updates.

---

# Overview

```
                    FordPass Integration
                           │
                           │
                           ▼
                  Home Assistant Entities
                           │
                           ▼
                ExplorerCoordinator
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
        ▼                  ▼                  ▼
   Trip Detection    Charge Detection   Statistics
        │                  │                  │
        └──────────────┬───┴──────────────────┘
                       │
                       ▼
                Local JSON Storage
                       │
                       ▼
               Home Assistant Sensors
                       │
                       ▼
          Dashboard • Automations • History
```

---

# Core Components

Ford Triplog consists of several independent components that work together.

## ExplorerCoordinator

The `ExplorerCoordinator` is the central component of the integration.

It is responsible for:

- monitoring FordPass entities
- detecting trips
- detecting charging sessions
- updating statistics
- writing JSON files
- refreshing Home Assistant sensors

All major logic is handled here.

---

## Trip Detection

Trip detection is based on vehicle state changes.

Information used includes:

- Ignition
- Vehicle position
- Odometer
- State of Charge

When a trip starts, the coordinator records the initial values.

When the trip ends, the complete trip is calculated and stored.

---

## Smart Trip

Smart Trip prevents unnecessary trip fragmentation.

Instead of immediately finishing a trip after the vehicle stops, the coordinator waits for the configured timeout.

```
Vehicle Stops

↓

Start Timer

↓

Vehicle Moves Again?

YES → Continue Trip

NO → Finish Trip
```

This produces cleaner trip histories.

---

## Charge Detection

Charging sessions are monitored independently of trips.

The coordinator records:

- charging start
- charging end
- duration
- battery level
- charging location

Trips and charging sessions remain separate data structures.

---

# Statistics Engine

Instead of recalculating all historical data after every update, Ford Triplog maintains aggregated statistics.

These include:

- total trips
- total charges
- total distance
- average consumption
- average durations

This greatly improves performance.

---

# Storage Layer

The storage layer uses simple JSON files.

```
Trips

↓

trips/
```

```
Charging Sessions

↓

charges/
```

```
Statistics

↓

statistics.json
```

```
Latest Activity

↓

last_trip.json

last_charge.json
```

This approach keeps the implementation transparent and easy to back up.

---

# Sensor Updates

Home Assistant sensors never calculate values themselves.

Instead they receive prepared values from the coordinator.

Benefits:

- lower CPU usage
- less disk access
- consistent values
- easier maintenance

---

# Home Assistant Integration

Ford Triplog follows Home Assistant best practices.

The integration uses:

- Config Entries
- DataUpdateCoordinator
- Entity Registry
- Device Registry
- Native Sensors
- Translation System

No unsupported techniques or custom frameworks are required.

---

# Performance Optimizations

Several optimizations reduce system load.

These include:

- Shared statistics cache
- Minimal disk access
- Incremental statistics updates
- Coordinator-based sensor refresh
- Individual JSON records

These optimizations allow Ford Triplog to scale efficiently even with extensive trip histories.

---

# Extensibility

The modular architecture allows new functionality to be added without changing existing data.

Examples include:

- additional statistics
- charging provider information
- charging costs
- trip exports
- dashboards
- timeline views

Existing installations remain compatible with future versions.

---

# Design Goals

Ford Triplog was designed with the following priorities:

- Reliability
- Transparency
- Performance
- Simplicity
- Native Home Assistant integration
- Local-first data storage

Every architectural decision supports one or more of these goals.

---

# Next Step

If something does not work as expected, see the troubleshooting guide.

➡ **[Troubleshooting](troubleshooting.md)**