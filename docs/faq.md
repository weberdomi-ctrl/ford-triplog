# FAQ

This document answers the most frequently asked questions about Ford Triplog.

If your question is not covered here, please check the documentation or open a GitHub issue.

---

# General

## What is Ford Triplog?

Ford Triplog is a Home Assistant custom integration that automatically records trips and charging sessions for Ford electric vehicles.

It extends the existing FordPass integration by creating a permanent local history with statistics, charging information and Home Assistant sensors.

---

## Does Ford Triplog replace the FordPass integration?

No.


Ford Triplog uses Home Assistant vehicle entities as its data source. FordPass is the traditional source, while Ford Triplog 2.2 allows the configured vehicle entities to be changed later when using another compatible vehicle-data integration.

Ford Triplog processes and stores the selected vehicle information locally.

---

## Is Ford Triplog free?

Yes.

Ford Triplog is an open-source project released under the MIT License.

---

## Which vehicles are supported?

Officially tested:

- Ford Explorer EV

Community tested:

- Ford Capri EV
- Mustang Mach-E
- Puma Gen-E

Other Ford EVs may work as long as they are supported by the FordPass integration.

---

# Installation

## How do I install Ford Triplog?

Install it through HACS.

See:

```
docs/installation.md
```

---

## Do I need HACS?

Yes.

Ford Triplog is distributed through HACS.

---

## Which Home Assistant version is required?

Home Assistant 2026.6 or newer.

---

## Which Python version is required?

Python 3.12 or newer.

---

# Trips

## When does a trip start?

A trip starts when:

- the ignition is on
- the vehicle starts moving

This avoids recording waiting time before driving.

---

## When does a trip end?

A trip ends when:

- the vehicle stops
- the Smart Trip timeout expires (if enabled)

---

## What is Smart Trip?

Smart Trip merges short stops into a single journey.

Typical examples include:

- Coffee breaks
- Shopping
- Picking up passengers

See:

```
docs/smart_trip.md
```

---

## Can I disable Smart Trip?

Yes.

Simply disable it in the integration options.

---

# Charging

## How are charging sessions detected?

Charging sessions are detected automatically using vehicle charging information and State of Charge (SOC).

No manual action is required.

---

## Can Ford Triplog distinguish AC and DC charging?

Charging sessions are recorded regardless of charging type.

At present, AC and DC charging are not stored as separate session types.

---

## Are charging sessions linked to trips?

Yes.

Whenever possible, Ford Triplog associates a charging session with the previous trip while keeping both records separate.

---

# Charging Locations

## How are charging locations recognized?

Ford Triplog uses the following priority:

1. FordPass
2. User Charging Locations
3. OpenStreetMap Charging Database
4. Reverse Geocoding

---

## Can I create my own charging locations?

Yes.

Home, Work and any public charger can be added manually.

User-defined locations always have priority over the OpenStreetMap database.

---

## Can I rename a charging location?

Yes.

User charging locations can be edited at any time.

---

## Does changing a charging location affect old charging sessions?

No.

Only future charging sessions use the updated location.

---

# Charging Database

## Is the OpenStreetMap database required?

No.

Ford Triplog works without it.

However, public charging location recognition is significantly improved when a charging database is installed.

---

## Does the charging database require an internet connection?

Only for downloading or updating.

Normal operation is completely offline.

---

## Can I install multiple countries?

Currently one charging database is active at a time.

Automatic country switching is planned for a future release.

---

# Sensors

## Which sensors are created?

Examples include:

- Last Trip
- Last Charging Session
- Lifetime Statistics
- Energy Consumption
- Charging Statistics

See:

```
docs/sensors.md
```

---

## Can I use the sensors in automations?

Yes.

All entities are standard Home Assistant entities.

---


# Export and Storage

## Can I export my history?

Yes.

Ford Triplog 2.2 can export Trips, Journeys and charging sessions as CSV files. Exports can optionally be filtered by date and downloaded directly through Home Assistant.

---

## Does Ford Triplog use SQLite?

Yes.

Ford Triplog 2.2 supports both JSON and SQLite during the storage transition. JSON remains the default read backend after an upgrade, while SQLite can be selected explicitly in the integration settings.

Compatible data is written to both formats during this transition phase.

---

## Can I delete an invalid charging session?

Yes.

Clearly invalid or suspicious charging sessions can be selected in the Ford Triplog options and deleted after confirmation. Dependent Journey and statistics data is rebuilt as required.

---

## Can pauses have receipts?

Yes.

Journey pauses can contain metadata such as category, note and costs, and can have multiple receipts attached. Pause receipts do not require OCR.

---

# Updates

## Will updating delete my history?

No.

Trips, charging sessions and statistics are migrated automatically.

---

## Do I need to download the charging database again?

Normally no.

Only when you want to update it or switch to another country.

---

# Privacy

## Is my trip history uploaded?

No.

Everything is stored locally.

---

## Does Ford Triplog use its own cloud?

No.

There is no Ford Triplog cloud service.

---

## Who owns my data?

You do.

All recorded data remains inside your Home Assistant installation.

---

# Backup

## Is my history included in Home Assistant backups?

Yes.

The complete Ford Triplog storage directory is included in normal Home Assistant backups.

---

## Can I restore my history?

Yes.

Restoring a Home Assistant backup restores the Ford Triplog history as well.

---

# Troubleshooting

## No trips are recorded.

Verify:

- Vehicle Tracker
- Ignition
- Odometer
- State of Charge

See:

```
docs/troubleshooting.md
```

---

## Charging locations are incorrect.

Try the following:

- Download the correct charging database.
- Reduce the matching radius.
- Create a user charging location.

---

## The integration does not start.

Verify:

- Home Assistant version
- FordPass integration
- Home Assistant logs

Restart Home Assistant after updating.

---

# Support

## Where can I report a bug?

GitHub Issues:

```
https://github.com/weberdomi-ctrl/ford-triplog/issues
```

Please include:

- Home Assistant version
- Ford Triplog version
- Diagnostics
- Relevant log entries

---

## Can I contribute?

Yes.

Bug reports, feature requests and pull requests are always welcome.

See:

```
CONTRIBUTING.md
```

---

## Where can I support the project?

If Ford Triplog is useful to you, consider supporting future development through the Ko-fi link provided in the README.

Every contribution helps improve the project.