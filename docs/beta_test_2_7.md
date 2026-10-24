# Ford Triplog 2.7.0-beta.1 — Beta test guide

## Before upgrading

1. Back up `ford_triplog.db`, the Home Assistant configuration and the current integration files.
2. Record your current integration version and charging tariff configuration.
3. Install the beta build using the project's normal update method and restart Home Assistant.
4. Check the integration log for startup and database migration errors.

## Suggested checks

- Verify that existing vehicles, trips, charging sessions and costs are still present.
- Check that each vehicle uses its intended charging tariff and Home Assistant charging zone.
- Select a compatible dynamic electricity-price sensor and confirm its unit and values.
- Run a controlled charging test; compare the recorded energy and price changes with the calculated cost.
- Restart Home Assistant and verify that the charging cost has not changed unexpectedly.
- Test a charging session spanning a price interval boundary (hourly or 15-minute where supported by the sensor and integration).
- Verify route export and inspect the exported data.
- Check the Home Assistant log for `ford_triplog`, `sqlite`, and JSON errors.

## Reporting a problem

Include the integration version, HA version, vehicle, sensor entity ID and units, price timestamps, charge start/end timestamps, charged/billed kWh, expected and displayed costs, and sanitized log excerpts. Do not publish VINs, addresses, tokens or private GPS coordinates.

**Scope:** The EV-versus-combustion-vehicle comparison is not part of beta 1.
