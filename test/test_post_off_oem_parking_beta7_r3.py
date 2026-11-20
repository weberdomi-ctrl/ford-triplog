"""Beta 7 R3 regressions: late OEM GPS may confirm a stale parking anchor.

Run without Home Assistant:
  python -m unittest discover -s test -p 'test_post_off_oem_parking_beta7_r3.py' -v
"""
from datetime import datetime, timedelta, timezone
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "custom_components" / "ford_triplog" / "trip_start_position.py"
spec = spec_from_file_location("parked_oem_r3", HELPER)
parking = module_from_spec(spec)
spec.loader.exec_module(parking)

# 09 November 2026: the recorded home trip ends at 17:24:58.704 CET.
OFF = datetime(2026, 11, 9, 16, 24, 58, 704000, tzinfo=timezone.utc)
OLD = (47.188301, 8.473695)  # Stale 07:33 OEM fix, at work
HOME = (47.175616, 8.951371)  # New 17:24:58 OEM fix, at home
ROUTE = (47.175649, 8.951427)  # Independent pre-OFF route endpoint


def stale():
    return {
        "latitude": OLD[0], "longitude": OLD[1],
        "gps_updated_at": "2026-11-09T06:33:50.245613Z",
        "ignition_off_at": OFF.isoformat(),
        "source": "vehicle_tracker_stale_ignition_off",
        "odometer": 63947.0,
    }


def vehicle(*, lat=HOME[0], lon=HOME[1], timestamp=None, odo=63948.0,
            source="ford_gps_module"):
    return {
        "latitude": lat, "longitude": lon,
        "gps_updated_at": timestamp or (OFF - timedelta(milliseconds=114)).isoformat(),
        "gps_timestamp_source": source,
        "odometer": odo,
    }


def point(*, time=None, accuracy=7.0, speed=0.2,
          lat=ROUTE[0], lon=ROUTE[1]):
    return {
        "latitude": lat, "longitude": lon,
        "timestamp": time or (OFF - timedelta(seconds=1.333)).isoformat(),
        "gps_accuracy": accuracy, "speed": speed,
    }


class PostOffFordGpsTests(unittest.TestCase):
    def confirmed(self, parked=None, state=None, endpoint=None, now=None):
        return parking.confirmed_post_off_oem_parking_fix(
            stale() if parked is None else parked,
            vehicle() if state is None else state,
            OFF + timedelta(seconds=4) if now is None else now,
            route_point=point() if endpoint is None else endpoint,
        )

    def test_real_november_ninth_36km_case_corrects_anchor(self):
        result = self.confirmed()
        self.assertIsNotNone(result)
        self.assertEqual(parking.coordinates(result), HOME)
        self.assertEqual(result["source"], "vehicle_oem_route_confirmed_post_off")
        self.assertEqual(result["odometer"], 63948.0)
        self.assertEqual(result["ignition_off_at"], OFF.isoformat())
        selected, reason = parking.parking_anchor(
            vehicle(odo=63948.0), result, OFF + timedelta(hours=14)
        )
        self.assertIsNotNone(selected, reason)
        self.assertEqual(parking.coordinates(selected), HOME)

    def test_stabilized_end_odometer_still_accepts_new_fix(self):
        parked = stale()
        parked["odometer"] = 63948.0
        self.assertEqual(parking.coordinates(self.confirmed(parked=parked)), HOME)

    def test_same_location_from_ha_update_is_not_new_oem_proof(self):
        for source in ("ha_last_updated", None, "coordinates_mismatch"):
            with self.subTest(source=source):
                self.assertIsNone(self.confirmed(state=vehicle(source=source)))

    def test_pre_off_old_or_post_off_delayed_fix_is_rejected(self):
        for sample in (
            OFF - timedelta(minutes=10),
            OFF - timedelta(seconds=121),
            OFF + timedelta(seconds=121),
        ):
            with self.subTest(sample=sample):
                self.assertIsNone(self.confirmed(state=vehicle(timestamp=sample.isoformat())))
        self.assertIsNone(self.confirmed(now=OFF + timedelta(minutes=11)))

    def test_route_must_belong_to_previous_trip(self):
        for route_time in (
            OFF + timedelta(milliseconds=1),
            OFF - timedelta(seconds=21),
        ):
            with self.subTest(route_time=route_time):
                self.assertIsNone(self.confirmed(endpoint=point(time=route_time.isoformat())))
        self.assertIsNone(parking.confirmed_post_off_oem_parking_fix(
            stale(), vehicle(), OFF + timedelta(seconds=4), route_point=None
        ))

    def test_route_must_spatially_confirm_ford_location(self):
        self.assertIsNone(self.confirmed(endpoint=point(lat=47.25, lon=8.83)))

    def test_bad_route_quality_or_motion_cannot_confirm(self):
        for sample in (
            point(accuracy=0), point(accuracy=75),
            point(speed=6), point(speed=None),
        ):
            with self.subTest(sample=sample):
                self.assertIsNone(self.confirmed(endpoint=sample))

    def test_odometer_is_required_and_must_be_stable(self):
        for odo in (None, 63949.2, 63945.0):
            with self.subTest(odo=odo):
                self.assertIsNone(self.confirmed(state=vehicle(odo=odo)))
        missing = stale()
        missing["odometer"] = None
        self.assertIsNone(self.confirmed(parked=missing))

    def test_never_displace_a_verified_route_or_newer_park(self):
        for source in ("parked_route_fix_corrob_pre_off", "vehicle_tracker_ignition_off",
                       "vehicle_oem_route_confirmed_post_off"):
            parked = stale()
            parked["source"] = source
            self.assertIsNone(self.confirmed(parked=parked))

    def test_ignition_off_snapshot_not_replaced_by_route_after_off(self):
        parked = stale()
        result = parking.stabilize_parking_snapshot(
            parked, vehicle(), OFF + timedelta(seconds=4), route_point=None
        )
        # Stable odometer may advance, but the invalid old coordinate is
        # not promoted to a confirmed parking position without route proof.
        self.assertIsNotNone(result)
        self.assertEqual(result["source"], "vehicle_tracker_stale_ignition_off")
        self.assertEqual(parking.coordinates(result), OLD)
        self.assertIsNone(self.confirmed(
            parked=result, endpoint=point(time=(OFF + timedelta(seconds=10)).isoformat())
        ))

    def test_coordinator_handles_both_update_and_finalize_paths(self):
        text = (ROOT / "custom_components" / "ford_triplog" / "coordinator.py").read_text()
        self.assertGreaterEqual(text.count("confirmed_post_off_oem_parking_fix("), 2)
        self.assertIn("self.route_tracker.get_last_point()", text)
        self.assertIn("self._schedule_parking_position_save(refreshed)", text)
        self.assertIn("gps_timestamp_source", text)


if __name__ == "__main__":
    unittest.main()
