"""
Ford Triplog

Track your Ford.

Configuration Flow.

Version: 1.4.13
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

from .countries import COUNTRIES
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
)


CONF_CHARGING_SITE_FILE = "charging_site_file"
CONF_CHARGING_SITE_COUNTRY = "charging_site_country"


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

    async def async_step_init(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Show the Ford Triplog options menu."""

        return self.async_show_menu(
            step_id="init",
            menu_options=[
                "settings",
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
                    status.get("log", [])
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
    ) -> str:
        """Format structured progress entries for the options dialog."""

        if not isinstance(entries, list) or not entries:
            return "Noch keine Fortschrittsmeldungen."

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
                    step_text = f"Schritt {step}/{total_steps}: "

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

        return "\n".join(lines) or "Noch keine Fortschrittsmeldungen."


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
