"""Cover platform for Ezlo Local integration."""

import logging
from typing import Any

from homeassistant.components.cover import (
    ATTR_POSITION,
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import BROADCAST_ITEM_UPDATED, CATEGORY_COVER, DOMAIN
from .hub import EzloHub

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up cover entities from a config entry."""
    hub: EzloHub = hass.data[DOMAIN][entry.entry_id]
    entities = []

    for dev_id, device in hub.devices.items():
        if device.get("category") == CATEGORY_COVER:
            entities.append(EzloCover(hub, device, entry))

    async_add_entities(entities)


class EzloCover(CoverEntity):
    """Representation of an Ezlo shade/cover."""

    _attr_has_entity_name = True
    _attr_device_class = CoverDeviceClass.SHADE
    _attr_supported_features = (
        CoverEntityFeature.OPEN
        | CoverEntityFeature.CLOSE
        | CoverEntityFeature.STOP
        | CoverEntityFeature.SET_POSITION
    )

    def __init__(self, hub: EzloHub, device: dict, entry: ConfigEntry) -> None:
        self._hub = hub
        self._device = device
        self._device_id = device["_id"]
        self._entry = entry

        info = device.get("info", {})
        self._attr_unique_id = f"{hub.serial}_{self._device_id}"
        self._attr_name = device.get("name", "Shade")
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            name=device.get("name", "Shade"),
            manufacturer=info.get("manufacturer", "Springs Window Fashions"),
            model=info.get("model", "RRZB"),
            sw_version=info.get("firmware.stack"),
            via_device=(DOMAIN, hub.serial),
        )

        self._position: int | None = None
        self._state: str | None = None
        self._update_from_items()

    def _update_from_items(self) -> None:
        """Pull current state from cached items."""
        dimmer = self._hub.get_item(self._device_id, "dimmer")
        if dimmer:
            self._position = dimmer.get("value")
        state = self._hub.get_item(self._device_id, "shutter_state")
        if state:
            self._state = state.get("value")

    async def async_added_to_hass(self) -> None:
        """Subscribe to hub broadcasts."""
        self._remove_listener = self._hub.add_listener(self._on_broadcast)

    async def async_will_remove_from_hass(self) -> None:
        if hasattr(self, "_remove_listener"):
            self._remove_listener()

    @callback
    def _on_broadcast(self, subclass: str, result: dict) -> None:
        """Handle hub broadcast."""
        if subclass != BROADCAST_ITEM_UPDATED:
            return
        if result.get("deviceId") != self._device_id:
            return

        name = result.get("name")
        if name == "dimmer":
            self._position = result.get("value")
            self.async_write_ha_state()
        elif name == "shutter_state":
            self._state = result.get("value")
            self.async_write_ha_state()

    @property
    def current_cover_position(self) -> int | None:
        return self._position

    @property
    def is_closed(self) -> bool | None:
        if self._position is not None:
            return self._position == 0
        return None

    @property
    def is_opening(self) -> bool:
        return self._state == "opening" if self._state else False

    @property
    def is_closing(self) -> bool:
        return self._state == "closing" if self._state else False

    async def async_open_cover(self, **kwargs: Any) -> None:
        await self._set_position(100)

    async def async_close_cover(self, **kwargs: Any) -> None:
        await self._set_position(0)

    async def async_set_cover_position(self, **kwargs: Any) -> None:
        position = kwargs.get(ATTR_POSITION)
        if position is not None:
            await self._set_position(position)

    async def async_stop_cover(self, **kwargs: Any) -> None:
        item = self._hub.get_item(self._device_id, "dimmer_stop")
        if item:
            await self._hub.set_item_value(item["_id"], True)

    async def _set_position(self, position: int) -> None:
        item = self._hub.get_item(self._device_id, "dimmer")
        if item:
            await self._hub.set_item_value(item["_id"], position)
            self._position = position
            self.async_write_ha_state()
