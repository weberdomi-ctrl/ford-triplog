# Smart Trip

One of the key features of Ford Triplog is **Smart Trip**.

Instead of creating a new trip every time the vehicle briefly stops, Smart Trip intelligently merges short stops into a single journey.

The result is a much cleaner and more realistic driving history.

---

# Why Smart Trip?

Many real-world journeys include short stops.

For example:

- Buying bread
- Picking up a parcel
- Dropping someone off
- Brief shopping
- Waiting at a charging station
- Waiting in the vehicle

Without Smart Trip, every stop would create a separate trip.

Example:

```
Home → Bakery
2 km

Bakery → Work
18 km
```

This would produce two trips even though it was actually one journey.

Smart Trip combines both into:

```
Home → Work
20 km
```

---

# How It Works

When the vehicle stops, Ford Triplog does **not** immediately finish the trip.

Instead, it starts a configurable timer.

```
Vehicle stops

↓

Start timeout

↓

Vehicle moves again?

        YES
         │
Continue current trip

        NO
         │
Finish trip
```

---

# Smart Trip Timeout

The timeout determines how long Ford Triplog waits before closing a trip.

Example:

```
120 seconds
```

If the vehicle starts moving again within those 120 seconds:

✅ Continue the existing trip

Otherwise:

✅ Finish the trip

The timeout can be changed in the integration options.

---

# Benefits

Smart Trip provides several advantages.

✔ Cleaner trip history

✔ More realistic journeys

✔ Better consumption calculations

✔ Reduced trip fragmentation

✔ Improved long-term statistics

---

# Example

Without Smart Trip:

```
08:00 Home → Bakery

2 km
```

```
08:07 Bakery → Work

18 km
```

Result:

```
2 trips
20 km total
```

---

With Smart Trip:

```
08:00 Home

↓

Bakery

↓

Work
```

Result:

```
1 trip
20 km
```

The short stop is automatically merged into the existing journey.

---

# Charging Stops

Smart Trip also works well together with charging sessions.

A charging session is always stored as its own event.

However, if charging only interrupts a journey briefly, the trip itself can continue after charging depending on the configured timeout.

This keeps driving history and charging history logically separated while preserving the complete travel timeline.

---

# Recovery

If Home Assistant restarts during an active trip, Ford Triplog restores the trip automatically after startup.

No completed trip is lost because of a restart.

---

# Configuration

Smart Trip can be enabled or disabled at any time.

Open:

```
Settings

↓

Devices & Services

↓

Ford Triplog

↓

Configure
```

Available options:

- Enable Smart Trip
- Smart Trip Timeout

Changes take effect immediately.

---

# Tips

> [!TIP]
> A timeout between **60 and 180 seconds** works well for most drivers.

Shorter values create more individual trips.

Longer values merge more short stops into a single journey.

---

# Next Step

Learn how Ford Triplog records charging sessions.

➡ **[Charging](charging.md)**