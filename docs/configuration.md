# Configuration

After installing Ford Triplog, a configuration wizard guides you through the initial setup.

The integration uses entities provided by the official FordPass integration to detect trips, charging sessions and calculate statistics.

---

# Before You Start

Ensure that:

- FordPass is working correctly.
- Your vehicle is updating normally.
- The required FordPass entities exist.

> [!IMPORTANT]
> Ford Triplog does not communicate directly with your vehicle.
>
> All vehicle information is provided by the FordPass integration.

---

# Required Entities

During setup you will be asked to select the required entities.

## Vehicle Tracker

Used to determine:

- Vehicle location
- Trip start position
- Trip destination
- Address lookup

Example:

```
device_tracker.ford_explorer
```

---

## Ignition Sensor

Used to detect when a trip starts and ends.

Example:

```
binary_sensor.ford_ignition
```

---

## Odometer Sensor

The odometer is used to calculate the driven distance.

Example:

```
sensor.ford_odometer
```

> [!NOTE]
> Ford Triplog always uses the vehicle's odometer.
>
> GPS distance is **not** used.

---

## State of Charge Sensor

The battery State of Charge (SOC) is used for:

- Energy calculations
- Charging history
- Efficiency statistics

Example:

```
sensor.ford_state_of_charge
```

---

# Optional Configuration

Depending on your vehicle and FordPass entities, additional options may be available.

---

## Battery Capacity

Specify the usable battery capacity of your vehicle.

This value is used to estimate:

- Energy used
- Energy charged
- Consumption (kWh/100 km)

Example:

| Vehicle | Usable Capacity |
| :------ | --------------: |
| Explorer Extended Range | 79 kWh |
| Capri Extended Range | 79 kWh |

> [!TIP]
> Use the **usable** battery capacity rather than the gross battery capacity.

---

## Smart Trip

Smart Trip combines short stops into a single journey.

Instead of creating multiple short trips, Ford Triplog waits before finalizing a trip.

Typical examples include:

- Bakery
- Parcel station
- Short shopping stop
- Picking someone up
- Traffic interruption

This results in:

- Cleaner history
- Better statistics
- More realistic consumption values

---

## Smart Trip Timeout

The timeout defines how long Ford Triplog waits before completing a trip.

Example:

```
120 seconds
```

If the vehicle starts moving again before the timeout expires:

✅ Continue the existing trip

Otherwise:

✅ Complete the trip

---

# Charging Detection

Charging sessions are detected automatically.

No additional configuration is required for basic charging detection.

Ford Triplog records:

- Charging start
- Charging end
- Charging duration
- Charging location
- Added State of Charge
- Estimated charged energy
- Detected charging station, when a matching local database is available

---

# Charging-Site Database

Ford Triplog can identify public charging locations by comparing the vehicle coordinates with a local charging-site database.

The database is optional. Charging sessions are still recorded without it, but the charging location may then contain only the resolved address.

When a matching charging site is found, Ford Triplog can add information such as:

- Station name
- Brand
- Operator
- Charging network
- Maximum charging power
- Number of charging points
- Connector types
- Distance between the vehicle and the charging site

---

## Downloading Charging Locations

Open:

```text
Settings

↓

Devices & Services

↓

Ford Triplog

↓

Configure

↓

Charging-Site Database
```

Select the required country and start the download.

Ford Triplog then:

1. Downloads charging locations from OpenStreetMap through the Overpass service.
2. Normalizes the downloaded charging-station data.
3. Groups related charging points into charging sites.
4. Builds a geohash index for fast local lookup.
5. Validates the generated database.
6. Activates the selected country database.

> [!NOTE]
> The initial download can take several minutes, depending on the country and the response time of the Overpass service.

> [!IMPORTANT]
> Home Assistant must have internet access while the charging-site database is being downloaded.
>
> Normal charging-site recognition is performed locally after the database has been created.

---

## Country Selection

The country selection is initially based on the Home Assistant country setting when available.

You can change the selected country manually in the Ford Triplog options.

The generated files use country-specific names, for example:

```text
charging_sites_ch.json
charging_sites_de.json
charging_sites_at.json
```

Only the currently selected country database is used for charging-site lookup.

---

## Updating the Database

Open the Ford Triplog options again and start a new download for the selected country.

The existing database is replaced only after the newly generated file has been validated successfully.

This makes it possible to refresh charging locations when OpenStreetMap data changes.

---

## Charging-Site Storage

Generated charging-site databases are stored locally under:

```text
/config/.storage/ford_triplog/charging_sites/generated/
```

Example:

```text
/config/.storage/ford_triplog/charging_sites/generated/charging_sites_ch.json
```

No trip or charging-session data is uploaded during charging-site recognition.

---

# After Setup

Once configuration is complete, Ford Triplog immediately starts monitoring your vehicle.

The integration automatically creates:

- Trips
- Charging sessions
- Statistics
- Home Assistant sensors

No further configuration is required.

---

# Changing the Configuration

Open

```
Settings

↓

Devices & Services

↓

Ford Triplog

↓

Configure
```

Here you can modify:

- Smart Trip
- Smart Trip Timeout
- Battery Capacity
- Charging-site country
- Download or update the charging-site database

The changes take effect immediately.

---

# Storage Location

Configuration data and trip history are stored locally.

```
/config/.storage/ford_triplog/
```

No cloud storage is used.

---

# Next Step

Learn how Smart Trip works.

➡ **[Smart Trip](smart_trip.md)**