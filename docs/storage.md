# Data Storage

Ford Triplog stores all trip and charging information locally inside your Home Assistant configuration directory.

No external database or cloud service is required.

---

# Storage Location

All files are stored under:

```
/config/.storage/ford_triplog/
```

The integration automatically creates the required folders during setup.

---

# Directory Structure

A typical installation looks like this:

```
ford_triplog/

├── trips/
│   ├── trip_20260722T081523.json
│   ├── trip_20260722T164518.json
│   └── ...
│
├── charges/
│   ├── charge_20260722T184212.json
│   ├── charge_20260724T093105.json
│   └── ...
│
├── statistics.json
├── last_trip.json
└── last_charge.json
```

---

# Trips

Each completed trip is stored as an individual JSON file.

A trip contains information such as:

- Start time
- End time
- Start location
- Destination
- Distance
- Driving duration
- Average speed
- Battery usage
- Estimated energy consumption

Keeping trips in separate files makes backups and future exports straightforward.

---

# Charging Sessions

Each completed charging session is also stored as a separate JSON file.

Typical information includes:

- Charging start
- Charging end
- Charging duration
- Charging location
- Battery level before charging
- Battery level after charging
- Added State of Charge
- Estimated charged energy

Trips and charging sessions are intentionally stored independently.

---

# Statistics

The integration maintains a central statistics file.

```
statistics.json
```

It contains aggregated values such as:

- Trip count
- Charge count
- Total distance
- Total energy used
- Average consumption
- Average trip duration
- Average charging duration

The statistics file allows Home Assistant sensors to update quickly without reading every archived trip.

---

# Latest Activity

Two helper files provide quick access to the latest completed records.

```
last_trip.json
```

Contains the most recently completed trip.

```
last_charge.json
```

Contains the most recently completed charging session.

Most dashboard sensors use these files directly.

---

# Performance

Ford Triplog is designed for long-term operation.

To minimize disk access:

- Cached statistics are used whenever possible.
- Individual trip files are only read when necessary.
- Sensors share a common statistics cache.
- JSON files remain small and efficient.

This allows the integration to scale to thousands of trips while maintaining good performance.

---

# Home Assistant Restart

If Home Assistant restarts while:

- a trip is active, or
- a charging session is active,

Ford Triplog restores the active state after startup and continues recording.

Completed trips and charging sessions remain unaffected.

---

# Backup

Because all data is stored as JSON files, backup is simple.

You only need to include:

```
/config/.storage/ford_triplog/
```

Home Assistant's built-in backup feature automatically includes this directory.

---

# Manual Editing

The JSON files are human-readable.

However:

> [!WARNING]
> Manual editing is not recommended unless you know exactly what you are doing.

Incorrect modifications may lead to inconsistent statistics or missing history.

---

# Future Compatibility

The storage format is designed to remain compatible across future versions whenever possible.

New information may be added to existing JSON files, but existing data should continue to work after upgrading.

---

# Next Step

Learn how Ford Triplog protects your privacy.

➡ **[Privacy](privacy.md)**