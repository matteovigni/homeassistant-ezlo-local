"""Config flow for Ezlo Local integration."""

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components import zeroconf
from homeassistant.data_entry_flow import FlowResult

from .const import CONF_SERIAL, DEFAULT_PORT, DOMAIN
from .hub import EzloHub

_LOGGER = logging.getLogger(__name__)


class EzloLocalConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Ezlo Local."""

    VERSION = 1

    def __init__(self) -> None:
        self._host: str | None = None
        self._port: int = DEFAULT_PORT
        self._serial: str | None = None
        self._name: str | None = None

    async def async_step_zeroconf(
        self, discovery_info: zeroconf.ZeroconfServiceInfo
    ) -> FlowResult:
        """Handle mDNS discovery."""
        self._host = str(discovery_info.host)
        self._port = discovery_info.port or DEFAULT_PORT
        props = discovery_info.properties
        self._serial = props.get("Serial") or props.get("serial")
        self._name = props.get("name") or f"Ezlo {self._serial}"

        if self._serial:
            await self.async_set_unique_id(self._serial)
            self._abort_if_unique_id_configured(updates={"host": self._host})

        self.context["title_placeholders"] = {"name": self._name}
        return await self.async_step_zeroconf_confirm()

    async def async_step_zeroconf_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Confirm mDNS discovery."""
        if user_input is not None:
            return await self._async_create_entry()

        return self.async_show_form(
            step_id="zeroconf_confirm",
            description_placeholders={
                "name": self._name,
                "host": self._host,
                "serial": self._serial or "unknown",
            },
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle manual configuration."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._host = user_input["host"]
            self._port = user_input.get("port", DEFAULT_PORT)
            hub = EzloHub(self._host, self._port)
            try:
                await hub.connect()
                self._serial = hub.serial
                self._name = f"Ezlo {self._serial}"
                await hub.disconnect()

                if self._serial:
                    await self.async_set_unique_id(self._serial)
                    self._abort_if_unique_id_configured()

                return await self._async_create_entry()
            except Exception:
                _LOGGER.exception("Failed to connect to hub")
                errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required("host"): str,
                vol.Optional("port", default=DEFAULT_PORT): int,
            }),
            errors=errors,
        )

    async def _async_create_entry(self) -> FlowResult:
        return self.async_create_entry(
            title=self._name or f"Ezlo {self._host}",
            data={
                "host": self._host,
                "port": self._port,
                CONF_SERIAL: self._serial,
            },
        )
