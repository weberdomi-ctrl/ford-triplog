# Journeys

Journeys are one of the key features introduced in Ford Triplog 1.6.

Instead of treating every trip independently, Ford Triplog automatically groups related trips and charging sessions into a single Journey, providing a complete view of your daily driving.

---

# Overview

A Journey starts automatically when a new trip begins.

While the Journey is active, Ford Triplog continuously collects:

- Trips
- Pauses
- Charging sessions
- Distance
- Driving time
- Pause time
- Charging time
- Energy consumption
- State of Charge (SOC) usage
- Charging costs

A Journey is automatically completed when one of the configured completion conditions is met.

---

# Typical Example

```
Journey

├── Trip 1 (Home → Supermarket)
├── Trip 2 (Supermarket → Fast Charger)
├── Charging Session
├── Trip 3 (Fast Charger → Restaurant)
├── Pause (Restaurant)
├── Trip 4 (Restaurant → Home)
└── Journey completed
```

Although four individual trips were made, they belong to one complete Journey.

---

# Journey Completion

Ford Triplog automatically detects when a Journey has finished.

A Journey can end in several ways.

## Home Zone

If the vehicle returns to the configured Home Zone, the Journey is completed automatically.

This is the preferred method because it reflects the natural end of a journey.

---

## Timeout

If no new trip starts within the configured Journey Timeout, the Journey is automatically completed.

This prevents Journeys from remaining open indefinitely.

---

## Maximum Journey Gap

If the time between two trips exceeds the configured Maximum Journey Gap, Ford Triplog starts a new Journey.

This allows multiple independent Journeys on the same day.

---

# Charging Sessions

Charging sessions are automatically assigned to the currently active Journey.

A Journey may contain:

- No charging session
- One charging session
- Multiple charging sessions

Charging sessions remain separate records while still being linked to the Journey.

---

# Journey Statistics

Each Journey stores useful summary information, including:

- Start time
- End time
- Total duration
- Driving duration
- Pause duration
- Charging duration
- Total distance
- Number of trips
- Number of charging sessions
- Energy consumption
- Energy charged
- SOC consumption
- Battery energy balance
- Charging cost summary
- Average charging price

These values are used by the Journey and Journey History sensors, dashboards and statistics.

---

# Configuration

Journey behaviour can be configured from the integration Options.

Available settings include:

- Home Zone
- Journey Timeout
- Maximum Journey Gap

These options allow Ford Triplog to adapt to different driving habits.

---

# Pause Metadata and Receipts

Journey pauses can contain additional user-maintained information, including:

- Category
- Note
- Costs
- Receipts

Multiple receipts can be linked to the same pause. Pause receipts do not require OCR.

Journey History exposes this information for the selected date so it can be used in dedicated Home Assistant dashboard cards.

---

# Local Storage

Journeys are stored locally through the Ford Triplog Storage Manager.

Ford Triplog 2.2 supports JSON and SQLite during the parallel-storage transition. No external database server or cloud service is required.

All Journey information remains under your control.

---

# Benefits

Journey Management provides several advantages:

- Complete driving history
- Better dashboard presentation
- Automatic grouping of related trips
- Automatic charging session assignment
- Improved long-term statistics
- Fully automatic operation

---

# Export

Ford Triplog 2.2 can export Journey history as CSV.

The export can optionally be filtered by date and downloaded directly through Home Assistant.

---

# Future Improvements

Future versions may further extend Journey functionality with:

- Long-term history improvements
- Additional SQL-based statistics and aggregation
- Multi-vehicle support