"""Ford Triplog Beta 6 R5: subunit price sensors and dynamic tariff audit."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "ford_triplog"
spec = importlib.util.spec_from_file_location(
    "ford_triplog_live_dynamic_pricing_test",
    ROOT / "live_dynamic_pricing.py",
)
pricing = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(pricing)


def price(value, unit):
    return SimpleNamespace(
        state=str(value),
        attributes={"unit_of_measurement": unit},
    )


class PriceUnitR5Tests(unittest.TestCase):
    def test_base_currency_backward_compatible(self):
        self.assertAlmostEqual(pricing.read_price_per_kwh(price(0.4071, "EUR/kWh"), "EUR"), 0.4071)
        self.assertAlmostEqual(pricing.read_price_per_kwh(price(0.2395, "CHF/kWh"), "CHF"), 0.2395)
        self.assertAlmostEqual(pricing.read_price_per_kwh(price(0.4071, "€/kWh"), "EUR"), 0.4071)
        self.assertAlmostEqual(pricing.read_price_per_kwh(price(0.4071, ""), "EUR"), 0.4071)

    def test_euro_cent_tibber_sensor(self):
        for unit in ("ct/kWh", "CT/KWH", "cts/kWh", "cent/kWh", "€ct/kWh", "EURct/kWh", " ct / kWh "):
            with self.subTest(unit=unit):
                self.assertAlmostEqual(pricing.read_price_per_kwh(price(40.71, unit), "EUR"), 0.4071)
        self.assertEqual(pricing.read_price_per_kwh(price(0, "ct/kWh"), "EUR"), 0.0)

    def test_swiss_rappen_sensor(self):
        for unit in ("Rp/kWh", "rappen/kWh", "CHFct/kWh", " Rp / kWh "):
            with self.subTest(unit=unit):
                self.assertAlmostEqual(pricing.read_price_per_kwh(price(23.95, unit), "CHF"), 0.2395)

    def test_mismatched_unsupported_or_invalid_prices_are_rejected(self):
        for value, unit, currency in (
            (40.71, "ct/kWh", "CHF"),
            (40.71, "Rp/kWh", "EUR"),
            (40.71, "USD/kWh", "EUR"),
            (40.71, "EUR/MWh", "EUR"),
            (-1, "ct/kWh", "EUR"),
            ("unavailable", "ct/kWh", "EUR"),
            ("nan", "Rp/kWh", "CHF"),
        ):
            with self.subTest(value=value, unit=unit, currency=currency):
                self.assertIsNone(pricing.read_price_per_kwh(price(value, unit), currency))

    def test_cent_conversion_preserved_across_price_boundaries(self):
        first = pricing.read_price_per_kwh(price(41, "ct/kWh"), "EUR")
        second = pricing.read_price_per_kwh(price(45, "ct/kWh"), "EUR")
        result = pricing.price_meter_boundaries(
            [
                {"at": "2026-11-04T22:00:00+01:00", "meter_kwh": 1000, "price_per_kwh": first},
                {"at": "2026-11-04T23:00:00+01:00", "meter_kwh": 1005, "price_per_kwh": second},
                {"at": "2026-11-05T00:00:00+01:00", "meter_kwh": 1017.93, "price_per_kwh": None},
            ],
            billed_energy_kwh=17.93,
        )
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result["total_cost"], 7.8685)
        self.assertEqual(len(result["steps"]), 2)
        self.assertEqual(result["meter_allocation_method"], "meter_boundary_samples")

    def test_swiss_currency_cost_not_scaled_by_100(self):
        rate = pricing.read_price_per_kwh(price(23.95, "Rp/kWh"), "CHF")
        result = pricing.price_meter_boundaries(
            [
                {"at": "2026-11-04T22:00:00+01:00", "meter_kwh": 1, "price_per_kwh": rate},
                {"at": "2026-11-04T23:00:00+01:00", "meter_kwh": 11, "price_per_kwh": None},
            ],
            billed_energy_kwh=10,
        )
        self.assertAlmostEqual(result["total_cost"], 2.395)

    def test_diagnostics_report_exact_status_without_large_samples(self):
        self.assertEqual(pricing.dynamic_price_diagnostics({})["dynamic_price_status"], "not_configured")
        active = {"dynamic_price_sensor": "sensor.tibber", "dynamic_price_valid": True}
        self.assertEqual(pricing.dynamic_price_diagnostics(active)["dynamic_price_status"], "in_progress")
        failed = {**active, "dynamic_price_finished": True, "dynamic_price_valid": False,
                  "dynamic_price_failure_reason": "invalid_initial_price_or_meter"}
        self.assertEqual(pricing.dynamic_price_diagnostics(failed)["dynamic_price_status"], "failed")
        self.assertEqual(pricing.dynamic_price_diagnostics(failed)["dynamic_price_failure_reason"],
                         "invalid_initial_price_or_meter")
        self.assertEqual(pricing.dynamic_price_diagnostics(
            {**active, "dynamic_price_finished": True}
        )["dynamic_price_status"], "not_applied")
        applied = {
            **failed, "dynamic_meter_pricing_applied": True, "dynamic_price_failure_reason": None,
            "dynamic_price_valid": True, "dynamic_price_steps": [{"price_per_kwh": 0.4}] * 8,
            "dynamic_meter_allocation_method": "meter_boundary_samples",
        }
        result = pricing.dynamic_price_diagnostics(applied)
        self.assertEqual(result["dynamic_price_status"], "applied")
        self.assertTrue(result["dynamic_meter_pricing_applied"])
        self.assertEqual(result["dynamic_price_interval_count"], 8)
        self.assertNotIn("dynamic_price_steps", result)
        self.assertNotIn("dynamic_price_samples", result)

    def test_sensor_exposes_diagnostics_and_version_matches(self):
        source = (ROOT / "sensor.py").read_text(encoding="utf-8")
        self.assertIn("**dynamic_price_diagnostics(last_charge)", source)
        self.assertIn('price_diagnostics["dynamic_price_status"]', source)
        self.assertIn('price_diagnostics["dynamic_price_interval_count"]', source)
        manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
        constants = (ROOT / "const.py").read_text(encoding="utf-8")
        self.assertEqual(manifest["version"], "2.7.0-beta.6-r5")
        self.assertIn('VERSION: Final = "2.7.0-beta.6-r5"', constants)
        self.assertIn('BUILD: Final = "27027"', constants)


if __name__ == "__main__":
    unittest.main()
