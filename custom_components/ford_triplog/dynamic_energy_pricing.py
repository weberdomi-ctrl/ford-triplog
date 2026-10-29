"""Allocate a session-level grid energy measurement to known price samples.

This is a proportional estimate: a single end-of-charge meter reading cannot
reveal when charging losses occurred. Never label allocated interval energy as
measured interval energy; retain the original vehicle energy for each step.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

_ENERGY_PRECISION = Decimal("0.000001")
_COST_PRECISION = Decimal("0.00000001")


def _valid_number(value, *, allow_zero=True):
    try:
        num = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
    if not num.is_finite() or num < 0 or (not allow_zero and num == 0):
        return None
    return num


def calculate_dynamic_pricing(steps, meter_energy_kwh=None):
    """Reprice original simulated price intervals using optional total grid kWh.

    Returns a freshly built structure, so rerunning never multiplies an already
    adjusted cost. In the absence of a trustworthy meter value, original step
    prices and costs are preserved exactly. The extra grid energy is distributed
    proportionally to vehicle kWh across the existing price steps; this is an
    estimate, not a measurement of energy per price interval.
    """
    samples = []
    for sample in steps:
        item = dict(sample)
        vehicle_energy = _valid_number(item.get('energy_kwh'))
        price = _valid_number(item.get('price_per_kwh'))
        cost = _valid_number(item.get('cost'))
        if vehicle_energy is None or price is None or cost is None:
            raise ValueError('Invalid dynamic pricing step')
        samples.append((item, vehicle_energy, price, cost))
    total_vehicle = sum((s[1] for s in samples), Decimal(0))
    original_cost = sum((s[3] for s in samples), Decimal(0))
    meter = _valid_number(meter_energy_kwh, allow_zero=False)
    use_meter = meter is not None and total_vehicle > 0 and len(samples) > 0
    processed = []
    allocated_so_far = Decimal(0)
    for idx, (item, vehicle_energy, price, cost) in enumerate(samples):
        # Keep original data when the meter is missing/invalid.
        if use_meter:
            if idx == len(samples) - 1:
                billed_energy = meter - allocated_so_far
            else:
                billed_energy = (meter * vehicle_energy / total_vehicle).quantize(
                    _ENERGY_PRECISION, rounding=ROUND_HALF_UP)
                allocated_so_far += billed_energy
            billed_cost = (billed_energy * price).quantize(_COST_PRECISION, rounding=ROUND_HALF_UP)
            item['vehicle_cost'] = float(cost)
            item['billed_energy_kwh'] = float(billed_energy)
            item['cost'] = float(billed_cost)
        processed.append(item)
    total_cost = (sum((Decimal(str(s['cost'])) for s in processed), Decimal(0))
                  .quantize(_ENERGY_PRECISION, rounding=ROUND_HALF_UP))
    return {
        'steps': processed,
        'total_energy_kwh': float(total_vehicle),
        'energy_billed_kwh': float(meter if use_meter else total_vehicle),
        'total_cost': float(total_cost),
        'vehicle_only_cost': float(original_cost.quantize(_ENERGY_PRECISION, rounding=ROUND_HALF_UP)),
        'meter_pricing_applied': use_meter,
        'meter_allocation_method': 'proportional' if use_meter else None,
    }
