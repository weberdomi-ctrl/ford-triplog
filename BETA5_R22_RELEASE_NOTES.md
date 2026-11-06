# Ford Triplog 2.7.0 – Beta 5 / Release 22 (Build 27022)

**Pre-release for testing — not a stable release.**

This update brings the latest Beta 5 development changes from Releases 12–22 to a new, clearly versioned pre-release.

## Highlights

- **Dynamic electricity tariffs:** configure a Home Assistant price sensor and an optional energy meter from evcc, a wallbox or Home Assistant. Choose automatic, session-based or cumulative meter mode. Costs are calculated across changing price intervals, including measured charging losses. Real-world verification with Tibber Grid Rewards and interrupted charges is still pending.
- **Short trips and Smart Trip:** improved handling when a new ignition-ON event arrives during the previous Smart Trip's timeout/finalization.
- **Parking GPS and start positions:** store the validated ignition-OFF parking position and use it for the next start. Reject stale vehicle GPS coordinates, account for delayed FordPass REST updates and recheck parking after the normal Smart Trip timeout. Home/Work zone centers no longer replace valid actual parking coordinates.
- **Route Tracker / OSRM:** better filtering of low-accuracy and drifting phone GPS; avoid fabricated links across GPS outages, keep quality-filtered raw GPS segments and support verified partial OSRM matches. An incomplete OSRM section is not treated as a complete driven route.
- **New in R22 – OSRM minimum trip distance:** configure a threshold under **Options → OSRM route smoothing**. Default **3 km**, adjustable from 0–100 km. Trips shorter than the threshold skip automatic OSRM matching and retain their raw GPS data; **0 km disables** the threshold. The decision uses vehicle odometer trip distance.

## Installation and notes

Install the **2.7.0-beta.5-r22** pre-release through HACS with beta/pre-release versions enabled, then restart Home Assistant. Back up your Home Assistant configuration and the Ford Triplog SQLite database before upgrading.

- Version: `2.7.0-beta.5-r22`
- Build: `27022`
- Source: branch `2.7.0_Beta.5` at commit `d958374d55df39dd5d54d2aa0970a45075e446eb`
- Earlier Beta 5 pre-release `2.7.0-beta.5` is preserved.
- Charging algorithms still require user feedback from real evcc/Tibber Grid Rewards sessions. Missing GPS coverage in underground garages cannot be reconstructed reliably.

This is a test release. Please report problems in GitHub issues, including the relevant debug logs.
