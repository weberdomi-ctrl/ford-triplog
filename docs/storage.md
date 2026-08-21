# Storage

Ford Triplog stores all data locally inside your Home Assistant installation.

No external database server is required.

No trip history, charging history or statistics are uploaded to cloud services.

---

# Storage Philosophy

Ford Triplog follows a simple design philosophy:

- Local-first
- Reliable recovery
- Fast startup
- Easy backup
- Automatic migration
- Backend-neutral access

Ford Triplog 2.1 introduced SQLite alongside the existing JSON storage. Ford Triplog 2.2 continues the parallel JSON/SQLite validation phase.

---

# Storage Location

Ford Triplog stores its persistent files locally inside the Home Assistant configuration and storage area.

The exact files depend on the enabled features and storage backend. The integration manages these locations automatically; manual file handling is not required.

---

# Stored Data

Ford Triplog maintains several independent local data sets.

Typical data includes:

- Trips
- Journeys
- Charging Sessions
- GPS routes
- Statistics and diagnostics
- User and pending Charging Locations
- Charging and pause metadata
- Receipts and receipt parser profiles
- OpenStreetMap Charging Database
- Runtime Information
- Configuration

The Storage Manager provides a backend-neutral interface so higher-level components do not depend directly on JSON or SQLite.

---


# Storage Backends

Ford Triplog 2.2 supports JSON and SQLite as local read backends.

JSON remains the default read backend after upgrading. Existing users are not switched automatically to SQLite.

SQLite can be selected explicitly in the Ford Triplog settings. Changing the selected read backend reloads the integration.

During the 2.2 transition phase:

- Compatible data is written to JSON and SQLite
- Existing compatible data is migrated or mirrored into SQLite
- Historical Trips, charging sessions, Journeys and routes can be read from SQLite
- Journey rebuild uses the selected read backend
- Statistics are recalculated from the selected backend after setup or reload
- JSON remains available as a compatibility and fallback path

No external database server is required.

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

# Receipts

Receipt documents are stored locally and linked through metadata to charging sessions or Journey pauses.

Multiple receipts can be linked to the same record. Charging receipts can optionally use OCR/parser information, while pause receipts do not require OCR.

---

# CSV Exports

Ford Triplog 2.2 can generate CSV exports for Trips, Journeys and charging sessions.

Export data is read through the Storage Manager so it works independently of the selected JSON or SQLite read backend.

Generated files remain local until explicitly downloaded through Home Assistant.

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

Trip, Journey, route, charging and receipt history grow over time.

Structured history remains relatively compact. Receipt files and route data can require additional storage depending on usage.

---

# Performance

The storage system has been optimized for:

- Fast startup
- Fast writing
- Low memory usage
- Reliable recovery

Statistics are maintained efficiently during normal operation. Backend-neutral archive access and SQL-backed queries/views are used where appropriate, while statistics can also be rebuilt from the selected historical backend.

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

Manual editing is not recommended.

Ford Triplog 2.2 may store related information in both JSON and SQLite. Editing one backend directly can therefore create inconsistencies between the mirrored data sets.

Use the Ford Triplog configuration and maintenance functions whenever possible.

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

SQLite is embedded locally and requires no separate server. Ford Triplog 2.2 continues to support JSON alongside SQLite during the storage transition.