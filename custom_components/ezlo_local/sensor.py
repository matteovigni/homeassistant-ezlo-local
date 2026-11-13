"""Sensor platform for Ezlo Local integration."""

import logging

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import BROADCAST_ITEM_UPDATED, DOMAIN
from .hub import EzloHub

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up sensor entities from a config entry."""
    hub: EzloHub = hass.data[DOMAIN][entry.entry_id]
    entities = []

    for dev_id, device in hub.devices.items():
        battery_item = hub.get_item(dev_id, "battery")
        if battery_item:
            entities.append(EzloBatterySensor(hub, device, battery_item))

    async_add_entities(entities)


class EzloBatterySensor(SensorEntity):
    """Battery level sensor for an Ezlo device."""

    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = PERCENTAGE

    def __init__(self, hub: EzloHub, device: dict, item: dict) -> None:
        self._hub = hub
        self._device_id = device["_id"]
        self._item_id = item["_id"]

        info = device.get("info", {})
        self._attr_unique_id = f"{hub.serial}_{self._item_id}"
        self._attr_name = "Battery"
        self._attr_native_value = item.get("value")
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            name=device.get("name", "Device"),
            manufacturer=info.get("manufacturer", "Unknown"),
            model=info.get("model", "Unknown"),
            via_device=(DOMAIN, hub.serial),
        )

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
        self._attr_native_value = result.get("value")
        self.async_write_ha_state()
