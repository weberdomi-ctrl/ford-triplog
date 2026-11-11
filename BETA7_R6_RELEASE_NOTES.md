# Ford Triplog 2.7.0 – Beta 7 / Release 6 (Build 27034)

**Pre-release for testing — not a stable release.**

Version: `2.7.0-beta.7-r6`  
Build: `27034`  
Source branch: `2.7.0_Beta.7` (after merging PR #98)

This is the first published Beta 7 candidate. It includes the cumulative parking GPS reliability work from R1–R5 and the fresh-install/shared-entity fix in R6. It is intended for testing before a stable 2.7.0 release.

## Fixed in Release 6 — Issue #96

- **Missing Home Assistant entities on fresh installs:** the first configured vehicle can be assigned an internal SQLite `vehicle_id` other than 1 (for example, ID 2 after the initial placeholder is removed). Previously, the sensor, binary sensor and select platforms refused to create their shared entities unless `vehicle_id == 1`. Trips and charges could still be stored, but the dashboard entities were missing.
- **Shared entity ownership no longer depends on SQLite vehicle ID.** Exactly one loaded Ford Triplog ConfigEntry owns the shared entity set. The normal vehicle selector and runtime proxies still switch between the loaded vehicles.
- Shared entity ownership remains stable during additional vehicle setups and is released on unload. When the owner ConfigEntry is **permanently removed**, a surviving ConfigEntry is reloaded to restore the shared UI.
- **TCO units:** active insurance, road-tax and financing sensors already use the stored contract currency (`CHF/month`, `EUR/month`, etc.). R6 also clears obsolete units when no active contract exists after a vehicle change. Mixed currencies are not silently converted.

**No database migration or vehicle-ID renumbering. Existing trips, charges and vehicle records are not rewritten.**

## Included from Beta 7 Releases 1–5 — Parking GPS

- **R1:** guard against stale vehicle parking coordinates using tightly bounded, accurate, stationary **pre-ignition-OFF** phone route points. Do not trust fresh Home Assistant `last_updated` timestamps as proof of fresh OEM GPS.
- **R2:** use the FordPass VIN-specific GPS sensor's genuine `gpsModuleTimestamp` (fallback: `updateTime`) when its coordinates agree with the device tracker. Explicitly mark stale positions as untrusted.
- **R3:** accept delayed, genuinely sampled Ford parking positions only when they match the accurate recorded route endpoint and a stable odometer.
- **R4:** retain an explicitly untrusted ignition-OFF parking candidate if FordPass GPS JSON and its device tracker update out of sequence; select route evidence captured **before**, not after, ignition OFF.
- **R5:** allow the VIN-specific Ford GPS JSON to be examined as *independent parking evidence* when the Ford device tracker is delayed. A pending parking anchor becomes trusted only after matching the OEM time, the recorded high-quality pre-OFF route point, and the stable odometer. Normal trip GPS pairing remains unchanged.

These changes are prospective: they improve the parking anchor for the *next* trip. They do not automatically rewrite old trip history or fill gaps in an unavailable GPS trace.

## Features carried forward from Beta 6 and Beta 5

- Vehicle-specific and zone-based charging tariffs; optional Home Assistant dynamic electricity price sensor, including support for `ct/kWh` and `Rp/kWh` with conversion to the base unit.
- Optional external charging energy meter, interval-aware charge costs and charging cost diagnostics.
- Vehicle costs and TCO, PDF/image receipts, documents and vehicle information.
- Smart Trip recovery, GPS route recording, OSRM matching with an optional minimum trip distance, and route/CSV exports.

## Installation / upgrade

1. **Back up** the Home Assistant configuration and `/config/.storage/ford_triplog/ford_triplog.db` (and associated vehicle documents/receipts) before changing versions.
2. After this tag has been published as a GitHub pre-release, use HACS to select **`2.7.0-beta.7-r6`** (enable beta/pre-release versions if needed); alternatively use the established manual integration-installation method.
3. Restart Home Assistant and check that the installed version is **`2.7.0-beta.7-r6`**, build **27034**.
4. Confirm the Ford Triplog sensors, binary sensors and vehicle selector exist. Verify that recent trip and charge history is still present.
5. With multiple vehicles, switch the shared vehicle selector and verify each vehicle's data. Optionally verify a complete drive/parking/next-start cycle for the GPS fixes.

**Do not delete, recreate or manually renumber SQLite vehicle records to repair missing entities.** Updating the integration is the intended fix.

## Testing and limitations

- All GitHub Actions checks for PR #98 passed, including new pure-Python shared-entity regression cases and the existing parking GPS tests.
- The affected reporter's Home Assistant installation has **not yet been retested**. The fix remains a beta candidate until validated on a fresh single-vehicle installation and an existing ID-2 installation.
- The first-owner handover after removing a ConfigEntry has automated helper tests, but still needs a real multi-vehicle Home Assistant test.
- FordPass/other vehicle integrations may deliver GPS with delays; GPS gaps and underground parking cannot be reconstructed reliably.
- Live dynamic-price charging sessions with interrupted charging and real metering still require further field validation.
- EUR and CHF are never summed or converted implicitly; cross-currency conversion is outside this release.

## Feedback

Please include the Ford Triplog version/build, Home Assistant version, number of configured Ford Triplog ConfigEntries, affected `vehicle_id`, whether `sensor`, `binary_sensor` and `select` entities appear, and relevant sanitized logs. Do **not** post VINs, private coordinates/addresses, tokens or personal data.

- [Issue #96 — fresh install missing shared entities](https://github.com/weberdomi-ctrl/ford-triplog/issues/96)
- [PR #98 — shared entities and TCO units](https://github.com/weberdomi-ctrl/ford-triplog/pull/98)
- [Issue #91 — parking GPS](https://github.com/weberdomi-ctrl/ford-triplog/issues/91)
