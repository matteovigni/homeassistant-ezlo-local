"""Ezlo Local integration for Home Assistant."""

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import device_registry as dr

from .const import (
    BROADCAST_DEVICE_ADDED,
    BROADCAST_DEVICE_REMOVED,
    BROADCAST_PLUGIN_UI,
    DOMAIN,
)
from .hub import EzloHub

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["cover", "sensor"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Ezlo Local from a config entry."""
    hub = EzloHub(entry.data["host"], entry.data.get("port", 17000))
    await hub.connect()
    await hub.refresh_devices()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = hub

    # Register the hub as a device
    dev_reg = dr.async_get(hass)
    dev_reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, hub.serial)},
        manufacturer="Ezlo (Springs Window Fashions OEM)",
        model=hub.model or "Ezlo Plus",
        name=entry.title,
        sw_version=hub.firmware,
    )

    # Listen for device add/remove broadcasts to trigger reload
    def _on_broadcast(subclass: str, result: dict) -> None:
        if subclass in (BROADCAST_DEVICE_ADDED, BROADCAST_DEVICE_REMOVED):
            _LOGGER.info("Device change detected, reloading integration")
            hass.async_create_task(
                hass.config_entries.async_reload(entry.entry_id)
            )
        elif subclass == BROADCAST_PLUGIN_UI:
            event = result.get("event", "")
            plugin = result.get("plugin", "")
            hass.bus.async_fire(f"{DOMAIN}_zwave_event", {
                "event": event,
                "plugin": plugin,
                "details": result,
            })

    hub.add_listener(_on_broadcast)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _register_services(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hub: EzloHub = hass.data[DOMAIN].pop(entry.entry_id)
        await hub.disconnect()
    return unload_ok


def _register_services(hass: HomeAssistant) -> None:
    """Register Z-Wave management services."""

    async def _get_hub(call: ServiceCall) -> EzloHub:
        entries = hass.data.get(DOMAIN, {})
        if not entries:
            raise ValueError("No Ezlo hub configured")
        entry_id = call.data.get("entry_id")
        if entry_id and entry_id in entries:
            return entries[entry_id]
        return next(iter(entries.values()))

    async def handle_zwave_include(call: ServiceCall) -> None:
        hub = await _get_hub(call)
        await hub.zwave_include()
        _LOGGER.info("Z-Wave inclusion mode started on %s", hub.serial)

    async def handle_zwave_stop_include(call: ServiceCall) -> None:
        hub = await _get_hub(call)
        await hub.zwave_stop_include()
        _LOGGER.info("Z-Wave inclusion mode stopped on %s", hub.serial)

    async def handle_zwave_exclude(call: ServiceCall) -> None:
        hub = await _get_hub(call)
        await hub.zwave_exclude()
        _LOGGER.info("Z-Wave exclusion mode started on %s", hub.serial)

    async def handle_zwave_stop_exclude(call: ServiceCall) -> None:
        hub = await _get_hub(call)
        await hub.zwave_stop_exclude()
        _LOGGER.info("Z-Wave exclusion mode stopped on %s", hub.serial)

    if not hass.services.has_service(DOMAIN, "zwave_include"):
        hass.services.async_register(DOMAIN, "zwave_include", handle_zwave_include)
        hass.services.async_register(DOMAIN, "zwave_stop_include", handle_zwave_stop_include)
        hass.services.async_register(DOMAIN, "zwave_exclude", handle_zwave_exclude)
        hass.services.async_register(DOMAIN, "zwave_stop_exclude", handle_zwave_stop_exclude)
