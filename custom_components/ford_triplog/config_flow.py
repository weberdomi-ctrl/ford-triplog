"""
Ford Triplog

Track your Ford.

Configuration Flow.

Version: 1.8.4
Phase: Detailed charging costs GUI
Build: 01
Release: 1.8.4

Changes:
- Uses compact one-line labels because Home Assistant select labels ignore line breaks.
- Formats home, work and public charging locations consistently with middle dots.
- Automatically assigns Zuhause or Arbeit when the name is left empty.
- Falls back to the address when no explicit name is available.
- Keeps Build 14 translation-placeholder compatibility.
- Adds configurable Journey base zone, home timeout and maximum gap options.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from time import perf_counter
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components.file_upload import process_uploaded_file
from homeassistant.components.http.auth import async_sign_path
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.network import NoURLAvailableError, get_url
from homeassistant.helpers.translation import async_get_translations
from homeassistant.util import dt as dt_util

from .countries import COUNTRIES
from .pending_charging_site_storage import PendingChargingSiteStorage
from .user_charging_site_storage import UserChargingSiteStorage
from .receipt_storage import FordTriplogReceiptStorage
from .ocr_client import (
    FordTriplogOCRAuthenticationError,
    FordTriplogOCRClient,
    FordTriplogOCRConnectionError,
    FordTriplogOCRResponseError,
)

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
    CONF_JOURNEY_HOME_ZONE,
    CONF_JOURNEY_HOME_TIMEOUT,
    CONF_JOURNEY_MAX_GAP_HOURS,
    DEFAULT_JOURNEY_HOME_ZONE,
    DEFAULT_JOURNEY_HOME_TIMEOUT,
    DEFAULT_JOURNEY_MAX_GAP_HOURS,
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

CONF_CHARGE_SELECTION = "charge_selection"
CONF_CHARGE_COST_TOTAL = "cost_total"
CONF_CHARGE_CURRENCY = "currency"
CONF_CHARGE_ENERGY_BILLED_KWH = "energy_billed_kwh"
CONF_CHARGE_ENERGY_COST = "energy_cost"
CONF_CHARGE_SESSION_FEE = "session_fee"
CONF_CHARGE_TIME_FEE = "time_fee"
CONF_CHARGE_BLOCKING_FEE = "blocking_fee"
CONF_CHARGE_PARKING_FEE = "parking_fee"
CONF_CHARGE_OTHER_COST = "other_cost"
CONF_CHARGE_ACTION = "action"

CONF_HOME_TARIFF_ENABLED = "home_tariff_enabled"
CONF_HOME_TARIFF_SUMMER_PRICE = "home_tariff_summer_price"
CONF_HOME_TARIFF_WINTER_PRICE = "home_tariff_winter_price"
CONF_HOME_TARIFF_CURRENCY = "home_tariff_currency"

CHARGE_ACTION_SAVE = "save"
CHARGE_ACTION_CLEAR = "clear"

CONF_PAUSE_SELECTION = "pause_selection"
CONF_PAUSE_CATEGORY = "category"
CONF_PAUSE_TITLE = "title"
CONF_PAUSE_NOTE = "note"
CONF_PAUSE_LOCATION = "location"
CONF_PAUSE_COST_TOTAL = "cost_total"
CONF_PAUSE_CURRENCY = "currency"
CONF_PAUSE_ACTION = "action"

PAUSE_ACTION_SAVE = "save"
PAUSE_ACTION_CLEAR = "clear"

CONF_RECEIPT_TARGET_TYPE = "target_type"
CONF_RECEIPT_TARGET = "target"
CONF_RECEIPT_FILE = "receipt_file"
CONF_RECEIPT_NOTE = "note"
CONF_RECEIPT_SELECTION = "receipt_selection"
CONF_RECEIPT_OCR_SELECTION = "receipt_ocr_selection"
CONF_OCR_ENABLED = "ocr_enabled"
CONF_OCR_URL = "ocr_url"
CONF_OCR_API_KEY = "ocr_api_key"
CONF_OCR_TIMEOUT = "ocr_timeout"
CONF_RECEIPT_DETAIL_ACTION = "receipt_detail_action"
RECEIPT_DETAIL_OPEN = "open"
RECEIPT_DETAIL_BACK = "back"
RECEIPT_TARGET_PAUSE = "pause"
RECEIPT_TARGET_CHARGE = "charge"


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
        self._journey_result: dict[str, str] = {}
        self._selected_charge_id: str | None = None
        self._charge_result: dict[str, str] = {}
        self._charge_translations: dict[str, str] | None = None
        self._selected_pause_journey_id: str | None = None
        self._selected_pause_id: str | None = None
        self._pause_result: dict[str, str] = {}
        self._pause_translations: dict[str, str] | None = None
        self._receipt_target_type: str | None = None
        self._receipt_result: dict[str, str] = {}
        self._selected_receipt_id: str | None = None
        self._selected_receipt_url: str | None = None
        self._receipt_ocr_result: dict[str, str] = {}
        self._ocr_connection_result: dict[str, str] = {}

    async def async_step_init(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Show the Ford Triplog options menu."""

        return self.async_show_menu(
            step_id="init",
            menu_options=[
                "settings",
                "journey_management",
                "pause_management",
                "charge_management",
                "receipt_management",
                "user_charging_sites",
                "download_charging_sites",
            ],
        )


    async def _async_get_charge_translations(self) -> dict[str, str]:
        """Load Charge Manager translations once for this options flow."""

        if self._charge_translations is not None:
            return self._charge_translations

        translations = await async_get_translations(
            self.hass,
            self.hass.config.language,
            "common",
            {DOMAIN},
        )

        self._charge_translations = {
            "save": translations.get(
                f"component.{DOMAIN}.common.charge_action_save",
                "Save",
            ),
            "clear": translations.get(
                f"component.{DOMAIN}.common.charge_action_clear",
                "Clear costs",
            ),
        }

        return self._charge_translations

    def _get_charge_manager(self):
        """Return the Charge Manager for this config entry."""

        runtime_data = self.hass.data.get(
            DOMAIN,
            {},
        ).get(
            self._config_entry.entry_id,
            {},
        )

        manager = runtime_data.get("charge_manager")

        if manager is None:
            raise HomeAssistantError(
                "Charge Manager is not initialized"
            )

        return manager

    async def async_step_charge_management(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Select one archived charging session."""

        errors: dict[str, str] = {}

        try:
            charges = await self._get_charge_manager().async_get_charges()
        except (HomeAssistantError, OSError, ValueError):
            charges = []
            errors["base"] = "charge_load_failed"

        if not charges and not errors:
            errors["base"] = "charge_none_available"

        if user_input is not None and not errors:
            self._selected_charge_id = str(
                user_input[CONF_CHARGE_SELECTION]
            ).strip()
            return await self.async_step_charge_cost_edit()

        options = [
            selector.SelectOptionDict(
                value=str(charge.charge_id),
                label=self._format_charge_label(charge),
            )
            for charge in charges
            if charge.charge_id
        ]

        schema: dict[Any, Any] = {}

        if options:
            schema[
                vol.Required(
                    CONF_CHARGE_SELECTION,
                    default=options[0]["value"],
                )
            ] = selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=options,
                    mode=selector.SelectSelectorMode.LIST,
                )
            )

        return self.async_show_form(
            step_id="charge_management",
            data_schema=vol.Schema(schema),
            errors=errors,
            description_placeholders={
                "charge_count": str(len(options)),
            },
        )

    async def async_step_charge_cost_edit(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Edit manual costs for the selected charging session."""

        if not self._selected_charge_id:
            return await self.async_step_charge_management()

        manager = self._get_charge_manager()
        charge_text = await self._async_get_charge_translations()
        charge = await manager.async_get_charge(
            self._selected_charge_id
        )

        if charge is None:
            self._selected_charge_id = None
            return self.async_show_form(
                step_id="charge_cost_edit",
                data_schema=vol.Schema({}),
                errors={"base": "charge_not_found"},
            )

        errors: dict[str, str] = {}

        if user_input is not None:
            action = str(
                user_input.get(
                    CONF_CHARGE_ACTION,
                    CHARGE_ACTION_SAVE,
                )
            )

            try:
                if action == CHARGE_ACTION_CLEAR:
                    result = await manager.async_clear_cost(
                        self._selected_charge_id
                    )
                else:
                    result = await manager.async_set_cost(
                        self._selected_charge_id,
                        currency=user_input[
                            CONF_CHARGE_CURRENCY
                        ],
                        cost_total=None,
                        energy_billed_kwh=user_input.get(
                            CONF_CHARGE_ENERGY_BILLED_KWH
                        ),
                        energy_cost=user_input.get(
                            CONF_CHARGE_ENERGY_COST
                        ),
                        session_fee=user_input.get(
                            CONF_CHARGE_SESSION_FEE
                        ),
                        time_fee=user_input.get(
                            CONF_CHARGE_TIME_FEE
                        ),
                        blocking_fee=user_input.get(
                            CONF_CHARGE_BLOCKING_FEE
                        ),
                        parking_fee=user_input.get(
                            CONF_CHARGE_PARKING_FEE
                        ),
                        other_cost=user_input.get(
                            CONF_CHARGE_OTHER_COST
                        ),
                        energy_billed_source="manual",
                    )
            except (HomeAssistantError, ValueError):
                errors["base"] = "charge_cost_save_failed"
            else:
                if not result.updated:
                    errors["base"] = (
                        "charge_not_found"
                        if result.reason == "charge_not_found"
                        else "charge_cost_save_failed"
                    )
                else:
                    saved_charge = result.charge
                    self._charge_result = {
                        "charge_id": result.charge_id,
                        "action": result.action,
                        "cost_total": self._format_optional_number(
                            getattr(saved_charge, "cost_total", None),
                            2,
                        ),
                        "currency": str(
                            getattr(saved_charge, "currency", None) or "—"
                        ),
                        "price_per_kwh": self._format_optional_number(
                            getattr(
                                saved_charge,
                                "effective_price_per_kwh",
                                getattr(
                                    saved_charge,
                                    "price_per_kwh",
                                    None,
                                ),
                            ),
                            4,
                        ),
                        "energy_price_per_kwh": self._format_optional_number(
                            getattr(
                                saved_charge,
                                "energy_price_per_kwh",
                                None,
                            ),
                            4,
                        ),
                        "energy_billed_kwh": self._format_optional_number(
                            getattr(
                                saved_charge,
                                "energy_billed_kwh",
                                None,
                            ),
                            2,
                        ),
                        "charging_loss_kwh": self._format_optional_number(
                            getattr(
                                saved_charge,
                                "charging_loss_kwh",
                                None,
                            ),
                            2,
                        ),
                        "charging_loss_percent": self._format_optional_number(
                            getattr(
                                saved_charge,
                                "charging_loss_percent",
                                None,
                            ),
                            2,
                        ),
                    }
                    self._selected_charge_id = None
                    return await self.async_step_charge_cost_result()

        default_currency = str(charge.currency or "CHF").upper()
        default_energy_billed = (
            float(charge.energy_billed_kwh)
            if getattr(charge, "energy_billed_kwh", None) is not None
            else 0.0
        )

        return self.async_show_form(
            step_id="charge_cost_edit",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_CHARGE_ENERGY_BILLED_KWH,
                        default=default_energy_billed,
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=0,
                            max=1000,
                            step=0.01,
                            unit_of_measurement="kWh",
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    ),
                    vol.Optional(
                        CONF_CHARGE_ENERGY_COST,
                        default=float(
                            getattr(charge, "energy_cost", None) or 0.0
                        ),
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=0,
                            max=100000,
                            step=0.01,
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    ),
                    vol.Optional(
                        CONF_CHARGE_SESSION_FEE,
                        default=float(
                            getattr(charge, "session_fee", None) or 0.0
                        ),
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=0,
                            max=100000,
                            step=0.01,
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    ),
                    vol.Optional(
                        CONF_CHARGE_TIME_FEE,
                        default=float(
                            getattr(charge, "time_fee", None) or 0.0
                        ),
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=0,
                            max=100000,
                            step=0.01,
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    ),
                    vol.Optional(
                        CONF_CHARGE_BLOCKING_FEE,
                        default=float(
                            getattr(charge, "blocking_fee", None) or 0.0
                        ),
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=0,
                            max=100000,
                            step=0.01,
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    ),
                    vol.Optional(
                        CONF_CHARGE_PARKING_FEE,
                        default=float(
                            getattr(charge, "parking_fee", None) or 0.0
                        ),
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=0,
                            max=100000,
                            step=0.01,
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    ),
                    vol.Optional(
                        CONF_CHARGE_OTHER_COST,
                        default=float(
                            getattr(charge, "other_cost", None) or 0.0
                        ),
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=0,
                            max=100000,
                            step=0.01,
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    ),
                    vol.Required(
                        CONF_CHARGE_CURRENCY,
                        default=default_currency,
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                "CHF",
                                "EUR",
                                "GBP",
                                "USD",
                            ],
                            custom_value=True,
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                    vol.Required(
                        CONF_CHARGE_ACTION,
                        default=CHARGE_ACTION_SAVE,
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                selector.SelectOptionDict(
                                    value=CHARGE_ACTION_SAVE,
                                    label=charge_text["save"],
                                ),
                                selector.SelectOptionDict(
                                    value=CHARGE_ACTION_CLEAR,
                                    label=charge_text["clear"],
                                ),
                            ],
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                }
            ),
            errors=errors,
            description_placeholders={
                "charge_id": str(charge.charge_id or ""),
                "date": self._format_charge_datetime(
                    charge.start_time
                ),
                "location": self._charge_location(charge),
                "energy_kwh": self._format_optional_number(
                    charge.energy_added_kwh,
                    2,
                ),
                "start_soc": self._format_optional_number(
                    charge.start_soc,
                    1,
                ),
                "end_soc": self._format_optional_number(
                    charge.end_soc,
                    1,
                ),
                "current_cost": self._format_optional_number(
                    charge.cost_total,
                    2,
                ),
                "current_currency": str(
                    charge.currency or "—"
                ),
                "current_price_per_kwh": (
                    self._format_optional_number(
                        getattr(
                            charge,
                            "effective_price_per_kwh",
                            charge.price_per_kwh,
                        ),
                        4,
                    )
                ),
                "current_energy_price_per_kwh": (
                    self._format_optional_number(
                        getattr(
                            charge,
                            "energy_price_per_kwh",
                            None,
                        ),
                        4,
                    )
                ),
                "current_energy_billed_kwh": (
                    self._format_optional_number(
                        getattr(
                            charge,
                            "energy_billed_kwh",
                            None,
                        ),
                        2,
                    )
                ),
                "current_charging_loss_kwh": (
                    self._format_optional_number(
                        getattr(
                            charge,
                            "charging_loss_kwh",
                            None,
                        ),
                        2,
                    )
                ),
                "current_charging_loss_percent": (
                    self._format_optional_number(
                        getattr(
                            charge,
                            "charging_loss_percent",
                            None,
                        ),
                        2,
                    )
                ),
            },
        )

    async def async_step_charge_cost_result(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Show the result of a charging-cost operation."""

        if user_input is not None:
            return await self.async_step_charge_management()

        return self.async_show_form(
            step_id="charge_cost_result",
            data_schema=vol.Schema({}),
            description_placeholders=self._charge_result,
        )

    @staticmethod
    def _format_charge_label(charge: Any) -> str:
        """Return a short one-line label for a charging session."""

        date_text = FordTriplogOptionsFlow._format_charge_datetime(
            getattr(charge, "start_time", None)
        )
        location = FordTriplogOptionsFlow._charge_location(charge)

        parts = [
            date_text,
            location,
        ]

        energy = getattr(charge, "energy_added_kwh", None)
        try:
            energy_value = float(energy) if energy is not None else None
        except (TypeError, ValueError):
            energy_value = None

        if energy_value is not None and energy_value > 0:
            parts.append(f"{energy_value:.2f} kWh")

        cost_total = getattr(charge, "cost_total", None)
        currency = str(getattr(charge, "currency", None) or "").strip()

        if cost_total is not None:
            try:
                parts.append(f"{float(cost_total):.2f} {currency}".strip())
            except (TypeError, ValueError):
                pass

        return " · ".join(part for part in parts if part)

    @staticmethod
    def _format_charge_datetime(value: Any) -> str:
        """Return a compact Home Assistant local date and time."""

        if not value:
            return "—"

        try:
            timestamp = datetime.fromisoformat(
                str(value).replace("Z", "+00:00")
            )
        except (TypeError, ValueError):
            return str(value)

        if timestamp.tzinfo is None:
            timestamp = dt_util.as_local(
                timestamp.replace(tzinfo=dt_util.UTC)
            )
        else:
            timestamp = dt_util.as_local(timestamp)

        return timestamp.strftime("%d.%m.%Y %H:%M")

    @staticmethod
    def _charge_location(charge: Any) -> str:
        """Return a short charging location label."""

        for attribute in (
            "charging_site_name",
            "charging_site_brand",
            "charging_site_operator",
            "charging_site_network",
        ):
            value = getattr(charge, attribute, None)
            if value:
                normalized = str(value).strip()
                if normalized:
                    return normalized

        address = getattr(charge, "start_address", None)

        if isinstance(address, dict):
            road = str(
                address.get("road")
                or address.get("street")
                or ""
            ).strip()
            house_number = str(
                address.get("house_number")
                or ""
            ).strip()
            city = str(
                address.get("city")
                or address.get("town")
                or address.get("village")
                or address.get("municipality")
                or ""
            ).strip()

            street_line = " ".join(
                part
                for part in (road, house_number)
                if part
            )

            compact = ", ".join(
                part
                for part in (street_line, city)
                if part
            )
            if compact:
                return compact

            for key in ("display", "display_name", "formatted"):
                value = address.get(key)
                if value:
                    return str(value).split(",", 1)[0].strip()

        if address:
            return str(address).split(",", 1)[0].strip()

        return "Unbekannter Ladeort"

    @staticmethod
    def _format_optional_number(
        value: Any,
        digits: int,
    ) -> str:
        """Format an optional numeric value."""

        if value is None:
            return "—"

        try:
            return f"{float(value):.{digits}f}"
        except (TypeError, ValueError):
            return "—"



    async def _async_get_pause_translations(self) -> dict[str, str]:
        """Load Pause Editor translations once for this options flow."""

        if self._pause_translations is not None:
            return self._pause_translations

        translations = await async_get_translations(
            self.hass,
            self.hass.config.language,
            "common",
            {DOMAIN},
        )

        self._pause_translations = {
            "save": translations.get(
                f"component.{DOMAIN}.common.pause_action_save",
                "Save",
            ),
            "clear": translations.get(
                f"component.{DOMAIN}.common.pause_action_clear",
                "Clear",
            ),
        }

        return self._pause_translations

    def _get_journey_storage(self):
        """Return Journey storage for this config entry."""

        runtime_data = self.hass.data.get(
            DOMAIN,
            {},
        ).get(
            self._config_entry.entry_id,
            {},
        )

        storage = runtime_data.get("journey_storage")

        if storage is None:
            raise HomeAssistantError(
                "Journey storage is not initialized"
            )

        return storage

    @staticmethod
    def _pause_location(current: Any, following: Any) -> str:
        """Return the most useful automatic location for a pause."""

        return str(
            getattr(current, "end_location", None)
            or getattr(current, "end_address", None)
            or getattr(following, "start_location", None)
            or getattr(following, "start_address", None)
            or "—"
        )

    @staticmethod
    def _pause_time(value: Any) -> str:
        """Format one ISO timestamp for a compact selection label."""

        if not value:
            return "—"

        try:
            return datetime.fromisoformat(str(value)).strftime("%H:%M")
        except ValueError:
            return str(value)

    async def _async_get_pause_entries(self) -> list[dict[str, Any]]:
        """Return editable pauses from all archived journeys."""

        from .journey import build_pause_id

        entries: list[dict[str, Any]] = []
        journeys = await self._get_journey_storage().get_all_journeys()

        for journey in reversed(journeys):
            for current, following in zip(journey.items, journey.items[1:]):
                if not current.end_time or not following.start_time:
                    continue

                try:
                    start = datetime.fromisoformat(current.end_time)
                    end = datetime.fromisoformat(following.start_time)
                    duration_seconds = max(0, int((end - start).total_seconds()))
                except ValueError:
                    duration_seconds = 0

                if duration_seconds <= 0:
                    continue

                # Short gaps of up to three minutes directly before or after
                # a charging session are charging buffers, not editable
                # Journey pauses. Keep the Pause Editor consistent with the
                # Journey timeline and hide these entries here as well.
                if (
                    duration_seconds <= 180
                    and (
                        current.item_type == "charge"
                        or following.item_type == "charge"
                    )
                ):
                    continue

                pause_id = build_pause_id(current.item_id, following.item_id)
                override = dict(journey.pause_overrides.get(pause_id, {}))
                location = override.get("location") or self._pause_location(
                    current,
                    following,
                )
                title = override.get("title")
                date_text = str(journey.date or "—")
                time_text = (
                    f"{self._pause_time(current.end_time)}–"
                    f"{self._pause_time(following.start_time)}"
                )
                minutes = round(duration_seconds / 60)
                label_parts = [date_text, time_text, f"{minutes} min", str(location)]
                if title:
                    label_parts.append(str(title))

                entries.append(
                    {
                        "value": f"{journey.journey_id}::{pause_id}",
                        "label": " · ".join(label_parts),
                        "journey_id": journey.journey_id,
                        "pause_id": pause_id,
                        "date": date_text,
                        "start_time": self._pause_time(current.end_time),
                        "title": str(title or ""),
                        "location": str(location or "—"),
                        "cost_total": override.get("cost_total"),
                        "currency": str(override.get("currency") or ""),
                    }
                )

        return entries

    async def async_step_pause_management(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Select one archived Journey pause."""

        errors: dict[str, str] = {}

        try:
            pauses = await self._async_get_pause_entries()
        except (HomeAssistantError, OSError, ValueError):
            pauses = []
            errors["base"] = "pause_load_failed"

        if not pauses and not errors:
            errors["base"] = "pause_none_available"

        if user_input is not None and not errors:
            selection = str(user_input[CONF_PAUSE_SELECTION])
            try:
                journey_id, pause_id = selection.split("::", 1)
            except ValueError:
                errors["base"] = "pause_invalid_selection"
            else:
                self._selected_pause_journey_id = journey_id
                self._selected_pause_id = pause_id
                return await self.async_step_pause_edit()

        schema: dict[Any, Any] = {}
        if pauses:
            options = [
                selector.SelectOptionDict(
                    value=pause["value"],
                    label=pause["label"],
                )
                for pause in pauses
            ]
            schema[
                vol.Required(
                    CONF_PAUSE_SELECTION,
                    default=options[0]["value"],
                )
            ] = selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=options,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            )

        return self.async_show_form(
            step_id="pause_management",
            data_schema=vol.Schema(schema),
            errors=errors,
            description_placeholders={"pause_count": str(len(pauses))},
        )

    async def async_step_pause_edit(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Edit one Journey pause."""

        if not self._selected_pause_journey_id or not self._selected_pause_id:
            return await self.async_step_pause_management()

        errors: dict[str, str] = {}
        journey = await self._get_journey_storage().load_journey_by_id(
            self._selected_pause_journey_id
        )
        if journey is None:
            errors["base"] = "pause_journey_not_found"
            return self.async_show_form(
                step_id="pause_edit",
                data_schema=vol.Schema({}),
                errors=errors,
            )

        override = dict(
            journey.pause_overrides.get(self._selected_pause_id, {})
        )
        pause_text = await self._async_get_pause_translations()

        if user_input is not None:
            action = user_input.get(CONF_PAUSE_ACTION, PAUSE_ACTION_SAVE)
            service = "clear_pause_edit" if action == PAUSE_ACTION_CLEAR else "edit_pause"
            service_data: dict[str, Any] = {
                "entry_id": self._config_entry.entry_id,
                "journey_id": self._selected_pause_journey_id,
                "pause_id": self._selected_pause_id,
            }

            if action == PAUSE_ACTION_SAVE:
                service_data.update(
                    {
                        "category": user_input.get(CONF_PAUSE_CATEGORY, ""),
                        "title": user_input.get(CONF_PAUSE_TITLE, ""),
                        "note": user_input.get(CONF_PAUSE_NOTE, ""),
                        "location": user_input.get(CONF_PAUSE_LOCATION, ""),
                        "cost_total": user_input.get(CONF_PAUSE_COST_TOTAL),
                        "currency": user_input.get(CONF_PAUSE_CURRENCY, "CHF"),
                    }
                )

            try:
                await self.hass.services.async_call(
                    DOMAIN,
                    service,
                    service_data,
                    blocking=True,
                    return_response=True,
                )
            except (HomeAssistantError, ValueError):
                errors["base"] = "pause_save_failed"
            else:
                self._pause_result = {
                    "journey_id": self._selected_pause_journey_id,
                    "pause_id": self._selected_pause_id,
                    "action": action,
                }
                return await self.async_step_pause_result()

        fields: dict[Any, Any] = {
            vol.Optional(
                CONF_PAUSE_CATEGORY,
                default=str(override.get("category") or "other"),
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        "food",
                        "shopping",
                        "leisure",
                        "work",
                        "parking",
                        "overnight",
                        "other",
                    ],
                    custom_value=True,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Optional(
                CONF_PAUSE_TITLE,
                default=str(override.get("title") or ""),
            ): selector.TextSelector(),
            vol.Optional(
                CONF_PAUSE_NOTE,
                default=str(override.get("note") or ""),
            ): selector.TextSelector(
                selector.TextSelectorConfig(multiline=True)
            ),
            vol.Optional(
                CONF_PAUSE_LOCATION,
                default=str(override.get("location") or ""),
            ): selector.TextSelector(),
            vol.Optional(
                CONF_PAUSE_COST_TOTAL,
                default=override.get("cost_total", 0),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0,
                    step=0.01,
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
            vol.Optional(
                CONF_PAUSE_CURRENCY,
                default=str(override.get("currency") or "CHF"),
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=["CHF", "EUR", "GBP", "USD"],
                    custom_value=True,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Required(
                CONF_PAUSE_ACTION,
                default=PAUSE_ACTION_SAVE,
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        selector.SelectOptionDict(
                            value=PAUSE_ACTION_SAVE,
                            label=pause_text["save"],
                        ),
                        selector.SelectOptionDict(
                            value=PAUSE_ACTION_CLEAR,
                            label=pause_text["clear"],
                        ),
                    ],
                    mode=selector.SelectSelectorMode.LIST,
                )
            ),
        }

        return self.async_show_form(
            step_id="pause_edit",
            data_schema=vol.Schema(fields),
            errors=errors,
            description_placeholders={
                "journey_id": self._selected_pause_journey_id,
                "pause_id": self._selected_pause_id,
                "current_title": str(override.get("title") or "—"),
            },
        )

    async def async_step_pause_result(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Show the result of a pause edit."""

        if user_input is not None:
            return await self.async_step_pause_management()

        return self.async_show_form(
            step_id="pause_result",
            data_schema=vol.Schema({}),
            description_placeholders=self._pause_result,
        )

    def _get_receipt_storage(self) -> FordTriplogReceiptStorage:
        """Return initialized receipt storage for this config entry."""

        runtime_data = self.hass.data.get(DOMAIN, {}).get(
            self._config_entry.entry_id, {}
        )
        storage = runtime_data.get("receipt_storage")
        if storage is None:
            raise HomeAssistantError("Receipt storage is not initialized")
        return storage

    async def async_step_receipt_management(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Show receipt management actions."""

        menu_options = ["ocr_settings"]
        if bool(self._options.get(CONF_OCR_ENABLED, False)):
            menu_options.append("receipt_ocr")
        menu_options.extend(
            [
                "receipt_import_type",
                "receipt_list",
                "receipt_delete",
            ]
        )

        return self.async_show_menu(
            step_id="receipt_management",
            menu_options=menu_options,
        )

    async def async_step_ocr_settings(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Configure and test the optional external OCR service."""

        errors: dict[str, str] = {}

        if user_input is not None:
            enabled = bool(user_input.get(CONF_OCR_ENABLED, False))
            url = str(user_input.get(CONF_OCR_URL) or "").strip().rstrip("/")
            api_key = str(user_input.get(CONF_OCR_API_KEY) or "").strip()
            timeout_seconds = int(user_input.get(CONF_OCR_TIMEOUT, 15))

            if enabled:
                try:
                    client = FordTriplogOCRClient(
                        async_get_clientsession(self.hass),
                        url,
                        api_key,
                        timeout_seconds,
                    )
                    health = await client.async_health()
                except ValueError:
                    errors["base"] = "ocr_invalid_url"
                except FordTriplogOCRAuthenticationError:
                    errors["base"] = "ocr_authentication_failed"
                except FordTriplogOCRConnectionError:
                    errors["base"] = "ocr_connection_failed"
                except FordTriplogOCRResponseError:
                    errors["base"] = "ocr_invalid_response"
                else:
                    updated_options = dict(self._config_entry.options)
                    updated_options.update(
                        {
                            CONF_OCR_ENABLED: True,
                            CONF_OCR_URL: client.base_url,
                            CONF_OCR_API_KEY: api_key,
                            CONF_OCR_TIMEOUT: timeout_seconds,
                        }
                    )
                    self.hass.config_entries.async_update_entry(
                        self._config_entry,
                        options=updated_options,
                    )
                    self._options.update(updated_options)
                    self._ocr_connection_result = {
                        "service": health.service,
                        "version": health.version,
                        "engine": health.engine,
                        "url": client.base_url,
                        "max_file_mb": (
                            str(health.max_file_mb)
                            if health.max_file_mb is not None
                            else "—"
                        ),
                        "pdf_mode": (
                            "Nur erste Seite"
                            if health.pdf_first_page_only
                            else "Alle Seiten / nicht angegeben"
                        ),
                    }
                    return await self.async_step_ocr_connection_result()
            else:
                updated_options = dict(self._config_entry.options)
                updated_options.update(
                    {
                        CONF_OCR_ENABLED: False,
                        CONF_OCR_URL: url,
                        CONF_OCR_API_KEY: api_key,
                        CONF_OCR_TIMEOUT: timeout_seconds,
                    }
                )
                self.hass.config_entries.async_update_entry(
                    self._config_entry,
                    options=updated_options,
                )
                self._options.update(updated_options)
                self._ocr_connection_result = {
                    "service": "OCR deaktiviert",
                    "version": "—",
                    "engine": "—",
                    "url": url or "—",
                    "max_file_mb": "—",
                    "pdf_mode": "—",
                }
                return await self.async_step_ocr_connection_result()

        current_enabled = bool(
            self._options.get(CONF_OCR_ENABLED, False)
        )
        current_url = str(
            self._options.get(CONF_OCR_URL, "http://")
        )
        current_api_key = str(
            self._options.get(CONF_OCR_API_KEY, "")
        )
        current_timeout = int(
            self._options.get(CONF_OCR_TIMEOUT, 15)
        )

        return self.async_show_form(
            step_id="ocr_settings",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_OCR_ENABLED,
                        default=current_enabled,
                    ): selector.BooleanSelector(),
                    vol.Required(
                        CONF_OCR_URL,
                        default=current_url,
                    ): selector.TextSelector(
                        selector.TextSelectorConfig(
                            type=selector.TextSelectorType.URL,
                        )
                    ),
                    vol.Optional(
                        CONF_OCR_API_KEY,
                        default=current_api_key,
                    ): selector.TextSelector(
                        selector.TextSelectorConfig(
                            type=selector.TextSelectorType.PASSWORD,
                        )
                    ),
                    vol.Required(
                        CONF_OCR_TIMEOUT,
                        default=current_timeout,
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=3,
                            max=120,
                            step=1,
                            unit_of_measurement="s",
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_ocr_connection_result(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Show the external OCR connection result."""

        if user_input is not None:
            return await self.async_step_receipt_management()

        return self.async_show_form(
            step_id="ocr_connection_result",
            data_schema=vol.Schema({}),
            description_placeholders=self._ocr_connection_result,
        )

    async def async_step_receipt_import_type(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Choose whether a receipt belongs to a pause or charge."""

        if user_input is not None:
            self._receipt_target_type = str(
                user_input[CONF_RECEIPT_TARGET_TYPE]
            )
            return await self.async_step_receipt_import()

        return self.async_show_form(
            step_id="receipt_import_type",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_RECEIPT_TARGET_TYPE,
                        default=RECEIPT_TARGET_PAUSE,
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                RECEIPT_TARGET_PAUSE,
                                RECEIPT_TARGET_CHARGE,
                            ],
                            translation_key="receipt_target_type",
                            mode=selector.SelectSelectorMode.LIST,
                        )
                    )
                }
            ),
        )

    async def _async_get_receipt_target_options(
        self,
    ) -> list[selector.SelectOptionDict]:
        """Return selectable receipt targets."""

        if self._receipt_target_type == RECEIPT_TARGET_PAUSE:
            entries = await self._async_get_pause_entries()
            return [
                selector.SelectOptionDict(
                    value=str(entry["pause_id"]),
                    label=str(entry["label"]),
                )
                for entry in entries
            ]

        if self._receipt_target_type == RECEIPT_TARGET_CHARGE:
            charges = await self._get_charge_manager().async_get_charges()
            return [
                selector.SelectOptionDict(
                    value=str(charge.charge_id),
                    label=self._format_charge_label(charge),
                )
                for charge in charges
                if charge.charge_id
            ]

        return []

    async def async_step_receipt_import(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Upload and attach one receipt."""

        if self._receipt_target_type not in (
            RECEIPT_TARGET_PAUSE,
            RECEIPT_TARGET_CHARGE,
        ):
            return await self.async_step_receipt_import_type()

        errors: dict[str, str] = {}
        try:
            targets = await self._async_get_receipt_target_options()
        except (HomeAssistantError, OSError, ValueError):
            targets = []
            errors["base"] = "receipt_target_load_failed"

        if not targets and not errors:
            errors["base"] = "receipt_no_targets"

        if user_input is not None and not errors:
            uploaded_file_id = user_input[CONF_RECEIPT_FILE]
            target_id = str(user_input[CONF_RECEIPT_TARGET])
            try:
                with process_uploaded_file(
                    self.hass,
                    uploaded_file_id,
                ) as uploaded_path:
                    receipt = await self._get_receipt_storage().async_import(
                        uploaded_path,
                        target_type=self._receipt_target_type,
                        target_id=target_id,
                        original_name=uploaded_path.name,
                        note=str(user_input.get(CONF_RECEIPT_NOTE) or ""),
                    )
            except (HomeAssistantError, OSError, ValueError):
                errors["base"] = "receipt_import_failed"
            else:
                self._receipt_result = {
                    "filename": str(receipt.get("original_filename") or receipt.get("filename") or ""),
                    "target_id": target_id,
                }
                return await self.async_step_receipt_result()

        schema: dict[Any, Any] = {}
        if targets:
            schema[
                vol.Required(
                    CONF_RECEIPT_TARGET,
                    default=targets[0]["value"],
                )
            ] = selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=targets,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            )
            schema[
                vol.Required(CONF_RECEIPT_FILE)
            ] = selector.FileSelector(
                selector.FileSelectorConfig(
                    accept=".pdf,.jpg,.jpeg,.png,.webp,application/pdf,image/jpeg,image/png,image/webp"
                )
            )
            schema[
                vol.Optional(CONF_RECEIPT_NOTE, default="")
            ] = selector.TextSelector(
                selector.TextSelectorConfig(multiline=True)
            )

        return self.async_show_form(
            step_id="receipt_import",
            data_schema=vol.Schema(schema),
            errors=errors,
        )

    async def _async_receipt_contexts(self) -> list[dict[str, Any]]:
        """Return receipts enriched with their pause or charge context."""

        receipts = await self._get_receipt_storage().async_list()
        pauses = {
            str(entry["pause_id"]): entry
            for entry in await self._async_get_pause_entries()
        }
        charges = {
            str(charge.charge_id): charge
            for charge in await self._get_charge_manager().async_get_charges()
            if charge.charge_id
        }

        enriched: list[dict[str, Any]] = []
        for receipt in receipts:
            item = dict(receipt)
            target_type = str(item.get("target_type") or "")
            target_id = str(item.get("target_id") or "")

            if target_type == RECEIPT_TARGET_PAUSE:
                pause = pauses.get(target_id, {})
                date_text = str(pause.get("date") or "—")
                time_text = str(pause.get("start_time") or "—")
                title = str(pause.get("title") or "Pause")
                location = str(pause.get("location") or "—")
                amount = pause.get("cost_total")
                currency = str(pause.get("currency") or "")
                label = f"⏸️ {date_text} {time_text} · {title} · {location}"
                kind = "Pause"
                soc = "—"
                energy = "—"
            else:
                charge = charges.get(target_id)
                date_text = self._format_charge_datetime(
                    getattr(charge, "start_time", None)
                ) if charge else "—"
                time_text = ""
                location = self._charge_location(charge) if charge else "—"
                title = location
                amount = getattr(charge, "cost_total", None) if charge else None
                currency = str(getattr(charge, "currency", None) or "") if charge else ""
                start_soc = getattr(charge, "start_soc", None) if charge else None
                end_soc = getattr(charge, "end_soc", None) if charge else None
                soc = (
                    f"{self._format_optional_number(start_soc, 0)} % → "
                    f"{self._format_optional_number(end_soc, 0)} %"
                )
                energy = (
                    f"{self._format_optional_number(getattr(charge, 'energy_added_kwh', None), 2)} kWh"
                    if charge else "—"
                )
                label = f"⚡ {date_text} · {location}"
                kind = "Ladevorgang"

            try:
                cost = f"{float(amount):.2f} {currency}".strip() if amount is not None else "—"
            except (TypeError, ValueError):
                cost = "—"

            item.update({
                "display_label": label,
                "display_type": kind,
                "display_date": date_text,
                "display_time": time_text,
                "display_title": title,
                "display_location": location,
                "display_cost": cost,
                "display_soc": soc,
                "display_energy": energy,
            })
            enriched.append(item)

        enriched.sort(
            key=lambda value: str(value.get("created_at") or ""),
            reverse=True,
        )
        return enriched

    async def async_step_receipt_list(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Select a receipt using its associated trip context."""

        errors: dict[str, str] = {}
        try:
            receipts = await self._async_receipt_contexts()
        except (HomeAssistantError, OSError, ValueError):
            receipts = []
            errors["base"] = "receipt_load_failed"

        options = [
            selector.SelectOptionDict(
                value=str(receipt.get("receipt_id")),
                label=str(receipt.get("display_label")),
            )
            for receipt in receipts
            if receipt.get("receipt_id")
        ]
        if not options and not errors:
            errors["base"] = "receipt_none_available"

        if user_input is not None and not errors:
            self._selected_receipt_id = str(
                user_input[CONF_RECEIPT_SELECTION]
            )
            return await self.async_step_receipt_detail()

        schema: dict[Any, Any] = {}
        if options:
            schema[
                vol.Required(
                    CONF_RECEIPT_SELECTION,
                    default=options[0]["value"],
                )
            ] = selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=options,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            )

        return self.async_show_form(
            step_id="receipt_list",
            data_schema=vol.Schema(schema),
            errors=errors,
            description_placeholders={"receipt_count": str(len(options))},
        )

    @staticmethod
    def _format_receipt_ocr_status(value: Any) -> str:
        """Return a translated-friendly OCR status label."""

        status = str(value or "not_started").strip().lower()
        labels = {
            "not_started": "Noch nicht ausgeführt",
            "queued": "Wartet",
            "running": "Wird verarbeitet",
            "completed": "Abgeschlossen",
            "failed": "Fehlgeschlagen",
        }
        return labels.get(status, status or "—")

    async def async_step_receipt_detail(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Show receipt details and offer an external browser step."""

        if user_input is not None:
            action = str(
                user_input.get(
                    CONF_RECEIPT_DETAIL_ACTION,
                    RECEIPT_DETAIL_OPEN,
                )
            )
            if action == RECEIPT_DETAIL_BACK:
                self._selected_receipt_url = None
                return await self.async_step_receipt_list()
            return await self.async_step_receipt_open()

        receipt_id = str(self._selected_receipt_id or "")
        receipts = await self._async_receipt_contexts()
        receipt = next(
            (
                item
                for item in receipts
                if str(item.get("receipt_id")) == receipt_id
            ),
            None,
        )
        if receipt is None:
            return self.async_show_form(
                step_id="receipt_detail",
                data_schema=vol.Schema({}),
                errors={"base": "receipt_not_found"},
            )

        size_bytes = int(receipt.get("size_bytes") or 0)
        size_text = (
            f"{size_bytes / 1024 / 1024:.1f} MB"
            if size_bytes >= 1024 * 1024
            else f"{max(1, round(size_bytes / 1024))} KB"
        )
        media_type = str(receipt.get("media_type") or "").lower()
        original_filename = str(
            receipt.get("original_filename")
            or receipt.get("filename")
            or ""
        )
        suffix = Path(original_filename).suffix.lower()

        if media_type == "application/pdf" or suffix == ".pdf":
            document_type = "PDF-Dokument"
        elif media_type.startswith("image/") or suffix in {
            ".jpg",
            ".jpeg",
            ".png",
            ".webp",
        }:
            document_type = "Bilddatei"
        else:
            document_type = "Dokument"

        receipt_path = f"/api/ford_triplog/receipts/{receipt_id}"
        signed_path = async_sign_path(
            self.hass,
            receipt_path,
            timedelta(minutes=10),
            use_content_user=True,
        )
        try:
            base_url = get_url(
                self.hass,
                allow_internal=True,
                allow_external=True,
                allow_cloud=True,
                allow_ip=True,
                prefer_external=False,
            ).rstrip("/")
            self._selected_receipt_url = f"{base_url}{signed_path}"
        except NoURLAvailableError:
            self._selected_receipt_url = signed_path

        return self.async_show_form(
            step_id="receipt_detail",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_RECEIPT_DETAIL_ACTION,
                        default=RECEIPT_DETAIL_OPEN,
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                selector.SelectOptionDict(
                                    value=RECEIPT_DETAIL_OPEN,
                                    label="Beleg im Browser öffnen",
                                ),
                                selector.SelectOptionDict(
                                    value=RECEIPT_DETAIL_BACK,
                                    label="Zurück zur Belegliste",
                                ),
                            ],
                            mode=selector.SelectSelectorMode.LIST,
                        )
                    )
                }
            ),
            description_placeholders={
                "type": str(receipt.get("display_type") or "—"),
                "date": str(receipt.get("display_date") or "—"),
                "title": str(receipt.get("display_title") or "—"),
                "location": str(receipt.get("display_location") or "—"),
                "soc": str(receipt.get("display_soc") or "—"),
                "energy": str(receipt.get("display_energy") or "—"),
                "cost": str(receipt.get("display_cost") or "—"),
                "document_type": document_type,
                "filename": document_type,
                "size": size_text,
                "ocr_status": self._format_receipt_ocr_status(
                    receipt.get("ocr_status")
                ),
            },
        )

    async def async_step_receipt_open(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Open the signed receipt URL using a Home Assistant external step."""

        if not self._selected_receipt_url:
            return await self.async_step_receipt_list()

        return self.async_external_step(
            step_id="receipt_open",
            url=self._selected_receipt_url,
        )

    def _get_ocr_client(self) -> FordTriplogOCRClient:
        """Return a configured client for the external OCR service."""

        if not bool(self._options.get(CONF_OCR_ENABLED, False)):
            raise HomeAssistantError("OCR is not enabled")

        return FordTriplogOCRClient(
            async_get_clientsession(self.hass),
            str(self._options.get(CONF_OCR_URL) or ""),
            str(self._options.get(CONF_OCR_API_KEY) or ""),
            int(self._options.get(CONF_OCR_TIMEOUT, 15)),
        )

    async def async_step_receipt_ocr(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Select a stored receipt and run external OCR."""

        errors: dict[str, str] = {}

        if not bool(self._options.get(CONF_OCR_ENABLED, False)):
            return self.async_show_form(
                step_id="receipt_ocr",
                data_schema=vol.Schema({}),
                errors={"base": "ocr_not_configured"},
            )

        try:
            receipts = await self._async_receipt_contexts()
        except (HomeAssistantError, OSError, RuntimeError, ValueError):
            receipts = []
            errors["base"] = "receipt_load_failed"

        options = [
            selector.SelectOptionDict(
                value=str(receipt.get("receipt_id")),
                label=str(
                    receipt.get("display_label")
                    or receipt.get("receipt_id")
                ),
            )
            for receipt in receipts
            if receipt.get("receipt_id")
        ]

        if not options and not errors:
            errors["base"] = "receipt_none_available"

        if user_input is not None and not errors:
            receipt_id = str(user_input[CONF_RECEIPT_OCR_SELECTION])

            try:
                receipt = await self._get_receipt_storage().async_analyze(
                    receipt_id,
                    self._get_ocr_client(),
                )
            except FordTriplogOCRAuthenticationError:
                errors["base"] = "ocr_authentication_failed"
            except FordTriplogOCRConnectionError:
                errors["base"] = "ocr_connection_failed"
            except FordTriplogOCRResponseError:
                errors["base"] = "receipt_ocr_response_failed"
            except (HomeAssistantError, OSError, RuntimeError, ValueError):
                errors["base"] = "receipt_ocr_failed"
            else:
                ocr_result = receipt.get("ocr_result", {})
                if not isinstance(ocr_result, dict):
                    ocr_result = {}

                raw_text = str(ocr_result.get("raw_text") or "").strip()
                display_text = raw_text
                if len(display_text) > 5000:
                    display_text = display_text[:5000] + "\n…"

                confidence = ocr_result.get("confidence")
                confidence_text = "—"
                if isinstance(confidence, (int, float)):
                    confidence_text = f"{float(confidence) * 100:.1f} %"

                elapsed = ocr_result.get("elapsed_seconds")
                elapsed_text = "—"
                if isinstance(elapsed, (int, float)):
                    elapsed_text = f"{float(elapsed):.3f} s"

                source_page = ocr_result.get("source_page")
                page_text = (
                    str(source_page)
                    if source_page is not None
                    else "—"
                )

                self._receipt_ocr_result = {
                    "document": str(
                        receipt.get("original_filename")
                        or "Beleg"
                    ),
                    "engine": str(
                        ocr_result.get("engine") or "—"
                    ),
                    "service_version": str(
                        ocr_result.get("service_version") or "—"
                    ),
                    "elapsed": elapsed_text,
                    "confidence": confidence_text,
                    "page": page_text,
                    "character_count": str(len(raw_text)),
                    "raw_text": display_text or "Kein Text erkannt.",
                }
                return await self.async_step_receipt_ocr_result()

        schema: dict[Any, Any] = {}
        if options:
            schema[
                vol.Required(
                    CONF_RECEIPT_OCR_SELECTION,
                    default=options[0]["value"],
                )
            ] = selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=options,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            )

        return self.async_show_form(
            step_id="receipt_ocr",
            data_schema=vol.Schema(schema),
            errors=errors,
        )

    async def async_step_receipt_ocr_result(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Show the stored external OCR result."""

        if user_input is not None:
            return await self.async_step_receipt_management()

        return self.async_show_form(
            step_id="receipt_ocr_result",
            data_schema=vol.Schema({}),
            description_placeholders=self._receipt_ocr_result,
        )

    async def async_step_receipt_delete(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Select and permanently remove one receipt."""

        errors: dict[str, str] = {}
        try:
            receipts = await self._async_receipt_contexts()
        except (HomeAssistantError, OSError, ValueError):
            receipts = []
            errors["base"] = "receipt_load_failed"

        options = [
            selector.SelectOptionDict(
                value=str(receipt.get("receipt_id")),
                label=str(receipt.get("display_label") or receipt.get("receipt_id")),
            )
            for receipt in receipts
            if receipt.get("receipt_id")
        ]
        if not options and not errors:
            errors["base"] = "receipt_none_available"

        if user_input is not None and not errors:
            receipt_id = str(user_input[CONF_RECEIPT_SELECTION])
            try:
                removed = await self._get_receipt_storage().async_remove(receipt_id)
            except (HomeAssistantError, OSError, ValueError):
                errors["base"] = "receipt_delete_failed"
            else:
                if removed is None:
                    errors["base"] = "receipt_not_found"
                else:
                    self._receipt_result = {
                        "filename": str(removed.get("original_filename") or removed.get("filename") or ""),
                        "target_id": "",
                    }
                    return await self.async_step_receipt_result()

        schema: dict[Any, Any] = {}
        if options:
            schema[
                vol.Required(
                    CONF_RECEIPT_SELECTION,
                    default=options[0]["value"],
                )
            ] = selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=options,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            )

        return self.async_show_form(
            step_id="receipt_delete",
            data_schema=vol.Schema(schema),
            errors=errors,
        )

    async def async_step_receipt_result(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Show receipt operation result."""

        if user_input is not None:
            return await self.async_step_receipt_management()
        return self.async_show_form(
            step_id="receipt_result",
            data_schema=vol.Schema({}),
            description_placeholders=self._receipt_result,
        )

    def _get_journey_rebuilder(self):
        """Return the Journey rebuilder for this config entry."""

        runtime_data = self.hass.data.get(
            DOMAIN,
            {},
        ).get(
            self._config_entry.entry_id,
            {},
        )

        rebuilder = runtime_data.get("journey_rebuilder")

        if rebuilder is None:
            raise HomeAssistantError(
                "Journey rebuilder is not initialized"
            )

        return rebuilder

    @staticmethod
    def _journey_date_schema(
        *,
        include_confirmation: bool = False,
    ) -> vol.Schema:
        """Build the optional Journey date-range schema."""

        fields: dict[Any, Any] = {
            vol.Optional("start_date"): selector.DateSelector(),
            vol.Optional("end_date"): selector.DateSelector(),
        }

        if include_confirmation:
            fields[
                vol.Required(
                    "confirm",
                    default=False,
                )
            ] = selector.BooleanSelector()

        return vol.Schema(fields)

    async def async_step_journey_management(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Show Journey maintenance actions."""

        return self.async_show_menu(
            step_id="journey_management",
            menu_options=[
                "journey_update",
                "journey_rebuild",
                "journey_delete",
            ],
        )

    async def async_step_journey_update(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Create missing Journeys in an optional date range."""

        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                result = await self._get_journey_rebuilder().async_update_journeys(
                    start_date=user_input.get("start_date"),
                    end_date=user_input.get("end_date"),
                )
            except (HomeAssistantError, ValueError):
                errors["base"] = "journey_operation_failed"
            else:
                self._journey_result = self._format_journey_result(
                    result.to_dict()
                )
                return await self.async_step_journey_result()

        return self.async_show_form(
            step_id="journey_update",
            data_schema=self._journey_date_schema(),
            errors=errors,
        )

    async def async_step_journey_rebuild(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Rebuild Journeys in an optional date range."""

        errors: dict[str, str] = {}

        if user_input is not None:
            if not user_input.get("confirm"):
                errors["base"] = "journey_confirmation_required"
            else:
                try:
                    result = await self._get_journey_rebuilder().async_rebuild_journeys(
                        start_date=user_input.get("start_date"),
                        end_date=user_input.get("end_date"),
                    )
                except (HomeAssistantError, ValueError):
                    errors["base"] = "journey_operation_failed"
                else:
                    self._journey_result = self._format_journey_result(
                        result.to_dict()
                    )
                    return await self.async_step_journey_result()

        return self.async_show_form(
            step_id="journey_rebuild",
            data_schema=self._journey_date_schema(
                include_confirmation=True
            ),
            errors=errors,
        )

    async def async_step_journey_delete(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Delete Journeys in an optional date range."""

        errors: dict[str, str] = {}

        if user_input is not None:
            if not user_input.get("confirm"):
                errors["base"] = "journey_confirmation_required"
            else:
                try:
                    result = await self._get_journey_rebuilder().async_delete_journeys(
                        start_date=user_input.get("start_date"),
                        end_date=user_input.get("end_date"),
                    )
                except (HomeAssistantError, ValueError):
                    errors["base"] = "journey_operation_failed"
                else:
                    self._journey_result = self._format_journey_result(
                        result.to_dict()
                    )
                    return await self.async_step_journey_result()

        return self.async_show_form(
            step_id="journey_delete",
            data_schema=self._journey_date_schema(
                include_confirmation=True
            ),
            errors=errors,
        )

    async def async_step_journey_result(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Show a Journey maintenance result."""

        if user_input is not None:
            return await self.async_step_journey_management()

        return self.async_show_form(
            step_id="journey_result",
            data_schema=vol.Schema({}),
            description_placeholders=self._journey_result,
        )

    @staticmethod
    def _format_journey_result(
        result: dict[str, Any],
    ) -> dict[str, str]:
        """Format result values for translation placeholders."""

        affected_dates = result.get("affected_dates") or []

        return {
            "mode": str(result.get("mode") or ""),
            "start_date": str(result.get("start_date") or "—"),
            "end_date": str(result.get("end_date") or "—"),
            "source_trips": str(result.get("source_trips", 0)),
            "source_charges": str(result.get("source_charges", 0)),
            "processed_records": str(result.get("processed_records", 0)),
            "journeys_created": str(result.get("journeys_created", 0)),
            "journeys_deleted": str(result.get("journeys_deleted", 0)),
            "source_files_skipped": str(
                result.get(
                    "source_files_skipped",
                    result.get("skipped_records", 0),
                )
            ),
            "affected_dates": ", ".join(affected_dates) or "—",
        }


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
            "common",
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
                f"component.{DOMAIN}.common.charging_site_{key}",
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

                vol.Optional(
                    CONF_JOURNEY_HOME_ZONE,
                    default=self._options.get(
                        CONF_JOURNEY_HOME_ZONE,
                        DEFAULT_JOURNEY_HOME_ZONE,
                    ),
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain="zone",
                    )
                ),

                vol.Optional(
                    CONF_HOME_TARIFF_ENABLED,
                    default=self._options.get(
                        CONF_HOME_TARIFF_ENABLED,
                        False,
                    ),
                ): selector.BooleanSelector(),

                vol.Optional(
                    CONF_HOME_TARIFF_SUMMER_PRICE,
                    default=self._options.get(
                        CONF_HOME_TARIFF_SUMMER_PRICE,
                        0.28,
                    ),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0,
                        max=10,
                        step=0.001,
                        unit_of_measurement="/kWh",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),

                vol.Optional(
                    CONF_HOME_TARIFF_WINTER_PRICE,
                    default=self._options.get(
                        CONF_HOME_TARIFF_WINTER_PRICE,
                        0.38,
                    ),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0,
                        max=10,
                        step=0.001,
                        unit_of_measurement="/kWh",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),

                vol.Optional(
                    CONF_HOME_TARIFF_CURRENCY,
                    default=self._options.get(
                        CONF_HOME_TARIFF_CURRENCY,
                        "CHF",
                    ),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            "CHF",
                            "EUR",
                            "GBP",
                            "USD",
                        ],
                        custom_value=True,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),

                vol.Optional(
                    CONF_JOURNEY_HOME_TIMEOUT,
                    default=self._options.get(
                        CONF_JOURNEY_HOME_TIMEOUT,
                        DEFAULT_JOURNEY_HOME_TIMEOUT,
                    ),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0,
                        max=120,
                        step=1,
                        unit_of_measurement="min",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),

                vol.Optional(
                    CONF_JOURNEY_MAX_GAP_HOURS,
                    default=self._options.get(
                        CONF_JOURNEY_MAX_GAP_HOURS,
                        DEFAULT_JOURNEY_MAX_GAP_HOURS,
                    ),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=1,
                        max=72,
                        step=1,
                        unit_of_measurement="h",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
            }
        )


#
# End of configuration flow.
#
