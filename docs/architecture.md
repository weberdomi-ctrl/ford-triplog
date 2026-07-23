# Architecture

Ford Triplog is built around Home Assistant's recommended integration architecture.

The integration follows an event-driven design and uses a central coordinator to manage trip detection, charging detection, charging-site recognition, statistics, storage and sensor updates.

<p align="center">
  <img src="images/architecture.svg" width="1100" alt="Ford Triplog architecture">
</p>

## Overview

FordPass provides the live vehicle entities used by Ford Triplog. The `FordTriplogCoordinator` monitors those entities and controls trip and charging-session processing.

Ford Triplog 1.4 adds a local charging-site pipeline. Charging locations can be downloaded from OpenStreetMap or imported as a compatible JSON database. The selected country database is loaded into a geohash-based lookup index and used to enrich charging sessions with station details.

The coordinator delegates work to these main areas:

- trip detection and Smart Trip
- charging-session detection
- charging-site lookup and enrichment
- reverse geocoding
- statistics processing
- local JSON storage
- Home Assistant sensor updates

Completed records are written to local JSON storage. Active trips and charging sessions can be restored after a Home Assistant restart. Home Assistant sensors expose the prepared values to dashboards, automations and history.

## Core components

### FordTriplogCoordinator

The `FordTriplogCoordinator` is the central runtime component.

It is responsible for:

- monitoring FordPass entities
- detecting trips
- detecting charging sessions
- waiting for stable vehicle data before finalization
- resolving addresses through reverse geocoding
- looking up nearby charging sites
- enriching charging records with station metadata
- linking charging sessions to preceding trips when plausible
- updating statistics
- writing recovery, history and cache files
- refreshing Home Assistant sensors

### FordPass vehicle data

Ford Triplog uses configured Home Assistant entities for:

- ignition
- odometer
- vehicle position
- state of charge
- charging status
- optional state of health

These entities remain the live source. Ford Triplog converts their state changes into persistent trip and charging history.

### Trip detection

Trip detection uses vehicle state changes and data from:

- ignition
- odometer
- vehicle position
- state of charge

Smart Trip pauses a trip after ignition-off and waits for a configurable timeout. If driving resumes within that period, the same trip is continued instead of creating a new record.

### Charging detection

Charging sessions are recorded independently from trips.

The coordinator records:

- charging start and end
- charging duration
- start and end SOC
- start and end coordinates
- start and end address
- estimated charged energy
- linked trip ID when a preceding trip is close enough in time and distance
- detected charging-site information

### Charging-site database pipeline

Charging-site databases are managed through the Home Assistant options flow.

A database can be created or activated in two ways:

1. Download charging locations for a selected country from OpenStreetMap.
2. Import an existing compatible Ford Triplog charging-site JSON file.

The OpenStreetMap pipeline performs these stages:

```text
OpenStreetMap / Overpass
        ↓
Raw charging-station elements
        ↓
Normalization
        ↓
Charging-site grouping
        ↓
Geohash index generation
        ↓
Country database
        ↓
Validation and activation
```

The active database is stored locally under:

```text
/config/.storage/ford_triplog/charging_sites/generated/
```

Country files use names such as:

```text
charging_sites_ch.json
charging_sites_de.json
charging_sites_at.json
```

The configured country is selected in the integration options. The default selection can be derived from `hass.config.country`, while the user can change it manually.

### ChargingSiteLookup

`ChargingSiteLookup` loads the selected country database when the coordinator starts.

For a charging session, the coordinator passes the current vehicle coordinates to the lookup component. The geohash index limits the search to nearby database cells. Candidate locations are then checked against the configured lookup radius.

When a matching site is found, the charging record can be enriched with:

- site ID
- name
- brand
- operator
- network
- charging power
- capacity
- connector types
- data quality
- distance from the vehicle position

Charging-site lookup remains entirely local during normal operation. OpenStreetMap access is required only when creating a new country database.

### Reverse geocoding

Reverse geocoding converts vehicle coordinates into address data.

Address information and charging-site information are separate:

- reverse geocoding provides the postal address
- charging-site lookup provides station identity and technical metadata

A charging session may therefore contain both a complete address and a named charging site such as an operator, network or station name.

### History and statistics

`FordTriplogHistory` provides:

- complete trip history access
- complete charging-history access
- recalculation of aggregate statistics
- a compact shared snapshot for Home Assistant sensors

The sensor snapshot reads only:

- statistics
- last trip
- last charging session

A short cache prevents all sensor entities from reading the same files repeatedly during a coordinated update.

### Storage layer

`FordTriplogStorage` stores data as local JSON files and uses atomic replacement for writes.

Current structure:

```text
/config/.storage/ford_triplog/
├── recovery/
│   ├── current_trip.json
│   └── current_charge.json
├── trips/
│   └── YYYY/MM/*.json
├── charges/
│   └── YYYY/MM/*.json
├── cache/
│   ├── last_trip.json
│   ├── last_charge.json
│   ├── statistics.json
│   └── diagnostics.json
└── charging_sites/
    └── generated/
        ├── charging_sites_ch.json
        ├── charging_sites_de.json
        └── ...
```

### Active session recovery

Active trips and charging sessions are saved in the recovery directory.

After a Home Assistant restart, the coordinator restores:

- the active trip
- the active charging session
- charging-site metadata already detected for the active session

Completed history remains unaffected.

### Home Assistant sensors

Sensors receive prepared data from the coordinator and history layer.

They expose:

- latest trip information
- latest charging information
- detected charging-site name
- charging-site details as attributes
- driving and charging statistics
- translated entity names
- native Home Assistant units and device classes

The charging-site sensor uses the first available value in this order:

1. site name
2. brand
3. operator
4. network

Additional station details remain available as entity attributes.

## Runtime data flow

```text
FordPass entities
        ↓
FordTriplogCoordinator
        ├── Trip / Smart Trip
        ├── Charging session
        ├── Reverse geocoding
        └── ChargingSiteLookup
                  ↑
        Local country database
                  ↑
        Import or OSM download pipeline
        ↓
Charge / Trip objects
        ↓
Storage + History + Statistics
        ↓
Home Assistant sensors
        ↓
Dashboard, automations and history
```

## Design goals

Ford Triplog is designed around:

- reliability
- local data ownership
- transparent JSON storage
- low disk activity
- non-blocking Home Assistant operation
- native Home Assistant integration
- country-specific charging-site databases
- fast local geohash lookup
- future extensibility

## Privacy

Trip history, charging history, statistics and the active charging-site database remain inside Home Assistant.

Ford Triplog does not upload recorded trips or charging sessions. OpenStreetMap is contacted only when the user explicitly downloads a new charging-site database.

## Next step

See the troubleshooting guide:

[ Troubleshooting](troubleshooting.md)
