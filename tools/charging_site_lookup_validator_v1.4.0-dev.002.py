"""
Ford Triplog

Charging-site lookup validator.

File: charging_site_lookup_validator_v1.4.0-dev.002.py
Version: 1.4.0-dev.002
Date: 2026-07-23

Purpose:
- Validate the indexed charging-site lookup against a full scan.
- Compare results according to the configured GPS tolerance.
- Count a point as correct when both methods agree that:
  - the same charging site is within tolerance, or
  - no charging site is within tolerance.
- Test exact site coordinates.
- Test random points near existing sites.
- Test random points across the database bounding box.
- Report mismatches and indexed candidate statistics.

Required files:
- charging_site_lookup_v1.4.0-dev.002.py
- charging_sites_ch.json
"""

from __future__ import annotations

import argparse
import importlib.util
import math
import random
import statistics
from pathlib import Path
from types import ModuleType
from typing import Any

FILE_VERSION = "1.4.0-dev.002"
DEFAULT_DATABASE = "charging_sites_ch.json"
DEFAULT_LOOKUP_FILE = "charging_site_lookup_v1.4.0-dev.002.py"
DEFAULT_RANDOM_TESTS = 1000
DEFAULT_NEARBY_TESTS = 1000
DEFAULT_NEARBY_RADIUS_M = 100.0
DEFAULT_TOLERANCE_M = 100.0
DEFAULT_SEED = 140002
EARTH_RADIUS_M = 6_371_000.0


def load_module(file_path: Path) -> ModuleType:
    """Load the lookup implementation directly from its Python file."""

    if not file_path.exists():
        raise FileNotFoundError(f"Lookup file not found: {file_path}")

    spec = importlib.util.spec_from_file_location(
        "ford_triplog_charging_site_lookup",
        file_path,
    )

    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load lookup module: {file_path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def offset_coordinate(
    latitude: float,
    longitude: float,
    distance_m: float,
    bearing_degrees: float,
) -> tuple[float, float]:
    """Move one coordinate by distance and bearing on a spherical Earth."""

    angular_distance = distance_m / EARTH_RADIUS_M
    bearing = math.radians(bearing_degrees)
    latitude_1 = math.radians(latitude)
    longitude_1 = math.radians(longitude)

    latitude_2 = math.asin(
        math.sin(latitude_1) * math.cos(angular_distance)
        + math.cos(latitude_1)
        * math.sin(angular_distance)
        * math.cos(bearing)
    )

    longitude_2 = longitude_1 + math.atan2(
        math.sin(bearing)
        * math.sin(angular_distance)
        * math.cos(latitude_1),
        math.cos(angular_distance)
        - math.sin(latitude_1) * math.sin(latitude_2),
    )

    return math.degrees(latitude_2), math.degrees(longitude_2)


def site_id(site: dict[str, Any] | None) -> str | None:
    """Return a stable identifier for one site."""

    if site is None:
        return None

    return str(site.get("site_id") or site.get("osm_ids") or "unknown")


def full_scan_result(
    lookup: Any,
    module: ModuleType,
    latitude: float,
    longitude: float,
    tolerance_m: float,
) -> dict[str, Any]:
    """Return the exact expected lookup result using all charging sites."""

    nearest_distance = math.inf
    nearest_site: dict[str, Any] | None = None

    for site_latitude, site_longitude, site in lookup._coordinate_sites:
        distance = module.haversine_distance_m(
            latitude,
            longitude,
            site_latitude,
            site_longitude,
        )

        if distance < nearest_distance:
            nearest_distance = distance
            nearest_site = site

    if nearest_site is None:
        raise RuntimeError("No searchable charging site found.")

    found = nearest_distance <= tolerance_m

    return {
        "found": found,
        "distance_m": nearest_distance,
        "site": nearest_site if found else None,
        "nearest_site": nearest_site,
    }


def compare_point(
    lookup: Any,
    module: ModuleType,
    latitude: float,
    longitude: float,
    tolerance_m: float,
    category: str,
) -> dict[str, Any]:
    """Compare indexed lookup and exact full-scan result for one point."""

    expected = full_scan_result(
        lookup,
        module,
        latitude,
        longitude,
        tolerance_m,
    )

    actual = lookup.find(
        latitude,
        longitude,
        tolerance_m=tolerance_m,
    )

    expected_site_id = site_id(expected["site"])
    actual_site_id = site_id(actual["site"])

    found_match = bool(expected["found"]) == bool(actual["found"])
    site_match = expected_site_id == actual_site_id
    match = found_match and site_match

    if match:
        reason = None
    elif not found_match:
        reason = "different_found_state"
    else:
        reason = "different_site_within_tolerance"

    return {
        "category": category,
        "latitude": latitude,
        "longitude": longitude,
        "match": match,
        "reason": reason,
        "expected_found": expected["found"],
        "actual_found": actual["found"],
        "expected_site": expected_site_id,
        "actual_site": actual_site_id,
        "expected_distance_m": expected["distance_m"],
        "actual_distance_m": actual["distance_m"],
        "nearest_site": site_id(expected["nearest_site"]),
        "candidate_count": actual.get("candidate_count", 0),
        "search_mode": actual.get("search_mode", "-"),
    }


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate the indexed charging-site lookup according to a "
            "configured GPS tolerance."
        )
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=Path(DEFAULT_DATABASE),
        help=f"Charging-site database, default: {DEFAULT_DATABASE}",
    )
    parser.add_argument(
        "--lookup-file",
        type=Path,
        default=Path(DEFAULT_LOOKUP_FILE),
        help=f"Lookup implementation, default: {DEFAULT_LOOKUP_FILE}",
    )
    parser.add_argument(
        "--tolerance",
        type=float,
        default=DEFAULT_TOLERANCE_M,
        help=(
            "GPS tolerance in metres used for validation, "
            f"default: {DEFAULT_TOLERANCE_M:g}"
        ),
    )
    parser.add_argument(
        "--random-tests",
        type=int,
        default=DEFAULT_RANDOM_TESTS,
        help=(
            "Random points across the database bounding box, "
            f"default: {DEFAULT_RANDOM_TESTS}"
        ),
    )
    parser.add_argument(
        "--nearby-tests",
        type=int,
        default=DEFAULT_NEARBY_TESTS,
        help=(
            "Random points near existing charging sites, "
            f"default: {DEFAULT_NEARBY_TESTS}"
        ),
    )
    parser.add_argument(
        "--nearby-radius",
        type=float,
        default=DEFAULT_NEARBY_RADIUS_M,
        help=(
            "Maximum distance from an existing site for nearby tests, "
            f"default: {DEFAULT_NEARBY_RADIUS_M:g} m"
        ),
    )
    parser.add_argument(
        "--exact-sites",
        type=int,
        default=0,
        help=(
            "Number of exact site-coordinate tests. "
            "Use 0 to test every searchable site."
        ),
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=DEFAULT_SEED,
        help=f"Random seed, default: {DEFAULT_SEED}",
    )
    parser.add_argument(
        "--show-mismatches",
        type=int,
        default=20,
        help="Maximum mismatches to print, default: 20",
    )

    return parser.parse_args()


def main() -> int:
    args = parse_arguments()

    if args.tolerance <= 0:
        raise ValueError("--tolerance must be greater than zero.")

    if args.random_tests < 0 or args.nearby_tests < 0:
        raise ValueError("Test counts must not be negative.")

    if args.nearby_radius <= 0:
        raise ValueError("--nearby-radius must be greater than zero.")

    if args.exact_sites < 0:
        raise ValueError("--exact-sites must not be negative.")

    if args.show_mismatches < 0:
        raise ValueError("--show-mismatches must not be negative.")

    module = load_module(args.lookup_file)
    lookup = module.ChargingSiteLookup(args.database)
    rng = random.Random(args.seed)

    coordinate_sites = lookup._coordinate_sites
    results: list[dict[str, Any]] = []

    if args.exact_sites == 0:
        exact_sites = coordinate_sites
    else:
        exact_sites = rng.sample(
            coordinate_sites,
            min(args.exact_sites, len(coordinate_sites)),
        )

    for latitude, longitude, _site in exact_sites:
        results.append(
            compare_point(
                lookup,
                module,
                latitude,
                longitude,
                args.tolerance,
                "exact_site",
            )
        )

    for _ in range(args.nearby_tests):
        site_latitude, site_longitude, _site = rng.choice(
            coordinate_sites
        )
        latitude, longitude = offset_coordinate(
            site_latitude,
            site_longitude,
            rng.uniform(0.0, args.nearby_radius),
            rng.uniform(0.0, 360.0),
        )

        results.append(
            compare_point(
                lookup,
                module,
                latitude,
                longitude,
                args.tolerance,
                "nearby_site",
            )
        )

    latitudes = [item[0] for item in coordinate_sites]
    longitudes = [item[1] for item in coordinate_sites]

    for _ in range(args.random_tests):
        latitude = rng.uniform(min(latitudes), max(latitudes))
        longitude = rng.uniform(min(longitudes), max(longitudes))

        results.append(
            compare_point(
                lookup,
                module,
                latitude,
                longitude,
                args.tolerance,
                "bounding_box",
            )
        )

    mismatches = [item for item in results if not item["match"]]
    candidate_counts = [item["candidate_count"] for item in results]

    category_totals: dict[str, int] = {}
    category_errors: dict[str, int] = {}

    true_hits = 0
    true_misses = 0

    for item in results:
        category = item["category"]
        category_totals[category] = category_totals.get(category, 0) + 1

        if item["expected_found"]:
            true_hits += 1
        else:
            true_misses += 1

        if not item["match"]:
            category_errors[category] = (
                category_errors.get(category, 0) + 1
            )

    accuracy = (
        (len(results) - len(mismatches)) / len(results) * 100.0
        if results
        else 100.0
    )

    print("Ford Triplog Charging Site Lookup Validator")
    print(f"File version:          {FILE_VERSION}")
    print()
    print(f"Database:              {args.database}")
    print(f"Lookup file:           {args.lookup_file}")
    print(f"Charging sites:        {lookup.site_count}")
    print(f"Searchable sites:      {lookup.searchable_site_count}")
    print(f"Geohash precision:     {lookup.geohash_precision}")
    print(f"Index cells:           {lookup.index_cell_count}")
    print(f"GPS tolerance:         {args.tolerance:g} m")
    print(f"Random seed:           {args.seed}")
    print()
    print("Tests")
    print("-----")
    print(f"Exact site points:     {category_totals.get('exact_site', 0)}")
    print(f"Nearby site points:    {category_totals.get('nearby_site', 0)}")
    print(f"Bounding-box points:   {category_totals.get('bounding_box', 0)}")
    print(f"Total tests:           {len(results)}")
    print()
    print("Expected full-scan results")
    print("--------------------------")
    print(f"Sites within tolerance:{true_hits:7}")
    print(f"No site in tolerance:  {true_misses:7}")
    print()
    print("Validation results")
    print("------------------")
    print(f"Matches:               {len(results) - len(mismatches)}")
    print(f"Mismatches:            {len(mismatches)}")
    print(f"Accuracy:              {accuracy:.4f}%")

    if candidate_counts:
        print()
        print("Indexed candidates")
        print("------------------")
        print(f"Minimum:               {min(candidate_counts)}")
        print(f"Maximum:               {max(candidate_counts)}")
        print(f"Average:               {statistics.mean(candidate_counts):.2f}")
        print(f"Median:                {statistics.median(candidate_counts):.2f}")

    print()
    print("Mismatches by category")
    print("----------------------")

    for category in ("exact_site", "nearby_site", "bounding_box"):
        print(
            f"{category:20} "
            f"{category_errors.get(category, 0):6} / "
            f"{category_totals.get(category, 0)}"
        )

    if mismatches and args.show_mismatches > 0:
        print()
        print("Mismatch details")
        print("----------------")

        for number, item in enumerate(
            mismatches[:args.show_mismatches],
            start=1,
        ):
            print(f"{number}. Category:       {item['category']}")
            print(
                "   Coordinates:    "
                f"{item['latitude']:.7f}, "
                f"{item['longitude']:.7f}"
            )
            print(f"   Reason:         {item['reason']}")
            print(f"   Expected found: {item['expected_found']}")
            print(f"   Actual found:   {item['actual_found']}")
            print(f"   Expected site:  {item['expected_site'] or '-'}")
            print(f"   Actual site:    {item['actual_site'] or '-'}")
            print(f"   Nearest site:   {item['nearest_site'] or '-'}")
            print(
                "   Expected dist.: "
                f"{item['expected_distance_m']:.1f} m"
            )
            print(
                "   Actual dist.:   "
                f"{item['actual_distance_m']:.1f} m"
            )
            print(f"   Search mode:    {item['search_mode']}")
            print(f"   Candidates:     {item['candidate_count']}")
            print()

    return 1 if mismatches else 0


if __name__ == "__main__":
    raise SystemExit(main())
