# Ford Triplog 2.7.0 — Stable Release (Build 27039)

Ford Triplog 2.7.0 brings dynamic charging tariffs, route export, and reliability improvements for parking GPS, route matching, vehicle entities and charging-session accounting.

## Highlights

- **Dynamic charging tariffs:** Configure a Home Assistant price entity per vehicle and charging location. Account for price changes during a charging session when suitable price and energy measurements are available. Supported units include EUR/kWh, CHF/kWh, ct/kWh and Rp/kWh.
- **External charging energy meters:** Use a compatible Home Assistant/evcc or wallbox energy sensor for billed electricity, including charging losses and any preconditioning energy drawn from the grid, while keeping vehicle-reported energy separate.
- **Charging lifecycle:** Preserve one plug session across pauses and resumptions. Distinguish charging completion from physical unplug, use active energy-transfer duration in statistics, and reconcile Ford Last Charge data.
- **Parking GPS:** Reliably retain verified ignition-OFF parking positions for the next journey start, including safely validated delayed Ford GPS updates.
- **OSRM routes:** Reject bad map-matching chunks and artificial jumps, and fall back to raw GPS where needed. Previously archived bad geometry is guarded on display without modifying raw GPS or odometer-based trip distance.
- **Other improvements:** Route export, locale-aware date inputs, currency labels, and shared entities on fresh installations even when the first vehicle's SQLite ID is not 1.

## Field validation

- Multiple real-world Home Assistant trips confirmed protected parking starts, successful route storage, and plausible route geometry.
- An overnight AC session with interrupted charging and later unplug was retained as one session and finalized after disconnect.
- An external evcc user reported that charging results from Ford Triplog and evcc matched after installing the ct/kWh support. This is user feedback; complete interval diagnostics have not been independently verified.
- Automated regression coverage includes OSRM geometry, parking GPS, shared entity ownership, and unplug/charging-duration behavior. All 12 release-branch checks passed, including HACS validation, Hassfest and regression workflows.

## Known limitations

- Phone GPS inaccuracies can still produce small route artifacts, particularly around the start or end. Further phone GPS filtering is planned for 2.8 (issue #101).
- An optional EV versus combustion-engine cost comparison remains a future enhancement (issue #75).
- FordPass updates may arrive late; expected GPS timeout/fallback messages are logged as INFO.
- Cross-currency conversion is not supported. External meter quality and availability affect billed-energy accuracy.

## Upgrade

1. Back up Home Assistant configuration and the Ford Triplog SQLite database, including linked files and receipts.
2. Install the stable `2.7.0` release through HACS after its tag and release have been published, or update the integration manually.
3. Restart Home Assistant and verify that both `manifest.json` and `const.py` show `2.7.0` (build `27039`).
4. Confirm existing trips, journeys, charges, vehicle history, and configured price/meter entities are preserved.

No forced SQLite migration, vehicle-ID renumbering, or retroactive rewriting of archived trips is required.

Please report any unexpected behavior with anonymized logs and the Home Assistant/Ford Triplog versions.
