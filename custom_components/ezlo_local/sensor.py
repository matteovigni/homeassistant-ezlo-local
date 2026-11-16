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

from .const import (
    BROADCAST_ITEM_UPDATED,
    BROADCAST_PLUGIN_UI,
    DOMAIN,
    ZWAVE_STATE_EXCLUDING,
    ZWAVE_STATE_IDLE,
    ZWAVE_STATE_INCLUDING,
)
from .hub import EzloHub

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up sensor entities from a config entry."""
    entry_data = hass.data[DOMAIN][entry.entry_id]
    hub: EzloHub = entry_data["hub"]
    entities: list[SensorEntity] = []

    # Battery sensors for each device
    for dev_id, device in hub.devices.items():
        battery_item = hub.get_item(dev_id, "battery")
        if battery_item:
            entities.append(EzloBatterySensor(hub, device, battery_item))

    # Hub status sensor
    entities.append(EzloHubStatusSensor(hub, entry, entry_data))

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


class EzloHubStatusSensor(SensorEntity):
    """Shows the current Z-Wave network state and device count."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:z-wave"

    def __init__(
        self, hub: EzloHub, entry: ConfigEntry, entry_data: dict
    ) -> None:
        self._hub = hub
        self._entry_data = entry_data
        self._attr_unique_id = f"{hub.serial}_zwave_status"
        self._attr_name = "Z-Wave Status"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, hub.serial)},
        )

    @property
    def native_value(self) -> str:
        return self._entry_data.get("zwave_state", ZWAVE_STATE_IDLE)

    @property
    def extra_state_attributes(self) -> dict:
        devices = []
        for dev_id, dev in self._hub.devices.items():
            info = dev.get("info", {})
            battery = self._hub.get_item(dev_id, "battery")
            dimmer = self._hub.get_item(dev_id, "dimmer")
            devices.append({
                "name": dev.get("name"),
                "ezlo_id": dev_id,
                "category": dev.get("category"),
                "manufacturer": info.get("manufacturer"),
                "model": info.get("model"),
                "protocol": info.get("protocol"),
                "zwave_node": info.get("zwave.node"),
                "signal": info.get("signal_quality"),
                "reachable": dev.get("reachable"),
                "security": dev.get("security"),
                "firmware": info.get("firmware.stack"),
                "battery": battery.get("value") if battery else None,
                "position": dimmer.get("value") if dimmer else None,
            })

        return {
            "hub_serial": self._hub.serial,
            "hub_model": self._hub.model,
            "hub_firmware": self._hub.firmware,
            "hub_connected": self._hub.connected,
            "device_count": len(self._hub.devices),
            "devices": devices,
        }

    async def async_added_to_hass(self) -> None:
        self._remove_listener = self._hub.add_listener(self._on_broadcast)

    async def async_will_remove_from_hass(self) -> None:
        if hasattr(self, "_remove_listener"):
            self._remove_listener()

    @callback
    def _on_broadcast(self, subclass: str, result: dict) -> None:
        if subclass == BROADCAST_PLUGIN_UI:
            self.async_write_ha_state()
