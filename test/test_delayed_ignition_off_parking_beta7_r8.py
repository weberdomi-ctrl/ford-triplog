"""R8 regression: Ford GPS is correct at ignition OFF, but phone GPS is 34s old.

Pure Python: python -m unittest discover -s test -p 'test_delayed_ignition_off_parking_beta7_r8.py' -v
The Nov 12 Cham field report had a Ford tracker/GPS race at OFF, a module
fix just before OFF and a recorded phone tail 34 seconds earlier.
"""
from datetime import datetime, timedelta, timezone
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "custom_components" / "ford_triplog"


def load_helper(name, filename):
    spec = spec_from_file_location(name, COMPONENT / filename)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


parking = load_helper("parking_r8", "trip_start_position.py")
ford_gps = load_helper("ford_gps_r8", "fordpass_gps_timestamp.py")

# Actual Ford GPS timestamps and coordinates at work on 2026-11-12.
OFF = datetime(2026, 11, 12, 11, 58, 5, 525000, tzinfo=timezone.utc)
OEM_AT = datetime(2026, 11, 12, 11, 58, 4, 334652, tzinfo=timezone.utc)
WILEN = (47.196256, 8.753345)
CHAM = (47.18831, 8.473664)
PHONE = (47.188474, 8.473061)


def phone(seconds_before=34.09, *, lat=PHONE[0], lon=PHONE[1],
          accuracy=3.0, speed=0.5):
    return {
        "timestamp": (OFF - timedelta(seconds=seconds_before)).isoformat(),
        "latitude": lat, "longitude": lon,
        "gps_accuracy": accuracy, "speed": speed,
    }


def pending():
    return parking.pending_ignition_off_parking_snapshot({
        "latitude": WILEN[0], "longitude": WILEN[1],
        "odometer": 64211.0, "gps_timestamp_source": "coordinates_mismatch",
        "gps_updated_at": None,
    }, OFF)


def ford(*, at=OEM_AT, source="ford_gps_module",
         lat=CHAM[0], lon=CHAM[1], odo=64211.0):
    return {
        "gps_updated_at": at.isoformat(),
        "gps_timestamp_source": source,
        "latitude": lat, "longitude": lon,
        "odometer": odo,
    }


def confirm(sample=None, route=None, *, allow_delayed_phone=True, delay=240):
    return parking.confirmed_post_off_oem_parking_fix(
        pending(), sample or ford(), OFF + timedelta(seconds=delay),
        route_point=phone() if route is None else route,
        allow_delayed_phone=allow_delayed_phone,
    )


class R8DelayedParkingTests(unittest.TestCase):
    def test_nov_12_cham_race_recovers_34_second_old_route(self):
        # The last recorded route fix was 12:57:31, ignition OFF 12:58:05.
        # The parked Ford GPS module was sampled at 12:58:04.
        self.assertGreater(
            parking.distance_meters(WILEN, CHAM), 20000
        )
        self.assertLess(
            parking.distance_meters(PHONE, CHAM), 100
        )
        points = [phone(48), phone(34.09), phone(-2)]
        selected = parking.latest_pre_off_route_point(
            points, OFF,
            max_age_seconds=parking.PARK_OEM_PHONE_MAX_AGE_SECONDS,
        )
        self.assertEqual(selected["timestamp"], phone(34.09)["timestamp"])
        attrs = {
            "value": {"location": {
                "lat": CHAM[0], "lon": CHAM[1], "alt": 0.0,
            }},
            "updateTime": "2026-11-12T11:58:01Z",
            "gpsModuleTimestamp": "2026-11-12T11:58:04.334652Z",
        }
        candidate = ford_gps.read_independent_oem_gps_position(
            attrs, OFF + timedelta(seconds=240),
        )
        self.assertEqual(candidate["gps_timestamp_source"], "ford_gps_module")
        candidate["odometer"] = 64211.0
        accepted = confirm(candidate, selected)
        self.assertIsNotNone(accepted)
        self.assertEqual(accepted["source"], "vehicle_oem_route_confirmed_post_off")
        self.assertEqual(parking.coordinates(accepted), CHAM)
        self.assertEqual(accepted["odometer"], 64211.0)
        next_start, reason = parking.parking_anchor(
            ford(), accepted, OFF + timedelta(hours=2)
        )
        self.assertIsNotNone(next_start, reason)
        self.assertEqual(parking.coordinates(next_start), CHAM)

    def test_normal_20_second_validation_is_unchanged(self):
        self.assertIsNone(parking.latest_pre_off_route_point([phone()], OFF))
        self.assertIsNone(confirm(allow_delayed_phone=False))

    def test_delayed_phone_selection_skips_more_recent_moving_fix(self):
        chosen = parking.latest_pre_off_route_point(
            [phone(44, speed=0.4), phone(32, speed=4.0)],
            OFF, max_age_seconds=parking.PARK_OEM_PHONE_MAX_AGE_SECONDS,
        )
        self.assertEqual(chosen["timestamp"], phone(44)["timestamp"])
        self.assertIsNotNone(confirm(route=chosen))

    def test_extended_window_requires_true_module_timestamp(self):
        self.assertIsNone(confirm(ford(source="ford_update_time")))
        self.assertIsNone(confirm(ford(source="coordinates_mismatch")))
        self.assertIsNone(confirm(ford(
            at=OFF - timedelta(seconds=16)
        )))
        self.assertIsNone(confirm(ford(
            at=OFF + timedelta(seconds=16)
        )))

    def test_extended_window_rejects_stale_or_post_off_phone(self):
        self.assertIsNone(parking.latest_pre_off_route_point(
            [phone(61), phone(-1)], OFF,
            max_age_seconds=parking.PARK_OEM_PHONE_MAX_AGE_SECONDS,
        ))
        self.assertIsNone(confirm(route=phone(61)))
        self.assertIsNone(confirm(route=phone(-1)))
        self.assertIsNone(confirm(route={}))

    def test_extended_window_rejects_untrusted_phone_quality(self):
        for route in (
            phone(accuracy=0),
            phone(accuracy=26),
            phone(speed=2.5),
            phone(speed=None),
            phone(accuracy=None),
        ):
            with self.subTest(route=route):
                self.assertIsNone(confirm(route=route))

    def test_extended_window_requires_phone_within_100m(self):
        self.assertIsNone(confirm(
            route=phone(lat=CHAM[0] + 0.00115, lon=CHAM[1]),
        ))
        self.assertIsNone(confirm(
            route=phone(lat=WILEN[0], lon=WILEN[1]),
        ))

    def test_odometer_and_confirmation_window_must_be_stable(self):
        self.assertIsNone(confirm(ford(odo=64213.0)))
        self.assertIsNone(confirm(delay=601))

    def test_old_oem_sample_still_rejected(self):
        self.assertIsNone(confirm(
            ford(at=OFF - timedelta(minutes=3))
        ))

    def test_actual_coordinator_calls_extended_validation_in_both_paths(self):
        code = (COMPONENT / "coordinator.py").read_text()
        self.assertGreaterEqual(code.count("allow_delayed_phone=True"), 2)
        self.assertGreaterEqual(code.count(
            "max_age_seconds=PARK_OEM_PHONE_MAX_AGE_SECONDS"
        ), 2)
        self.assertIn(
            "Post-OFF OEM parking not confirmed", code
        )


if __name__ == "__main__":
    unittest.main()
