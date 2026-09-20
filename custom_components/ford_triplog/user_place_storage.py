"""User-defined places for automatic Journey pause enrichment."""

from __future__ import annotations

import uuid
from typing import Any

from pathlib import Path

from homeassistant.core import HomeAssistant

from .charging_site_lookup import haversine_distance_m, validate_coordinate
from .const import STORAGE_DIR
from .database import FordTriplogDatabase


DEFAULT_USER_PLACE_RADIUS_M = 75


class FordTriplogUserPlaceStorage:
    """Persist and resolve user-defined places."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self.storage_directory = Path(hass.config.path(".storage", STORAGE_DIR))
        self.database = FordTriplogDatabase(hass, self.storage_directory)
        self._places: list[dict[str, Any]] | None = None

    async def async_setup(self) -> None:
        await self.database.async_setup()
        self._places = self._normalize_places(
            await self.database.load_user_places(),
            generate_id=False,
        )

    async def async_load(self) -> list[dict[str, Any]]:
        if self._places is None:
            self._places = self._normalize_places(
                await self.database.load_user_places(),
                generate_id=False,
            )
        return [dict(place) for place in self._places]

    async def async_save(self, places: list[dict[str, Any]]) -> None:
        normalized = self._normalize_places(places, generate_id=True)
        if not await self.database.save_user_places(normalized):
            raise OSError("Unable to save user-defined places")
        self._places = normalized

    async def async_add(self, place: dict[str, Any]) -> dict[str, Any]:
        places = await self.async_load()
        normalized = self._normalize_place(place, generate_id=True)
        places.append(normalized)
        await self.async_save(places)
        return normalized

    async def async_update(
        self,
        place_id: str,
        changes: dict[str, Any],
    ) -> dict[str, Any]:
        places = await self.async_load()
        normalized_id = str(place_id).strip()
        for index, existing in enumerate(places):
            if existing.get("place_id") != normalized_id:
                continue
            merged = {**existing, **changes, "place_id": normalized_id}
            normalized = self._normalize_place(merged, generate_id=False)
            places[index] = normalized
            await self.async_save(places)
            return normalized
        raise KeyError(f"User place not found: {normalized_id}")

    async def async_delete(self, place_id: str) -> bool:
        places = await self.async_load()
        normalized_id = str(place_id).strip()
        remaining = [
            place for place in places
            if place.get("place_id") != normalized_id
        ]
        if len(remaining) == len(places):
            return False
        await self.async_save(remaining)
        return True

    async def async_get(self, place_id: str) -> dict[str, Any] | None:
        normalized_id = str(place_id).strip()
        for place in await self.async_load():
            if place.get("place_id") == normalized_id:
                return place
        return None

    def resolve_cached(
        self,
        latitude: Any,
        longitude: Any,
    ) -> dict[str, Any] | None:
        """Resolve a coordinate against the in-memory place cache.

        Smallest configured radius wins first; distance breaks ties. This lets
        users define a precise place inside a broader area deterministically.
        """
        if self._places is None or latitude is None or longitude is None:
            return None
        try:
            lat = float(latitude)
            lon = float(longitude)
            validate_coordinate(lat, lon)
        except (TypeError, ValueError):
            return None

        matches: list[tuple[float, float, dict[str, Any]]] = []
        for place in self._places:
            try:
                place_lat = float(place["latitude"])
                place_lon = float(place["longitude"])
                radius = float(place["radius_m"])
                distance = haversine_distance_m(
                    lat,
                    lon,
                    place_lat,
                    place_lon,
                )
            except (KeyError, TypeError, ValueError):
                continue
            if distance <= radius:
                matches.append((radius, distance, place))

        if not matches:
            return None
        matches.sort(key=lambda item: (item[0], item[1], str(item[2].get("name") or "")))
        selected = dict(matches[0][2])
        selected["distance_m"] = round(matches[0][1], 1)
        return selected

    @classmethod
    def _normalize_places(
        cls,
        places: list[dict[str, Any]],
        *,
        generate_id: bool,
    ) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for place in places or []:
            if not isinstance(place, dict):
                continue
            try:
                result.append(cls._normalize_place(place, generate_id=generate_id))
            except ValueError:
                continue
        return result

    @staticmethod
    def _clean_optional_text(value: Any) -> str:
        return str(value or "").strip()

    @classmethod
    def _normalize_place(
        cls,
        place: dict[str, Any],
        *,
        generate_id: bool,
    ) -> dict[str, Any]:
        place_id = cls._clean_optional_text(place.get("place_id"))
        if not place_id and generate_id:
            place_id = uuid.uuid4().hex
        if not place_id:
            raise ValueError("User place requires place_id")

        name = cls._clean_optional_text(place.get("name"))
        if not name:
            raise ValueError("User place requires name")

        try:
            latitude = float(place.get("latitude"))
            longitude = float(place.get("longitude"))
            validate_coordinate(latitude, longitude)
            radius_m = int(float(place.get("radius_m", DEFAULT_USER_PLACE_RADIUS_M)))
        except (TypeError, ValueError) as error:
            raise ValueError("Invalid user place coordinates/radius") from error

        radius_m = max(10, min(radius_m, 5000))

        return {
            "place_id": place_id,
            "name": name,
            "category": cls._clean_optional_text(place.get("category")),
            "description": cls._clean_optional_text(place.get("description")),
            "latitude": round(latitude, 7),
            "longitude": round(longitude, 7),
            "radius_m": radius_m,
            "icon": cls._clean_optional_text(place.get("icon")),
        }
