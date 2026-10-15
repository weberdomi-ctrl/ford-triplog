# Dynamic charging tariffs — Ford Triplog 2.7.0-beta.1

**Status:** Pre-release. The behavior described here is based on the beta implementation and simulation testing; it is not a guarantee of correct billing under every tariff.

## Overview

Ford Triplog 2.7 beta supports a compatible Home Assistant sensor that reports an electricity price. It can calculate charging costs with changing prices during a session when suitable price and charging-energy data is available.

Tariff configuration can be scoped by **vehicle** and **Home Assistant charging zone**. This extends the global fixed home-tariff periods documented for 2.6.

## Preparation

1. Create or identify a Home Assistant sensor reporting the current electricity price.
2. Check that its numeric values and units match the tariff configuration used in Ford Triplog.
3. Configure the appropriate vehicle and charging location/zone in the integration options.
4. Confirm that charging-energy information is available for the vehicle.
5. Test with a short charging session and compare the calculated cost with your own reference calculation.

The exact options-flow labels can differ between beta builds. Do not assume a provider-specific integration such as Tibber is required; the source is a Home Assistant entity.

## Price changes and persistence

The intended beta behavior is to account for price changes within a charging session, depending on the available measurement data. Calculated costs should remain stable after a Home Assistant restart rather than being overwritten using a later price.

Billed or receipt-derived charging costs remain authoritative according to Ford Triplog's existing cost-source priorities.

## Known limitations and feedback

Simulation tests have been performed, but a full live dynamic-tariff charging session is still outstanding. Testers should report the price sensor, its unit, timestamps, energy readings, expected and calculated costs, and relevant redacted logs.

The requested EV-versus-combustion cost comparison in [issue #70](https://github.com/weberdomi-ctrl/ford-triplog/issues/70) is **not** included.
