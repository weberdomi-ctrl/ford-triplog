# Smart Trip

Smart Trip is one of the core features of Ford Triplog.

It intelligently combines short vehicle stops into a single journey, creating a driving history that better reflects how people actually travel.

Without Smart Trip, every short stop would create a new trip. With Smart Trip enabled, brief interruptions are merged into one continuous journey.

---

# Why Smart Trip?

Many everyday journeys include short stops.

Typical examples include:

- Picking up groceries
- Collecting a parcel
- Dropping off passengers
- Buying coffee
- Brief charging stops

These are usually part of one journey rather than several independent trips.

Smart Trip automatically handles these situations.

---

# Example

Without Smart Trip:

```
Home

↓

Bakery

↓

Supermarket

↓

Office
```

Recorded as:

- Trip 1
- Trip 2
- Trip 3

---

With Smart Trip enabled:

```
Home

↓

Bakery

↓

Supermarket

↓

Office
```

Recorded as:

- One single trip

---

# How It Works

A trip starts when:

- the ignition is switched on, and
- the vehicle begins moving.

The trip remains active while the vehicle is driving.

If the vehicle stops, Ford Triplog starts a configurable timeout.

If the vehicle starts moving again before the timeout expires, the journey continues as the same trip.

If the timeout expires, the trip is finalized and stored.

---

# Smart Trip Timeout

The timeout determines how long a stop may last before a trip is considered complete.

The default value is:

```
180 seconds
```

Typical values:

| Timeout | Behaviour |
|----------|-----------|
| 60 seconds | Only very short stops are merged |
| 180 seconds | Recommended |
| 300 seconds | Longer stops remain part of the same trip |

---

# Timeline Example

```
08:00  Leave Home

↓

08:18  Coffee Stop

↓

08:20  Continue Driving

↓

08:45  Arrive at Work
```

Coffee stop duration:

```
2 minutes
```

Result:

```
One Trip
```

---

Second example:

```
17:00 Leave Work

↓

17:08 Shopping

↓

17:45 Continue Driving

↓

18:00 Arrive Home
```

Shopping duration:

```
37 minutes
```

With a timeout of 180 seconds:

```
Trip 1

+

Trip 2
```

The stop exceeds the Smart Trip timeout and therefore starts a new journey.

---

# Benefits

Smart Trip provides:

- Cleaner trip history
- More realistic driving statistics
- Better average speed calculations
- Reduced fragmentation
- Improved charging and trip association

---

# Charging Sessions

Charging sessions are handled independently.

A charging session may occur:

- during a Smart Trip stop
- after a completed trip
- before the next trip

Whenever possible, Ford Triplog automatically links charging sessions with the corresponding trip while keeping both records separate.

---

# Configuration

Navigate to:

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

Existing trip history remains unchanged.

---

# Best Practices

Recommended timeout values:

| Usage | Timeout |
|--------|----------|
| City driving | 120–180 seconds |
| Mixed driving | 180 seconds |
| Frequent short stops | 240–300 seconds |

For most users, the default value of **180 seconds** provides the best balance between accurate trip separation and realistic journey tracking.

---

# Frequently Asked Questions

## Does Smart Trip modify completed trips?

No.

Only the currently active trip can be extended.

Completed trips are never changed.

---

## Can Smart Trip be disabled?

Yes.

When disabled, every completed drive is stored as an individual trip.

---

## Does Smart Trip affect charging history?

No.

Charging sessions are recorded independently of Smart Trip.

They may be linked to trips for timeline purposes, but each charging session remains a separate record.

---

## Is Smart Trip required?

No.

The integration works normally without Smart Trip.

Enabling it simply produces a cleaner and more natural trip history for most driving patterns.