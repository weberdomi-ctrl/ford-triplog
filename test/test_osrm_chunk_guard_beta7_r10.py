"""Beta 7 R10 regression: reject false OSRM chunk stitching on Nov 15.

Run: python -m unittest discover -s test -p 'test_osrm_chunk_guard_beta7_r10.py' -v
The actual OSRM client methods are compiled from AST to avoid Home Assistant
imports. Pure route-quality/matching modules are loaded from the repository.
"""

import ast
import asyncio
from datetime import datetime, timedelta, timezone
import importlib.util
import logging
from pathlib import Path
import sys
import types
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "custom_components" / "ford_triplog"
PKG = "_ford_triplog_osrm_r10_test"
package = types.ModuleType(PKG)
package.__path__ = [str(COMPONENT)]
sys.modules[PKG] = package


def load(name):
    spec = importlib.util.spec_from_file_location(
        PKG + "." + name, COMPONENT / (name + ".py")
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[PKG + "." + name] = module
    spec.loader.exec_module(module)
    return module


quality = load("route_quality")
guard = load("osrm_geometry_guard")
matching = load("route_matching")


class FakeOSRMResponseError(Exception):
    pass


source = (COMPONENT / "osrm_client.py").read_text(encoding="utf-8")
tree = ast.parse(source)
original = next(
    node for node in tree.body if isinstance(node, ast.ClassDef)
    and node.name == "FordTriplogOSRMClient"
)
required = {
    "async_match",
    "_build_match_chunks",
    "_normalize_geometry_coordinates",
    "_coordinates_equal",
    "_find_stitch_index",
    "_geometry_distance_m",
}
methods = [
    node for node in original.body
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    and node.name in required
]
assert {m.name for m in methods} == required
module = ast.Module(
    body=[
        ast.ImportFrom(
            module="__future__", names=[ast.alias(name="annotations")],
            level=0
        ),
        ast.ClassDef(
            name="OSRMClientUnderTest", bases=[], keywords=[],
            body=methods, decorator_list=[]
        ),
    ],
    type_ignores=[],
)
ns = {
    "OSRM_MATCH_CHUNK_SIZE": 90,
    "OSRM_MATCH_CHUNK_OVERLAP": 5,
    "FordTriplogOSRMResponseError": FakeOSRMResponseError,
    "FordTriplogOSRMMatchResult": types.SimpleNamespace,
    "confidence_valid": quality.confidence_valid,
    "oversized_osrm_step_m": guard.oversized_osrm_step_m,
    "_LOGGER": logging.getLogger("ford_triplog_r10_regression"),
}
exec(
    compile(ast.fix_missing_locations(module), "<actual OSRM client methods>", "exec"),
    ns
)
OSRMClientUnderTest = ns["OSRMClientUnderTest"]


def test_points(count=135):
    base = 1763204075
    return [
        (47.204132 - i * 0.000008, 9.022385 - i * 0.000008, base + i)
        for i in range(count)
    ]


def result_for(points, confidence, *, fixed_position=None, jump=False):
    if fixed_position is not None:
        lat, lon = fixed_position
        coords = [[lon + i * 0.00001, lat] for i in range(len(points))]
    else:
        coords = [[lon, lat] for lat, lon, _ in points]
    if jump:
        coords[-1] = [8.980933, 47.178170]
    locations = tuple(tuple(coordinate) for coordinate in coords)
    return types.SimpleNamespace(
        geometry={"type": "LineString", "coordinates": coords},
        distance_m=1000.0,
        duration_s=200.0,
        confidence=confidence,
        matched_tracepoints=len(points),
        unmatched_tracepoints=0,
        tracepoint_matched=tuple(True for _ in points),
        tracepoint_locations=locations,
    )


def client_with_match(side_effect):
    client = OSRMClientUnderTest()
    client._normalize_points = lambda points: points
    client._async_match_normalized = AsyncMock(side_effect=side_effect)
    return client


class OSRMChunkRegressionTests(IsolatedAsyncioTestCase):
    async def test_nov_15_terrible_first_chunk_cannot_hide_in_average(self):
        calls = 0

        async def match(chunk):
            nonlocal calls
            calls += 1
            return result_for(chunk, 0.002879 if calls == 1 else 0.983847)

        client = client_with_match(match)
        with self.assertRaisesRegex(
            FakeOSRMResponseError, "chunk 1/2 low confidence"
        ):
            await client.async_match(test_points())
        self.assertEqual(calls, 1)

    async def test_good_overlapping_chunks_still_merge(self):
        client = client_with_match(
            lambda chunk: result_for(chunk, 0.98)
        )
        result = await client.async_match(test_points())
        self.assertEqual(result.geometry["type"], "LineString")
        self.assertEqual(result.matched_tracepoints, 135)
        self.assertEqual(result.unmatched_tracepoints, 0)
        self.assertIsNone(guard.oversized_osrm_step_m(result.geometry))
        self.assertAlmostEqual(result.confidence, 0.98)

    async def test_good_chunks_with_distant_stitch_are_rejected(self):
        calls = 0

        def match(chunk):
            nonlocal calls
            calls += 1
            return result_for(
                chunk, 0.98,
                fixed_position=(
                    (47.204514, 9.023784) if calls == 1
                    else (47.178170, 8.980933)
                ),
            )

        client = client_with_match(match)
        with self.assertRaisesRegex(
            FakeOSRMResponseError, "geometry jump"
        ):
            await client.async_match(test_points())
        self.assertEqual(calls, 2)

    async def test_large_jump_inside_chunk_is_rejected(self):
        client = client_with_match(
            lambda chunk: result_for(chunk, 0.98, jump=True)
        )
        with self.assertRaisesRegex(FakeOSRMResponseError, "geometry jump"):
            await client.async_match(test_points())


class StoredGeometryRegressionTests(TestCase):
    @staticmethod
    def fake_route():
        point = lambda lat, lon, time: {
            "latitude": lat, "longitude": lon,
            "gps_accuracy": 5, "speed": 12, "timestamp": time,
        }
        return {
            "osrm_match_status": "complete",
            "points": [
                point(47.204514, 9.023784, "2026-11-15T11:55:00+01:00"),
                point(47.204500, 9.023740, "2026-11-15T11:55:01+01:00"),
                point(47.178190, 8.980980, "2026-11-15T12:01:00+01:00"),
                point(47.178170, 8.980933, "2026-11-15T12:01:01+01:00"),
            ],
            "matched_route": {
                "provider": "osrm",
                "confidence": 0.3298683333333334,
                "coverage_status": "complete",
                "geometry": {
                    "type": "LineString",
                    "coordinates": [
                        [9.023784, 47.204514],
                        [8.980933, 47.178170],
                    ],
                },
            },
        }

    def test_recorded_nov_15_gap_is_over_four_km(self):
        route = self.fake_route()
        leap = guard.largest_osrm_step_m(
            route["matched_route"]["geometry"]
        )
        self.assertGreater(leap, 4_300)
        self.assertLess(leap, 4_500)

    def test_existing_archived_osrm_match_is_rejected_on_read(self):
        route = self.fake_route()
        valid, status, reason = matching.evaluate_stored_osrm_match(route)
        self.assertFalse(valid)
        self.assertEqual(status, "rejected")
        self.assertIn("unobserved_osrm_geometry_jump", reason)

    def test_archived_gap_displays_separate_raw_sections(self):
        route = self.fake_route()
        geo, source, status, reason = matching.choose_display_geometry(route)
        self.assertEqual(source, "raw")
        self.assertEqual(geo["type"], "MultiLineString")
        self.assertEqual(len(geo["coordinates"]), 2)

    def test_independent_multiline_segments_do_not_count_as_jump(self):
        geo = {
            "type": "MultiLineString",
            "coordinates": [
                [[9.023784, 47.204514], [9.023750, 47.204500]],
                [[8.980933, 47.178170], [8.980900, 47.178150]],
            ]
        }
        self.assertIsNone(guard.oversized_osrm_step_m(geo))

    def test_single_leg_oversized_hop_is_rejected(self):
        points = [
            {"latitude": 47.204514, "longitude": 9.023784},
            {"latitude": 47.178170, "longitude": 8.980933},
        ]
        bad = types.SimpleNamespace(
            confidence=0.99, distance_m=5000.0,
            geometry=self.fake_route()["matched_route"]["geometry"],
            unmatched_tracepoints=0,
        )
        with self.assertRaisesRegex(matching.RouteMatchRejected, "geometry_jump"):
            matching.validate_osrm_result(points, bad)


if __name__ == "__main__":
    import unittest
    unittest.main()
