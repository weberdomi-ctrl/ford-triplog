"""Regression tests for Beta 5 Release 22's OSRM trip distance gate."""
import importlib.util
from pathlib import Path
import unittest

MODULE = Path(__file__).resolve().parents[1] / "custom_components" / "ford_triplog" / "osrm_policy.py"
SPEC = importlib.util.spec_from_file_location("ford_triplog_osrm_policy", MODULE)
POLICY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(POLICY)
skip = POLICY.skip_osrm_for_short_trip


class TestOsrmMinTripDistance(unittest.TestCase):
    def test_two_kilometre_drive_skips(self):
        self.assertTrue(skip(2.0, 3.0))

    def test_exact_threshold_matches(self):
        self.assertFalse(skip(3.0, 3.0))

    def test_long_drive_matches(self):
        self.assertFalse(skip(53.0, 3.0))

    def test_zero_threshold_disables_gate(self):
        self.assertFalse(skip(0.5, 0))

    def test_custom_threshold(self):
        self.assertTrue(skip(4.5, 5))
        self.assertFalse(skip(4.5, 4))

    def test_missing_invalid_odo_keeps_original_matching(self):
        for value in (None, "unknown", float("nan"), float("inf"), -1):
            with self.subTest(value=value):
                self.assertFalse(skip(value, 3.0))

    def test_zero_distance_is_short(self):
        self.assertTrue(skip(0, 3))


if __name__ == "__main__":
    unittest.main()
