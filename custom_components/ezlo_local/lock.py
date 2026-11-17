"""Lock platform for Ezlo Local integration."""

import logging
from typing import Any

from homeassistant.components.lock import LockEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import BROADCAST_ITEM_UPDATED, DOMAIN
from .hub import EzloHub

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up lock entities from a config entry."""
    hub: EzloHub = hass.data[DOMAIN][entry.entry_id]["hub"]
    entities = []

    for dev_id, device in hub.devices.items():
        if device.get("category") == "door_lock":
            lock_item = hub.get_item(dev_id, "door_lock")
            if lock_item:
                entities.append(EzloLock(hub, device, lock_item))

    async_add_entities(entities)


class EzloLock(LockEntity):
    """Representation of an Ezlo door lock."""

    _attr_has_entity_name = True

    def __init__(self, hub: EzloHub, device: dict, lock_item: dict) -> None:
        self._hub = hub
        self._device_id = device["_id"]
        self._lock_item_id = lock_item["_id"]

        info = device.get("info", {})
        self._attr_unique_id = f"{hub.serial}_{self._device_id}"
        self._attr_name = None  # Use device name
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            name=device.get("name", "Lock"),
            manufacturer=info.get("manufacturer", "Unknown"),
            model=info.get("model", "Unknown"),
            sw_version=info.get("firmware.stack"),
            via_device=(DOMAIN, hub.serial),
        )

        self._lock_state = lock_item.get("value")
        self._info = info

    @property
    def is_locked(self) -> bool | None:
        if self._lock_state == "secured":
            return True
        if self._lock_state == "unsecured":
            return False
        return None

    @property
    def is_jammed(self) -> bool:
        op_item = self._hub.get_item(self._device_id, "lock_operation")
        if op_item:
            return op_item.get("value") == "lock_jammed"
        return False

    @property
    def extra_state_attributes(self) -> dict:
        attrs = {
            "ezlo_id": self._device_id,
            "zwave_node": self._info.get("zwave.node"),
        }
        op_item = self._hub.get_item(self._device_id, "lock_operation")
        if op_item:
            attrs["last_operation"] = op_item.get("value")
        code_op = self._hub.get_item(self._device_id, "user_code_operation")
        if code_op:
            attrs["last_code_operation"] = code_op.get("value")
        return attrs

    async def async_lock(self, **kwargs: Any) -> None:
        await self._hub.set_item_value(self._lock_item_id, "secured")
        self._lock_state = "secured"
        self.async_write_ha_state()

    async def async_unlock(self, **kwargs: Any) -> None:
        await self._hub.set_item_value(self._lock_item_id, "unsecured")
        self._lock_state = "unsecured"
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
        if result.get("_id") == self._lock_item_id:
            self._lock_state = result.get("value")
            self.async_write_ha_state()
