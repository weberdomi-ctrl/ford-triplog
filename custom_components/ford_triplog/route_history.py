"""
Ford Triplog

Historical route GeoJSON builder

Version: 2.0.1-dev
Phase: 2 - Journey route aggregation

Purpose:
- Build one GeoJSON FeatureCollection from multiple stored Trip routes.
- Preserve Journey Trip ID order.
- Prefer OSRM matched geometry.
- Fall back to raw GPS points when no valid OSRM geometry exists.
- Keep this logic independent from Home Assistant entities/UI.
"""

from __future__ import annotations

from typing import Any

from .route_storage import FordTriplogRouteStorage


def _raw_coordinates(route: dict[str, Any]) -> list[list[float]]:
    """Return valid raw GPS coordinates as [longitude, latitude]."""

    coordinates: list[list[float]] = []

    points = route.get("points")
    if not isinstance(points, list):
        return coordinates

    for point in points:
        if not isinstance(point, dict):
            continue

        try:
            latitude = float(point.get("latitude"))
            longitude = float(point.get("longitude"))
        except (TypeError, ValueError):
            continue

        coordinates.append([longitude, latitude])

    return coordinates


def _matched_coordinates(route: dict[str, Any]) -> list[list[float]]:
    """Return valid OSRM matched coordinates."""

    matched_route = route.get("matched_route")
    if not isinstance(matched_route, dict):
        return []

    geometry = matched_route.get("geometry")
    if not isinstance(geometry, dict) or geometry.get("type") != "LineString":
        return []

    raw_coordinates = geometry.get("coordinates")
    if not isinstance(raw_coordinates, list):
        return []

    coordinates: list[list[float]] = []

    for coordinate in raw_coordinates:
        if (
            not isinstance(coordinate, (list, tuple))
            or len(coordinate) < 2
        ):
            continue

        try:
            longitude = float(coordinate[0])
            latitude = float(coordinate[1])
        except (TypeError, ValueError):
            continue

        coordinates.append([longitude, latitude])

    return coordinates


def _route_feature(
    route: dict[str, Any],
    *,
    sequence: int,
) -> dict[str, Any] | None:
    """Build one map-ready GeoJSON feature for a stored route."""

    raw_coordinates = _raw_coordinates(route)
    matched_coordinates = _matched_coordinates(route)

    if len(matched_coordinates) >= 2:
        coordinates = matched_coordinates
        geometry_source = "osrm"
    elif len(raw_coordinates) >= 2:
        coordinates = raw_coordinates
        geometry_source = "raw"
    else:
        return None

    matched_route = route.get("matched_route")
    matched_route = (
        matched_route
        if isinstance(matched_route, dict)
        else {}
    )

    properties: dict[str, Any] = {
        "trip_id": str(route.get("trip_id") or ""),
        "sequence": sequence,
        "source_type": route.get("source_type"),
        "geometry_source": geometry_source,
        "raw_point_count": len(raw_coordinates),
        "point_count": len(coordinates),
    }

    if geometry_source == "osrm":
        properties.update(
            {
                "osrm_confidence": matched_route.get("confidence"),
                "osrm_matched_tracepoints": matched_route.get(
                    "matched_tracepoints"
                ),
                "osrm_unmatched_tracepoints": matched_route.get(
                    "unmatched_tracepoints"
                ),
            }
        )

        try:
            properties["osrm_distance_km"] = round(
                float(matched_route.get("distance_m")) / 1000.0,
                3,
            )
        except (TypeError, ValueError):
            pass

    properties = {
        key: value
        for key, value in properties.items()
        if value is not None
    }

    return {
        "type": "Feature",
        "properties": properties,
        "geometry": {
            "type": "LineString",
            "coordinates": coordinates,
        },
    }


async def async_build_route_feature_collection(
    route_storage: FordTriplogRouteStorage,
    trip_ids: list[str],
    *,
    journey_id: str | None = None,
    journey_date: str | None = None,
) -> dict[str, Any]:
    """Build a FeatureCollection for the supplied ordered Trip IDs."""

    normalized_trip_ids = [
        str(trip_id).strip()
        for trip_id in trip_ids
        if str(trip_id).strip()
    ]

    routes = await route_storage.async_load_routes_for_trip_ids(
        normalized_trip_ids
    )

    route_by_trip_id = {
        str(route.get("trip_id") or ""): route
        for route in routes
        if route.get("trip_id")
    }

    features: list[dict[str, Any]] = []
    missing_trip_ids: list[str] = []
    osrm_route_count = 0
    raw_route_count = 0

    for sequence, trip_id in enumerate(normalized_trip_ids, start=1):
        route = route_by_trip_id.get(trip_id)

        if route is None:
            missing_trip_ids.append(trip_id)
            continue

        feature = _route_feature(route, sequence=sequence)
        if feature is None:
            missing_trip_ids.append(trip_id)
            continue

        if feature["properties"]["geometry_source"] == "osrm":
            osrm_route_count += 1
        else:
            raw_route_count += 1

        features.append(feature)

    return {
        "type": "FeatureCollection",
        "features": features,
        "properties": {
            "journey_id": journey_id,
            "date": journey_date,
            "requested_trip_count": len(normalized_trip_ids),
            "route_count": len(features),
            "osrm_route_count": osrm_route_count,
            "raw_route_count": raw_route_count,
            "missing_route_count": len(missing_trip_ids),
            "missing_trip_ids": missing_trip_ids,
        },
    }


async def async_build_journey_route_feature_collection(
    route_storage: FordTriplogRouteStorage,
    journey: Any,
) -> dict[str, Any]:
    """Build a FeatureCollection directly from a Journey object/dict."""

    if isinstance(journey, dict):
        trip_ids = journey.get("trip_ids", [])
        journey_id = journey.get("journey_id")
        journey_date = journey.get("date")
    else:
        trip_ids = getattr(journey, "trip_ids", [])
        journey_id = getattr(journey, "journey_id", None)
        journey_date = getattr(journey, "date", None)

    if not isinstance(trip_ids, list):
        trip_ids = list(trip_ids) if trip_ids else []

    return await async_build_route_feature_collection(
        route_storage,
        trip_ids,
        journey_id=str(journey_id) if journey_id else None,
        journey_date=str(journey_date) if journey_date else None,
    )
