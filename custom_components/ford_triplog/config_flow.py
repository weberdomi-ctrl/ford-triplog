"""
Ford Triplog

Track your Ford.

Configuration Flow.

Version: 1.6.0
Phase: 3.5
Build: 15

Changes:
- Uses compact one-line labels because Home Assistant select labels ignore line breaks.
- Formats home, work and public charging locations consistently with middle dots.
- Automatically assigns Zuhause or Arbeit when the name is left empty.
- Falls back to the address when no explicit name is available.
- Keeps Build 14 translation-placeholder compatibility.
"""

from __future__ import annotations

import asyncio
from time import perf_counter
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components.file_upload import process_uploaded_file
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import selector
from homeassistant.helpers.translation import async_get_translations

from .countries import COUNTRIES
from .pending_charging_site_storage import PendingChargingSiteStorage
from .user_charging_site_storage import UserChargingSiteStorage

from .services import (
    async_download_charging_database,
    async_import_charging_site_database,
)

from .const import (
    CONF_CHARGING,
    CONF_IGNITION,
    CONF_ODOMETER,
    CONF_SMART_TRIP,
    CONF_SMART_TRIP_TIMEOUT,
    CONF_SOC,
    CONF_TRACKER,
    CONF_BATTERY_CAPACITY,
    DOMAIN,
    NAME,
    VERSION as FORD_TRIPLOG_VERSION,
)


CONF_CHARGING_SITE_FILE = "charging_site_file"
CONF_CHARGING_SITE_COUNTRY = "charging_site_country"
CONF_USER_CHARGING_SITE_SELECTION = "user_charging_site_selection"
CONF_USER_CHARGING_SITE_NAME = "name"
CONF_USER_CHARGING_SITE_STREET = "street"
CONF_USER_CHARGING_SITE_HOUSE_NUMBER = "house_number"
CONF_USER_CHARGING_SITE_POSTCODE = "postcode"
CONF_USER_CHARGING_SITE_CITY = "city"
CONF_USER_CHARGING_SITE_COUNTRY = "country"
CONF_USER_CHARGING_SITE_LATITUDE = "latitude"
CONF_USER_CHARGING_SITE_LONGITUDE = "longitude"
CONF_USER_CHARGING_SITE_RADIUS = "radius"
CONF_USER_CHARGING_SITE_TYPE = "type"
CONF_USER_CHARGING_SITE_POWER = "power_kw"
CONF_USER_CHARGING_SITE_CAPACITY = "capacity"
CONF_USER_CHARGING_SITE_CONNECTORS = "connectors"
CONF_USER_CHARGING_SITE_OPERATOR = "operator"
CONF_USER_CHARGING_SITE_NETWORK = "network"
CONF_USER_CHARGING_SITE_BRAND = "brand"
CONF_USER_CHARGING_SITE_NOTES = "notes"
CONF_USER_CHARGING_SITE_ACTION = "action"
USER_CHARGING_SITE_NEW = "__new__"
USER_CHARGING_SITE_PENDING = "__pending__"


class FordTriplogConfigFlow(
    config_entries.ConfigFlow,
    domain=DOMAIN,
):
    """Handle Ford Triplog configuration."""

    VERSION = 1
    INTEGRATION_VERSION = FORD_TRIPLOG_VERSION

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> OptionsFlow:
        """Return the options flow."""
        return FordTriplogOptionsFlow(config_entry)

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Handle the initial configuration."""

        if user_input is not None:

            await self.async_set_unique_id(DOMAIN)
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title=NAME,
                data=user_input,
            )

        return self.async_show_form(
            step_id="user",
            data_schema=self._build_schema(),
        )

    @staticmethod
    def _build_schema() -> vol.Schema:
        """Return configuration schema."""

        return vol.Schema(
            {
                vol.Required(CONF_IGNITION): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor")
                ),
                vol.Required(CONF_ODOMETER): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor")
                ),
                vol.Required(CONF_TRACKER): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="device_tracker")
                ),
                vol.Optional(CONF_SOC): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor")
                ),
                vol.Optional(CONF_CHARGING): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor")
                ),
                vol.Required(CONF_SMART_TRIP, default=True): selector.BooleanSelector(),
                vol.Required(CONF_SMART_TRIP_TIMEOUT, default=300): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=30,
                        max=900,
                        step=10,
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
            }
        )


class FordTriplogOptionsFlow(OptionsFlow):
    """Ford Triplog options."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize options flow."""

        self._config_entry = config_entry
        self._options = {
            **config_entry.data,
            **config_entry.options,
        }
        self._import_result: dict[str, str] = {}
        self._download_result: dict[str, str] = {}
        self._download_task: asyncio.Task[None] | None = None
        self._download_error: str | None = None
        self._download_country_code: str | None = None
        self._download_started: float | None = None
        self._user_charging_site_storage: UserChargingSiteStorage | None = None
        self._pending_charging_site_storage: PendingChargingSiteStorage | None = None
        self._selected_user_charging_site: dict[str, Any] | None = None
        self._selected_pending_charging_site: dict[str, Any] | None = None
        self._charging_site_translations: dict[str, str] | None = None

    async def async_step_init(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Show the Ford Triplog options menu."""

        return self.async_show_menu(
            step_id="init",
            menu_options=[
                "settings",
                "user_charging_sites",
                "download_charging_sites",
            ],
        )

    async def async_step_settings(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Manage integration settings."""

        if user_input is not None:
            return self.async_create_entry(
                title="",
                data=user_input,
            )

        return self.async_show_form(
            step_id="settings",
            data_schema=self.add_suggested_values_to_schema(
                self._build_options_schema(),
                self._options,
            ),
        )


    async def _async_get_charging_site_translations(self) -> dict[str, str]:
        """Load charging-site translations once for this options flow."""

        if self._charging_site_translations is not None:
            return self._charging_site_translations

        translations = await async_get_translations(
            self.hass,
            self.hass.config.language,
            "charging_site",
            {DOMAIN},
        )

        defaults = {
            "home": "Home",
            "work": "Work",
            "public": "Public",
            "private": "Private",
            "dealer": "Dealer",
            "hotel": "Hotel",
            "other": "Other",
            "custom": "Custom",
            "location": "Charging location",
            "unknown_location": "Unknown charging location",
            "new_location": "+ New charging location",
            "pending_locations": "⚠ Newly detected charging locations ({count})",
            "save": "Save",
            "delete": "Delete",
            "step": "Step",
            "no_progress": "No progress messages yet.",
            "stored_one": "1 custom charging location saved.",
            "stored_many": "{count} custom charging locations saved.",
            "pending_one": (
                "1 unknown charging location was detected. "
                "It can now be saved as a custom charging location."
            ),
            "pending_many": (
                "{count} unknown charging locations were detected. "
                "They can now be saved as custom charging locations."
            ),
        }

        self._charging_site_translations = {
            key: translations.get(
                f"component.{DOMAIN}.charging_site.{key}",
                default,
            )
            for key, default in defaults.items()
        }
        return self._charging_site_translations

    async def _async_ensure_charging_site_storages(self) -> None:
        """Initialize user and pending charging-site storages lazily."""

        if self._user_charging_site_storage is None:
            self._user_charging_site_storage = UserChargingSiteStorage(
                self.hass
            )
        if self._pending_charging_site_storage is None:
            self._pending_charging_site_storage = PendingChargingSiteStorage(
                self.hass
            )

        await self._user_charging_site_storage.async_setup()
        await self._pending_charging_site_storage.async_setup()

    async def async_step_user_charging_sites(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """List stored charging locations and show pending-location notice."""

        errors: dict[str, str] = {}
        charging_site_text = await self._async_get_charging_site_translations()

        try:
            await self._async_ensure_charging_site_storages()
            sites = await self._user_charging_site_storage.async_load()
            pending_sites = (
                await self._pending_charging_site_storage.async_load()
            )
        except (OSError, ValueError):
            sites = []
            pending_sites = []
            errors["base"] = "user_charging_sites_load_failed"

        if user_input is not None and not errors:
            selected_id = str(
                user_input[CONF_USER_CHARGING_SITE_SELECTION]
            )

            if selected_id == USER_CHARGING_SITE_PENDING:
                return await self.async_step_pending_charging_sites()

            if selected_id == USER_CHARGING_SITE_NEW:
                self._selected_user_charging_site = None
                self._selected_pending_charging_site = None
                return await self.async_step_user_charging_site_edit()

            selected = next(
                (
                    site
                    for site in sites
                    if str(site.get("site_id")) == selected_id
                ),
                None,
            )
            if selected is None:
                errors["base"] = "user_charging_site_not_found"
            else:
                self._selected_user_charging_site = selected
                self._selected_pending_charging_site = None
                return await self.async_step_user_charging_site_edit()

        options: list[selector.SelectOptionDict] = []

        if pending_sites:
            options.append(
                selector.SelectOptionDict(
                    value=USER_CHARGING_SITE_PENDING,
                    label=charging_site_text["pending_locations"].format(
                        count=len(pending_sites)
                    ),
                )
            )

        options.append(
            selector.SelectOptionDict(
                value=USER_CHARGING_SITE_NEW,
                label=charging_site_text["new_location"],
            )
        )

        options.extend(
            selector.SelectOptionDict(
                value=str(site["site_id"]),
                label=self._format_user_charging_site_label(
                    site,
                    charging_site_text,
                ),
            )
            for site in sorted(
                sites,
                key=lambda item: str(item.get("name") or "").casefold(),
            )
        )

        step_id = (
            "user_charging_sites_pending_notice"
            if pending_sites
            else "user_charging_sites"
        )

        return self.async_show_form(
            step_id=step_id,
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_USER_CHARGING_SITE_SELECTION,
                        default=(
                            USER_CHARGING_SITE_PENDING
                            if pending_sites
                            else USER_CHARGING_SITE_NEW
                        ),
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=options,
                            mode=selector.SelectSelectorMode.LIST,
                        )
                    )
                }
            ),
            errors=errors,
            description_placeholders={
                # Current Build 13+ placeholders.
                "stored_text": self._format_stored_site_count(
                    len(sites),
                    charging_site_text,
                ),
                "pending_text": self._format_pending_site_count(
                    len(pending_sites),
                    charging_site_text,
                ),
                # Backward compatibility for cached/older translations.
                "site_count": str(len(sites)),
                "pending_count": str(len(pending_sites)),
            },
        )

    async def async_step_user_charging_sites_pending_notice(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Handle the stored-location page when a pending notice is visible."""

        return await self.async_step_user_charging_sites(user_input)

    async def async_step_pending_charging_sites(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """List detected unknown charging locations separately."""

        errors: dict[str, str] = {}
        charging_site_text = await self._async_get_charging_site_translations()

        try:
            await self._async_ensure_charging_site_storages()
            pending_sites = (
                await self._pending_charging_site_storage.async_load()
            )
        except (OSError, ValueError):
            pending_sites = []
            errors["base"] = "user_charging_sites_load_failed"

        if not pending_sites and not errors:
            return await self.async_step_user_charging_sites()

        if user_input is not None and not errors:
            pending_id = str(
                user_input[CONF_USER_CHARGING_SITE_SELECTION]
            )
            pending = next(
                (
                    site
                    for site in pending_sites
                    if str(site.get("site_id")) == pending_id
                ),
                None,
            )

            if pending is None:
                errors["base"] = "user_charging_site_not_found"
            else:
                self._selected_user_charging_site = None
                self._selected_pending_charging_site = pending
                return await self.async_step_user_charging_site_edit()

        options = [
            selector.SelectOptionDict(
                value=str(site["site_id"]),
                label=str(
                    site.get("name")
                    or charging_site_text["unknown_location"]
                ),
            )
            for site in pending_sites
        ]

        return self.async_show_form(
            step_id="pending_charging_sites",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_USER_CHARGING_SITE_SELECTION,
                        default=str(pending_sites[0]["site_id"]),
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=options,
                            mode=selector.SelectSelectorMode.LIST,
                        )
                    )
                }
            ),
            errors=errors,
            description_placeholders={
                "pending_count": str(len(pending_sites)),
            },
        )

    async def async_step_user_charging_site_edit(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Create or update a user-defined charging location."""

        await self._async_ensure_charging_site_storages()
        charging_site_text = await self._async_get_charging_site_translations()
        errors: dict[str, str] = {}

        existing = self._selected_user_charging_site
        pending = self._selected_pending_charging_site

        defaults: dict[str, Any] = {
            CONF_USER_CHARGING_SITE_NAME: "",
            CONF_USER_CHARGING_SITE_STREET: "",
            CONF_USER_CHARGING_SITE_HOUSE_NUMBER: "",
            CONF_USER_CHARGING_SITE_POSTCODE: "",
            CONF_USER_CHARGING_SITE_CITY: "",
            CONF_USER_CHARGING_SITE_COUNTRY: "",
            CONF_USER_CHARGING_SITE_POWER: 0.0,
            CONF_USER_CHARGING_SITE_CAPACITY: 0.0,
            CONF_USER_CHARGING_SITE_CONNECTORS: [],
            CONF_USER_CHARGING_SITE_LATITUDE: 0.0,
            CONF_USER_CHARGING_SITE_LONGITUDE: 0.0,
            CONF_USER_CHARGING_SITE_RADIUS: 50.0,
            CONF_USER_CHARGING_SITE_TYPE: "public",
            CONF_USER_CHARGING_SITE_OPERATOR: "",
            CONF_USER_CHARGING_SITE_NETWORK: "",
            CONF_USER_CHARGING_SITE_BRAND: "",
            CONF_USER_CHARGING_SITE_NOTES: "",
        }

        source = existing or pending
        if source is not None:
            (
                detected_street,
                detected_house_number,
                detected_postcode,
                detected_city,
                detected_country,
            ) = self._address_parts(source.get("address"))
            defaults.update(
                {
                    CONF_USER_CHARGING_SITE_NAME: (
                        source.get("name") or ""
                    ),
                    CONF_USER_CHARGING_SITE_STREET: (
                        source.get("street") or detected_street
                    ),
                    CONF_USER_CHARGING_SITE_HOUSE_NUMBER: (
                        source.get("house_number")
                        or detected_house_number
                    ),
                    CONF_USER_CHARGING_SITE_POSTCODE: (
                        source.get("postcode") or detected_postcode
                    ),
                    CONF_USER_CHARGING_SITE_CITY: (
                        source.get("city") or detected_city
                    ),
                    CONF_USER_CHARGING_SITE_COUNTRY: (
                        source.get("country") or detected_country
                    ),
                    CONF_USER_CHARGING_SITE_CONNECTORS: [
                        str(value)
                        for value in (source.get("connectors") or [])
                    ],
                    CONF_USER_CHARGING_SITE_LATITUDE: float(
                        source.get("latitude") or 0.0
                    ),
                    CONF_USER_CHARGING_SITE_LONGITUDE: float(
                        source.get("longitude") or 0.0
                    ),
                    CONF_USER_CHARGING_SITE_RADIUS: float(
                        source.get("radius") or 50.0
                    ),
                    CONF_USER_CHARGING_SITE_TYPE: (
                        source.get("type") or "public"
                    ),
                    CONF_USER_CHARGING_SITE_OPERATOR: (
                        source.get("operator") or ""
                    ),
                    CONF_USER_CHARGING_SITE_NETWORK: (
                        source.get("network") or ""
                    ),
                    CONF_USER_CHARGING_SITE_BRAND: (
                        source.get("brand") or ""
                    ),
                    CONF_USER_CHARGING_SITE_NOTES: (
                        source.get("notes") or ""
                    ),
                }
            )
            if source.get("power_kw"):
                defaults[CONF_USER_CHARGING_SITE_POWER] = float(
                    max(source["power_kw"])
                )
            if source.get("capacity"):
                defaults[CONF_USER_CHARGING_SITE_CAPACITY] = float(
                    max(source["capacity"])
                )

        if user_input is not None:
            if (
                existing is not None
                and user_input.get(CONF_USER_CHARGING_SITE_ACTION) == "delete"
            ):
                return await self.async_step_user_charging_site_delete()

            site_type = str(
                user_input[CONF_USER_CHARGING_SITE_TYPE]
            )
            site_name = str(
                user_input.get(CONF_USER_CHARGING_SITE_NAME) or ""
            ).strip()

            if not site_name:
                if site_type == "home":
                    site_name = charging_site_text["home"]
                elif site_type == "work":
                    site_name = charging_site_text["work"]
                else:
                    street = str(
                        user_input.get(
                            CONF_USER_CHARGING_SITE_STREET
                        ) or ""
                    ).strip()
                    house_number = str(
                        user_input.get(
                            CONF_USER_CHARGING_SITE_HOUSE_NUMBER
                        ) or ""
                    ).strip()
                    postcode = str(
                        user_input.get(
                            CONF_USER_CHARGING_SITE_POSTCODE
                        ) or ""
                    ).strip()
                    city = str(
                        user_input.get(
                            CONF_USER_CHARGING_SITE_CITY
                        ) or ""
                    ).strip()

                    street_line = " ".join(
                        value
                        for value in (street, house_number)
                        if value
                    )
                    city_line = " ".join(
                        value
                        for value in (postcode, city)
                        if value
                    )
                    site_name = ", ".join(
                        value
                        for value in (street_line, city_line)
                        if value
                    ) or charging_site_text["location"]

            site_data = {
                "name": site_name,
                "street": user_input.get(
                    CONF_USER_CHARGING_SITE_STREET
                ),
                "house_number": user_input.get(
                    CONF_USER_CHARGING_SITE_HOUSE_NUMBER
                ),
                "postcode": user_input.get(
                    CONF_USER_CHARGING_SITE_POSTCODE
                ),
                "city": user_input.get(
                    CONF_USER_CHARGING_SITE_CITY
                ),
                "country": user_input.get(
                    CONF_USER_CHARGING_SITE_COUNTRY
                ),
                "latitude": user_input[
                    CONF_USER_CHARGING_SITE_LATITUDE
                ],
                "longitude": user_input[
                    CONF_USER_CHARGING_SITE_LONGITUDE
                ],
                "radius": user_input[CONF_USER_CHARGING_SITE_RADIUS],
                "type": site_type,
                "power_kw": user_input.get(
                    CONF_USER_CHARGING_SITE_POWER
                ),
                "capacity": user_input.get(
                    CONF_USER_CHARGING_SITE_CAPACITY
                ),
                "connectors": user_input.get(
                    CONF_USER_CHARGING_SITE_CONNECTORS
                ),
                "operator": user_input.get(
                    CONF_USER_CHARGING_SITE_OPERATOR
                ),
                "network": user_input.get(
                    CONF_USER_CHARGING_SITE_NETWORK
                ),
                "brand": user_input.get(
                    CONF_USER_CHARGING_SITE_BRAND
                ),
                "notes": user_input.get(
                    CONF_USER_CHARGING_SITE_NOTES
                ),
            }

            try:
                if existing is None:
                    await self._user_charging_site_storage.async_add(
                        site_data
                    )
                else:
                    await self._user_charging_site_storage.async_update(
                        str(existing["site_id"]),
                        site_data,
                    )

                if pending is not None:
                    await self._pending_charging_site_storage.async_delete(
                        str(pending["id"])
                    )
            except (OSError, ValueError):
                errors["base"] = "user_charging_site_save_failed"
            else:
                self._selected_user_charging_site = None
                self._selected_pending_charging_site = None
                return await self.async_step_user_charging_sites()

        schema_fields: dict[Any, Any] = {
            vol.Optional(
                CONF_USER_CHARGING_SITE_NAME,
                default=defaults[CONF_USER_CHARGING_SITE_NAME],
            ): selector.TextSelector(),
            vol.Optional(
                CONF_USER_CHARGING_SITE_STREET,
                default=defaults[CONF_USER_CHARGING_SITE_STREET],
            ): selector.TextSelector(),
            vol.Optional(
                CONF_USER_CHARGING_SITE_HOUSE_NUMBER,
                default=defaults[
                    CONF_USER_CHARGING_SITE_HOUSE_NUMBER
                ],
            ): selector.TextSelector(),
            vol.Optional(
                CONF_USER_CHARGING_SITE_POSTCODE,
                default=defaults[CONF_USER_CHARGING_SITE_POSTCODE],
            ): selector.TextSelector(),
            vol.Optional(
                CONF_USER_CHARGING_SITE_CITY,
                default=defaults[CONF_USER_CHARGING_SITE_CITY],
            ): selector.TextSelector(),
            vol.Optional(
                CONF_USER_CHARGING_SITE_COUNTRY,
                default=defaults[CONF_USER_CHARGING_SITE_COUNTRY],
            ): selector.TextSelector(),
            vol.Required(
                CONF_USER_CHARGING_SITE_LATITUDE,
                default=defaults[CONF_USER_CHARGING_SITE_LATITUDE],
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=-90,
                    max=90,
                    step="any",
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
            vol.Required(
                CONF_USER_CHARGING_SITE_LONGITUDE,
                default=defaults[CONF_USER_CHARGING_SITE_LONGITUDE],
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=-180,
                    max=180,
                    step="any",
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
            vol.Required(
                CONF_USER_CHARGING_SITE_RADIUS,
                default=defaults[CONF_USER_CHARGING_SITE_RADIUS],
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=5,
                    max=5000,
                    step=5,
                    unit_of_measurement="m",
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
            vol.Required(
                CONF_USER_CHARGING_SITE_TYPE,
                default=defaults[CONF_USER_CHARGING_SITE_TYPE],
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        selector.SelectOptionDict(
                            value="public",
                            label=charging_site_text["public"],
                        ),
                        selector.SelectOptionDict(
                            value="private",
                            label=charging_site_text["private"],
                        ),
                        selector.SelectOptionDict(
                            value="home",
                            label=charging_site_text["home"],
                        ),
                        selector.SelectOptionDict(
                            value="work",
                            label=charging_site_text["work"],
                        ),
                        selector.SelectOptionDict(
                            value="dealer",
                            label=charging_site_text["dealer"],
                        ),
                        selector.SelectOptionDict(
                            value="hotel",
                            label=charging_site_text["hotel"],
                        ),
                        selector.SelectOptionDict(
                            value="other",
                            label=charging_site_text["other"],
                        ),
                    ],
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Optional(
                CONF_USER_CHARGING_SITE_OPERATOR,
                default=defaults[CONF_USER_CHARGING_SITE_OPERATOR],
            ): selector.TextSelector(),
            vol.Optional(
                CONF_USER_CHARGING_SITE_NETWORK,
                default=defaults[CONF_USER_CHARGING_SITE_NETWORK],
            ): selector.TextSelector(),
            vol.Optional(
                CONF_USER_CHARGING_SITE_BRAND,
                default=defaults[CONF_USER_CHARGING_SITE_BRAND],
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        "Allego",
                        "Aral pulse",
                        "BP Pulse",
                        "ChargePoint",
                        "Electra",
                        "EnBW",
                        "E.ON Drive",
                        "evpass",
                        "Fastned",
                        "GOFAST",
                        "IONITY",
                        "MOVE",
                        "Shell Recharge",
                        "Swisscharge",
                        "Tesla",
                    ],
                    custom_value=True,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                    sort=True,
                )
            ),
            vol.Optional(
                CONF_USER_CHARGING_SITE_NOTES,
                default=defaults[CONF_USER_CHARGING_SITE_NOTES],
            ): selector.TextSelector(
                selector.TextSelectorConfig(
                    multiline=True,
                )
            ),
        }

        schema_fields[
            vol.Optional(
                CONF_USER_CHARGING_SITE_POWER,
                default=defaults[CONF_USER_CHARGING_SITE_POWER],
            )
        ] = selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=0,
                max=1000,
                step="any",
                unit_of_measurement="kW",
                mode=selector.NumberSelectorMode.BOX,
            )
        )

        schema_fields[
            vol.Optional(
                CONF_USER_CHARGING_SITE_CAPACITY,
                default=defaults[CONF_USER_CHARGING_SITE_CAPACITY],
            )
        ] = selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=0,
                max=1000,
                step=1,
                mode=selector.NumberSelectorMode.BOX,
            )
        )

        schema_fields[
            vol.Optional(
                CONF_USER_CHARGING_SITE_CONNECTORS,
                default=defaults[CONF_USER_CHARGING_SITE_CONNECTORS],
            )
        ] = selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=[
                    selector.SelectOptionDict(
                        value="CCS",
                        label="CCS (Combo 2)",
                    ),
                    selector.SelectOptionDict(
                        value="Type2",
                        label="Type 2 / Mennekes (AC)",
                    ),
                    selector.SelectOptionDict(
                        value="CHAdeMO",
                        label="CHAdeMO",
                    ),
                    selector.SelectOptionDict(
                        value="NACS",
                        label="NACS (Tesla)",
                    ),
                    selector.SelectOptionDict(
                        value="TeslaSupercharger",
                        label="Tesla Supercharger",
                    ),
                    selector.SelectOptionDict(
                        value="TeslaDestination",
                        label="Tesla Destination",
                    ),
                    selector.SelectOptionDict(
                        value="Type1",
                        label="Type 1 / J1772 (AC)",
                    ),
                    selector.SelectOptionDict(
                        value="CEE_Red",
                        label="CEE rot",
                    ),
                    selector.SelectOptionDict(
                        value="CEE_Blue",
                        label="CEE blau",
                    ),
                    selector.SelectOptionDict(
                        value="Schuko",
                        label="Schuko",
                    ),
                    selector.SelectOptionDict(
                        value="GBT_DC",
                        label="GB/T DC",
                    ),
                    selector.SelectOptionDict(
                        value="GBT_AC",
                        label="GB/T AC",
                    ),
                    selector.SelectOptionDict(
                        value="Other",
                        label=charging_site_text["other"],
                    ),
                ],
                multiple=True,
                mode=selector.SelectSelectorMode.DROPDOWN,
            )
        )

        if existing is not None:
            schema_fields[
                vol.Required(
                    CONF_USER_CHARGING_SITE_ACTION,
                    default="save",
                )
            ] = selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        selector.SelectOptionDict(
                            value="save",
                            label=charging_site_text["save"],
                        ),
                        selector.SelectOptionDict(
                            value="delete",
                            label=charging_site_text["delete"],
                        ),
                    ],
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            )

        return self.async_show_form(
            step_id="user_charging_site_edit",
            data_schema=vol.Schema(schema_fields),
            errors=errors,
            description_placeholders={
                "mode": (
                    "detected"
                    if pending is not None
                    else "edit"
                    if existing is not None
                    else "new"
                ),
            },
        )

    async def async_step_user_charging_site_delete(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Delete the selected user-defined charging location."""

        await self._async_ensure_charging_site_storages()
        existing = self._selected_user_charging_site

        if existing is None:
            return await self.async_step_user_charging_sites()

        if user_input is not None:
            await self._user_charging_site_storage.async_delete(
                str(existing["site_id"])
            )
            self._selected_user_charging_site = None
            return await self.async_step_user_charging_sites()

        return self.async_show_form(
            step_id="user_charging_site_delete",
            data_schema=vol.Schema({}),
            description_placeholders={
                "name": str(existing.get("name") or ""),
            },
        )

    @staticmethod
    def _address_parts(
        address: Any,
    ) -> tuple[str, str, str, str, str]:
        """Extract address fields from reverse-geocoding metadata."""

        if not isinstance(address, dict):
            return "", "", "", "", ""

        street = (
            address.get("road")
            or address.get("street")
            or address.get("pedestrian")
            or address.get("footway")
            or ""
        )
        house_number = address.get("house_number") or ""
        postcode = address.get("postcode") or ""
        city = (
            address.get("city")
            or address.get("town")
            or address.get("village")
            or address.get("municipality")
            or address.get("hamlet")
            or ""
        )
        country = (
            address.get("country_code")
            or address.get("country")
            or ""
        )

        return (
            str(street).strip(),
            str(house_number).strip(),
            str(postcode).strip(),
            str(city).strip(),
            str(country).strip().upper(),
        )

    @staticmethod
    def _format_user_charging_site_label(
        site: dict[str, Any],
        translations: dict[str, str],
    ) -> str:
        """Return a compact one-line label for a stored charging location."""

        site_type = str(site.get("type") or "public")
        type_labels = {
            "public": translations["public"],
            "private": translations["private"],
            "home": translations["home"],
            "work": translations["work"],
            "dealer": translations["dealer"],
            "hotel": translations["hotel"],
            "other": translations["other"],
            "custom": translations["custom"],
        }
        type_label = type_labels.get(site_type, site_type)

        name = str(site.get("name") or "").strip()
        provider = str(
            site.get("brand")
            or site.get("network")
            or site.get("operator")
            or ""
        ).strip()
        street = str(site.get("street") or "").strip()
        house_number = str(site.get("house_number") or "").strip()
        postcode = str(site.get("postcode") or "").strip()
        city = str(site.get("city") or "").strip()

        street_line = " ".join(
            value
            for value in (street, house_number)
            if value
        )
        city_line = city or postcode
        address_fallback = ", ".join(
            value
            for value in (
                street_line,
                " ".join(
                    value
                    for value in (postcode, city)
                    if value
                ),
            )
            if value
        )

        parts: list[str]
        if site_type == "home":
            parts = [type_label, street_line, city_line]
        elif site_type == "work":
            work_names = {
                translations["work"].casefold(),
                "work",
                "arbeitsplatz",
                "arbeit",
            }
            work_name = name if name.casefold() not in work_names else ""
            parts = [
                type_label,
                work_name or street_line,
                city_line,
            ]
        else:
            parts = [
                name or address_fallback or translations["location"],
                provider,
                type_label,
            ]

        result: list[str] = []
        seen: set[str] = set()
        for part in parts:
            value = str(part or "").strip()
            key = value.casefold()
            if value and key not in seen:
                result.append(value)
                seen.add(key)

        return " · ".join(result) or translations["location"]

    @staticmethod
    def _format_pending_site_count(
        count: int,
        translations: dict[str, str],
    ) -> str:
        """Return translated pending-site information."""

        if count == 1:
            return translations["pending_one"]
        if count > 1:
            return translations["pending_many"].format(count=count)
        return ""

    @staticmethod
    def _format_stored_site_count(
        count: int,
        translations: dict[str, str],
    ) -> str:
        """Return translated stored-site information."""

        if count == 1:
            return translations["stored_one"]
        return translations["stored_many"].format(count=count)

    async def async_step_import_charging_sites(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Upload and import a charging-site database."""

        errors: dict[str, str] = {}

        if user_input is not None:
            uploaded_file_id = user_input[CONF_CHARGING_SITE_FILE]

            try:
                with process_uploaded_file(
                    self.hass,
                    uploaded_file_id,
                ) as uploaded_path:
                    _, _, active_lookup = (
                        await async_import_charging_site_database(
                            self.hass,
                            uploaded_path,
                        )
                    )
            except (HomeAssistantError, OSError, ValueError):
                errors["base"] = "invalid_charging_site_database"
            else:
                self._import_result = {
                    "searchable_sites": str(
                        active_lookup.searchable_site_count
                    ),
                    "index_cells": str(
                        active_lookup.index_cell_count
                    ),
                }
                return await self.async_step_import_charging_sites_success()

        return self.async_show_form(
            step_id="import_charging_sites",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_CHARGING_SITE_FILE
                    ): selector.FileSelector(
                        selector.FileSelectorConfig(
                            accept=".json,application/json"
                        )
                    )
                }
            ),
            errors=errors,
        )

    async def async_step_import_charging_sites_success(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Show the successful charging-site import result."""

        if user_input is not None:
            return await self.async_step_init()

        return self.async_show_form(
            step_id="import_charging_sites_success",
            data_schema=vol.Schema({}),
            description_placeholders=self._import_result,
        )


    async def async_step_download_charging_sites(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Select and start an OpenStreetMap charging-site download."""

        errors: dict[str, str] = {}

        if user_input is not None:
            progress_manager = self.hass.data[DOMAIN]["progress_manager"]

            if progress_manager.is_running:
                errors["base"] = "charging_site_download_in_progress"
            else:
                self._download_country_code = str(
                    user_input[CONF_CHARGING_SITE_COUNTRY]
                ).strip().upper()
                self._download_error = None
                self._download_result = {}
                self._download_started = perf_counter()

                self._download_task = self.hass.async_create_task(
                    self._async_run_charging_site_download(
                        self._download_country_code,
                    ),
                    "ford_triplog_download_charging_sites",
                )

                return await self.async_step_download_charging_sites_progress()

        country_options = [
            selector.SelectOptionDict(
                value=country_code,
                label=f"{country['name']} ({country_code})",
            )
            for country_code, country in COUNTRIES.items()
        ]

        default_country = self._download_country_code

        if not default_country:
            home_assistant_country = (
                str(self.hass.config.country or "")
                .strip()
                .upper()
            )

            # Home Assistant normally uses ISO 3166-1 alpha-2.
            # Accept UK as a defensive alias for the official GB code.
            if home_assistant_country == "UK":
                home_assistant_country = "GB"

            default_country = (
                home_assistant_country
                if home_assistant_country in COUNTRIES
                else "CH"
            )

        return self.async_show_form(
            step_id="download_charging_sites",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_CHARGING_SITE_COUNTRY,
                        default=default_country,
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=country_options,
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    )
                }
            ),
            errors=errors,
        )

    async def _async_run_charging_site_download(
        self,
        country_code: str,
    ) -> None:
        """Run and monitor a charging-site download in the background."""

        progress_manager = self.hass.data[DOMAIN]["progress_manager"]

        download_task = self.hass.async_create_task(
            async_download_charging_database(
                self.hass,
                country_code,
            ),
            f"ford_triplog_build_charging_sites_{country_code.lower()}",
        )

        try:
            while not download_task.done():
                status = progress_manager.get_status()
                self.async_update_progress(
                    max(
                        0.0,
                        min(
                            1.0,
                            float(status.get("progress", 0)) / 100.0,
                        ),
                    )
                )
                await asyncio.sleep(0.5)

            build_result, backup_path, active_lookup = await download_task
        except asyncio.CancelledError:
            # Closing the options dialog cancels the progress monitor.
            # The actual database task may still finish in the background.
            raise
        except (HomeAssistantError, OSError, RuntimeError, ValueError):
            self._download_error = "charging_site_download_failed"
            return

        self.async_update_progress(1.0)

        duration_seconds = (
            perf_counter() - self._download_started
            if self._download_started is not None
            else progress_manager.get_status().get("elapsed_seconds", 0.0)
        )
        database_size_mib = (
            build_result.output_file.stat().st_size
            / (1024 * 1024)
        )

        persisted_options = dict(self._config_entry.options)
        persisted_options[CONF_CHARGING_SITE_COUNTRY] = (
            build_result.country_code
        )
        self.hass.config_entries.async_update_entry(
            self._config_entry,
            options=persisted_options,
        )
        self._options[CONF_CHARGING_SITE_COUNTRY] = (
            build_result.country_code
        )
        self._download_country_code = build_result.country_code

        self._download_result = {
            "country": build_result.country_name,
            "country_code": build_result.country_code,
            "downloaded_elements": self._format_count(
                build_result.downloaded_elements
            ),
            "normalized_stations": self._format_count(
                build_result.normalized_stations
            ),
            "searchable_sites": self._format_count(
                active_lookup.searchable_site_count
            ),
            "index_cells": self._format_count(
                active_lookup.index_cell_count
            ),
            "skipped_elements": self._format_count(
                build_result.skipped_elements
            ),
            "database_size": f"{database_size_mib:.2f} MiB",
            "duration": f"{float(duration_seconds):.1f} s",
            "backup_status": (
                "yes" if backup_path is not None else "no"
            ),
        }

    async def async_step_download_charging_sites_progress(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Show live progress while the database is being generated."""

        if self._download_task is None:
            return await self.async_step_download_charging_sites()

        if self._download_task.done():
            return self.async_show_progress_done(
                next_step_id="download_charging_sites_result",
            )

        status = self.hass.data[DOMAIN]["progress_manager"].get_status()

        return self.async_show_progress(
            step_id="download_charging_sites_progress",
            progress_action="download_charging_sites",
            progress_task=self._download_task,
            description_placeholders={
                "country_code": self._download_country_code or "",
                "stage": str(status.get("title") or ""),
                "message": str(status.get("message") or ""),
                "step": str(status.get("step", 0)),
                "total_steps": str(status.get("total_steps", 6)),
                "progress": str(status.get("progress", 0)),
                "elapsed": f"{float(status.get('elapsed_seconds', 0.0)):.1f}",
                "progress_log": self._format_progress_log(
                    status.get("log", []),
                    await self._async_get_charging_site_translations(),
                ),
            },
        )

    async def async_step_download_charging_sites_result(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Route the completed background task to success or retry."""

        if self._download_task is not None:
            try:
                self._download_task.result()
            except asyncio.CancelledError:
                self._download_error = "charging_site_download_failed"
            except Exception:
                self._download_error = "charging_site_download_failed"

        self._download_task = None

        if self._download_error is not None:
            error_key = self._download_error
            self._download_error = None

            country_options = [
                selector.SelectOptionDict(
                    value=country_code,
                    label=f"{country['name']} ({country_code})",
                )
                for country_code, country in COUNTRIES.items()
            ]

            return self.async_show_form(
                step_id="download_charging_sites",
                data_schema=vol.Schema(
                    {
                        vol.Required(
                            CONF_CHARGING_SITE_COUNTRY,
                            default=self._download_country_code or "CH",
                        ): selector.SelectSelector(
                            selector.SelectSelectorConfig(
                                options=country_options,
                                mode=selector.SelectSelectorMode.DROPDOWN,
                            )
                        )
                    }
                ),
                errors={"base": error_key},
            )

        return await self.async_step_download_charging_sites_success()

    async def async_step_download_charging_sites_success(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Show the successful OpenStreetMap download result."""

        if user_input is not None:
            return self.async_create_entry(
                title="",
                data=dict(self._options),
            )

        return self.async_show_form(
            step_id="download_charging_sites_success",
            data_schema=vol.Schema({}),
            description_placeholders=self._download_result,
        )


    @staticmethod
    def _format_count(value: int) -> str:
        """Format an integer for readable result placeholders."""

        return f"{value:,}".replace(",", "'")

    @staticmethod
    def _format_progress_log(
        entries: list[dict[str, Any]] | Any,
        translations: dict[str, str],
    ) -> str:
        """Format structured progress entries for the options dialog."""

        if not isinstance(entries, list) or not entries:
            return translations["no_progress"]

        lines: list[str] = []

        for entry in entries:
            if not isinstance(entry, dict):
                continue

            title = str(entry.get("title") or "").strip()
            message = str(entry.get("message") or "").strip()
            level = str(entry.get("level") or "info").strip().lower()
            step = entry.get("step")
            total_steps = entry.get("total_steps")
            elapsed = entry.get("elapsed_seconds")

            prefix = {
                "success": "✓",
                "warning": "!",
                "error": "✗",
            }.get(level, "•")

            step_text = ""
            if isinstance(step, int) and isinstance(total_steps, int):
                if total_steps > 0:
                    step_text = (
                        f"{translations['step']} {step}/{total_steps}: "
                    )

            text = message or title
            if title and message and title != message:
                text = f"{title} – {message}"

            if not text:
                continue

            elapsed_text = ""
            if isinstance(elapsed, (int, float)):
                elapsed_text = f" ({float(elapsed):.1f} s)"

            lines.append(
                f"{prefix} {step_text}{text}{elapsed_text}"
            )

        return "\n".join(lines) or translations["no_progress"]


    def _build_options_schema(self) -> vol.Schema:
        """Return options schema."""

        return vol.Schema(
            {
                vol.Optional(CONF_CHARGING): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor")
                ),

                vol.Optional(CONF_SMART_TRIP): bool,

                vol.Optional(CONF_SMART_TRIP_TIMEOUT): int,

                vol.Optional(
                    CONF_CHARGING_SITE_COUNTRY,
                    default=self._options.get(
                        CONF_CHARGING_SITE_COUNTRY,
                        "CH",
                    ),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(
                                value=country_code,
                                label=(
                                    f"{country['name']} ({country_code})"
                                ),
                            )
                            for country_code, country
                            in sorted(COUNTRIES.items())
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),

                vol.Optional(
                    CONF_BATTERY_CAPACITY,
                    default=self._options.get(CONF_BATTERY_CAPACITY, 77),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=40,
                        max=120,
                        step=1,
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
            }
        )


#
# End of configuration flow.
#
