"""
Ford Triplog

Normalize raw OpenStreetMap charging-station data.

File: normalizer_v1.4.0-dev.005.py
Version: 1.4.0-dev.005
Date: 2026-07-23

Changes:
- Complete rewrite of the normalizer.
- Canonical provider handling.
- Brand fallback: brand -> network -> operator.
- Explicit provider-source statistics.
- Robust node, way and relation coordinate handling.
- Clean JSON output with deterministic sorting.
- Final provider mapping cleanup before freezing the normalizer.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any


FILE_VERSION = "1.4.0-dev.005"

CONNECTOR_TAGS = {
    "socket:type2": "Type 2",
    "socket:type2_combo": "CCS",
    "socket:chademo": "CHAdeMO",
    "socket:tesla_supercharger": "Tesla Supercharger",
    "socket:tesla_destination": "Tesla Destination",
    "socket:type1": "Type 1",
    "socket:type1_combo": "CCS Type 1",
    "socket:schuko": "Schuko",
    "socket:cee_blue": "CEE Blue",
    "socket:cee_red_16a": "CEE Red 16A",
    "socket:cee_red_32a": "CEE Red 32A",
    "socket:cee_red_63a": "CEE Red 63A",
}

PROVIDER_MAPPING = {
    "agrola": "Agrola",
    "altis": "ALTIS",
    "amag": "AMAG",
    "ebl": "EBL",
    "ebs": "ebs",
    "emoti": "emotì",
    "emotì": "emotì",
    "enalpin": "EnAlpin",
    "energie360": "Energie 360°",
    "energie360°": "Energie 360°",
    "eniva": "Eniva",
    "evbox": "EVBox",
    "ewz": "ewz",
    "groupe e": "Groupe E",
    "has.to.be": "has.to.be",
    "intercharge": "intercharge",
    "m-way": "m-way",
    "mobilecharge": "Mobilecharge",
    "ost-mobil": "Ost-mobil",
    "partino": "Partino",
    "swisscharge.ch": "Swisscharge",
    "bike energy": "bike-energy",
    "bike-energy": "bike-energy",
    "chargepoint": "ChargePoint",
    "ecarup": "eCarUp",
    "electra": "Electra",
    "energie 360": "Energie 360°",
    "energie 360°": "Energie 360°",
    "evite": "EVite",
    "evpass": "evpass",
    "fastned": "Fastned",
    "gofast": "GOFAST",
    "green motion": "Green Motion",
    "green motion sa": "Green Motion",
    "ionity": "IONITY",
    "lidl": "Lidl",
    "m-charge": "M-Charge",
    "mcharge": "M-Charge",
    "migrol": "Migrol",
    "move": "MOVE",
    "oiken": "OIKEN",
    "plug'n roll": "Plug'n Roll",
    "plug’n roll": "Plug'n Roll",
    "shell recharge": "Shell Recharge",
    "socar": "SOCAR",
    "supercharger": "Tesla",
    "swisscharge": "Swisscharge",
    "tesla": "Tesla",
    "tesla destination charging": "Tesla",
    "tesla supercharger": "Tesla",
}


def clean_text(value: Any) -> str | None:
    """Return stripped text or None."""

    if value is None:
        return None

    text = str(value).strip()
    return text or None


def normalize_lookup_key(value: str) -> str:
    """Create a stable lookup key for provider names."""

    return " ".join(
        value.replace("’", "'")
        .replace("`", "'")
        .casefold()
        .split()
    )


def normalize_provider(value: Any) -> str | None:
    """Return a canonical provider spelling where known."""

    text = clean_text(value)

    if text is None:
        return None

    return PROVIDER_MAPPING.get(normalize_lookup_key(text), text)


def get_coordinates(
    element: dict[str, Any],
) -> tuple[float, float] | None:
    """Return coordinates for a node, way or relation."""

    latitude = element.get("lat")
    longitude = element.get("lon")

    if latitude is None or longitude is None:
        center = element.get("center")

        if isinstance(center, dict):
            latitude = center.get("lat")
            longitude = center.get("lon")

    if (
        not isinstance(latitude, (int, float))
        or isinstance(latitude, bool)
        or not isinstance(longitude, (int, float))
        or isinstance(longitude, bool)
    ):
        return None

    return float(latitude), float(longitude)


def parse_integer(value: Any) -> int | None:
    """Extract the first non-negative integer."""

    if value is None or isinstance(value, bool):
        return None

    if isinstance(value, int):
        return value if value >= 0 else None

    if isinstance(value, float):
        return int(value) if value >= 0 else None

    match = re.search(r"\d+", str(value))

    if match is None:
        return None

    return int(match.group())


def parse_power_kw(value: Any) -> float | None:
    """Parse a power value and return kilowatts."""

    text = clean_text(value)

    if text is None:
        return None

    normalized = text.casefold().replace(",", ".")
    match = re.search(r"(-?\d+(?:\.\d+)?)", normalized)

    if match is None:
        return None

    number = float(match.group(1))

    if number < 0:
        return None

    if "mw" in normalized:
        number *= 1000
    elif "kw" in normalized:
        pass
    elif re.search(r"(^|\s)w($|\s)", normalized):
        number /= 1000
    elif number > 1000:
        number /= 1000

    return round(number, 3)


def determine_power_kw(tags: dict[str, Any]) -> float | None:
    """Return the highest available charging power."""

    values: list[float] = []

    for key in ("capacity:charging", "maxpower"):
        power = parse_power_kw(tags.get(key))

        if power is not None:
            values.append(power)

    for connector_tag in CONNECTOR_TAGS:
        for suffix in (":output", ":output:voltage"):
            power = parse_power_kw(tags.get(f"{connector_tag}{suffix}"))

            if power is not None:
                values.append(power)

    return max(values) if values else None


def determine_connectors(tags: dict[str, Any]) -> list[str]:
    """Return available connector names."""

    connectors: set[str] = set()

    for osm_tag, connector_name in CONNECTOR_TAGS.items():
        raw_value = tags.get(osm_tag)

        if raw_value is None:
            continue

        value = str(raw_value).strip().casefold()

        if value in {"no", "0", "false"}:
            continue

        connectors.add(connector_name)

    return sorted(connectors)


def determine_brand(
    tags: dict[str, Any],
) -> tuple[str | None, str | None]:
    """
    Determine the display brand and its source.

    Priority:
    1. brand
    2. network
    3. operator
    """

    for source in ("brand", "network", "operator"):
        provider = normalize_provider(tags.get(source))

        if provider is not None:
            return provider, source

    return None, None


def determine_name(tags: dict[str, Any]) -> str | None:
    """Return the best available station name."""

    for key in ("name", "brand", "network", "operator"):
        value = clean_text(tags.get(key))

        if value is not None:
            return value

    return None


def normalize_station(
    element: dict[str, Any],
) -> tuple[dict[str, Any] | None, str | None]:
    """Normalize one Overpass element."""

    coordinates = get_coordinates(element)

    if coordinates is None:
        return None, None

    osm_id = element.get("id")
    osm_type = clean_text(element.get("type"))

    if not isinstance(osm_id, int) or osm_type is None:
        return None, None

    raw_tags = element.get("tags")
    tags = raw_tags if isinstance(raw_tags, dict) else {}

    latitude, longitude = coordinates
    brand, brand_source = determine_brand(tags)

    station = {
        "id": f"{osm_type}/{osm_id}",
        "osm_type": osm_type,
        "osm_id": osm_id,
        "lat": round(latitude, 7),
        "lon": round(longitude, 7),
        "name": determine_name(tags),
        "operator": clean_text(tags.get("operator")),
        "network": clean_text(tags.get("network")),
        "brand": brand,
        "capacity": parse_integer(tags.get("capacity")),
        "power_kw": determine_power_kw(tags),
        "connectors": determine_connectors(tags),
        "access": clean_text(tags.get("access")),
        "fee": clean_text(tags.get("fee")),
        "opening_hours": clean_text(tags.get("opening_hours")),
        "website": clean_text(tags.get("website")),
    }

    cleaned_station = {
        key: value
        for key, value in station.items()
        if value is not None and value != []
    }

    return cleaned_station, brand_source


def normalize_data(
    data: dict[str, Any],
) -> tuple[list[dict[str, Any]], Counter[str], int]:
    """Normalize all Overpass elements."""

    elements = data.get("elements")

    if not isinstance(elements, list):
        raise ValueError("The Overpass JSON contains no element list.")

    stations: list[dict[str, Any]] = []
    source_counter: Counter[str] = Counter()
    skipped = 0

    for element in elements:
        if not isinstance(element, dict):
            skipped += 1
            continue

        station, brand_source = normalize_station(element)

        if station is None:
            skipped += 1
            continue

        stations.append(station)

        if brand_source is None:
            source_counter["none"] += 1
        else:
            source_counter[brand_source] += 1

    stations.sort(
        key=lambda station: (
            str(station.get("brand", "")).casefold(),
            str(station.get("name", "")).casefold(),
            station["id"],
        )
    )

    return stations, source_counter, skipped


def load_json(input_file: Path) -> dict[str, Any]:
    """Load input JSON."""

    with input_file.open("r", encoding="utf-8") as file_handle:
        data = json.load(file_handle)

    if not isinstance(data, dict):
        raise ValueError("The input JSON must contain an object.")

    return data


def save_json(
    stations: list[dict[str, Any]],
    output_file: Path,
) -> None:
    """Save normalized data."""

    with output_file.open("w", encoding="utf-8") as file_handle:
        json.dump(
            stations,
            file_handle,
            ensure_ascii=False,
            indent=2,
        )


def main() -> None:
    """Run the normalizer."""

    tools_directory = Path(__file__).parent
    input_path = tools_directory / "overpass_ch_raw.json"
    output_path = tools_directory / "charging_stations_ch_normalized.json"

    data = load_json(input_path)
    stations, source_counter, skipped = normalize_data(data)
    save_json(stations, output_path)

    brand_count = sum(
        isinstance(station.get("brand"), str)
        and bool(station["brand"].strip())
        for station in stations
    )

    print("Ford Triplog Charging Database Normalizer")
    print(f"File version: {FILE_VERSION}")
    print()
    print(f"Input elements:       {len(data.get('elements', []))}")
    print(f"Normalized stations:  {len(stations)}")
    print(f"Skipped elements:     {skipped}")
    print()
    print("Brand source statistics")
    print("-----------------------")
    print(f"brand:                {source_counter['brand']}")
    print(f"network fallback:     {source_counter['network']}")
    print(f"operator fallback:    {source_counter['operator']}")
    print(f"no provider field:    {source_counter['none']}")
    print(f"brand written:        {brand_count}")
    print()
    print(f"Normalized data saved: {output_path}")

    if stations:
        print("\nFirst normalized station:")
        print(json.dumps(stations[0], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
