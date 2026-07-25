# Troubleshooting

This document describes the most common issues encountered when using Ford Triplog and provides recommended solutions.

If a problem persists after following these steps, please open a GitHub issue and include the Home Assistant diagnostics file.

---

# General Checklist

Before troubleshooting a specific problem, verify the following:

- Home Assistant is fully updated.
- Ford Triplog is updated to the latest version.
- The FordPass integration is working correctly.
- Home Assistant has been restarted after installing or updating Ford Triplog.

---

# No Trips Are Recorded

## Symptoms

- No new trips appear.
- Trip sensors never update.
- Statistics remain unchanged.

## Verify

Check that the following entities are configured correctly:

- Vehicle Tracker
- Ignition
- Odometer
- State of Charge

All four entities must provide valid values.

---

## Check Vehicle Tracker

The tracker should update while driving.

Example:

```
device_tracker.ford_explorer
```

Verify that:

- the position changes
- the entity is available
- latitude and longitude are valid

---

## Check Ignition

The ignition sensor must change state when the vehicle starts or stops.

If the ignition never changes, trip detection cannot begin.

---

## Check Odometer

The odometer should increase while driving.

If the value remains constant, distance calculations cannot be performed.

---

## Check SOC

The State of Charge sensor should report valid percentages.

Example:

```
82 %
```

---

# Charging Sessions Are Not Detected

## Verify

Check that:

- SOC changes during charging
- FordPass reports charging correctly
- the charging session completes normally

Charging sessions are finalized when charging stops.

---

## Charging Ends Too Early

Occasionally, FordPass may temporarily stop reporting charging.

Ford Triplog includes recovery mechanisms to reduce false charging completions.

If the problem occurs repeatedly, verify that the FordPass integration remains connected.

---

# Charging Location Not Recognized

Ford Triplog searches charging locations in the following order:

```
FordPass

↓

User Charging Locations

↓

OpenStreetMap Database

↓

Reverse Geocoding
```

If only an address appears:

- verify that the charging database is installed
- verify the correct country is selected
- create a user charging location

---

# Wrong Charging Location

If the detected location is incorrect:

- verify the stored coordinates
- reduce the matching radius
- create a dedicated user charging location

User charging locations always override the OpenStreetMap database.

---

# Charging Database Not Available

If no charging database can be selected:

Verify:

- internet connection
- latest Ford Triplog version
- supported country

The database is downloaded directly from the integration.

---

# Database Download Failed

Possible causes:

- internet connection unavailable
- temporary download server issue
- interrupted download

Simply retry the download.

---

# Statistics Do Not Update

Statistics are updated automatically whenever:

- a trip finishes
- a charging session finishes

Incomplete trips do not update lifetime statistics until they are finalized.

---

# Smart Trip Does Not Merge Trips

Verify:

- Smart Trip is enabled
- timeout is long enough

Example:

```
180 seconds
```

If a stop lasts longer than the configured timeout, a new trip is created.

---

# Duplicate Charging Locations

If multiple charging locations exist in the same area:

- reduce the matching radius
- remove obsolete charging locations
- keep only the preferred location

Ford Triplog always attempts to select the best matching location.

---

# Integration Does Not Start

Verify:

- Home Assistant version
- Python version
- FordPass integration
- Home Assistant log

Restart Home Assistant after installing or updating the integration.

---

# Configuration Flow Cannot Be Completed

Verify that:

- all required entities are available
- no entity reports an unavailable state
- entity permissions are correct

Then restart the configuration wizard.

---

# Home Assistant Restart During Trip

If Home Assistant restarts while driving:

- the integration restores its runtime state
- trip recording continues whenever possible

Very short interruptions normally do not affect the recorded trip.

---

# Home Assistant Restart During Charging

If Home Assistant restarts while charging:

Ford Triplog attempts to restore the active charging session automatically.

The final charging history depends on the vehicle information available after startup.

---

# Diagnostics

Diagnostics can be downloaded from:

```
Settings

↓

Devices & Services

↓

Ford Triplog

↓

Download Diagnostics
```

When reporting a bug, include:

- Home Assistant version
- Ford Triplog version
- FordPass version
- Diagnostics file
- Relevant log entries

---

# Debug Logging

If requested during troubleshooting, enable debug logging for Ford Triplog.

This provides additional information about:

- trip detection
- charging detection
- charging location resolution
- storage
- recovery

Disable debug logging again after troubleshooting to reduce log size.

---

# Frequently Asked Questions

## Do I lose my trips after an update?

No.

Trips, charging sessions and statistics are migrated automatically.

---

## Can I safely reinstall the integration?

Yes.

As long as the storage directory is preserved, your recorded history remains available.

---

## Can I edit trips manually?

Not currently.

Trip records are intended to represent the recorded vehicle data.

---

## Where can I report a bug?

GitHub Issues:

```
https://github.com/weberdomi-ctrl/ford-triplog/issues
```

Please include diagnostics whenever possible.

---

# Still Need Help?

If the problem cannot be resolved:

1. Update Home Assistant.
2. Update Ford Triplog.
3. Restart Home Assistant.
4. Download diagnostics.
5. Open a GitHub issue with a detailed description of the problem.

This information usually allows issues to be identified quickly.