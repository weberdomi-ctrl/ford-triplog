"""Regression: stale (but apparently fresh) Ford tracker parking GPS.

Run locally with:
  python -m unittest discover -s test -p 'test_trip_start_position_beta7_r1.py' -v
No Home Assistant install needed.
"""
from datetime import datetime, timedelta, timezone
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "custom_components" / "ford_triplog" / "trip_start_position.py"
spec = spec_from_file_location("trip_start_position_beta7_r1", MODULE)
parking = module_from_spec(spec)
spec.loader.exec_module(parking)

OFF = datetime(2026, 11, 8, 9, 51, 31, tzinfo=timezone.utc)
# Deliberately synthetic coordinates. About 6 km apart.
STALE = (47.000, 8.000)
ACTUAL = (47.034, 8.057)


def parked():
    return {
        "latitude": STALE[0], "longitude": STALE[1],
        "gps_updated_at": (OFF - timedelta(seconds=1)).isoformat(),
        "ignition_off_at": OFF.isoformat(),
        "odometer": 63843.0,
        "source": "vehicle_tracker_ignition_off",
    }


def stable_vehicle():
    return {
        "latitude": STALE[0], "longitude": STALE[1],
        "gps_updated_at": (OFF + timedelta(seconds=4)).isoformat(),
        "odometer": 63843.0,
    }


def phone_point(seconds_before, *, lat=None, lon=None, accuracy=7.0, speed=0.2):
    return {
        "latitude": ACTUAL[0] if lat is None else lat,
        "longitude": ACTUAL[1] if lon is None else lon,
        "timestamp": (OFF - timedelta(seconds=seconds_before)).isoformat(),
        "gps_accuracy": accuracy,
        "speed": speed,
    }


class ParkGpsStaleTrackerTests(unittest.TestCase):
    def reconcile(self, points, vehicle=None, saved=None):
        vehicle = stable_vehicle() if vehicle is None else vehicle
        saved = parked() if saved is None else saved
        return parking.stabilize_parking_snapshot(
            saved, vehicle, OFF + timedelta(seconds=5),
            route_point=points[-1] if points else None, route_points=points,
        )

    def test_sunday_parking_scenario_recovers_six_kilometres(self):
        """Route ends at park; Ford tracker still reports the intermediate stop."""
        points = [
            phone_point(12, lat=ACTUAL[0] + 0.00005),
            phone_point(3),
        ]
        result = self.reconcile(points)
        self.assertIsNotNone(result)
        self.assertEqual(result["source"], "parked_route_fix_corrob_pre_off")
        self.assertEqual(result["latitude"], ACTUAL[0])
        self.assertEqual(result["longitude"], ACTUAL[1])
        self.assertEqual(result["odometer"], 63843.0)
        self.assertEqual(result["gps_updated_at"], points[-1]["timestamp"])

        # The next drive really starts at the parked spot. Reuse is protected
        # rather than rejected as position_mismatch_6236m.
        start = {"latitude": ACTUAL[0], "longitude": ACTUAL[1], "odometer": 63843.0}
        anchor, reason = parking.parking_anchor(start, result, OFF + timedelta(hours=20))
        self.assertEqual(parking.coordinates(anchor), ACTUAL)
        self.assertIn("parking_confirmed_", reason)

    def test_single_accurate_phone_fix_cannot_override_distant_vehicle(self):
        self.assertIsNone(self.reconcile([phone_point(3)]))

    def test_no_recent_route_points_remains_conservative(self):
        self.assertIsNone(self.reconcile([]))

    def test_bad_quality_or_moving_phone_is_rejected(self):
        for altered in (
            {"gps_accuracy": 0}, {"gps_accuracy": 50},
            {"speed": 3}, {"speed": None},
        ):
            with self.subTest(altered=altered):
                point = phone_point(3)
                point.update(altered)
                self.assertIsNone(self.reconcile([phone_point(12), point]))

    def test_post_off_phone_position_never_used(self):
        self.assertIsNone(self.reconcile([phone_point(12), phone_point(-1)]))

    def test_old_or_duplicate_phone_fixes_rejected(self):
        self.assertIsNone(self.reconcile([phone_point(80), phone_point(3)]))
        self.assertIsNone(self.reconcile([phone_point(3), phone_point(3)]))
        self.assertIsNone(self.reconcile([phone_point(65), phone_point(52)]))

    def test_two_recent_points_must_really_agree(self):
        self.assertIsNone(self.reconcile([
            phone_point(12, lat=ACTUAL[0] + 0.004),
            phone_point(3),
        ]))

    def test_odometer_inconsistent_or_missing_does_not_override(self):
        good = [phone_point(12), phone_point(3)]
        for odo in (63847.0, None):
            with self.subTest(odo=odo):
                new_vehicle = stable_vehicle()
                new_vehicle["odometer"] = odo
                result = self.reconcile(good, vehicle=new_vehicle)
                self.assertTrue(result is None or parking.coordinates(result) == STALE)

    def test_ten_kilometre_mismatch_limit(self):
        far = [
            phone_point(12, lat=47.20, lon=8.20),
            phone_point(3, lat=47.20, lon=8.20),
        ]
        self.assertIsNone(self.reconcile(far))

    def test_existing_nearby_fix_works_without_two_samples(self):
        saved = parked()
        point = phone_point(3, lat=STALE[0] + 0.0001, lon=STALE[1] + 0.0001)
        saved["gps_updated_at"] = (OFF - timedelta(seconds=45)).isoformat()
        result = self.reconcile([point], saved=saved, vehicle={})
        self.assertIsNotNone(result)
        self.assertEqual(result["source"], "parked_route_fix_at_ignition_off")

    def test_unchanged_tracker_and_no_phone_not_promoted(self):
        saved = parked()
        result = self.reconcile([], vehicle=stable_vehicle(), saved=saved)
        self.assertIsNone(result)

    def test_coordinator_passes_bounded_tail_to_both_end_paths(self):
        coordinator = (ROOT / "custom_components" / "ford_triplog" / "coordinator.py").read_text()
        tracker = (ROOT / "custom_components" / "ford_triplog" / "route_tracker.py").read_text()
        self.assertIn("def get_recent_points(self, limit:", tracker)
        self.assertGreaterEqual(coordinator.count("self.route_tracker.get_recent_points()"), 2)
        self.assertGreaterEqual(coordinator.count("route_points=recent_route_points"), 2)


if __name__ == "__main__":
    unittest.main()
