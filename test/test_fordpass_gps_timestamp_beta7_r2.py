"""Beta 7 R2: OEM FordPass GPS timestamps and stale parking snapshots."""
from datetime import datetime, timedelta, timezone
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "ford_triplog"


def load(name, filename):
    spec = spec_from_file_location(name, ROOT / filename)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gps = load("test_ford_gps_timestamp_r2", "fordpass_gps_timestamp.py")
parking = load("test_ford_parking_r2", "trip_start_position.py")

NOW = datetime(2026, 11, 9, 12, 8, tzinfo=timezone.utc)
LAT, LON = 47.188301, 8.473695
ACTUAL = (LAT + 0.025, LON + 0.040)


def sensor(module_time="2026-11-09T06:33:50.245613Z", update_time="2026-11-09T06:33:48Z",
           lat=LAT, lon=LON):
    return {
        "value": {"location": {"lat": lat, "lon": lon}},
        "gpsModuleTimestamp": module_time, "updateTime": update_time,
    }


def route_point(age, latitude=ACTUAL[0], longitude=ACTUAL[1]):
    return {
        "latitude": latitude, "longitude": longitude,
        "timestamp": (NOW - timedelta(seconds=age)).isoformat(),
        "gps_accuracy": 7.0, "speed": 0.2,
    }


class FordGpsTimestampTests(unittest.TestCase):
    def test_vin_based_mapping_and_other_trackers_unchanged(self):
        self.assertEqual(
            gps.gps_sensor_entity_id("device_tracker.fordpass_wf0rpbef5rrl15460_tracker"),
            "sensor.fordpass_wf0rpbef5rrl15460_gps",
        )
        self.assertIsNone(gps.gps_sensor_entity_id("device_tracker.ford_explorer"))
        self.assertIsNone(gps.gps_sensor_entity_id("device_tracker.fordpass_other_tracker_2"))

    def test_actual_ha_example_is_five_hours_old(self):
        sampled, source = gps.resolve_oem_gps_timestamp(LAT, LON, sensor(), NOW)
        self.assertEqual(source, "ford_gps_module")
        self.assertEqual(sampled.isoformat(), "2026-11-09T06:33:50.245613+00:00")
        self.assertGreater((NOW - sampled).total_seconds(), 5 * 3600)

    def test_update_time_fallback_without_module_time(self):
        sampled, source = gps.resolve_oem_gps_timestamp(
            LAT, LON, sensor(module_time=None), NOW
        )
        self.assertEqual(source, "ford_update_time")
        self.assertEqual(sampled.isoformat(), "2026-11-09T06:33:48+00:00")

    def test_pairing_requires_matching_coordinates(self):
        for latitude, longitude in ((LAT + 0.01, LON), (None, LON), (0, 0)):
            with self.subTest(pos=(latitude, longitude)):
                sampled, reason = gps.resolve_oem_gps_timestamp(
                    LAT, LON, sensor(lat=latitude, lon=longitude), NOW
                )
                self.assertIsNone(sampled)
                self.assertIn(reason, ("coordinates_mismatch", "coordinates_unavailable"))

    def test_no_fresh_ha_fallback_for_invalid_or_future_sensor_timestamp(self):
        for values in (
            sensor(module_time="bad", update_time="bad"),
            sensor(module_time="2026-11-09T13:08:00Z", update_time=None),
            {"value": {"location": {"lat": LAT, "lon": LON}}},
        ):
            with self.subTest(values=values):
                sampled, reason = gps.resolve_oem_gps_timestamp(LAT, LON, values, NOW)
                self.assertIsNone(sampled)
                self.assertEqual(reason, "oem_timestamp_unavailable")

    def test_ignition_off_stale_position_remains_untrusted(self):
        state = {
            "latitude": LAT, "longitude": LON, "odometer": 63843,
            "gps_updated_at": sensor()["gpsModuleTimestamp"],
        }
        self.assertIsNone(parking.parking_snapshot(state, NOW))
        provisional = parking.parking_snapshot(state, NOW, allow_stale=True)
        self.assertIsNotNone(provisional)
        self.assertEqual(provisional["source"], "vehicle_tracker_stale_ignition_off")
        anchor, why = parking.parking_anchor(state, provisional, NOW + timedelta(hours=1))
        self.assertIsNone(anchor)
        self.assertEqual(why, "stale_ignition_off_unconfirmed")

    def test_stale_ignition_off_requires_two_preoff_stationary_points(self):
        state = {
            "latitude": LAT, "longitude": LON, "odometer": 63843,
            "gps_updated_at": sensor()["gpsModuleTimestamp"],
        }
        provisional = parking.parking_snapshot(state, NOW, allow_stale=True)
        current = dict(state)
        self.assertIsNone(parking.stabilize_parking_snapshot(
            provisional, current, NOW + timedelta(seconds=10),
            route_point=route_point(3), route_points=[route_point(3)]
        ))
        result = parking.stabilize_parking_snapshot(
            provisional, current, NOW + timedelta(seconds=10),
            route_point=route_point(3), route_points=[route_point(12), route_point(3)]
        )
        self.assertIsNotNone(result)
        self.assertEqual(result["source"], "parked_route_fix_corrob_pre_off")
        self.assertEqual(parking.coordinates(result), ACTUAL)
        # OEM still has the old position; the proven endpoint must survive.
        anchor, why = parking.parking_anchor(
            {"latitude": ACTUAL[0], "longitude": ACTUAL[1], "odometer": 63843},
            result, NOW + timedelta(hours=12)
        )
        self.assertIsNotNone(anchor, why)

    def test_stale_snapshot_older_than_day_is_rejected(self):
        state = {
            "latitude": LAT, "longitude": LON, "odometer": 63843,
            "gps_updated_at": (NOW - timedelta(days=2)).isoformat(),
        }
        self.assertIsNone(parking.parking_snapshot(state, NOW, allow_stale=True))

    def test_coordinator_reads_sensor_and_handles_sensor_event(self):
        code = (ROOT / "coordinator.py").read_text()
        self.assertIn("resolve_oem_gps_timestamp(", code)
        self.assertIn("self._fordpass_gps_sensor_entity", code)
        self.assertIn("gps_timestamp_source", code)
        self.assertIn("fresh_gps_state or self._read_vehicle_state()", code)


if __name__ == "__main__":
    unittest.main()
