"""Switch platform for Ezlo Local integration."""

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import BROADCAST_ITEM_UPDATED, DOMAIN
from .hub import EzloHub

_LOGGER = logging.getLogger(__name__)

# Categories that map to switches
SWITCH_CATEGORIES = {"switch", "generic_io"}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up switch entities from a config entry."""
    hub: EzloHub = hass.data[DOMAIN][entry.entry_id]["hub"]
    entities = []

    for dev_id, device in hub.devices.items():
        if device.get("category") not in SWITCH_CATEGORIES:
            continue
        # Skip controllers (e.g. 2gig secondary Z-Wave controllers)
        if device.get("subcategory") == "controller":
            continue
        # Use 'switch' item if available, fall back to 'basic'
        item = hub.get_item(dev_id, "switch") or hub.get_item(dev_id, "basic")
        if item and item.get("hasSetter"):
            entities.append(EzloSwitch(hub, device, item))

    async_add_entities(entities)


class EzloSwitch(SwitchEntity):
    """Representation of an Ezlo switch."""

    _attr_has_entity_name = True

    def __init__(self, hub: EzloHub, device: dict, item: dict) -> None:
        self._hub = hub
        self._device_id = device["_id"]
        self._item_id = item["_id"]
        self._state = bool(item.get("value"))

        info = device.get("info", {})
        self._attr_unique_id = f"{hub.serial}_{self._device_id}_switch"
        self._attr_name = None  # Use device name
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            name=device.get("name", "Switch"),
            manufacturer=info.get("manufacturer", "Unknown"),
            model=info.get("model", "Unknown"),
            sw_version=info.get("firmware.stack"),
            via_device=(DOMAIN, hub.serial),
        )
        self._info = info

    @property
    def is_on(self) -> bool:
        return self._state

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "ezlo_id": self._device_id,
            "zwave_node": self._info.get("zwave.node"),
        }

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._hub.set_item_value(self._item_id, True)
        self._state = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._hub.set_item_value(self._item_id, False)
        self._state = False
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        self._remove_listener = self._hub.add_listener(self._on_broadcast)

    async def async_will_remove_from_hass(self) -> None:
        if hasattr(self, "_remove_listener"):
            self._remove_listener()

    @callback
    def _on_broadcast(self, subclass: str, result: dict) -> None:
        if subclass != BROADCAST_ITEM_UPDATED:
            return
        if result.get("_id") != self._item_id:
            return
        self._state = bool(result.get("value"))
        self.async_write_ha_state()
