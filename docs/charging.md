# Charging Sessions

Ford Triplog automatically detects and records charging sessions without requiring any manual interaction.

Each charging session becomes a permanent part of your local vehicle history and can be linked to the surrounding trips whenever possible.

---

# Automatic Detection

Charging sessions are detected automatically by monitoring the vehicle's charging state and battery State of Charge (SOC).

No user interaction is required.

Once charging starts, Ford Triplog creates a new charging session and continuously updates it until charging has finished.

---

# Recorded Information

Each charging session contains the following information.

## Time

- Start date
- Start time
- End date
- End time
- Charging duration

---

## Battery

- Start State of Charge (SOC)
- End State of Charge (SOC)
- SOC gained

---

## Energy

Ford Triplog estimates the charged energy using the configured usable battery capacity.

Recorded values include:

- Estimated charged energy (kWh)
- Average charging rate
- Charging efficiency (future)

---

## Location

Whenever possible, the charging location is identified automatically.

Depending on the available information, the session may include:

- Charging location name
- Address
- Charging provider
- Charging network
- Operator
- Maximum charging power
- Available connectors
- Number of charging points

---

# Charging Location Recognition

Charging locations are resolved using the following priority.

```
Home Assistant Zones

↓

User Charging Locations

↓

FordPass

↓

OpenStreetMap Database

↓

Reverse Geocoding
```

This approach combines the strengths of all available data sources while allowing complete user customization.

---

# Linking Trips and Charging Sessions

Trips and charging sessions are stored independently.

However, Ford Triplog automatically links them whenever appropriate.

A charging session is typically associated with the previous trip when:

- the charging location is close to the trip destination
- charging starts shortly after the trip ends

This allows future dashboard views and timelines to present a complete travel history without merging the underlying records.

---

# Charging History

Every completed charging session is stored locally.

Historical data remains available after:

- Home Assistant restart
- Integration update
- Vehicle restart
- System reboot

No manual backup is required beyond your normal Home Assistant backup strategy.

---

# Home Charging

Home charging locations can be created manually.

Benefits include:

- Consistent location names
- Reliable recognition
- Independent of OpenStreetMap
- Higher priority than public charging databases

Typical example:

```
Zuhause
```

---

# Workplace Charging

Workplace chargers can also be configured manually.

Typical example:

```
Arbeit
```

These locations are handled the same way as home charging locations and always take priority over the OpenStreetMap database.

---

# Public Charging

Public charging stations can be recognized automatically using:

- FordPass charging information
- User-defined locations
- OpenStreetMap charging database

If available, additional information such as provider, charging network and connectors is stored together with the charging session.

---

# Unknown Charging Locations

If Ford Triplog cannot identify a charging location, reverse geocoding is used as a fallback.

The charging session will still be recorded, typically including:

- Street
- City
- Country

You can later convert this location into a permanent user-defined charging location through the integration options.

Future charging sessions at the same place will then be recognized automatically.



---

# Charging Costs

Ford Triplog supports comprehensive charging cost tracking.

Charging sessions may contain:

- Energy costs
- Session fees
- Time-based fees
- Blocking fees
- Parking fees
- Additional costs
- Total charging cost
- Effective charging price
- Manual or automatic cost source
- Verified costs
- Receipt reference

---

# Home Charging Tariffs

Charging sessions inside the configured Home zone can be priced automatically.

Supported features:

- Two seasonal tariffs
- Configurable summer and winter periods
- Automatic tariff selection
- Automatic home charging cost calculation

---

# Energy Tracking

Charging sessions distinguish between:

- Energy stored in the battery
- Energy billed by the charging provider
- Charging losses
- Effective charging price

---

# Statistics

Charging sessions contribute to the lifetime charging statistics.

Examples include:

- Total charging sessions
- Total charged energy
- Average charged energy
- Total charging time

Additional statistics will be introduced in future releases.

---

# Local Storage

Charging sessions are stored locally in the Ford Triplog storage directory.

No charging history is uploaded to external services.

This ensures:

- Full privacy
- Fast access
- Complete ownership of your data

---

# Frequently Asked Questions

## Can I edit a charging session?

No.

Charging sessions are automatically generated and represent the recorded vehicle data.

---

## Are charging sessions deleted after updates?

No.

Existing charging history is preserved during updates and storage migrations.

---

## Does Ford Triplog support AC and DC charging?

Yes.

Both AC and DC charging sessions are recorded automatically.

At present, the charging type is not explicitly distinguished in the recorded data.

---

## What happens if Home Assistant restarts during charging?

Ford Triplog includes recovery mechanisms designed to resume normal operation after a restart.

Depending on the timing of the restart and the available vehicle data, the current charging session is restored or completed automatically whenever possible.

---

## Is an internet connection required?

Only for:

- FordPass communication
- Downloading OpenStreetMap charging databases

Normal charging detection and charging history operate entirely locally.