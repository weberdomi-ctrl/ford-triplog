"""
Ford Triplog

Track your Ford.

Configuration Flow.

Version: 1.4.0
"""

from __future__ import annotations

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

from .services import async_import_charging_site_database

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
)


CONF_CHARGING_SITE_FILE = "charging_site_file"


class FordTriplogConfigFlow(
    config_entries.ConfigFlow,
    domain=DOMAIN,
):
    """Handle Ford Triplog configuration."""

    VERSION = 1

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

        self._options = {
            **config_entry.data,
            **config_entry.options,
        }
        self._import_result: dict[str, str] = {}

    async def async_step_init(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Show the Ford Triplog options menu."""

        return self.async_show_menu(
            step_id="init",
            menu_options=[
                "settings",
                "import_charging_sites",
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
                    _, active_lookup = (
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
