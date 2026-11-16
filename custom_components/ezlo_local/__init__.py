"""Ezlo Local integration for Home Assistant."""

import logging

import voluptuous as vol

from homeassistant.components import persistent_notification
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.helpers import device_registry as dr

from .const import (
    BROADCAST_DEVICE_ADDED,
    BROADCAST_DEVICE_REMOVED,
    BROADCAST_PLUGIN_UI,
    DOMAIN,
    EVENT_ZWAVE_OPERATION,
    ZWAVE_STATE_EXCLUDING,
    ZWAVE_STATE_IDLE,
    ZWAVE_STATE_INCLUDING,
)
from .hub import EzloHub

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["cover", "sensor"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Ezlo Local from a config entry."""
    hub = EzloHub(entry.data["host"], entry.data.get("port", 17000))
    await hub.connect()
    await hub.refresh_devices()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "hub": hub,
        "zwave_state": ZWAVE_STATE_IDLE,
    }

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

    # Register each Z-Wave device in the HA device registry
    _register_child_devices(hass, entry, hub)

    # Listen for broadcasts
    def _on_broadcast(subclass: str, result: dict) -> None:
        if subclass == BROADCAST_DEVICE_ADDED:
            _LOGGER.info("Device added broadcast: %s", result.get("_id"))
            persistent_notification.async_create(
                hass,
                f"New Z-Wave device added to hub. "
                f"Restart the integration to configure it.\n\n"
                f"Device ID: `{result.get('_id')}`",
                title="Ezlo: Device Added",
                notification_id=f"{DOMAIN}_device_added",
            )
            hass.async_create_task(hub.refresh_devices())
            hass.async_create_task(
                hass.config_entries.async_reload(entry.entry_id)
            )

        elif subclass == BROADCAST_DEVICE_REMOVED:
            dev_id = result.get("_id")
            _LOGGER.info("Device removed broadcast: %s", dev_id)
            persistent_notification.async_create(
                hass,
                f"Z-Wave device removed from hub.\n\n"
                f"Device ID: `{dev_id}`",
                title="Ezlo: Device Removed",
                notification_id=f"{DOMAIN}_device_removed",
            )
            hass.async_create_task(hub.refresh_devices())
            hass.async_create_task(
                hass.config_entries.async_reload(entry.entry_id)
            )

        elif subclass == BROADCAST_PLUGIN_UI:
            event_name = result.get("event", "")
            plugin = result.get("plugin", "")
            status = result.get("status", "")
            completed = result.get("completed", 0)
            error = result.get("error")

            # Fire HA event for automations / frontend
            hass.bus.async_fire(EVENT_ZWAVE_OPERATION, {
                "event": event_name,
                "plugin": plugin,
                "status": status,
                "completed": completed,
                "error": error,
                "details": result,
            })

            # Track state and send notifications
            entry_data = hass.data[DOMAIN].get(entry.entry_id, {})

            if event_name == "include_invoked":
                entry_data["zwave_state"] = ZWAVE_STATE_INCLUDING
                persistent_notification.async_create(
                    hass,
                    "Z-Wave **inclusion** mode active.\n\n"
                    "Put your device into pairing mode now "
                    "(usually hold a button for 3 seconds).",
                    title="Ezlo: Adding Device...",
                    notification_id=f"{DOMAIN}_zwave_op",
                )

            elif event_name == "exclude_invoked":
                entry_data["zwave_state"] = ZWAVE_STATE_EXCLUDING
                persistent_notification.async_create(
                    hass,
                    "Z-Wave **exclusion** mode active.\n\n"
                    "Trigger the device you want to remove "
                    "(usually press its button).",
                    title="Ezlo: Removing Device...",
                    notification_id=f"{DOMAIN}_zwave_op",
                )

            elif status == "finished":
                entry_data["zwave_state"] = ZWAVE_STATE_IDLE
                if error:
                    persistent_notification.async_create(
                        hass,
                        f"Z-Wave operation failed.\n\n"
                        f"Error: `{error}`",
                        title="Ezlo: Operation Failed",
                        notification_id=f"{DOMAIN}_zwave_op",
                    )
                else:
                    persistent_notification.async_dismiss(
                        hass, f"{DOMAIN}_zwave_op"
                    )

            elif status == "started":
                pct = completed or 0
                if pct > 0 and pct < 100:
                    persistent_notification.async_create(
                        hass,
                        f"Z-Wave operation in progress: **{pct}%**",
                        title="Ezlo: Working...",
                        notification_id=f"{DOMAIN}_zwave_op",
                    )

    hub.add_listener(_on_broadcast)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _register_services(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        entry_data = hass.data[DOMAIN].pop(entry.entry_id)
        hub = entry_data["hub"]
        await hub.disconnect()
    return unload_ok


def _register_child_devices(
    hass: HomeAssistant, entry: ConfigEntry, hub: EzloHub
) -> None:
    """Register each hub device in the HA device registry."""
    dev_reg = dr.async_get(hass)
    for dev_id, device in hub.devices.items():
        info = device.get("info", {})
        dev_reg.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, dev_id)},
            name=device.get("name", "Unknown"),
            manufacturer=info.get("manufacturer", "Unknown"),
            model=info.get("model", "Unknown"),
            sw_version=info.get("firmware.stack"),
            via_device=(DOMAIN, hub.serial),
        )


def _register_services(hass: HomeAssistant) -> None:
    """Register Z-Wave management services."""
    if hass.services.has_service(DOMAIN, "zwave_include"):
        return

    async def _get_hub(call: ServiceCall) -> EzloHub:
        entries = hass.data.get(DOMAIN, {})
        if not entries:
            raise ValueError("No Ezlo hub configured")
        entry_id = call.data.get("entry_id")
        if entry_id and entry_id in entries:
            return entries[entry_id]["hub"]
        return next(iter(entries.values()))["hub"]

    async def handle_zwave_include(call: ServiceCall) -> None:
        """Start Z-Wave inclusion mode."""
        hub = await _get_hub(call)
        await hub.zwave_include()
        _LOGGER.info("Z-Wave inclusion started on %s", hub.serial)

    async def handle_zwave_stop_include(call: ServiceCall) -> None:
        """Stop Z-Wave inclusion mode."""
        hub = await _get_hub(call)
        await hub.zwave_stop_include()
        persistent_notification.async_dismiss(hass, f"{DOMAIN}_zwave_op")
        for data in hass.data.get(DOMAIN, {}).values():
            data["zwave_state"] = ZWAVE_STATE_IDLE
        _LOGGER.info("Z-Wave inclusion stopped on %s", hub.serial)

    async def handle_zwave_exclude(call: ServiceCall) -> None:
        """Start Z-Wave exclusion mode."""
        hub = await _get_hub(call)
        await hub.zwave_exclude()
        _LOGGER.info("Z-Wave exclusion started on %s", hub.serial)

    async def handle_zwave_stop_exclude(call: ServiceCall) -> None:
        """Stop Z-Wave exclusion mode."""
        hub = await _get_hub(call)
        await hub.zwave_stop_exclude()
        persistent_notification.async_dismiss(hass, f"{DOMAIN}_zwave_op")
        for data in hass.data.get(DOMAIN, {}).values():
            data["zwave_state"] = ZWAVE_STATE_IDLE
        _LOGGER.info("Z-Wave exclusion stopped on %s", hub.serial)

    async def handle_force_remove(call: ServiceCall) -> None:
        """Force-remove a device from the hub by ID or name."""
        hub = await _get_hub(call)
        device_id = call.data.get("device_id")
        device_name = call.data.get("device_name")

        # Read from an input_text helper entity if provided
        entity_id = call.data.get("input_text_entity")
        if entity_id and not device_id and not device_name:
            state = hass.states.get(entity_id)
            if state and state.state not in ("", "unknown", "unavailable"):
                device_name = state.state

        if not device_id and not device_name:
            raise ValueError("Provide device_id, device_name, or input_text_entity")

        if not device_id and device_name:
            # Look up by name (case-insensitive)
            name_lower = device_name.lower()
            for did, dev in hub.devices.items():
                if dev.get("name", "").lower() == name_lower:
                    device_id = did
                    break
            if not device_id:
                persistent_notification.async_create(
                    hass,
                    f"No device found with name **{device_name}**.\n\n"
                    f"Call `ezlo_local.list_devices` to see all devices.",
                    title="Ezlo: Device Not Found",
                    notification_id=f"{DOMAIN}_device_removed",
                )
                return

        try:
            await hub.device_force_remove(device_id)
            persistent_notification.async_create(
                hass,
                f"Device `{device_id}` removed from hub.",
                title="Ezlo: Device Removed",
                notification_id=f"{DOMAIN}_device_removed",
            )
            await hub.refresh_devices()
            # Reload to remove stale entities
            for eid in list(hass.data.get(DOMAIN, {}).keys()):
                hass.async_create_task(
                    hass.config_entries.async_reload(eid)
                )
        except Exception as err:
            _LOGGER.error("Failed to remove device %s: %s", device_id, err)
            persistent_notification.async_create(
                hass,
                f"Failed to remove device `{device_id}`.\n\n"
                f"Error: `{err}`\n\n"
                f"Try using Z-Wave exclusion instead.",
                title="Ezlo: Remove Failed",
                notification_id=f"{DOMAIN}_device_removed",
            )

    async def handle_refresh_devices(call: ServiceCall) -> None:
        """Refresh the device list from the hub."""
        hub = await _get_hub(call)
        await hub.refresh_devices()
        _LOGGER.info("Refreshed %d devices from hub %s", len(hub.devices), hub.serial)
        for eid in list(hass.data.get(DOMAIN, {}).keys()):
            hass.async_create_task(
                hass.config_entries.async_reload(eid)
            )

    async def handle_list_devices(call: ServiceCall) -> None:
        """List all devices on the hub as a persistent notification."""
        hub = await _get_hub(call)
        await hub.refresh_devices()

        if not hub.devices:
            persistent_notification.async_create(
                hass,
                "No devices paired to the hub.",
                title="Ezlo: Device List",
                notification_id=f"{DOMAIN}_device_list",
            )
            return

        lines = [
            "| # | Name | Ezlo ID | Node | Model | Signal | Battery |",
            "|---|------|---------|------|-------|--------|---------|",
        ]
        for idx, (dev_id, dev) in enumerate(hub.devices.items(), 1):
            info = dev.get("info", {})
            battery = hub.get_item(dev_id, "battery")
            bat_val = f"{battery.get('value')}%" if battery else "n/a"
            lines.append(
                f"| {idx} | {dev.get('name', '?')} | `{dev_id}` "
                f"| {info.get('zwave.node', '?')} "
                f"| {info.get('model', '?')} "
                f"| {info.get('signal_quality', '?')} "
                f"| {bat_val} |"
            )

        lines.append("")
        lines.append(
            "To force-remove a device, call `ezlo_local.force_remove_device` "
            "with the **Ezlo ID** from the table above."
        )

        persistent_notification.async_create(
            hass,
            "\n".join(lines),
            title=f"Ezlo: {len(hub.devices)} Device(s)",
            notification_id=f"{DOMAIN}_device_list",
        )

    hass.services.async_register(DOMAIN, "zwave_include", handle_zwave_include)
    hass.services.async_register(DOMAIN, "zwave_stop_include", handle_zwave_stop_include)
    hass.services.async_register(DOMAIN, "zwave_exclude", handle_zwave_exclude)
    hass.services.async_register(DOMAIN, "zwave_stop_exclude", handle_zwave_stop_exclude)
    hass.services.async_register(
        DOMAIN, "force_remove_device", handle_force_remove,
        schema=vol.Schema({
            vol.Optional("device_id"): str,
            vol.Optional("device_name"): str,
            vol.Optional("input_text_entity"): str,
        }),
    )
    hass.services.async_register(DOMAIN, "refresh_devices", handle_refresh_devices)
    hass.services.async_register(DOMAIN, "list_devices", handle_list_devices)
