# Charging Sessions

Ford Triplog automatically records every completed charging session.

Each charging session is stored independently from trips, creating a complete charging history alongside your driving history.

No manual interaction is required.

---

# Automatic Detection

Charging starts automatically when the configured charging entities indicate that the vehicle is charging.

Ford Triplog monitors the charging process and records all relevant information until charging is complete.

Each charging session includes:

- Start time
- End time
- Charging duration
- Charging location
- Battery level at start
- Battery level at end
- State of Charge added
- Estimated charged energy

---

# Estimated Charged Energy

Ford Triplog estimates the charged energy using:

- Configured usable battery capacity
- State of Charge difference

Example:

Battery capacity

```
79 kWh
```

Charging

```
20 % → 80 %
```

Estimated charged energy

```
47.4 kWh
```

This calculation provides a realistic estimate without requiring data from the charging station.

---

# Charging Location

The charging location is determined from the vehicle position at the beginning of the charging session.

The location is converted into a readable address, for example:

```
IONITY Neuenkirch
Switzerland
```

or

```
Home
Buttikon SZ
```

This makes it easy to browse your charging history without interpreting GPS coordinates.

---

# Charging History

Every completed charging session is permanently stored.

Example:

```
Home

↓

Fastned Oftringen

↓

IONITY Neuenkirch

↓

Tesla Supercharger Pratteln
```

Your complete charging history remains available even after Home Assistant restarts.

---

# Relation to Trips

Trips and charging sessions are stored as separate records.

This provides several advantages:

- Independent trip history
- Independent charging history
- Better statistics
- Easier future expansion

Although stored separately, charging sessions can be linked to trips when appropriate.

This enables a complete travel timeline while keeping the underlying data clean and flexible.

---

# Local Storage

Charging sessions are stored as JSON files.

```
/config/.storage/ford_triplog/charges/
```

Each charging session is written as an individual file.

This allows:

- Simple backups
- Human-readable data
- Easy future export
- Fast recovery

---

# Recovery

If Home Assistant restarts during an active charging session, Ford Triplog restores the unfinished charging session automatically.

Once charging ends, the session is completed normally.

No charging information is lost because of a restart.

---

# Statistics

Charging sessions automatically update lifetime statistics.

Available statistics include:

- Charge Count
- Average Charge Duration
- Average Charge Start SOC
- Average Charge End SOC
- Average Charge SOC Added

These statistics are continuously updated after every completed charging session.

---

# Future Improvements

Several charging features are planned for future releases.

## Version 1.4

Planned improvements include:

- Smart Charge Pause / Resume
- Named charging locations
- Charging provider detection
- AC / DC recognition
- Improved charging statistics

These additions will further improve the charging history while remaining fully compatible with existing data.

---

# Tips

> [!TIP]
> Ford Triplog estimates charged energy using the configured usable battery capacity.
>
> Keeping this value accurate results in more precise charging statistics.

---

# Next Step

Learn about all available entities.

➡ **[Sensors](sensors.md)**