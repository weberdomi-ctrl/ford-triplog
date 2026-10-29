"""Production dynamic-tariff calculations from HA meter/price boundary snapshots.

Only price boundaries actually captured during the active charge are used.
A missing sample or counter reset suppresses automatic cost calculation; do
not invent historical prices from a sensor's current state.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


def _number(value):
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return number if number.is_finite() and number >= 0 else None


def read_price_per_kwh(state, currency):
    """Read a non-negative price in the configured currency per kWh."""
    if state is None or str(state.state).strip().lower() in (
        "", "unknown", "unavailable", "none", "null"
    ):
        return None
    unit = str(state.attributes.get("unit_of_measurement") or "").strip().upper().replace(" ", "")
    currency = str(currency or "").strip().upper()
    if unit and unit != f"{currency}/KWH":
        return None
    value = _number(state.state)
    return float(value) if value is not None else None


def price_meter_boundaries(samples, billed_energy_kwh):
    """Compute actual interval energy from sampled meter boundaries.

    Samples: [{at, meter_kwh, price_per_kwh}, ..., {at, meter_kwh,
    price_per_kwh: None}]. The last sample closes the final interval.
    It is safe to run more than once: no mutated input and no double billing.
    A timestamp is retained for provenance, but not used for estimating energy.
    """
    if not isinstance(samples, list) or len(samples) < 2:
        return None
    billed = _number(billed_energy_kwh)
    if billed is None or billed <= 0:
        return None
    normalized = []
    for sample in samples:
        if not isinstance(sample, dict) or not sample.get("at"):
            return None
        meter = _number(sample.get("meter_kwh"))
        price = _number(sample.get("price_per_kwh")) if sample.get("price_per_kwh") is not None else None
        if meter is None or (price is None and len(normalized) < len(samples)-1):
            return None
        normalized.append((str(sample["at"]), meter, price))
    if normalized[-1][2] is not None:
        return None
    steps = []
    measured = Decimal(0)
    cost = Decimal(0)
    for current, following in zip(normalized, normalized[1:]):
        if current[2] is None or following[1] < current[1]:
            return None
        delta = following[1] - current[1]
        measured += delta
        amount = delta * current[2]
        cost += amount
        steps.append({
            "at": current[0], "end_at": following[0],
            "price_per_kwh": float(current[2]),
            "billed_energy_kwh": float(delta),
            "cost": float(amount.quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)),
        })
    # Cross-check that every measured kWh belongs to precisely one interval.
    # R4 rounds the final session energy to 4 decimals.
    if abs(measured - billed) > Decimal("0.00011"):
        return None
    return {
        "steps": steps,
        "energy_billed_kwh": float(billed),
        "total_cost": float(cost.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)),
        "meter_allocation_method": "meter_boundary_samples",
    }
