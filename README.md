# Ezlo Local - Home Assistant Integration

A custom Home Assistant integration for Ezlo hubs (including Bali/Springs Window Fashions OEM gateways) with **fully local** control over WebSocket. No cloud dependency for device control.

## Features

- **mDNS auto-discovery** (`_ezlo._tcp.local.`) -- no hardcoded IP addresses
- **Manual setup** -- enter IP if mDNS discovery doesn't work
- **Cover entities** for motorized shades (position, open/close/stop)
- **Battery sensors** for battery-powered devices
- **Push-based updates** via persistent WebSocket connection
- **Z-Wave device management** via HA services:
  - `ezlo_local.zwave_include` -- add new Z-Wave devices
  - `ezlo_local.zwave_stop_include` -- stop inclusion
  - `ezlo_local.zwave_exclude` -- remove Z-Wave devices
  - `ezlo_local.zwave_stop_exclude` -- stop exclusion
- **Auto-reconnect** with exponential backoff

## Prerequisites

The hub must have anonymous local access enabled:
- `offlineAnonymousAccess: true`
- `offlineInsecureAccess: true`

These are set via the Ezlo cloud relay API (see setup notes below).

## Installation

### HACS (recommended)
1. Open **HACS** from the Home Assistant sidebar
2. Click the **3-dot menu** (top right corner)
3. Select **Custom repositories**
4. In the **Repository** field, paste: `https://github.com/matteovigni/homeassistant-ezlo-local`
5. In the **Type** dropdown, select **Integration**
6. Click **Add**
7. The integration will appear in the list -- click it and hit **Download**
8. Restart Home Assistant

### Manual
1. Copy the `custom_components/ezlo_local` folder to your HA `config/custom_components/` directory
2. Restart Home Assistant

## Setup

1. After restart, go to **Settings** > **Devices & Services**
2. The hub should be auto-discovered via mDNS. Click **Configure**.
3. Or click **Add Integration**, search for "Ezlo Local", and enter the hub IP manually.

## Adding/Removing Z-Wave Devices

Use the Developer Tools > Services page or create dashboard buttons:

### Add a device
1. Call service `ezlo_local.zwave_include`
2. Put the Z-Wave device into pairing mode (e.g., hold button for 3 seconds)
3. Wait for the device to appear (integration auto-reloads on new devices)
4. Call `ezlo_local.zwave_stop_include` to exit inclusion mode

### Remove a device
1. Call service `ezlo_local.zwave_exclude`
2. Trigger the Z-Wave device (e.g., press its button)
3. Call `ezlo_local.zwave_stop_exclude` to exit exclusion mode

### Dashboard buttons example
```yaml
type: horizontal-stack
cards:
  - type: button
    name: Add Device
    icon: mdi:plus-circle
    tap_action:
      action: call-service
      service: ezlo_local.zwave_include
  - type: button
    name: Stop
    icon: mdi:stop-circle
    tap_action:
      action: call-service
      service: ezlo_local.zwave_stop_include
  - type: button
    name: Remove Device
    icon: mdi:minus-circle
    tap_action:
      action: call-service
      service: ezlo_local.zwave_exclude
```

## Supported Devices

| Device Type | HA Platform | Items Used |
|---|---|---|
| Motorized shades / covers | `cover` | dimmer, dimmer_stop, shutter_state |
| Any device with battery | `sensor` | battery |

The integration maps Ezlo `window_cov` devices to HA cover entities. Additional device types (switches, dimmers, sensors, locks) can be added by extending the integration.

## Technical Details

- **Connection**: WebSocket to port 17000 (tries `ws://` then `wss://`)
- **Auth**: Anonymous (no credentials required after initial setup)
- **Updates**: Push-based via `hub.item.updated` broadcasts
- **Z-Wave events**: Fired as `ezlo_local_zwave_event` on the HA event bus
