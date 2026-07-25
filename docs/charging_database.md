# Charging Database

Ford Triplog supports offline charging station databases based on OpenStreetMap (OSM).

The charging database significantly improves charging location recognition by identifying public charging stations without requiring an internet connection during normal operation.

---

# Overview

The charging database contains public charging infrastructure extracted from OpenStreetMap.

Depending on the available data, a charging station may include:

- Station name
- Operator
- Charging network
- Address
- Geographic coordinates
- Connector types
- Maximum charging power
- Number of charging points

The database is optimized for fast local lookups and integrates seamlessly with the charging location resolver.

---

# Why an Offline Database?

An offline database offers several advantages over live online lookups.

Benefits include:

- Very fast lookups
- No external API calls
- No usage limits
- Improved privacy
- Works without internet access
- No dependency on third-party services

Only the initial database download requires an internet connection.

---

# Downloading a Database

Charging databases can be downloaded directly from the integration.

Navigate to:

```
Settings

↓

Devices & Services

↓

Ford Triplog

↓

Configure

↓

Download Charging Database
```

Select the desired country.

The integration downloads and installs the database automatically.

---

# Supported Countries

Available countries depend on the databases published for Ford Triplog.

Each country is downloaded independently.

Only the selected database is stored locally.

Future releases will expand the list of supported countries.

---

# Storage

Downloaded databases are stored locally inside Home Assistant.

No external database server is required.

Databases remain available after:

- Home Assistant restart
- Integration update
- System reboot

A database only needs to be downloaded once.

---

# Lookup Process

When a charging session finishes, Ford Triplog attempts to identify the charging location.

If no FordPass or user-defined location is available, the charging database is searched.

```
Charging Session

↓

FordPass

↓

User Locations

↓

Charging Database

↓

Reverse Geocoding
```

The first matching charging station is used.

---

# Matching

Charging stations are matched using the recorded vehicle position.

Ford Triplog searches nearby charging stations within the configured search radius.

If multiple stations are available, the closest match is selected.

---

# Included Information

Depending on the OpenStreetMap data, the following information may be available.

## General

- Station name
- Address
- City
- Country

---

## Operator

Examples:

- IONITY
- Fastned
- Tesla
- Shell Recharge
- EVPass
- GOFAST

---

## Network

Charging networks are stored separately when available.

Examples:

- IONITY
- Tesla Supercharger
- Swisscharge
- EnBW mobility+
- Allego

---

## Connectors

Supported connector types depend on the OpenStreetMap data.

Typical examples:

- CCS
- Type 2
- CHAdeMO
- NACS
- Tesla Destination
- Tesla Supercharger
- Schuko
- CEE Red
- CEE Blue
- GBT AC
- GBT DC

---

## Charging Power

If available, the maximum charging power is stored.

Example:

```
350 kW
```

This information is provided for reference and is not currently used for charging calculations.

---

## Charging Points

Some charging stations include the number of available charging points.

Example:

```
12 charging points
```

Availability depends on the OpenStreetMap data.

---

# Updating a Database

Charging databases can be updated at any time.

Downloading the same country again replaces the existing local database with the latest version.

Previously recorded charging sessions remain unchanged.

---

# Country Changes

If you regularly travel in another country, simply download and activate the corresponding charging database.

Future versions of Ford Triplog will automatically switch databases based on the vehicle's current location.

---

# Performance

The charging database is optimized for Home Assistant.

Features include:

- Fast local lookups
- Optimized storage format
- Efficient geographic indexing
- Low memory usage

The lookup process typically completes within a fraction of a second.

---

# Privacy

The charging database operates completely locally.

After download:

- No internet connection is required.
- No charging history is uploaded.
- No location history is shared.

Only the database download itself requires internet access.

---

# Frequently Asked Questions

## Is the charging database required?

No.

Ford Triplog works without it.

However, public charging location recognition is significantly improved when a database is installed.

---

## Does the charging database replace FordPass?

No.

FordPass always has the highest priority.

The charging database is only used when FordPass does not provide sufficient charging location information.

---

## Can I use my own charging locations together with the database?

Yes.

User-defined charging locations always have priority over the OpenStreetMap database.

This allows you to customize names or override public charging stations.

---

## Will updating the database change old charging sessions?

No.

Charging sessions keep the information that was stored when the charging session was recorded.

Only future charging sessions use the updated database.

---

## Is an internet connection required?

Only to download or update the database.

Normal charging location recognition works completely offline afterwards.