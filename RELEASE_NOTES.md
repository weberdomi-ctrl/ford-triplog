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
