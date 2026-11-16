# Ezlo Local - Home Assistant Integration

A custom Home Assistant integration for Ezlo hubs (including Bali/Springs Window Fashions OEM gateways) with **fully local** control over WebSocket. No cloud dependency for device control.

## Features

- **mDNS auto-discovery** (`_ezlo._tcp.local.`) -- no hardcoded IP addresses
- **Manual setup** -- enter IP if mDNS discovery doesn't work
- **Cover entities** for motorized shades (position, open/close/stop)
- **Battery sensors** for battery-powered devices
- **Z-Wave hub status sensor** with full device list and details
- **Push-based updates** via persistent WebSocket connection
- **Z-Wave device management** via HA services:
  - `ezlo_local.zwave_include` -- add new Z-Wave devices
  - `ezlo_local.zwave_stop_include` -- stop inclusion
  - `ezlo_local.zwave_exclude` -- remove Z-Wave devices
  - `ezlo_local.zwave_stop_exclude` -- stop exclusion
  - `ezlo_local.force_remove_device` -- force-remove a device by ID
  - `ezlo_local.refresh_devices` -- refresh device list and reload
- **Persistent notifications** for inclusion/exclusion progress
- **HA events** (`ezlo_local_zwave_operation`) for automations
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

## Z-Wave Device Management

The integration provides persistent notifications during Z-Wave operations so you always know what's happening. When a device is added or removed, the integration automatically reloads.

### Add a device
1. Call service `ezlo_local.zwave_include` (or use a dashboard button)
2. A notification will appear: "Put your device into pairing mode now"
3. Put the Z-Wave device into pairing mode (e.g., hold button for 3 seconds)
4. Wait for the notification to confirm success
5. The integration reloads automatically and the new device appears

### Remove a device
1. Call service `ezlo_local.zwave_exclude`
2. A notification will appear: "Trigger the device you want to remove"
3. Press the device's button
4. The integration reloads automatically

### Force remove (for unreachable devices)
1. Find the device's Ezlo ID in its entity attributes (`ezlo_id`)
2. Call service `ezlo_local.force_remove_device` with `device_id: <ezlo_id>`

### Refresh device list
Call `ezlo_local.refresh_devices` to re-fetch all devices from the hub and reload.

## Hub Management Dashboard

Create a dashboard view for managing your Ezlo hub. Copy this YAML into a new dashboard:

```yaml
title: Ezlo Hub Management
views:
  - title: Hub
    cards:
      # Hub status
      - type: entities
        title: Hub Status
        entities:
          - entity: sensor.ezlo_local_z_wave_status
            name: Z-Wave Network

      # Z-Wave management buttons
      - type: horizontal-stack
        cards:
          - type: button
            name: Add Device
            icon: mdi:plus-circle
            icon_height: 40px
            tap_action:
              action: call-service
              service: ezlo_local.zwave_include
          - type: button
            name: Stop
            icon: mdi:stop-circle
            icon_height: 40px
            tap_action:
              action: call-service
              service: ezlo_local.zwave_stop_include
          - type: button
            name: Remove Device
            icon: mdi:minus-circle
            icon_height: 40px
            tap_action:
              action: call-service
              service: ezlo_local.zwave_exclude
          - type: button
            name: Refresh
            icon: mdi:refresh
            icon_height: 40px
            tap_action:
              action: call-service
              service: ezlo_local.refresh_devices

      # Device list with details
      - type: markdown
        title: Connected Devices
        content: >
          {% set status = state_attr('sensor.ezlo_local_z_wave_status', 'devices') %}
          {% if status %}
          | Name | Node | Signal | Battery | Model |
          |------|------|--------|---------|-------|
          {% for dev in status %}
          | {{ dev.name }} | {{ dev.zwave_node }} | {{ dev.signal }} | {{ dev.battery }}% | {{ dev.model }} |
          {% endfor %}
          {% else %}
          No devices found.
          {% endif %}
```

## Supported Devices

| Device Type | HA Platform | Items Used |
|---|---|---|
| Motorized shades / covers | `cover` | dimmer, dimmer_stop, shutter_state |
| Any device with battery | `sensor` | battery |
| Hub status | `sensor` | Z-Wave state + device list |

The integration maps Ezlo `window_cov` devices to HA cover entities. Additional device types (switches, dimmers, sensors, locks) can be added by extending the integration.

## Entity Attributes

### Cover entities
- `ezlo_id` -- Ezlo device ID (needed for force_remove)
- `zwave_node` -- Z-Wave node number
- `signal_quality` -- Signal strength (good/fair/poor)
- `security` -- Z-Wave security level
- `protocol` -- Protocol (zwave)

### Z-Wave Status sensor
- `hub_serial`, `hub_model`, `hub_firmware` -- Hub info
- `hub_connected` -- WebSocket connection status
- `device_count` -- Number of paired devices
- `devices` -- Full list with name, node, signal, battery, model, etc.

## Technical Details

- **Connection**: WebSocket to port 17000 (tries `ws://` then `wss://`)
- **Auth**: Anonymous (no credentials required after initial setup)
- **Updates**: Push-based via `hub.item.updated` broadcasts
- **Z-Wave events**: Fired as `ezlo_local_zwave_operation` on the HA event bus
- **Notifications**: Persistent notifications during inclusion/exclusion operations
