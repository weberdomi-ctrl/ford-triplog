# Charging Locations

Ford Triplog can automatically identify where your vehicle is being charged.

The integration combines multiple data sources to recognize charging locations as accurately as possible while allowing complete user control through custom charging locations.

---

# Overview

Charging locations are resolved using a priority-based system.

The first successful match is used for the charging session.

Priority:

```
1. FordPass Charging Information

↓

2. User Charging Locations

↓

3. OpenStreetMap Charging Database

↓

4. Reverse Geocoding
```

This approach combines manufacturer-provided information, user-defined locations and offline map data to achieve reliable charging location recognition.

---

# FordPass Charging Information

Whenever the FordPass API provides charging location information, it is used as the preferred source.

Typical information may include:

- Charging station name
- Address
- Coordinates

FordPass data always has the highest priority.

---

# User Charging Locations

User-defined charging locations override every other local source.

They are intended for locations that are frequently visited or require custom naming.

Typical examples include:

- Home
- Workplace
- Company parking
- Favourite public charger
- Hotel
- Dealer

---

# Creating a Charging Location

Open:

```
Settings

↓

Devices & Services

↓

Ford Triplog

↓

Configure

↓

Manage Charging Locations
```

Select:

```
Add Charging Location
```

Enter the desired information.

---

# Available Information

Depending on the location, the following information can be stored.

## General

- Name
- Type
- Notes

---

## Address

- Street
- House number
- Postal code
- City
- Country

---

## Charging Information

- Brand
- Operator
- Network
- Connectors
- Maximum charging power
- Number of charging points

---

## Position

Every charging location stores:

- Latitude
- Longitude

Additionally, a configurable matching radius determines how close the vehicle must be for the location to be recognized.

---

# Charging Location Types

Supported types are:

| Type | Typical Usage |
|------|---------------|
| Public | Public charging stations |
| Home | Private home charging |
| Work | Workplace charging |
| Private | Other private locations |
| Hotel | Hotels |
| Dealer | Ford dealers or workshops |
| Other | Custom locations |

---

# Home and Work

Home and Work receive special treatment.

When creating a new location, Ford Triplog automatically suggests the names:

```
Zuhause
```

and

```
Arbeit
```

These names can be changed at any time.

---

# Matching Radius

Each charging location has its own matching radius.

The radius determines how close the vehicle must be to identify the location.

Typical values:

| Radius | Usage |
|---------|------|
| 15 m | Private charger |
| 25 m | Recommended |
| 50 m | Large parking area |
| 100 m | Very large charging sites |

Smaller values provide more precise matching.

---

# OpenStreetMap Charging Database

If no user-defined location matches, Ford Triplog searches the local OpenStreetMap charging database.

The database contains public charging stations and may include:

- Station name
- Operator
- Charging network
- Maximum charging power
- Connector types
- Number of charging points

The database operates entirely offline after download.

---

# Reverse Geocoding

If neither FordPass, user locations nor the OpenStreetMap database provide a match, Ford Triplog falls back to reverse geocoding.

Typical information includes:

- Street
- City
- Country

This ensures that every charging session receives a meaningful location, even when no charging station information is available.

---

# Managing Charging Locations

Existing charging locations can be:

- viewed
- edited
- deleted

Changes immediately affect future charging sessions.

Previously recorded charging sessions remain unchanged.

---

# Unknown Charging Locations

If Ford Triplog encounters a new charging location that cannot be matched automatically, it can be added as a permanent user-defined location through the configuration dialog.

Future charging sessions at that location will then be recognized automatically.

---

# Recognition Example

```
Vehicle starts charging

↓

FordPass location available?

↓

Yes
→ Use FordPass

↓

No

↓

User location match?

↓

Yes
→ Use user location

↓

No

↓

OSM match?

↓

Yes
→ Use OpenStreetMap

↓

No

↓

Reverse Geocoding
```

---

# Best Practices

For the most accurate recognition:

- Create Home and Work charging locations.
- Use a realistic matching radius.
- Download the OpenStreetMap charging database for your country.
- Add frequently used public charging stations if you prefer custom names.

---

# Frequently Asked Questions

## Can I rename charging locations?

Yes.

Every user-defined charging location can be renamed at any time.

---

## Does editing a charging location affect previous charging sessions?

No.

Changes only affect future charging sessions.

---

## Can multiple charging locations overlap?

Yes.

If multiple user-defined locations overlap, the closest matching location is used.

---

## Is the OpenStreetMap database mandatory?

No.

Ford Triplog works without it.

However, installing the database significantly improves charging location recognition for public charging stations.

---

## Which source has the highest priority?

Priority is always:

1. FordPass
2. User Charging Locations
3. OpenStreetMap
4. Reverse Geocoding