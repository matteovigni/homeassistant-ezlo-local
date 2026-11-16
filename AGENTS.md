# Ezlo Local - Development Guide

## Project Overview

Custom Home Assistant integration for Ezlo hubs (including Bali/Springs Window Fashions OEM gateways) with fully local WebSocket control. No cloud dependency for device control.

## Architecture

- `hub.py` - WebSocket connection manager. Handles connect (tries `ws://` then `wss://`), reconnect with exponential backoff, request/response matching, and broadcast listeners.
- `config_flow.py` - HA config flow with mDNS auto-discovery (`_ezlo._tcp.local.`) and manual IP entry.
- `cover.py` - Cover entities for motorized shades. Maps Ezlo `dimmer` item (0-100) to cover position; uses `dimmer_stop` (int, not bool) for stop.
- `sensor.py` - Battery sensor entities for devices with a `battery` item.
- `__init__.py` - Integration setup, hub device registration, broadcast listener for auto-reload on device add/remove, Z-Wave management services.
- `const.py` - Constants for WebSocket methods, broadcast subclasses, Z-Wave scripts.

## Hub API

- **Protocol**: WebSocket on port 17000, anonymous access (no auth needed)
- **Request format**: `{"method": "...", "id": "unique_id", "params": {}}`
- **Key methods**: `hub.info.get`, `hub.devices.list`, `hub.items.list`, `hub.item.value.set`
- **Broadcasts**: Hub sends `{"id": "ui_broadcast", "msg_subclass": "hub.item.updated", "result": {...}}` on state changes
- **Z-Wave management**: `hub.extensions.plugin.run` with scripts like `HUB:zwave/scripts/start_include`

## Item value types

Pay attention to each item's expected value type. The hub strictly validates types:
- `dimmer`: int (0-100)
- `dimmer_stop`, `dimmer_up`, `dimmer_down`: int (use 1, not true)
- `switch`: bool
- `battery`: int (read-only)
- `shutter_state`: string (read-only, values: "idle", "opening", "closing")

## Build & Test

No build step required. To test:
1. Copy `custom_components/ezlo_local` to a Home Assistant `config/custom_components/` directory
2. Restart Home Assistant
3. Add the integration via Settings > Devices & Services

## Versioning

- Version in `custom_components/ezlo_local/manifest.json` must match the git tag
- HACS requires a published GitHub release (not just a tag)
- Tag format: `v1.0.0`

## Hub Management

- Z-Wave operations (include/exclude) fire `ezlo_local_zwave_operation` events on the HA bus
- Persistent notifications are created/updated during operations with ID `ezlo_local_zwave_op`
- Device add/remove broadcasts trigger automatic integration reload
- `__init__.py` tracks Z-Wave state (`idle`/`including`/`excluding`) in `hass.data[DOMAIN][entry_id]["zwave_state"]`
- The Z-Wave Status sensor exposes full device list with details as `extra_state_attributes`
- Cover entities expose `ezlo_id` attribute for use with `force_remove_device` service

## Services

| Service | Parameters | Description |
|---|---|---|
| `zwave_include` | none | Start Z-Wave inclusion |
| `zwave_stop_include` | none | Stop inclusion |
| `zwave_exclude` | none | Start Z-Wave exclusion |
| `zwave_stop_exclude` | none | Stop exclusion |
| `force_remove_device` | `device_id` (string) | Force-remove device by Ezlo ID |
| `refresh_devices` | none | Re-fetch devices and reload |

## Adding support for new device types

1. Add the category constant to `const.py`
2. Create a new platform file (e.g., `switch.py`, `light.py`)
3. Add the platform name to `PLATFORMS` in `__init__.py`
4. Map Ezlo items to HA entity attributes, respecting value types
5. Subscribe to `BROADCAST_ITEM_UPDATED` for push-based state updates
