# Privacy

Privacy is one of the core principles of Ford Triplog.

The integration is designed to keep all trip and charging data under your control.

---

# Local Storage Only

Ford Triplog stores all recorded information locally inside your Home Assistant configuration.

No trip history is uploaded to external servers.

No cloud account is required.

No telemetry is collected.

---

# No External Database

Ford Triplog does **not** use:

- SQL databases
- Cloud databases
- Third-party storage providers

All information is stored as local JSON files.

---

# Internet Access

Ford Triplog does not communicate directly with your vehicle.

Instead, it uses entities provided by the official FordPass integration.

The integration itself does not send trip or charging data to external services.

---

# Stored Information

Depending on your configuration, Ford Triplog stores information such as:

## Trips

- Start time
- End time
- Start location
- Destination
- Distance
- Driving duration
- Battery usage
- Estimated energy consumption

## Charging Sessions

- Charging start
- Charging end
- Charging duration
- Charging location
- Battery level before charging
- Battery level after charging
- Estimated charged energy

---

# GPS Information

Vehicle coordinates are only used to determine readable locations.

These locations are stored together with the trip or charging session.

No continuous GPS tracking is performed.

---

# Address Lookup

When enabled, Ford Triplog converts GPS coordinates into human-readable addresses.

Examples:

```
Home
```

```
IONITY Neuenkirch
```

```
Zurich Airport
```

The resulting address is stored locally together with the trip.

---

# Home Assistant

Ford Triplog uses standard Home Assistant mechanisms:

- Entity Registry
- Device Registry
- DataUpdateCoordinator
- Local Storage

No custom background services are installed.

---

# Sharing Data

You remain in full control of your data.

If you choose to share:

- JSON files
- screenshots
- log files

please remember that they may contain:

- locations
- timestamps
- driving history
- charging history

Review the files before publishing them.

---

# Backup

Trip history is automatically included in Home Assistant backups.

No additional export is required.

---

# Open Source

Ford Triplog is fully open source.

All source code can be reviewed to verify how data is processed and stored.

Community contributions are welcome.

---

# Summary

Ford Triplog follows a simple privacy philosophy:

✔ Local storage only

✔ No telemetry

✔ No cloud database

✔ No analytics

✔ No advertising

✔ Full ownership of your own driving data

---

# Next Step

Interested in how Ford Triplog works internally?

➡ **[Architecture](architecture.md)**