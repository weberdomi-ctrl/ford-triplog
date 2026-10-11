"""Read-only GPX and GeoJSON export for Ford Triplog stored routes."""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from xml.etree import ElementTree as ET
from typing import Any

from .route_history import _raw_coordinates, _matched_coordinates

GPX_NS = "http://www.topografix.com/GPX/1/1"
ET.register_namespace("", GPX_NS)


def _valid_coordinates(route: dict[str, Any], geometry: str) -> tuple[list[list[float]], str]:
    if geometry not in ("raw", "osrm"):
        raise ValueError("geometry must be raw or osrm")
    raw = _raw_coordinates(route)
    matched = _matched_coordinates(route)
    chosen, source = (matched, "osrm") if geometry == "osrm" and len(matched) >= 2 else (raw, "raw")
    if len(chosen) < 2:
        return [], source
    result = []
    for lon, lat in chosen:
        if all(math.isfinite(x) for x in (lon, lat)) and -180 <= lon <= 180 and -90 <= lat <= 90:
            result.append([lon, lat])
    return (result if len(result) >= 2 else []), source


def route_geojson(routes: list[dict[str, Any]], *, geometry: str = "raw") -> dict[str, Any]:
    """Export routes in caller-supplied order, retaining Trip boundaries."""
    features = []
    for sequence, route in enumerate(routes, 1):
        coords, source = _valid_coordinates(route, geometry)
        if not coords:
            continue
        features.append({
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": coords},
            "properties": {
                "trip_id": str(route.get("trip_id") or ""),
                "sequence": sequence,
                "geometry_source": source,
                "point_count": len(coords),
            },
        })
    return {"type": "FeatureCollection", "features": features}


def _iso_time(value: Any) -> str | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return None
        return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    except (ValueError, TypeError):
        return None


def route_gpx(routes: list[dict[str, Any]], *, geometry: str = "raw") -> str:
    """Create GPX 1.1 with one track per Trip. OSRM has no original timestamps."""
    root = ET.Element(f"{{{GPX_NS}}}gpx", version="1.1", creator="Ford Triplog")
    for route in routes:
        coords, source = _valid_coordinates(route, geometry)
        if not coords:
            continue
        track = ET.SubElement(root, f"{{{GPX_NS}}}trk")
        ET.SubElement(track, f"{{{GPX_NS}}}name").text = str(route.get("trip_id") or "Trip")
        seg = ET.SubElement(track, f"{{{GPX_NS}}}trkseg")
        raw_points = route.get("points") if isinstance(route.get("points"), list) else []
        for index, (lon, lat) in enumerate(coords):
            point = ET.SubElement(seg, f"{{{GPX_NS}}}trkpt", lat=str(lat), lon=str(lon))
            if source == "raw" and index < len(raw_points) and isinstance(raw_points[index], dict):
                item = raw_points[index]
                timestamp = _iso_time(item.get("timestamp") or item.get("time"))
                if timestamp:
                    ET.SubElement(point, f"{{{GPX_NS}}}time").text = timestamp
    return '<?xml version="1.0" encoding="utf-8"?>\n' + ET.tostring(root, encoding="unicode")


async def async_export_routes(route_storage: Any, trip_ids: list[str], *,
                              format: str = "gpx", geometry: str = "raw") -> str:
    """Read only routes belonging to the supplied vehicle-scoped route storage."""
    if format not in ("gpx", "geojson"):
        raise ValueError("format must be gpx or geojson")
    if geometry not in ("raw", "osrm"):
        raise ValueError("geometry must be raw or osrm")
    ordered_ids = list(dict.fromkeys(str(t).strip() for t in trip_ids if str(t).strip()))
    loaded = await route_storage.async_load_routes_for_trip_ids(ordered_ids)
    by_id = {str(route.get("trip_id")): route for route in loaded}
    routes = [by_id[trip_id] for trip_id in ordered_ids if trip_id in by_id]
    if format == "gpx":
        return route_gpx(routes, geometry=geometry)
    return json.dumps(route_geojson(routes, geometry=geometry), ensure_ascii=False, indent=2)
