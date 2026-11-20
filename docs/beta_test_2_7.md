# Ford Triplog 2.7.0-beta.7-r6 — Pre-release test guide

**Beta test build 27034. Not a stable version.**  
See [complete Beta 7 R6 release notes](../BETA7_R6_RELEASE_NOTES.md).

## Before upgrading

1. Back up the Home Assistant configuration, `/config/.storage/ford_triplog/ford_triplog.db`, and stored receipts/documents.
2. Record your current Ford Triplog version and the number of vehicle ConfigEntries, plus their internal `vehicle_id` values.
3. Install the published `2.7.0-beta.7-r6` pre-release with HACS (or using your established manual installation method), then restart Home Assistant.
4. Confirm the integration reports **2.7.0-beta.7-r6 / 27034** and check the Home Assistant log for startup, SQLite, platform or entity registry errors.

## Priority: Issue #96 — shared entities

- On a clean setup with **one real vehicle**, verify that the shared sensors, binary sensors and vehicle selector are created even if the assigned SQLite `vehicle_id` is **2** rather than 1.
- On an existing installation with only a vehicle at ID 2, verify that installing R6 restores the shared entities **without deleting the database or the existing vehicle ConfigEntry**.
- Confirm recorded trips/charges, route history, stored costs and exports remain available.
- On a legacy installation with vehicle ID 1, confirm the same shared entity IDs still exist, without duplicates.
- With multiple ConfigEntries, switch the shared vehicle selector and verify sensors, statistics and history follow the selected vehicle.
- Test Home Assistant restart and an ordinary ConfigEntry options reload. Verify shared entities remain available, without duplicate unique IDs.
- If possible in a **test installation**, permanently remove the shared entity owner ConfigEntry while another vehicle remains. Check that the other entry restores the shared entities. **Back up first; deleting a ConfigEntry may intentionally delete that vehicle's data. Never use a productive vehicle for this destructive test.**

## Priority: Beta 7 parking GPS fixes (R1–R5)

- Make an outbound trip, switch ignition OFF, and let Smart Trip finalize.
- When supported, compare Ford's OEM GPS timestamp with the associated device tracker. A refreshed Home Assistant timestamp alone must not certify stale GPS.
- Verify the stored park location agrees with the accurate pre-OFF route endpoint and, if available, a genuine near-OFF Ford GPS fix.
- Start the next trip and check that a confirmed ignition-OFF park position is reused as a protected trip start. Do not use home/work zone centers as substitute parking coordinates.
- Repeat after a delayed FordPass update. Ensure no false multi-kilometre jump or post-OFF phone movement is accepted.
- Inspect the last route's `osrm_match_status`, `osrm_match_reason` and `route_incomplete` attributes. Missing GPS segments must remain explicit.

## TCO and charging regression checks

- For EUR insurance, road-tax and financing contracts, confirm their sensors show `EUR/month`; for CHF contracts, `CHF/month`.
- Select a vehicle without an active contract and confirm the previous vehicle's amount and unit are cleared.
- Verify stored currencies and amounts remain unchanged; mixed currencies are never converted or presented as a single total.
- Verify existing vehicle-specific, seasonal and zone-based charging tariffs.
- If using a dynamic price sensor, check its units (for example `EUR/kWh`, `ct/kWh`, `CHF/kWh` or `Rp/kWh`) and run a controlled charging session across an hourly/15-minute price interval.
- Compare the recorded energy and price changes with the calculated charging cost, then restart Home Assistant to confirm costs are retained.
- Verify route/CSV export, recorded Journeys and the minimum-distance OSRM option.

## Reporting a problem

Please include:
- Home Assistant version and Ford Triplog version/build
- Number of vehicle ConfigEntries and affected internal `vehicle_id` values
- Whether sensors, binary sensors and selectors are missing or duplicated
- Whether this is a fresh install, an upgrade or a vehicle removal
- Relevant log lines, sensor units, GPS sample/observation timestamps or charging price data, as appropriate

**Remove VINs, private street addresses, exact coordinates, personal data and secrets before publishing diagnostics.**

Issue #96: https://github.com/weberdomi-ctrl/ford-triplog/issues/96  
Parking GPS issue #91: https://github.com/weberdomi-ctrl/ford-triplog/issues/91

**Outside this beta:** automatic cross-currency conversion and the optional EV-versus-combustion-vehicle cost comparison.
