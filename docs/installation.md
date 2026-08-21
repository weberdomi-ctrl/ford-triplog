# Installation

Ford Triplog is distributed through the Home Assistant Community Store (HACS).

Installation only takes a few minutes and does not require any manual file copying.

---

# Requirements

Before installing Ford Triplog, ensure the following requirements are met.

## Home Assistant

- Home Assistant 2026.6 or newer

Earlier versions may work but are not officially supported.

---

## HACS

Ford Triplog is installed and updated using HACS.

If HACS is not installed yet, follow the official installation guide:

https://hacs.xyz/

---

## FordPass Integration

Ford Triplog requires compatible Home Assistant vehicle entities.

FordPass is the traditional data source. Ford Triplog 2.2 allows the selected vehicle entities to be changed later, so another compatible vehicle-data integration can be used without deleting the existing Triplog history.

Make sure your vehicle data source is correctly connected and the following entities are available:

- Vehicle Tracker
- Odometer
- State of Charge (SOC)
- Ignition

---

# Installation

## Step 1

Open **HACS**.

Navigate to:

**Integrations**

---

## Step 2

Search for:

```
Ford Triplog
```

Open the integration page.

---

## Step 3

Click

```
Download
```

Wait until HACS has finished installing the integration.

---

## Step 4

Restart Home Assistant.

This step is required after the first installation.

---

## Step 5

Open

```
Settings
→ Devices & Services
→ Add Integration
```

Search for

```
Ford Triplog
```

Select the integration.

---

# Initial Configuration

During setup you will be asked to select four vehicle entities. These selections can be changed later in the Ford Triplog options.

## Vehicle Tracker

The tracker entity representing your vehicle.

Example:

```
device_tracker.ford_explorer
```

---

## Ignition Sensor

Entity indicating whether the vehicle ignition is on.

Example:

```
binary_sensor.explorer_ignition
```

---

## Odometer

Current vehicle mileage.

Example:

```
sensor.explorer_odometer
```

---

## State of Charge

Battery charge level.

Example:

```
sensor.explorer_soc
```

---

# Optional Settings

After installation, additional options are available.

## Smart Trip

Combines short stops into one continuous journey.

Useful for:

- Shopping
- Charging stops
- Picking up passengers
- Short breaks

---

## Smart Trip Timeout

Defines how long a stop may last before a trip is considered finished.

Typical values:

| Timeout | Result |
|----------|--------|
| 60 seconds | Very aggressive merging |
| 180 seconds | Recommended |
| 300 seconds | Conservative |

---

## Battery Capacity

Allows entering the usable battery capacity.

This improves energy calculations.

Example:

```
79 kWh
```

---

## Charging Database Country

Select the OpenStreetMap charging database to use.

Supported countries depend on the available downloadable databases.

The selected country can be changed later at any time.

---

# Download Charging Database

Open

```
Settings
→ Devices & Services
→ Ford Triplog
→ Configure
```

Select

```
Download Charging Database
```

Choose the desired country.

The database is downloaded automatically and stored locally.

---

# Changing Vehicle Data Source

Ford Triplog 2.2 allows the configured tracker, ignition, odometer and SOC entities to be changed later.

This can be used to migrate between compatible vehicle-data integrations while preserving the existing Ford Triplog history.

---

# Updating

Updates are installed through HACS.

Steps:

1. Open HACS
2. Update Ford Triplog
3. Restart Home Assistant

Existing trips, charging sessions and statistics are preserved automatically.

---

# Migration

Ford Triplog automatically migrates stored data when upgrading to newer versions.

No manual migration is required.

If a migration cannot be completed safely, the integration preserves the existing data and reports the problem in the Home Assistant log.

---

# Verifying the Installation

After setup you should see:

- Ford Triplog device
- Trip sensors
- Charging sensors
- Statistics sensors

The integration will automatically start recording new trips and charging sessions.

No further configuration is required.

---

# Troubleshooting

## Integration not found

Verify:

- HACS is installed.
- Home Assistant has been restarted after installation.

---

## No trips are recorded

Verify that:

- the tracker updates correctly
- the ignition entity changes state
- the odometer increases while driving
- the SOC sensor reports valid values

---

## Charging sessions are not detected

Verify:

- SOC updates while charging
- the charging database has been downloaded (optional)
- charging locations are configured correctly if using custom locations

---

## Need More Help?

See:

- [Configuration](configuration.md)
- [Troubleshooting](troubleshooting.md)
- [FAQ](../FAQ.md)