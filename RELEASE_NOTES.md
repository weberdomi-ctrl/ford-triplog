# Ford Triplog 2.0.2

Ford Triplog 2.0.2 expands statistics, improves Route Tracker reliability and road matching, and completes a number of dashboard and translation refinements.

## 📊 Top Statistics

New native Top Statistics sensors provide quick access to notable driving and charging records.

New statistics include:

- **Top Trip** with distance, duration, energy use and consumption
- **Top Journey** with Journey-level driving and energy information
- **Top Day** aggregating all Journeys and trips of the same local calendar day
- **Top Charging** with leading charging providers and locations
- Largest charging session
- Session count and remaining unknown-provider statistics
- Charging costs and average price per kWh

Top Charging now refreshes automatically after stored charging data or charging costs are changed. A Home Assistant or integration reload is no longer required for updated cost statistics.

## 🛰️ Route Tracker Improvements

Route tracking introduced in Ford Triplog 2.0 has been refined for more reliable everyday recording.

Improvements include:

- Improved Route Tracker persistence and recovery
- Better handling of trip start and end route points
- Improved ABRP-based route recording
- More reliable route completion and Trip ID association
- Raw GPS route data remains preserved independently from matched route data

## 🗺️ OSRM Route Matching

Optional local OSRM map matching is now supported for recorded routes.

Features include:

- Configurable local OSRM server
- Configurable matching radius
- Automatic road matching after trip completion
- Raw and matched route data stored separately
- Matching diagnostics
- Manual rebuild of the latest route
- DACH example configuration for Germany, Austria and Switzerland

OSRM remains completely optional. Without OSRM, Ford Triplog continues to record and display the raw GPS route.

## 📅 Top Day

The new **Top Day** sensor aggregates driving activity by the Home Assistant local calendar date.

It includes:

- Total daily distance
- Total and driving duration
- Journey and trip counts
- Charging information
- Energy used and charged
- Average consumption
- Charging costs
- Start and end locations
- Associated Journey, Trip, Charge and Route IDs

This makes it possible to identify the longest recorded driving day even when it consists of multiple Journeys.

## ⚡ Charging Statistics Improvements

Charging statistics now make better use of resolved charging locations and providers.

Improvements include:

- Home charging grouped as Home
- Provider and location aggregation
- User-defined charging locations included in statistics
- Improved matching of charging locations
- Unknown-provider sessions exposed separately
- Immediate Top Charging recalculation after manual cost or stored charge changes

## 🌍 Translations and Entity Names

Entity naming and translations have been cleaned up and synchronized.

Improvements include:

- German, English and Polish translation updates
- Translatable **Charging History**
- Translatable **Journey History**
- Translatable **Route History**
- Translatable shared **History Date** selector
- Translatable **Trip Active**
- Translation support for the new Top Statistics sensors
- Removal of the redundant unavailable FordPass last-charge energy sensor

## ⚙️ Improvements and Fixes

- Fixed Journey History aggregation when multiple separate Journeys exist on the same calendar date
  - Distance, durations, energy, SoC and charging costs are now aggregated across all Journeys
  - Journey timelines are merged chronologically instead of showing only the last Journey
  - Average consumption and average charging price are recalculated from the aggregated totals
  - Start SoC is taken from the first available Journey value and end SoC from the last available value
- Improved Top Charging aggregation
- Charging provider and location corrections are reflected in statistics
- Manual charging cost changes can update Top Charging without reloading the integration
- Reduced redundant sensor exposure
- Existing Trip, Journey, Charge and Route storage remains compatible

## ⬆️ Upgrade Notes

Ford Triplog 2.0.2 is compatible with existing Ford Triplog 2.0.x stored data.

No external database or storage migration is required.

OSRM is optional and only needs to be configured when local road matching is desired.

---

# Ford Triplog 2.0.1

Ford Triplog 2.0.1 extends the Route Tracker introduced in 2.0.0 with a complete date-based History view for routes, Journeys, charging sessions and charging receipts.

## 🕓 History

A shared History date selection is now available for reviewing stored Ford Triplog data by day.

New capabilities include:

- Shared History date selection
- Daily Journey history
- Daily route history
- Daily charging history
- Charging-only days are available in History
- History sensors update together when the selected date changes

## 🗺️ Route History

Stored Route Tracker data can now be viewed for previously recorded days.

Features include:

- Native **Route History** sensor
- Historical route loading from persistent route storage
- Routes grouped by local Home Assistant calendar date
- GeoJSON output for historical map visualization
- Multiple routes from the selected day can be displayed together
- Active and paused recovery routes are excluded from historical views
- Existing Ford Triplog 2.0.0 route files remain compatible

## 🛣️ Journey History

The selected day can now be displayed as a complete Journey overview.

History data includes:

- Journey summary
- Distance and duration
- Driving, pause and charging time
- Energy consumption
- Charged energy
- Journey energy balance
- Charging costs
- Battery and SOC information
- Complete Journey timeline with trips, pauses and charging sessions

## ⚡ Charging History

Charging sessions are now available for the selected History date.

History data includes:

- Charging location
- Charging times and duration
- Start and end SOC
- Charged and billed energy
- Charging losses
- Charging costs and price information
- Charging source and provider information
- Associated charging receipts

## 🧾 Receipt History

Charging receipts can now be accessed directly from the History dashboard.

- Receipts are linked to their charging session
- Multiple receipts per charging session are supported
- Receipt filename and media information are exposed to the dashboard
- Authenticated signed receipt links are generated for dashboard access
- Relative signed URLs allow the current Home Assistant host to be used
- Receipt links can be opened directly from the dashboard

## 📊 Dashboard Examples

New ready-to-use History dashboard examples are included for:

- History date selection
- Journey history
- Historical route map
- Charging history
- Charging receipts

The historical route map uses **Google Map Card** and **Config Template Card** from HACS. The map example can be hidden automatically on days without route data.

## ⚙️ Improvements

- Reduced Journey diagnostic log noise
- Improved synchronization of the History views
- History uses the Home Assistant local timezone for date assignment
- Existing trip, Journey, charging and route storage remains compatible

## ⬆️ Upgrade Notes

Ford Triplog 2.0.1 is compatible with existing Ford Triplog 2.0.0 route data.

No external database or storage migration is required.

The new History dashboard examples are optional. Users who want to use the historical route map need the **Google Map Card** and **Config Template Card** custom cards installed through HACS.

---

# Ford Triplog 2.0.0

Ford Triplog 2.0 introduced GPS route recording and optional local road matching.

See the previous release notes for the complete 2.0.0 feature list.
