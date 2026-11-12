# Ford Triplog 2.7.0-beta.7-r8 — GPS parking anchor correction

**Build:** 27036  
**Status:** Development candidate; requires CI and an on-vehicle validation before pre-release.

## Field failure reproduced

2026-11-12, Ford Explorer EV, Wilen b. Wollerau to Cham:

- 12:57:31 CET: last logged phone route point, approximately 34 seconds before OFF; accurate and near the eventual parking location.
- 12:58:04 CET: Ford GPS-module timestamp at 47.188310, 8.473664 (Cham).
- 12:58:05 CET: Ford ignition OFF, but the vehicle tracker and GPS JSON did not yet match. Triplog saved an untrusted pending parking position at 47.196256, 8.753345 (Wilen).
- 13:02 CET: the Smart Trip GPS check failed to promote the pending parking candidate. The completed trip was correctly saved at Cham, but the next-trip parking anchor remained unconfirmed.

The existing OEM confirmation helper required the independent route point to have been recorded no more than 20 seconds before ignition OFF. That hard limit can reject otherwise consistent evidence from the Ford GPS module and a recorded phone route.

## R8 fix

- Preserve the normal 20-second route-only acceptance window.
- Only in the **post-OFF Ford OEM corroboration** path, consider a recorded phone GPS point up to 60 seconds before OFF.
- For phone fixes older than 20 seconds, additionally require:
  - a **genuine Ford `gpsModuleTimestamp`** sampled within 15 seconds of ignition OFF;
  - phone GPS accuracy 1–25 m and speed 0–2 m/s;
  - phone position within 100 m of the independent Ford GPS-module location;
  - an unchanged vehicle odometer within 1 km;
  - the existing 10-minute post-OFF confirmation window.
- Never use phone positions recorded after ignition OFF or a Ford `updateTime`-only sample to apply the extended window.
- Report rejected OEM parking evidence in DEBUG logs.

## Regression tests

The new R8 test suite replays the November 12 timestamps and validates the successful recovery to Cham; it also checks stale, moving, inaccurate, distant, post-OFF, publication-only, and mismatched-odometer scenarios. Existing parking GPS test suites remain in CI.

## Upgrade and test status

- Based on Beta 7 R7, retaining its charging unplug-end correction.
- No storage schema change and no automatic rewrite of previously archived trips or parking positions.
- **Do not publish a stable release from this candidate.** Review CI, install manually, and validate another real ignition-OFF stop where the Ford GPS JSON and tracker update asynchronously.
- After the vehicle has been parked, check for `Post-OFF vehicle parking GPS saved` or `Stabilized parking anchor` with a correct confirmed source, and verify the next trip begins at the parked position.
