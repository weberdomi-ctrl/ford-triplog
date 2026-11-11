"""Beta 7 R5: VIN GPS JSON and device_tracker disagree at ignition OFF.

Reproduces the 2026-11-11 Buttikon -> Cham arrival without Home Assistant.
Run: python -m unittest discover -s test -p 'test_independent_ford_gps_parking_beta7_r5.py' -v
"""
from datetime import datetime, timedelta
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import SimpleNamespace
import ast
import unittest

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "custom_components" / "ford_triplog"


def _load(name, filename):
    spec = spec_from_file_location(name, COMPONENT / filename)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gps = _load("ford_gps_r5", "fordpass_gps_timestamp.py")
parking = _load("parking_r5", "trip_start_position.py")

# Test the coordinator's actual method without importing Home Assistant.
coordinator_source = (COMPONENT / "coordinator.py").read_text(encoding="utf-8")
coordinator_tree = ast.parse(coordinator_source)
cls = next(
    node for node in coordinator_tree.body
    if isinstance(node, ast.ClassDef) and node.name == "FordTriplogCoordinator"
)
method = next(
    node for node in cls.body
    if isinstance(node, ast.FunctionDef)
    and node.name == "_confirmed_post_off_parking_fix"
)
function_source = ast.Module(body=[method], type_ignores=[])
namespace = {
    "Any": object, "datetime": datetime,
    "confirmed_post_off_oem_parking_fix": parking.confirmed_post_off_oem_parking_fix,
    "read_independent_oem_gps_position": gps.read_independent_oem_gps_position,
}
exec(compile(function_source, "<R5 parking coordinator method>", "exec"), namespace)
confirm_from_coordinator = namespace["_confirmed_post_off_parking_fix"]

OFF = datetime.fromisoformat("2026-11-11T07:32:02.435853+01:00")
OEM = "2026-11-11T06:32:01.012268Z"
HOME = (47.175637, 8.951383)
CHAM = (47.188304, 8.473648)


def gps_attrs(*, lat=CHAM[0], lon=CHAM[1], sampled_at=OEM):
    return {
        "value": {"location": {"lat": lat, "lon": lon, "alt": 0.0}},
        "gpsModuleTimestamp": sampled_at,
        "updateTime": "2026-11-11T06:31:58Z",
    }


def phone(*, seconds=3, lat=47.188449, lon=8.473054,
          accuracy=10.0, speed=0.2):
    return {
        "latitude": lat, "longitude": lon,
        "timestamp": (OFF - timedelta(seconds=seconds)).isoformat(),
        "gps_accuracy": accuracy, "speed": speed,
    }


def vehicle(*, odometer=64106):
    # As observed: tracker still reports Buttikon while the VIN GPS JSON is Cham.
    return {
        "latitude": HOME[0], "longitude": HOME[1],
        "odometer": odometer,
        "gps_timestamp_source": "coordinates_mismatch",
        "gps_updated_at": None,
    }


def coordinator(attributes=None, sensor_state="47.188304"):
    gps_sensor = SimpleNamespace(
        state=sensor_state,
        attributes=attributes if attributes is not None else gps_attrs(),
    )
    return SimpleNamespace(
        _fordpass_gps_sensor_entity="sensor.fordpass_wf0rpbef5rrl15460_gps",
        hass=SimpleNamespace(states={
            "sensor.fordpass_wf0rpbef5rrl15460_gps": gps_sensor,
        }),
    )


def pending():
    return parking.pending_ignition_off_parking_snapshot(vehicle(), OFF)


class IndependentFordGpsParkingR5Tests(unittest.TestCase):
    def call(self, sensor=None, route=None, *, at=None, state=None,
             anchor=None):
        return confirm_from_coordinator(
            sensor or coordinator(),
            anchor or pending(),
            state or vehicle(),
            at=at or OFF + timedelta(minutes=4),
            route_point=route if route is not None else phone(),
        )

    def test_real_november_eleventh_race_four_minutes_after_off(self):
        result = self.call()
        self.assertIsNotNone(result)
        self.assertEqual(parking.coordinates(result), CHAM)
        self.assertEqual(result["odometer"], 64106)
        self.assertEqual(result["ignition_off_at"], OFF.isoformat())
        self.assertEqual(result["source"], "ford_gps_sensor_route_confirmed_post_off")
        self.assertEqual(result["gps_updated_at"], datetime.fromisoformat(
            OEM.replace("Z", "+00:00")
        ).isoformat())
        origin, reason = parking.parking_anchor(
            {"latitude": CHAM[0], "longitude": CHAM[1], "odometer": 64106},
            result, OFF + timedelta(hours=9),
        )
        self.assertIsNotNone(origin, reason)

    def test_independent_candidate_has_oem_time_and_not_ha_time(self):
        self.assertIsNone(gps.resolve_oem_gps_timestamp(
            HOME[0], HOME[1], gps_attrs(), OFF,
        )[0])
        sampled = gps.read_independent_oem_gps_position(gps_attrs(), OFF)
        self.assertEqual(sampled["gps_timestamp_source"], "ford_gps_module")
        self.assertEqual(parking.coordinates(sampled), CHAM)

    def test_missing_or_invalid_sensor_timestamp_does_not_promote(self):
        for bad in (None, "", "2026-11-11T08:32:01Z", "2026-11-10T06:32:01Z"):
            with self.subTest(sampled_at=bad):
                attrs = gps_attrs(sampled_at=bad)
                attrs["updateTime"] = bad
                self.assertIsNone(self.call(coordinator(attrs)))

    def test_oem_update_time_is_an_explicit_fallback(self):
        attrs = gps_attrs(sampled_at=None)
        result = self.call(coordinator(attrs))
        self.assertIsNotNone(result)
        self.assertEqual(result["gps_updated_at"], "2026-11-11T06:31:58+00:00")

    def test_rejects_unverified_or_implausible_phone_fixes(self):
        for wrong in (
            phone(seconds=-1),
            phone(seconds=21),
            phone(accuracy=70),
            phone(speed=7),
            phone(lat=47.2, lon=8.4),
        ):
            with self.subTest(phone=wrong):
                self.assertIsNone(self.call(route=wrong))

    def test_rejects_unrelated_oem_position_and_bad_odometer(self):
        self.assertIsNone(self.call(coordinator(gps_attrs(lat=47.2, lon=8.4))))
        self.assertIsNone(self.call(state=vehicle(odometer=64108)))

    def test_rejects_when_arriving_too_late(self):
        self.assertIsNone(self.call(at=OFF + timedelta(minutes=11)))

    def test_never_promotes_unknown_sensor_or_trusted_anchor(self):
        self.assertIsNone(self.call(coordinator(sensor_state="unknown")))
        trusted = parking.parking_snapshot({
            "latitude": HOME[0], "longitude": HOME[1],
            "odometer": 64106,
            "gps_updated_at": (OFF - timedelta(seconds=1)).isoformat(),
        }, OFF)
        self.assertIsNotNone(trusted)
        self.assertIsNone(self.call(anchor=trusted))

    def test_rejects_missing_gps_json_or_invalid_coordinates(self):
        self.assertIsNone(gps.read_independent_oem_gps_position({}, OFF))
        self.assertIsNone(gps.read_independent_oem_gps_position(
            gps_attrs(lat=0, lon=0), OFF,
        ))
        self.assertIsNone(self.call(coordinator(attributes={"value": {}})))

    def test_coordinator_uses_fallback_for_refresh_and_smart_trip(self):
        self.assertGreaterEqual(coordinator_source.count(
            "self._confirmed_post_off_parking_fix("), 2)
        self.assertIn("read_independent_oem_gps_position(", coordinator_source)
        self.assertIn("resolve_oem_gps_timestamp(\n", coordinator_source)
        self.assertIn("gps_sensor_entity_id(config.get(CONF_TRACKER))",
                      coordinator_source)
        self.assertIn("latest_pre_off_route_point(recent_points, off_at)",
                      coordinator_source)
        self.assertIn("latest_pre_off_route_point(route_points, off_at)",
                      coordinator_source)


if __name__ == "__main__":
    unittest.main()
