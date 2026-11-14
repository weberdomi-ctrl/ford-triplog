"""R9 regression: charged duration differs from overnight plug duration."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import importlib.util
import unittest

MODULE = Path(__file__).resolve().parents[1] / "custom_components" / "ford_triplog" / "charging_duration.py"
spec = importlib.util.spec_from_file_location("charging_duration_r9", MODULE)
timing = importlib.util.module_from_spec(spec)
spec.loader.exec_module(timing)


class ChargingDurationTests(unittest.TestCase):
    def test_november_13_overnight_charge(self):
        start = datetime.fromisoformat("2026-11-13T17:41:00.962022+01:00")
        completed = datetime.fromisoformat("2026-11-13T20:31:47.557514+00:00")
        unplugged = datetime.fromisoformat("2026-11-14T09:55:01.948649+01:00")
        charge = {
            "start_time": start.isoformat(),
            "end_time": unplugged.isoformat(),
            "completion_time": completed.isoformat(),
            "pause_count": 1,
            "pause_duration_seconds": (unplugged - completed).total_seconds(),
        }
        self.assertEqual(timing.charging_end_time(charge), completed.isoformat())
        self.assertEqual(timing.charging_duration_seconds(charge), 13846)
        self.assertEqual(timing.plug_duration_seconds(charge), 58440)
        self.assertEqual(charge["end_time"], unplugged.isoformat())

    def test_single_completion_without_recorded_pause(self):
        charge = {
            "start_time": "2026-11-13T17:00:00+01:00",
            "end_time": "2026-11-14T09:00:00+01:00",
            "completion_time": "2026-11-13T21:00:00+01:00",
        }
        self.assertEqual(timing.charging_duration_seconds(charge), 4 * 3600)

    def test_resume_subtracts_all_pauses_not_only_final_pause(self):
        charge = {
            "start_time": "2026-11-13T17:00:00+01:00",
            "end_time": "2026-11-13T20:00:00+01:00",
            "completion_time": "2026-11-13T19:00:00+01:00",
            "pause_duration_seconds": 100 * 60,
        }
        self.assertEqual(timing.charging_duration_seconds(charge), 80 * 60)

    def test_unplug_without_completion_uses_connection_duration(self):
        charge = {
            "start_time": "2026-11-13T17:00:00+01:00",
            "end_time": "2026-11-13T18:00:00+01:00",
        }
        self.assertEqual(timing.charging_duration_seconds(charge), 3600)
        self.assertEqual(timing.charging_end_time(charge), charge["end_time"])

    def test_invalid_completion_cannot_override_unplug(self):
        charge = {
            "start_time": "2026-11-13T17:00:00+01:00",
            "end_time": "2026-11-13T20:00:00+01:00",
            "completion_time": "2026-11-14T02:00:00+01:00",
        }
        self.assertEqual(timing.charging_end_time(charge), charge["end_time"])
        self.assertEqual(timing.charging_duration_seconds(charge), 10800)

    def test_invalid_timestamps_are_safe(self):
        charge = {"start_time": "invalid", "end_time": "invalid"}
        self.assertIsNone(timing.charging_duration_seconds(charge))
        self.assertIsNone(timing.plug_duration_seconds(charge))


if __name__ == "__main__":
    unittest.main()
