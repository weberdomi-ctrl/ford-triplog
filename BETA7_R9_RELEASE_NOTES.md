# Ford Triplog 2.7.0 – Beta 7 / Release 9 (Build 27037)

**Pre-release for testing — not a stable release.**

Version: `2.7.0-beta.7-r9`  
Build: `27037`  
Source branch: `2.7.0_Beta.7` (includes merged PRs #99, #100 and #103)  
Previous published pre-release: `2.7.0-beta.7-r6` (Build 27034)

Beta 7 Release 9 includes fixes to charging timestamps and duration reporting, as well as a stricter recovery path for delayed ignition-OFF parking GPS. All previous Beta 7 R1–R6 changes remain included.

## Fixed since Beta 7 Release 6

### R7 — Keep unplug time distinct from charging completion (PR #99)

- For vehicles with a physical plug-status sensor, the end of the **plug session** remains the actual `DISCONNECTED` event, even when energy transfer reached `COMPLETED` much earlier.
- Preserve `completion_time` independently as the end of energy transfer.
- This allows Ford Last Charge matching to compare against the actual unplug event rather than prematurely ending the archived plug session at `COMPLETED`.
- Vehicles without a plug-status sensor retain the existing charging-state lifecycle.
- No database migration or automatic rewrite of previously archived charges.

### R8 — Recover parking GPS when the phone route point arrives early (PR #100)

- When Ford GPS JSON and the device tracker update out of sequence at ignition OFF, allow a genuine Ford `gpsModuleTimestamp` to confirm the parking position using accurate independent route evidence recorded **21–60 seconds before** ignition OFF.
- The extended window only applies to the post-OFF OEM confirmation path and requires a Ford module sample close to ignition OFF, accurate near-stationary phone GPS within 100 m, a stable odometer, and the existing 10-minute validation window.
- The standard route-only 20-second window remains unchanged.
- Reject post-OFF phone movement, stale/unverified GPS, and publication-only timestamps as independent confirmation.
- Existing trip history and parking anchors are not retroactively rewritten.

### R9 — Report actual charging time rather than plugged-in time (PR #103)

- The last-charge end-time sensor and charge-history display now prefer the verified `completion_time` when available.
- The charging-duration sensor, charging averages and Journey charging summaries exclude stored charging pauses and idle time after charging completes.
- Keep the physical plug-out timestamp in the archived record for Ford Last Charge matching and chronology.
- Last-charge attributes and charging-history entries additionally expose `plug_out_time` and `plug_duration_seconds`.
- Previously archived charges with valid completion/pause information are evaluated correctly when read; no database migration is required.

## Real-world charging verification

An overnight home AC session was recorded with charging starting on 13 November 2026, completing at approximately 21:31, and remaining plugged in until the morning of 14 November.

- The earlier version displayed **16 h 14 min** as charging time because the unplug timestamp was used.
- With R9 installed manually in Home Assistant, the same archived session displayed **3 h 50 min 49 s** of charging time.
- The separate physical plug duration remained **16 h 14 min**.
- The archived energy was **38.5 kWh**. Ford Last Charge did not provide a matching record within the five-minute stabilization window, so the session used the charging-status energy source.

This confirms the charging-time display fix for the observed overnight case; it does not imply every FordPass Last Charge delay or paused/resumed charging scenario has been verified in the field.

## Installation / upgrade

1. Back up your Home Assistant configuration and Ford Triplog SQLite database, including any linked documents and receipts.
2. In HACS, enable pre-release versions if needed, then select `2.7.0-beta.7-r9` **after the GitHub pre-release has been published**. Alternatively, use the existing manual installation method.
3. Restart Home Assistant. Verify that the integration files report version `2.7.0-beta.7-r9`, build `27037`. A HACS update entity can continue to show an older installed version after files were copied manually.
4. Confirm that trip, charging and vehicle history remain intact.
5. Verify a charge that completes while still plugged in: the last-charge end time and duration should reflect energy-transfer completion, while `plug_out_time` remains separate.
6. On the next real drive, verify the ignition-OFF parking position and subsequent trip start.

## Testing and known limitations

- CI: Python and existing charging-unplug regression tests, the new overnight charging-duration regression, parking GPS tests, HACS validation and Hassfest passed on the R9 development branch.
- Charging-duration display was verified in a real Home Assistant installation using the archived November 13–14 session.
- FordPass and companion-app GPS data can be delayed or absent. The more permissive R8 OEM corroboration path still requires additional real-world edge-case validation.
- Route geometry can still contain a loop or matching artifact near the start when the first phone GPS points are inaccurate. That separate route/OSRM issue is not fixed by R9.
- Live dynamic-price and interrupted/resumed sessions with an independent external energy meter still require field testing.
- Never combine amounts in different currencies without explicit conversion. No currency conversion is introduced here.

## Feedback

When reporting issues, include the Ford Triplog version/build, Home Assistant version, relevant charging timestamps (start, completion, unplug), energy source and anonymized logs. For GPS reports, include the timing and trust source without exposing private locations, VINs or tokens.

Related changes: [PR #99](https://github.com/weberdomi-ctrl/ford-triplog/pull/99) · [PR #100](https://github.com/weberdomi-ctrl/ford-triplog/pull/100) · [PR #103](https://github.com/weberdomi-ctrl/ford-triplog/pull/103)
