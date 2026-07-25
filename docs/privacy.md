# Privacy

Privacy is one of the core design principles of Ford Triplog.

The integration is designed to keep your vehicle history under your control by storing all recorded data locally inside your Home Assistant installation.

Ford Triplog does not operate a cloud service and does not require an external account.

---

# Local-First Design

Ford Triplog follows a local-first approach.

All processing is performed inside Home Assistant, including:

- Trip recording
- Charging session recording
- Statistics
- Charging location recognition
- Charging history
- User charging locations

No external database is required.

---

# What Ford Triplog Stores

The integration stores only the information required to provide its functionality.

Examples include:

- Trip history
- Charging history
- Driving statistics
- Charging statistics
- User-defined charging locations
- Configuration settings

All data is stored locally.

---

# What Ford Triplog Does NOT Upload

Ford Triplog never uploads:

- Trip history
- Charging history
- Driving statistics
- Charging statistics
- Charging locations
- Home address
- Workplace address
- User-defined charging locations

There is no Ford Triplog cloud service.

---

# FordPass Communication

Ford Triplog does not communicate directly with Ford servers.

Instead, it uses the existing Home Assistant FordPass integration.

FordPass communication is limited to retrieving vehicle information already provided by that integration.

Ford Triplog simply processes this information locally.

---

# OpenStreetMap Data

The optional charging database is generated from publicly available OpenStreetMap data.

Downloading a charging database requires an internet connection once.

After the download:

- No further internet access is required.
- All charging location lookups are performed locally.
- No vehicle locations are sent to OpenStreetMap.

---

# Reverse Geocoding

If enabled, reverse geocoding may be used when no charging location can be identified.

Its purpose is to provide a readable address for a charging session.

Reverse geocoding is only used as the lowest-priority fallback after:

1. FordPass
2. User Charging Locations
3. OpenStreetMap Charging Database

Users who prefer to avoid reverse geocoding can instead create their own charging locations for frequently visited places.

---

# Home Assistant Diagnostics

Home Assistant allows diagnostics to be generated for troubleshooting.

Diagnostics are only created when explicitly requested by the user.

They are intended for debugging and support.

Before sharing diagnostics publicly, always review the file for sensitive information.

---

# Home Assistant Backups

Ford Triplog data is included in normal Home Assistant backups.

Your trip history, charging history and statistics remain under your control.

You decide:

- where backups are stored
- how long they are retained
- who can access them

---

# Open Source

Ford Triplog is an open-source project.

The complete source code is publicly available on GitHub.

Anyone can review:

- how data is collected
- how data is processed
- how data is stored

This transparency allows users to verify the privacy behaviour of the integration themselves.

---

# Data Ownership

All recorded information belongs to you.

Your driving history remains available even if:

- FordPass is temporarily unavailable
- Home Assistant restarts
- the integration is updated

Because the data is stored locally, you always retain full ownership.

---

# Best Practices

To maximise privacy, consider the following recommendations:

- Keep Home Assistant updated.
- Protect your Home Assistant installation with authentication.
- Create regular backups.
- Review diagnostics before sharing them.
- Only install charging databases for countries you actually use.

---

# Frequently Asked Questions

## Does Ford Triplog send my trips to a cloud service?

No.

Trip history is stored locally inside Home Assistant.

---

## Does Ford Triplog know my home address?

Only if you create a Home charging location or if reverse geocoding resolves your location.

This information remains stored locally.

---

## Can I delete my history?

Yes.

You can remove the Ford Triplog storage files at any time.

Deleting the storage removes all recorded trips, charging sessions and statistics.

It is recommended to create a backup before doing so.

---

## Is an internet connection required?

Only for:

- FordPass communication
- Downloading OpenStreetMap charging databases
- Optional reverse geocoding

Normal trip recording, charging detection and statistics operate locally.

---

## Is Ford Triplog GDPR friendly?

Ford Triplog is designed around data minimisation and local processing.

Because the integration does not operate a backend service or collect user data, all recorded information remains under the control of the Home Assistant user.