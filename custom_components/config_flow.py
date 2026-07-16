"""
Ford Triplog

Track your Ford.

Configuration Flow.
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    DOMAIN,
    NAME,
    CONF_IGNITION,
    CONF_ODOMETER,
    CONF_TRACKER,
    CONF_SOC,
    CONF_SMART_TRIP,
    CONF_SMART_TRIP_TIMEOUT
)


class FordTriplogConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Ford Triplog."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Get the options flow for this handler."""
        return FordTriplogOptionsFlow(config_entry)
        """Return the options flow."""
        return FordTriplogOptionsFlow(config_entry)
    
    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ):
        """Handle the initial step."""

        if user_input is not None:

            await self.async_set_unique_id(DOMAIN)

            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title=NAME,
                data=user_input,
            )

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_IGNITION,
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain="sensor",
                    )
                ),
                vol.Required(
                    CONF_ODOMETER,
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain="sensor",
                    )
                ),
                vol.Required(
                    CONF_TRACKER,
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain="device_tracker",
                    )
                ),
                vol.Optional(
                    CONF_SOC,
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain="sensor",
                    )
                ),
                vol.Optional(
                    CONF_SMART_TRIP,
                    default=True,
                ): selector.BooleanSelector(),

                vol.Optional(
                    CONF_SMART_TRIP_TIMEOUT,
                    default=300,
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=30,
                        max=900,
                        step=10,
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
        )
    
class FordTriplogOptionsFlow(config_entries.OptionsFlow):
    """Ford Triplog options."""

    def __init__(self, config_entry):
        self.config_entry = config_entry

    async def async_step_init(
        self,
        user_input: dict[str, Any] | None = None,
    ):
        """Manage the options."""

        if user_input is not None:
            return self.async_create_entry(
                title="",
                data=user_input,
            )

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_SMART_TRIP,
                    default=self.config_entry.options.get(
                        CONF_SMART_TRIP,
                        self.config_entry.data.get(
                            CONF_SMART_TRIP,
                            True,
                        ),
                    ),
                ): selector.BooleanSelector(),

                vol.Required(
                    CONF_SMART_TRIP_TIMEOUT,
                    default=self.config_entry.options.get(
                        CONF_SMART_TRIP_TIMEOUT,
                        self.config_entry.data.get(
                            CONF_SMART_TRIP_TIMEOUT,
                            300,
                        ),
                    ),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=30,
                        max=900,
                        step=10,
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="init",
            data_schema=schema,
        )