# Dashboard

Ford Triplog exposes native Home Assistant entities that can be used with any standard Lovelace card.

No custom dashboard or frontend components are required.

---

# Typical Dashboard

A common dashboard consists of three sections:

- Last Trip
- Last Charging Session
- Lifetime Statistics

Example:

```
┌─────────────────────────────────────┐
│ Ford Explorer EV                    │
├─────────────────────────────────────┤
│ Last Trip                           │
│ 42.8 km                             │
│ 15.7 kWh/100 km                     │
│ 58 min                              │
├─────────────────────────────────────┤
│ Last Charging Session               │
│ 28 % → 80 %                         │
│ 41 min                              │
│ Home                                │
├─────────────────────────────────────┤
│ Statistics                          │
│ 18,452 km                           │
│ 486 Trips                           │
│ 132 Charges                         │
│ 16.1 kWh/100 km                     │
└─────────────────────────────────────┘
```

---

# Last Trip Card

Recommended entities:

- Last Distance
- Last Consumption
- Last Energy Used
- Last Average Speed
- Last Driving Time
- Last Destination

This card gives an immediate overview of your latest journey.

---

# Charging Card

Recommended entities:

- Last Charging Location
- Last Charge Start SOC
- Last Charge End SOC
- Last Charge Duration
- Last Charge SOC Added

Perfect for monitoring your latest charging session.

---

# Statistics Card

Recommended entities:

- Total Distance
- Trip Count
- Charge Count
- Average Consumption
- Average Trip Distance
- Average Trip Energy

These values continuously grow with your driving history.

---

# Battery Card

Useful entities:

- Last Trip SOC Used
- Average Trip SOC Used
- Average Charge Start SOC
- Average Charge End SOC

These sensors provide a good overview of battery usage over time.

---

# Maps

The following entities work well together with the standard Home Assistant Map Card:

- Last Start Address
- Last Destination
- Last Charging Location

Future releases may include interactive trip maps.

---

# Graphs

The History Graph and Statistics Graph cards are ideal for visualising:

- Average Consumption
- Average Trip Distance
- Average Trip Energy
- Average Charge Duration

Because all sensors are native Home Assistant entities, they integrate directly with the built-in statistics engine.

---

# Dashboard Tips

> [!TIP]
> Create separate dashboard sections for:
>
> - Recent Activity
> - Charging
> - Statistics
> - Battery
> - Vehicle Information

This keeps the dashboard easy to read.

---

# Example Layout

Suggested layout:

```
Vehicle

├── Last Trip
├── Last Charging Session
├── Lifetime Statistics
├── Battery Information
└── Consumption History
```

---

# Future Dashboard Features

The following features are planned:

- Ready-made dashboard cards
- Interactive trip timeline
- Charging timeline
- Monthly statistics
- Annual summaries
- Map visualisations

---

# Next Step

Ford Triplog sensors can also be used in automations.

➡ **[Automations](automations.md)**