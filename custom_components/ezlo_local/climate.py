"""Climate platform for Ezlo Local integration."""

import logging
from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import BROADCAST_ITEM_UPDATED, DOMAIN
from .hub import EzloHub

_LOGGER = logging.getLogger(__name__)

# Ezlo mode -> HA mode
EZLO_TO_HVAC_MODE = {
    "off": HVACMode.OFF,
    "heat": HVACMode.HEAT,
    "cool": HVACMode.COOL,
    "auto": HVACMode.HEAT_COOL,
}
HVAC_MODE_TO_EZLO = {v: k for k, v in EZLO_TO_HVAC_MODE.items()}

# Ezlo operating state -> HA action
EZLO_TO_HVAC_ACTION = {
    "idle": HVACAction.IDLE,
    "heating": HVACAction.HEATING,
    "cooling": HVACAction.COOLING,
    "pending_heat": HVACAction.IDLE,
    "pending_cool": HVACAction.IDLE,
    "fan_only": HVACAction.FAN,
    "vent_economizer": HVACAction.FAN,
    "aux_heating": HVACAction.HEATING,
    "2nd_stage_heating": HVACAction.HEATING,
    "2nd_stage_cooling": HVACAction.COOLING,
    "2nd_stage_aux_heat": HVACAction.HEATING,
    "3rd_stage_aux_heat": HVACAction.HEATING,
}

# Ezlo fan mode -> HA fan mode
EZLO_TO_FAN_MODE = {
    "auto_low": "auto",
    "low": "on",
}
FAN_MODE_TO_EZLO = {v: k for k, v in EZLO_TO_FAN_MODE.items()}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up climate entities from a config entry."""
    hub: EzloHub = hass.data[DOMAIN][entry.entry_id]["hub"]
    entities = []

    for dev_id, device in hub.devices.items():
        if device.get("category") == "hvac":
            mode_item = hub.get_item(dev_id, "thermostat_mode")
            if mode_item:
                entities.append(EzloClimate(hub, device))

    async_add_entities(entities)


class EzloClimate(ClimateEntity):
    """Representation of an Ezlo thermostat."""

    _attr_has_entity_name = True
    _attr_temperature_unit = UnitOfTemperature.FAHRENHEIT
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.TARGET_TEMPERATURE_RANGE
        | ClimateEntityFeature.FAN_MODE
    )
    _attr_hvac_modes = [
        HVACMode.OFF, HVACMode.HEAT, HVACMode.COOL, HVACMode.HEAT_COOL,
    ]
    _attr_fan_modes = ["auto", "on"]
    _enable_turn_on_off_backwards_compatibility = False

    def __init__(self, hub: EzloHub, device: dict) -> None:
        self._hub = hub
        self._device_id = device["_id"]
        self._item_ids: dict[str, str] = {}

        info = device.get("info", {})
        self._attr_unique_id = f"{hub.serial}_{self._device_id}_climate"
        self._attr_name = None  # Use device name
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            name=device.get("name", "Thermostat"),
            manufacturer=info.get("manufacturer", "Unknown"),
            model=info.get("model", "Unknown"),
            sw_version=info.get("firmware.stack"),
            via_device=(DOMAIN, hub.serial),
        )

        # Cache item IDs for fast lookup
        for item_name in (
            "thermostat_mode", "thermostat_operating_state",
            "thermostat_fan_mode", "thermostat_fan_state",
            "thermostat_setpoint_heating", "thermostat_setpoint_cooling",
            "temp",
        ):
            item = hub.get_item(self._device_id, item_name)
            if item:
                self._item_ids[item_name] = item["_id"]

    def _get_item_value(self, name: str) -> Any:
        item_id = self._item_ids.get(name)
        if item_id and item_id in self._hub.items:
            return self._hub.items[item_id].get("value")
        return None

    @property
    def current_temperature(self) -> float | None:
        val = self._get_item_value("temp")
        return float(val) if val is not None else None

    @property
    def hvac_mode(self) -> HVACMode:
        mode = self._get_item_value("thermostat_mode")
        return EZLO_TO_HVAC_MODE.get(mode, HVACMode.OFF)

    @property
    def hvac_action(self) -> HVACAction | None:
        state = self._get_item_value("thermostat_operating_state")
        return EZLO_TO_HVAC_ACTION.get(state)

    @property
    def target_temperature(self) -> float | None:
        mode = self._get_item_value("thermostat_mode")
        if mode == "heat":
            val = self._get_item_value("thermostat_setpoint_heating")
        elif mode == "cool":
            val = self._get_item_value("thermostat_setpoint_cooling")
        else:
            return None
        return float(val) if val is not None else None

    @property
    def target_temperature_high(self) -> float | None:
        if self._get_item_value("thermostat_mode") == "auto":
            val = self._get_item_value("thermostat_setpoint_cooling")
            return float(val) if val is not None else None
        return None

    @property
    def target_temperature_low(self) -> float | None:
        if self._get_item_value("thermostat_mode") == "auto":
            val = self._get_item_value("thermostat_setpoint_heating")
            return float(val) if val is not None else None
        return None

    @property
    def fan_mode(self) -> str | None:
        mode = self._get_item_value("thermostat_fan_mode")
        return EZLO_TO_FAN_MODE.get(mode)

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "ezlo_id": self._device_id,
            "operating_state": self._get_item_value("thermostat_operating_state"),
            "fan_state": self._get_item_value("thermostat_fan_state"),
        }

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        ezlo_mode = HVAC_MODE_TO_EZLO.get(hvac_mode)
        if ezlo_mode and "thermostat_mode" in self._item_ids:
            await self._hub.set_item_value(
                self._item_ids["thermostat_mode"], ezlo_mode
            )

    async def async_set_temperature(self, **kwargs: Any) -> None:
        temp = kwargs.get(ATTR_TEMPERATURE)
        low = kwargs.get("target_temp_low")
        high = kwargs.get("target_temp_high")

        if temp is not None:
            mode = self._get_item_value("thermostat_mode")
            if mode == "heat" and "thermostat_setpoint_heating" in self._item_ids:
                await self._hub.set_item_value(
                    self._item_ids["thermostat_setpoint_heating"], temp
                )
            elif mode == "cool" and "thermostat_setpoint_cooling" in self._item_ids:
                await self._hub.set_item_value(
                    self._item_ids["thermostat_setpoint_cooling"], temp
                )

        if low is not None and "thermostat_setpoint_heating" in self._item_ids:
            await self._hub.set_item_value(
                self._item_ids["thermostat_setpoint_heating"], low
            )
        if high is not None and "thermostat_setpoint_cooling" in self._item_ids:
            await self._hub.set_item_value(
                self._item_ids["thermostat_setpoint_cooling"], high
            )

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        ezlo_fan = FAN_MODE_TO_EZLO.get(fan_mode)
        if ezlo_fan and "thermostat_fan_mode" in self._item_ids:
            await self._hub.set_item_value(
                self._item_ids["thermostat_fan_mode"], ezlo_fan
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
        if result.get("_id") in self._item_ids.values():
            self.async_write_ha_state()
