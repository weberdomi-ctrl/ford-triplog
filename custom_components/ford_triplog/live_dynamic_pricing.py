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
    """Read a price normalized to the configured currency per kWh.

    EUR/kWh and CHF/kWh remain supported. German Tibber/evcc price sensors
    may report euro cents (ct/kWh) or Swiss rappen (Rp/kWh); normalize those
    units before recording price boundaries so the actual interval costs
    always use the base currency. Reject mismatched currencies rather than
    silently treating cents as euros or rappen as francs.
    """
    if state is None or str(state.state).strip().lower() in (
        "", "unknown", "unavailable", "none", "null"
    ):
        return None
    currency = str(currency or "").strip().upper()
    if currency not in ("EUR", "CHF"):
        return None
    unit = (
        str(state.attributes.get("unit_of_measurement") or "")
        .strip()
        .upper()
        .replace(" ", "")
        .replace("\u00a0", "")
        .replace("\u202f", "")
    )
    whole = {"EUR": {"EUR/KWH", "€/KWH"}, "CHF": {"CHF/KWH"}}[currency]
    subunit = {
        "EUR": {"CT/KWH", "CTS/KWH", "CENT/KWH", "CENTS/KWH", "€CT/KWH", "EURCT/KWH"},
        "CHF": {"RP/KWH", "RAPPEN/KWH", "CHFCT/KWH"},
    }[currency]
    # Preserve legacy unitless sensors; users must configure these in
    # base currency units, as before R5.
    if not unit or unit in whole:
        divisor = Decimal(1)
    elif unit in subunit:
        divisor = Decimal(100)
    else:
        return None
    value = _number(state.state)
    return float(value / divisor) if value is not None else None


def dynamic_price_diagnostics(charge):
    """Small, recorder-safe price calculation diagnostics for HA sensors.

    Do not publish full price steps as HA attributes; long charging sessions
    can exceed Home Assistant's 16 KiB recorder attribute limit.
    """
    sensor = charge.get("dynamic_price_sensor")
    applied = bool(charge.get("dynamic_meter_pricing_applied", False))
    finished = bool(charge.get("dynamic_price_finished", False))
    valid = bool(charge.get("dynamic_price_valid", False))
    failure = charge.get("dynamic_price_failure_reason")
    if not sensor:
        status = "not_configured"
    elif applied:
        status = "applied"
    elif failure:
        status = "failed"
    elif finished:
        status = "not_applied"
    else:
        status = "in_progress"
    steps = charge.get("dynamic_price_steps") or []
    return {
        "dynamic_price_sensor": sensor,
        "dynamic_price_status": status,
        "dynamic_meter_pricing_applied": applied,
        "dynamic_price_valid": valid,
        "dynamic_price_failure_reason": failure,
        "dynamic_price_interval_count": len(steps) if isinstance(steps, list) else 0,
        "dynamic_meter_allocation_method": charge.get("dynamic_meter_allocation_method"),
    }


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
