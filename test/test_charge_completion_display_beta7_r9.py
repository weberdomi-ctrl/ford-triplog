"""Beta 7 R9: display energy-transfer completion, not morning unplug.

Run: python -m unittest discover -s test -p 'test_charge_completion_display_beta7_r9.py' -v
This does not need Home Assistant.
"""
import ast
from datetime import datetime, timezone
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from unittest import TestCase

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "custom_components" / "ford_triplog"
spec = spec_from_file_location("charging_time", PATH / "charging_time.py")
module = module_from_spec(spec)
spec.loader.exec_module(module)


def sample(**changes):
    data = {
        "start_time": "2026-11-13T17:41:00.962022+01:00",
        "completion_time": "2026-11-13T20:31:47.557514+00:00",
        "end_time": "2026-11-14T09:55:01.948649+01:00",
        "detected_end_time": "2026-11-14T09:55:01.948649+01:00",
        "energy_added_kwh": 38.5,
        "start_soc": 28,
        "end_soc": 78,
    }
    data.update(changes)
    return data


class ChargingTimeTests(TestCase):
    def test_real_november_13_overnight_charge(self):
        charge = sample()
        self.assertEqual(
            module.charge_transfer_end_time(charge),
            "2026-11-13T20:31:47.557514+00:00",
        )
        self.assertEqual(module.charge_transfer_duration_seconds(charge), 13846)
        # Preserve R7 Ford Last Charge matching against physical unplug.
        self.assertEqual(charge["end_time"], "2026-11-14T09:55:01.948649+01:00")
        self.assertEqual(charge["detected_end_time"], charge["end_time"])
        self.assertEqual(
            module.charge_plug_disconnected_time(charge),
            charge["end_time"],
        )

    def test_legacy_or_never_completed_uses_unplug(self):
        charge = sample(completion_time=None)
        self.assertEqual(module.charge_transfer_end_time(charge), charge["end_time"])
        self.assertEqual(module.charge_transfer_duration_seconds(charge), 58440)
        self.assertIsNone(module.charge_plug_disconnected_time(charge))

    def test_completion_before_start_is_rejected(self):
        charge = sample(completion_time="2026-11-12T20:31:47+00:00")
        self.assertEqual(module.charge_transfer_end_time(charge), charge["end_time"])

    def test_completion_after_unplug_is_rejected(self):
        charge = sample(completion_time="2026-11-14T11:01:00+01:00")
        self.assertEqual(module.charge_transfer_end_time(charge), charge["end_time"])

    def test_invalid_completion_is_rejected(self):
        charge = sample(completion_time="invalid")
        self.assertEqual(module.charge_transfer_end_time(charge), charge["end_time"])

    def test_no_archived_end_is_not_presented_as_completed(self):
        charge = sample(end_time=None)
        self.assertIsNone(module.charge_transfer_end_time(charge))
        self.assertIsNone(module.charge_transfer_duration_seconds(charge))

    def test_equal_completion_and_unplug_stays_unchanged(self):
        charge = sample(completion_time="2026-11-14T09:55:01.948649+01:00")
        self.assertEqual(module.charge_transfer_end_time(charge), charge["end_time"])

    def test_resumed_session_uses_latest_completed_segment(self):
        charge = sample(
            completion_time="2026-11-14T08:20:00+01:00",
            charging_resume_count=1,
            pause_count=2,
        )
        self.assertEqual(
            module.charge_transfer_end_time(charge),
            "2026-11-14T08:20:00+01:00",
        )


class SensorIntegrationTests(TestCase):
    def test_last_charge_duration_sensor_uses_transfer_time(self):
        source = (PATH / "sensor.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        cls = next(
            n for n in tree.body
            if isinstance(n, ast.ClassDef)
            and n.name == "FordTriplogLastChargeDurationSensor"
        )
        update = next(n for n in cls.body
                      if isinstance(n, ast.FunctionDef)
                      and n.name == "update_values")
        namespace = {
            "charge_transfer_duration_seconds":
                module.charge_transfer_duration_seconds,
        }
        mock_cls = ast.ClassDef(
            name="DurationSensorUnderTest", bases=[], keywords=[],
            body=[update], decorator_list=[],
        )
        isolated = ast.Module(body=[mock_cls], type_ignores=[])
        exec(compile(ast.fix_missing_locations(isolated), "<duration>", "exec"),
             namespace)
        sensor = namespace["DurationSensorUnderTest"]()
        sensor.update_values({}, None, sample())
        self.assertEqual(sensor._value, 13846)
        sensor.update_values({}, None, sample(completion_time=None))
        self.assertEqual(sensor._value, 58440)

    def test_csv_charge_export_has_both_endpoints(self):
        source = (PATH / "export.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        row_method = next(n for n in tree.body
                          if isinstance(n, ast.FunctionDef) and n.name == "_charge_row")
        row_source = ast.get_source_segment(source, row_method)
        self.assertIn('"end_time": _csv_value(charge_transfer_end_time(data))',
                      row_source)
        self.assertIn('"plug_disconnected_time": _csv_value(', row_source)
        self.assertIn('charge_transfer_duration_seconds(data)', row_source)
