#!/usr/bin/env python3
"""Build an offline Ford Triplog charging-station database."""
from __future__ import annotations
import argparse
import gzip
import json
import logging
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from countries import get_country
from geohash import encode as geohash_encode
from normalizer import normalize_station
from overpass import DEFAULT_URL, build_query, fetch

LOGGER = logging.getLogger("ford_triplog_db_builder")
SCHEMA_VERSION = 1
GEOHASH_PRECISION = 5

def load_input(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, dict) or not isinstance(data.get("elements"), list):
        raise ValueError("Input file is not a valid Overpass JSON response")
    return data

def build_database(country_code: str, elements: list[dict[str, Any]]) -> dict[str, Any]:
    cells: dict[str, list[dict[str, Any]]] = defaultdict(list)
    skipped = 0
    for element in elements:
        station = normalize_station(element)
        if station is None:
            skipped += 1
            continue
        cell = geohash_encode(float(station["lat"]), float(station["lon"]), GEOHASH_PRECISION)
        cells[cell].append(station)
    for stations in cells.values():
        stations.sort(key=lambda item: item["id"])
    station_count = sum(len(items) for items in cells.values())
    return {
        "schema": SCHEMA_VERSION,
        "country": country_code,
        "generated": datetime.now(UTC).isoformat(),
        "source": "OpenStreetMap",
        "license": "ODbL-1.0",
        "geohash_precision": GEOHASH_PRECISION,
        "station_count": station_count,
        "cell_count": len(cells),
        "skipped_count": skipped,
        "cells": dict(sorted(cells.items())),
    }

def write_database(database: dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(database, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    with output_path.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as gz:
            gz.write(encoded)

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a Ford Triplog offline charging database")
    parser.add_argument("country_positional", nargs="?", help="ISO alpha-2 country code")
    parser.add_argument("--country", help="ISO alpha-2 country code")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--input", type=Path, help="Use stored Overpass JSON")
    parser.add_argument("--save-raw", type=Path)
    parser.add_argument("--overpass-url", default=DEFAULT_URL)
    parser.add_argument("--timeout", type=int, default=360)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args()

def main() -> int:
    args = parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s: %(message)s")
    try:
        country = get_country(args.country or args.country_positional or "CH")
        output = args.output or (
            Path(__file__).resolve().parents[1]
            / "custom_components" / "ford_triplog" / "charging_database"
            / f"{country.code.lower()}.json.gz"
        )
        if args.input:
            raw = load_input(args.input)
            LOGGER.info("Loaded raw Overpass data from %s", args.input)
        else:
            raw = fetch(args.overpass_url, build_query(country.osm_iso_code), args.timeout, args.retries)
        if args.save_raw:
            args.save_raw.parent.mkdir(parents=True, exist_ok=True)
            args.save_raw.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
        database = build_database(country.code, raw["elements"])
        write_database(database, output)
        LOGGER.info("Created %s with %s stations in %s cells (%.2f MiB)", output, database["station_count"], database["cell_count"], output.stat().st_size / 1024 / 1024)
        return 0
    except (OSError, ValueError, RuntimeError) as err:
        LOGGER.error("Database build failed: %s", err)
        return 1

if __name__ == "__main__":
    sys.exit(main())
