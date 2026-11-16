"""Constants for Ezlo Local integration."""

DOMAIN = "ezlo_local"
DEFAULT_PORT = 17000

# WebSocket methods
METHOD_HUB_INFO = "hub.info.get"
METHOD_DEVICES_LIST = "hub.devices.list"
METHOD_ITEMS_LIST = "hub.items.list"
METHOD_ITEM_VALUE_SET = "hub.item.value.set"
METHOD_PLUGIN_RUN = "hub.extensions.plugin.run"
METHOD_DEVICE_FORCE_REMOVE = "hub.device.force_remove"

# Z-Wave scripts
SCRIPT_ZWAVE_INCLUDE = "HUB:zwave/scripts/start_include"
SCRIPT_ZWAVE_STOP_INCLUDE = "HUB:zwave/scripts/stop_include"
SCRIPT_ZWAVE_EXCLUDE = "HUB:zwave/scripts/start_exclude"
SCRIPT_ZWAVE_STOP_EXCLUDE = "HUB:zwave/scripts/stop_exclude"
SCRIPT_ZWAVE_CHECK_DEVICE = "HUB:zwave/scripts/check_device"

# Broadcast subclasses
BROADCAST_ITEM_UPDATED = "hub.item.updated"
BROADCAST_DEVICE_ADDED = "hub.device.added"
BROADCAST_DEVICE_REMOVED = "hub.device.removed"
BROADCAST_PLUGIN_UI = "hub.extensions.plugin.ui_broadcast"

# Device categories mapped to HA platforms
CATEGORY_COVER = "window_cov"
CATEGORY_SWITCH = "switch"
CATEGORY_DIMMER = "dimmable_light"
CATEGORY_SENSOR = "generic_sensor"
CATEGORY_DOOR_LOCK = "door_lock"

CONF_SERIAL = "serial"

# Z-Wave operation events fired on the HA event bus
EVENT_ZWAVE_OPERATION = f"{DOMAIN}_zwave_operation"

# Z-Wave operation states
ZWAVE_STATE_IDLE = "idle"
ZWAVE_STATE_INCLUDING = "including"
ZWAVE_STATE_EXCLUDING = "excluding"
