"""
Ford Triplog

Diagnostic inspector for the charging site database.

File: charging_site_inspector_v1.4.0-dev.001.py
Version: 1.4.0-dev.001
Date: 2026-07-23

Purpose:
- Inspect charging_sites_ch.json.
- Filter by quality classification.
- Show grouped or single-record sites.
- Search by brand, operator, network, name, site ID, or OSM ID.
- Limit output for practical diagnostics.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


FILE_VERSION = "1.4.0-dev.001"
DEFAULT_INPUT_FILE = "charging_sites_ch.json"
VALID_QUALITIES = {
    "detailed",
    "location_only",
    "technical_only",
    "unknown",
}


def load_site_database(input_file: Path) -> dict[str, Any]:
    """Load and minimally validate charging_sites_ch.json."""

    with input_file.open("r", encoding="utf-8") as file_handle:
        database = json.load(file_handle)

    if not isinstance(database, dict):
        raise ValueError("Database root must be a JSON object.")

    data = database.get("data")
    if not isinstance(data, list):
        raise ValueError("Database must contain a 'data' list.")

    return database


def normalize_text(value: Any) -> str:
    """Normalize arbitrary values for case-insensitive text search."""

    if value is None:
        return ""

    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True).casefold()

    return str(value).casefold()


def site_matches_search(site: dict[str, Any], query: str) -> bool:
    """Return True when query occurs in useful site fields."""

    searchable_fields = (
        "site_id",
        "brand",
        "operator",
        "network",
        "name",
        "brands",
        "operators",
        "networks",
        "names",
        "osm_ids",
    )

    normalized_query = query.casefold()

    return any(
        normalized_query in normalize_text(site.get(field))
        for field in searchable_fields
    )


def filter_sites(
    sites: list[dict[str, Any]],
    quality: str | None,
    grouped_only: bool,
    single_only: bool,
    search: str | None,
    minimum_members: int | None,
) -> list[dict[str, Any]]:
    """Apply diagnostic filters to charging sites."""

    filtered: list[dict[str, Any]] = []

    for site in sites:
        if quality and site.get("quality") != quality:
            continue

        member_count = site.get("member_count", 0)

        if grouped_only and member_count <= 1:
            continue

        if single_only and member_count != 1:
            continue

        if minimum_members is not None and member_count < minimum_members:
            continue

        if search and not site_matches_search(site, search):
            continue

        filtered.append(site)

    filtered.sort(
        key=lambda site: (
            -int(site.get("member_count", 0)),
            str(site.get("brand") or "").casefold(),
            str(site.get("name") or "").casefold(),
            str(site.get("site_id") or ""),
        )
    )

    return filtered


def format_value(value: Any) -> str:
    """Format empty and structured values for console output."""

    if value in (None, "", [], {}):
        return "-"

    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)

    return str(value)


def print_site(site: dict[str, Any], number: int, show_members: bool) -> None:
    """Print one charging site in a readable diagnostic format."""

    print(f"{number}. {site.get('site_id', '-')}")
    print(f"   Quality:      {format_value(site.get('quality'))}")
    print(f"   Coordinates:  {format_value(site.get('latitude'))}, "
          f"{format_value(site.get('longitude'))}")
    print(f"   Brand:        {format_value(site.get('brand'))}")
    print(f"   Name:         {format_value(site.get('name'))}")
    print(f"   Operator:     {format_value(site.get('operator'))}")
    print(f"   Network:      {format_value(site.get('network'))}")
    print(f"   Power:        {format_value(site.get('power_kw'))}")
    print(f"   Capacity:     {format_value(site.get('capacity'))}")
    print(f"   Connectors:   {format_value(site.get('connectors'))}")
    print(f"   Members:      {format_value(site.get('member_count'))}")
    print(f"   OSM IDs:      {format_value(site.get('osm_ids'))}")

    if show_members:
        members = site.get("members", [])

        if members:
            print("   Member records:")

            for member_index, member in enumerate(members, start=1):
                print(f"      {member_index}. {format_value(member.get('id'))}")
                print(f"         Brand:      {format_value(member.get('brand'))}")
                print(f"         Name:       {format_value(member.get('name'))}")
                print(f"         Operator:   {format_value(member.get('operator'))}")
                print(f"         Network:    {format_value(member.get('network'))}")
                print(f"         Power:      {format_value(member.get('power_kw'))}")
                print(f"         Capacity:   {format_value(member.get('capacity'))}")
                print(f"         Connectors: {format_value(member.get('connectors'))}")

    print()


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Inspect charging_sites_ch.json for diagnostic purposes."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=Path(DEFAULT_INPUT_FILE),
        help=f"Input site database, default: {DEFAULT_INPUT_FILE}",
    )
    parser.add_argument(
        "--quality",
        choices=sorted(VALID_QUALITIES),
        help="Filter by site quality classification",
    )
    parser.add_argument(
        "--grouped-only",
        action="store_true",
        help="Show only sites containing more than one OSM record",
    )
    parser.add_argument(
        "--single-only",
        action="store_true",
        help="Show only sites containing exactly one OSM record",
    )
    parser.add_argument(
        "--minimum-members",
        type=int,
        help="Show only sites with at least this many member records",
    )
    parser.add_argument(
        "--search",
        help=(
            "Search site ID, OSM ID, brand, operator, network, or name"
        ),
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum number of sites to print, default: 20",
    )
    parser.add_argument(
        "--show-members",
        action="store_true",
        help="Print all member records of each site",
    )

    return parser.parse_args()


def main() -> int:
    arguments = parse_arguments()

    if arguments.grouped_only and arguments.single_only:
        raise ValueError(
            "--grouped-only and --single-only cannot be used together."
        )

    if arguments.minimum_members is not None and arguments.minimum_members < 1:
        raise ValueError("--minimum-members must be at least 1.")

    if arguments.limit < 1:
        raise ValueError("--limit must be at least 1.")

    database = load_site_database(arguments.input)
    sites = database["data"]

    filtered_sites = filter_sites(
        sites=sites,
        quality=arguments.quality,
        grouped_only=arguments.grouped_only,
        single_only=arguments.single_only,
        search=arguments.search,
        minimum_members=arguments.minimum_members,
    )

    print("Ford Triplog Charging Site Inspector")
    print(f"File version:          {FILE_VERSION}")
    print()
    print(f"Input file:            {arguments.input}")
    print(f"Total charging sites:  {len(sites)}")
    print(f"Matching sites:        {len(filtered_sites)}")
    print(f"Displayed sites:       {min(len(filtered_sites), arguments.limit)}")
    print()

    if not filtered_sites:
        print("No matching charging sites found.")
        return 0

    print("Charging sites")
    print("--------------")

    for number, site in enumerate(filtered_sites[:arguments.limit], start=1):
        print_site(site, number, arguments.show_members)

    if len(filtered_sites) > arguments.limit:
        remaining = len(filtered_sites) - arguments.limit
        print(f"... {remaining} additional matching sites not displayed.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
