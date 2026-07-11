"""
Ford Triplog

Track your Ford.

Configuration Flow.
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.helpers import selector

from .const import (
    DOMAIN,
    NAME,
    CONF_IGNITION,
    CONF_ODOMETER,
    CONF_TRACKER,
    CONF_SOC,
)


class FordTriplogConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Ford Triplog."""

    VERSION = 1

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
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
        )