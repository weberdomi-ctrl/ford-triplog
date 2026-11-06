"""Regressions for Ford Triplog beta.5-r21 parking GPS selection.

Run with: python -m unittest discover -s test -p "test_trip_start_position_r21.py" -v
No Home Assistant installation is required for these pure helper tests.
"""
from datetime import datetime, timedelta, timezone
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import unittest

HELPER_PATH = (
    Path(__file__).resolve().parents[1]
    / "custom_components" / "ford_triplog" / "trip_start_position.py"
)
spec = spec_from_file_location("test_triplog_parking_helpers", HELPER_PATH)
helper = module_from_spec(spec)
spec.loader.exec_module(helper)

OFF = datetime(2026, 11, 6, 8, 0, tzinfo=timezone.utc)


def parked(gps_age=70):
    return {
        "latitude": 47.1750,
        "longitude": 8.9510,
        "odometer": 63702.0,
        "gps_updated_at": (OFF - timedelta(seconds=gps_age)).isoformat(),
        "ignition_off_at": OFF.isoformat(),
        "source": "vehicle_tracker_ignition_off",
    }


class ParkGpsRelease21Tests(unittest.TestCase):
    def test_unchanged_park_location_is_the_start(self):
        park = parked()
        current = {
            "latitude": 47.1752,
            "longitude": 8.9510,
            "odometer": 63702.0,
        }
        selected, reason = helper.parking_anchor(
            current, park, OFF + timedelta(hours=12)
        )
        self.assertIsNotNone(selected, reason)
        self.assertEqual(selected["latitude"], park["latitude"])
        self.assertIn("parking_confirmed", reason)

    def test_two_minute_delayed_on_keeps_original_parking_point(self):
        park = parked()
        current = {
            "latitude": 47.1870,  # approx. 1.3 km down the road
            "longitude": 8.9510,
            "odometer": 63703.5,
        }
        selected, reason = helper.parking_anchor(
            current, park, OFF + timedelta(hours=12)
        )
        self.assertIsNotNone(selected, reason)
        self.assertEqual(selected["latitude"], 47.1750)
        self.assertIn("parking_delayed_rest", reason)

    def test_distant_stale_park_cannot_create_29km_false_start(self):
        park = parked()
        current = {
            "latitude": 47.4340,
            "longitude": 8.9510,
            "odometer": 63703.0,
        }
        selected, reason = helper.parking_anchor(
            current, park, OFF + timedelta(hours=12)
        )
        self.assertIsNone(selected)
        self.assertIn(reason.split("_")[0], ("position", "odometer"))

    def test_timeout_uses_recent_accurate_stationary_tracker_as_fallback(self):
        park = parked(gps_age=100)
        route_point = {
            "latitude": 47.1885,
            "longitude": 8.9510,
            "timestamp": (OFF - timedelta(seconds=5)).isoformat(),
            "gps_accuracy": 8.0,
            "speed": 0.3,
        }
        selected = helper.stabilize_parking_snapshot(
            park, {}, OFF + timedelta(minutes=4), route_point=route_point
        )
        self.assertIsNotNone(selected)
        self.assertEqual(selected["source"], "parked_route_fix_at_ignition_off")
        self.assertEqual(selected["latitude"], route_point["latitude"])

    def test_phone_point_after_ignition_off_is_never_park_gps(self):
        park = parked(gps_age=100)
        late_point = {
            "latitude": 47.1885,
            "longitude": 8.9510,
            "timestamp": (OFF + timedelta(seconds=25)).isoformat(),
            "gps_accuracy": 8.0,
            "speed": 0.3,
        }
        result = helper.stabilize_parking_snapshot(
            park, {}, OFF + timedelta(minutes=4), route_point=late_point
        )
        self.assertIsNone(result)

    def test_fordpass_newer_gps_can_confirm_park_after_timeout(self):
        park = parked(gps_age=100)
        vehicle = {
            "latitude": 47.1760,
            "longitude": 8.9510,
            "gps_updated_at": (OFF + timedelta(minutes=3)).isoformat(),
            "odometer": 63702.0,
        }
        result = helper.stabilize_parking_snapshot(
            park, vehicle, OFF + timedelta(minutes=4)
        )
        self.assertIsNotNone(result)
        self.assertEqual(result["latitude"], vehicle["latitude"])
        self.assertEqual(result["source"], "vehicle_tracker_stable_parked_fix")

    def test_same_old_fordpass_fix_is_not_treated_as_new(self):
        park = parked(gps_age=100)
        vehicle = {
            "latitude": park["latitude"],
            "longitude": park["longitude"],
            "gps_updated_at": park["gps_updated_at"],
            "odometer": park["odometer"],
        }
        result = helper.stabilize_parking_snapshot(
            park, vehicle, OFF + timedelta(minutes=4)
        )
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
