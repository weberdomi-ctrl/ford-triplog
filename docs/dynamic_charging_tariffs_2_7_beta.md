# Dynamic charging tariffs — Ford Triplog 2.7.0

**Status:** Stable in 2.7.0 (build 27039). This guide retains its original beta-era filename for existing links. Verify billing against your provider or meter; tariff precision depends on price-history and energy data.

## Overview

Ford Triplog 2.7.0 supports a compatible Home Assistant sensor that reports an electricity price. It can calculate charging costs with changing prices during a session when suitable price and charging-energy data is available.

Tariff configuration can be scoped by **vehicle** and **Home Assistant charging zone**. This extends the global fixed home-tariff periods documented for 2.6.

## Preparation

1. Create or identify a Home Assistant sensor reporting the current electricity price.
2. Check the numeric values and units. Supported units are EUR/kWh, CHF/kWh, ct/kWh and Rp/kWh (with matching configured currency).
3. Configure the appropriate vehicle and charging location/zone in the integration options.
4. Confirm that charging-energy information is available for the vehicle.
5. Test with a short charging session and compare the calculated cost with your own reference calculation.

Options-flow labels may differ slightly by Home Assistant language. Do not assume a provider-specific integration such as Tibber is required; the source is a Home Assistant entity.

## Price changes and persistence

The intended behavior is to account for price changes within a charging session, depending on the available measurement data. Calculated costs should remain stable after a Home Assistant restart rather than being overwritten using a later price.

Billed or receipt-derived charging costs remain authoritative according to Ford Triplog's existing cost-source priorities.

## Known limitations and feedback

Automated tariff and diagnostic tests passed. An external Tibber/evcc tester reported matching overall charge costs after the price-unit improvement, but detailed interval-by-interval diagnostics were not independently reviewed. Testers should report the price sensor, its unit, timestamps, energy readings, expected and calculated costs, and relevant redacted logs.

The requested EV-versus-combustion cost comparison in [issue #70](https://github.com/weberdomi-ctrl/ford-triplog/issues/70) is **not** included.
