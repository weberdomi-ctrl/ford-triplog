# Storage

Ford Triplog stores all data locally inside your Home Assistant installation.

No external database server is required.

No trip history, charging history or statistics are uploaded to cloud services.

---

# Storage Philosophy

Ford Triplog follows a simple design philosophy:

- Local-first
- Human-readable data
- Reliable recovery
- Fast startup
- Easy backup
- Automatic migration

All persistent data is stored as JSON files.

---

# Storage Location

All files are stored in the Home Assistant storage directory.

```
/config/.storage/ford_triplog/
```

The directory is created automatically during the first startup.

---

# Stored Data

Ford Triplog maintains several independent storage files.

Typical data includes:

- Trips
- Charging Sessions
- Statistics
- User Charging Locations
- OpenStreetMap Charging Database
- Runtime Information

Keeping these components separate simplifies updates and future migrations.

---

# Trips

The trip history contains every completed journey.

Each trip typically stores:

- Start time
- End time
- Distance
- Duration
- Average speed
- Start SOC
- End SOC
- Estimated energy consumption
- Start location
- End location
- Linked charging session (if available)

Trips are never modified after completion.

---

# Charging Sessions

Charging history contains every completed charging session.

Typical information includes:

- Start time
- End time
- Charging duration
- Start SOC
- End SOC
- Charged energy
- Charging location
- Charging provider
- Charging network
- Linked trip (if available)

Charging sessions are stored independently from trips.

---

# Statistics

Statistics are stored separately from individual trips.

Examples include:

- Total trips
- Total distance
- Total charging sessions
- Total charged energy
- Average consumption

This allows Home Assistant sensors to update quickly without recalculating the complete history.

---

# User Charging Locations

Custom charging locations are stored independently.

Each location may contain:

- Name
- Type
- Coordinates
- Address
- Brand
- Operator
- Network
- Connectors
- Charging power
- Charging points
- Matching radius
- Notes

These locations have priority over the OpenStreetMap charging database.

---

# OpenStreetMap Database

Downloaded charging databases are stored locally.

They are optimized for:

- Fast lookup
- Low memory usage
- Offline operation

The database only needs to be downloaded once for each country.

---

# Automatic Saving

Ford Triplog automatically saves data whenever necessary.

Examples include:

- Trip completed
- Charging session completed
- Statistics updated
- Charging location changed
- Configuration modified

No manual save operation is required.

---

# Recovery

Ford Triplog is designed to recover automatically after unexpected interruptions.

Examples:

- Home Assistant restart
- Power outage
- System reboot
- Integration restart

After startup, the integration restores its previous state and continues operating normally.

---

# Migration

Storage migrations are performed automatically.

When upgrading to a newer version:

- Existing files are preserved.
- Required migrations are executed automatically.
- Unsupported data is never deleted without migration.

No manual intervention is normally required.

---

# Backup

All Ford Triplog data is included in normal Home Assistant backups.

Recommended backup methods:

- Home Assistant Backup
- Home Assistant Google Drive Backup
- NAS Backup
- Manual backup of the configuration directory

No additional backup procedure is necessary.

---

# Restoring

After restoring a Home Assistant backup:

- Trips are restored.
- Charging sessions are restored.
- Statistics are restored.
- Charging locations are restored.
- Configuration is restored.

Ford Triplog resumes operation automatically.

---

# File Size

Trip and charging history grow over time.

Typical installations remain relatively small because data is stored efficiently as JSON.

Even several years of driving history usually require only a few megabytes of storage.

---

# Performance

The storage system has been optimized for:

- Fast startup
- Fast writing
- Low memory usage
- Reliable recovery

Statistics are maintained incrementally, avoiding expensive recalculations during normal operation.

---

# Privacy

All stored information remains inside your Home Assistant installation.

Ford Triplog never uploads:

- Trips
- Charging sessions
- Statistics
- Charging locations
- User-defined locations

Only the communication already performed by the FordPass integration is required.

---

# Frequently Asked Questions

## Can I edit the storage files?

Yes.

The files are standard JSON files.

However, manual editing is only recommended for advanced users and should always be performed while Home Assistant is stopped.

---

## Will updates delete my history?

No.

Storage migrations preserve existing data whenever possible.

---

## Can I move the storage directory?

Not directly.

Ford Triplog uses Home Assistant's configuration directory.

If the Home Assistant configuration is moved, the storage directory moves with it.

---

## Is a database server required?

No.

Ford Triplog uses lightweight local JSON storage and does not require SQLite, MariaDB or PostgreSQL.

Future versions may optionally support a database backend for very large installations, while JSON storage will remain the default.