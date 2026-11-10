"""Beta 7 R4 regression: GPS JSON/tracker race at ignition OFF.

No Home Assistant dependency:
  python -m unittest discover -s test -p 'test_missing_off_parking_beta7_r4.py' -v
"""
from datetime import datetime, timedelta, timezone
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "custom_components" / "ford_triplog" / "trip_start_position.py"
spec = spec_from_file_location("parking_off_r4", HELPER)
parking = module_from_spec(spec)
spec.loader.exec_module(parking)

# Real 2026-11-10 morning drive: ignition OFF at 07:35:06.511 CET.
OFF = datetime(2026, 11, 10, 6, 35, 6, 511000, tzinfo=timezone.utc)
HOME = (47.175616, 8.951371)
WORK = (47.188301, 8.473701)
FORD_AT_WORK = datetime(2026, 11, 10, 6, 35, 5, 484951, tzinfo=timezone.utc)


def before(seconds, lat=WORK[0] + 0.00004, lon=WORK[1] - 0.00004,
           accuracy=9.0, speed=0.4):
    return {
        "latitude": lat, "longitude": lon,
        "timestamp": (OFF - timedelta(seconds=seconds)).isoformat(),
        "gps_accuracy": accuracy, "speed": speed,
    }


def after(seconds):
    return before(-seconds, lat=WORK[0] + 0.00001, lon=WORK[1])


def current_vehicle(*, sample_at=FORD_AT_WORK, odo=64001, lat=WORK[0],
                    lon=WORK[1], source="ford_gps_module"):
    return {
        "latitude": lat, "longitude": lon,
        "gps_updated_at": sample_at.isoformat() if sample_at else None,
        "gps_timestamp_source": source,
        "odometer": odo,
    }


def pending(*, odo=64001, lat=HOME[0], lon=HOME[1],
            source="coordinates_mismatch", gps_at=None):
    # GPS sensor has received the new Cham coordinates but the tracker
    # temporarily still reports the old Buttikon coordinates. Neither may
    # certify a fresh OEM position at this instant.
    vehicle = {
        "latitude": lat, "longitude": lon,
        "odometer": odo,
        "gps_timestamp_source": source,
        "gps_updated_at": gps_at,
    }
    return parking.pending_ignition_off_parking_snapshot(vehicle, OFF)


class MissingOffParkingR4Tests(unittest.TestCase):
    def test_race_generates_explicitly_untrusted_candidate(self):
        anchor = pending()
        self.assertIsNotNone(anchor)
        self.assertIsNone(anchor["gps_updated_at"])
        self.assertEqual(anchor["source"], "vehicle_tracker_pending_ignition_off")
        self.assertEqual(anchor["ignition_off_at"], OFF.isoformat())
        confirmed, reason = parking.parking_anchor(
            current_vehicle(), anchor, OFF + timedelta(hours=1)
        )
        self.assertIsNone(confirmed)
        self.assertEqual(reason, "stale_ignition_off_unconfirmed")

    def test_no_coordinates_can_be_confirmed_with_odometer(self):
        anchor = pending(lat=None, lon=None)
        self.assertIsNotNone(anchor)
        self.assertIsNone(parking.coordinates(anchor))
        chosen = parking.confirmed_post_off_oem_parking_fix(
            anchor, current_vehicle(), OFF + timedelta(seconds=4),
            route_point=before(3),
        )
        self.assertIsNotNone(chosen)
        self.assertEqual(parking.coordinates(chosen), WORK)

    def test_real_november_tenth_race_from_missing_off_snapshot(self):
        anchor = pending()
        # The newest point was sampled *after* the ignition-OFF edge and must
        # never be used. Select the nearest accurate pre-OFF point instead.
        route_points = [before(13), before(5), before(2), after(0.5), after(2)]
        best = parking.latest_pre_off_route_point(route_points, OFF)
        self.assertIsNotNone(best)
        self.assertEqual(best["timestamp"], before(2)["timestamp"])
        accepted = parking.confirmed_post_off_oem_parking_fix(
            anchor, current_vehicle(), OFF + timedelta(seconds=4),
            route_point=best,
        )
        self.assertIsNotNone(accepted)
        self.assertEqual(accepted["source"], "vehicle_oem_route_confirmed_post_off")
        self.assertEqual(parking.coordinates(accepted), WORK)
        self.assertEqual(accepted["ignition_off_at"], OFF.isoformat())
        self.assertEqual(accepted["odometer"], 64001)
        selected, reason = parking.parking_anchor(
            current_vehicle(), accepted, OFF + timedelta(hours=20)
        )
        self.assertIsNotNone(selected, reason)
        self.assertEqual(parking.coordinates(selected), WORK)

    def test_four_minute_ha_delay_is_not_a_four_minute_old_sample(self):
        anchor = pending()
        result = parking.confirmed_post_off_oem_parking_fix(
            anchor, current_vehicle(), OFF + timedelta(minutes=4),
            route_point=before(2),
        )
        self.assertIsNotNone(result)

    def test_reject_more_than_ten_minutes_after_off(self):
        anchor = pending()
        result = parking.confirmed_post_off_oem_parking_fix(
            anchor, current_vehicle(), OFF + timedelta(minutes=11),
            route_point=before(2),
        )
        self.assertIsNone(result)

    def test_no_route_or_only_post_off_phone_fixes(self):
        anchor = pending()
        self.assertIsNone(parking.latest_pre_off_route_point(
            [after(1), after(5)], OFF
        ))
        self.assertIsNone(parking.confirmed_post_off_oem_parking_fix(
            anchor, current_vehicle(), OFF + timedelta(seconds=4), route_point=None
        ))

    def test_no_valid_accurate_still_phone_fix(self):
        anchor = pending()
        for phone in (before(21), before(2, accuracy=0),
                      before(2, accuracy=70), before(2, speed=7)):
            with self.subTest(phone=phone):
                self.assertIsNone(parking.latest_pre_off_route_point([phone], OFF))
                self.assertIsNone(parking.confirmed_post_off_oem_parking_fix(
                    anchor, current_vehicle(), OFF + timedelta(seconds=4),
                    route_point=phone,
                ))

    def test_reject_unmatched_ford_position_and_non_oem_source(self):
        anchor = pending()
        for wrong_state in (
            current_vehicle(lat=HOME[0], lon=HOME[1]),
            current_vehicle(source="ha_last_updated"),
            current_vehicle(source="coordinates_mismatch"),
            current_vehicle(sample_at=OFF - timedelta(hours=1)),
            current_vehicle(sample_at=OFF + timedelta(minutes=3)),
            current_vehicle(odo=64003.0),
        ):
            with self.subTest(state=wrong_state):
                self.assertIsNone(parking.confirmed_post_off_oem_parking_fix(
                    anchor, wrong_state, OFF + timedelta(minutes=4),
                    route_point=before(2),
                ))

    def test_pending_candidate_remains_untrusted_through_stabilization(self):
        anchor = pending()
        stabilized = parking.stabilize_parking_snapshot(
            anchor, current_vehicle(), OFF + timedelta(seconds=5),
            route_point=before(2), route_points=[before(8), before(2)],
        )
        # The helper must not silently make a pending position trusted without
        # the explicit OEM/route verification path.
        if stabilized is not None:
            self.assertEqual(
                stabilized["source"], "vehicle_tracker_pending_ignition_off"
            )

    def test_pending_cannot_be_promoted_by_proximity_only_refresh(self):
        anchor = pending(
            lat=WORK[0], lon=WORK[1],
            source="ford_gps_module",
            gps_at=(OFF - timedelta(hours=26)).isoformat(),
        )
        refreshed = parking.refresh_parking_snapshot(
            anchor,
            current_vehicle(lat=WORK[0] + 0.00007, lon=WORK[1]),
            OFF + timedelta(seconds=5),
        )
        self.assertIsNone(refreshed)

    def test_pending_helper_does_not_generate_empty_record(self):
        self.assertIsNone(pending(lat=None, lon=None, odo=None))

    def test_source_matching_original_timestamp_is_preserved_when_real(self):
        anchor = pending(source="ford_gps_module", gps_at=(
            OFF - timedelta(hours=10)).isoformat())
        self.assertEqual(anchor["gps_updated_at"], (
            OFF - timedelta(hours=10)).isoformat())
        self.assertIsNotNone(parking.confirmed_post_off_oem_parking_fix(
            anchor, current_vehicle(), OFF + timedelta(seconds=5),
            route_point=before(2),
        ))

    def test_new_code_watches_and_rechecks_both_relevant_events(self):
        coordinator = (ROOT / "custom_components" / "ford_triplog" /
                       "coordinator.py").read_text()
        self.assertIn("pending_ignition_off_parking_snapshot(", coordinator)
        self.assertGreaterEqual(coordinator.count(
            "latest_pre_off_route_point("), 2)
        self.assertIn("self._fordpass_gps_sensor_entity", coordinator)
        self.assertIn("self._schedule_parking_position_save(updated)", coordinator)


if __name__ == "__main__":
    unittest.main()
