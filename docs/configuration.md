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
> All vehicle information is provided by the official FordPass integration.

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

No additional configuration is required.

Ford Triplog records:

- Charging start
- Charging end
- Charging duration
- Charging location
- Added State of Charge
- Estimated charged energy

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