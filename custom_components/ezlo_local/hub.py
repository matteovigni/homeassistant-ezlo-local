"""Ezlo hub WebSocket connection manager."""

import asyncio
import json
import logging
import ssl
from typing import Any, Callable

import websockets

from .const import (
    BROADCAST_DEVICE_ADDED,
    BROADCAST_DEVICE_REMOVED,
    BROADCAST_ITEM_UPDATED,
    BROADCAST_PLUGIN_UI,
    DEFAULT_PORT,
    METHOD_DEVICE_FORCE_REMOVE,
    METHOD_DEVICES_LIST,
    METHOD_HUB_INFO,
    METHOD_ITEMS_LIST,
    METHOD_ITEM_VALUE_SET,
    METHOD_PLUGIN_RUN,
    SCRIPT_ZWAVE_EXCLUDE,
    SCRIPT_ZWAVE_INCLUDE,
    SCRIPT_ZWAVE_STOP_EXCLUDE,
    SCRIPT_ZWAVE_STOP_INCLUDE,
)

_LOGGER = logging.getLogger(__name__)


class EzloHub:
    """Manages a persistent WebSocket connection to an Ezlo hub."""

    def __init__(self, host: str, port: int = DEFAULT_PORT) -> None:
        self.host = host
        self.port = port
        self._ws: websockets.WebSocketClientProtocol | None = None
        self._msg_id = 0
        self._pending: dict[str, asyncio.Future] = {}
        self._listeners: list[Callable] = []
        self._listen_task: asyncio.Task | None = None
        self._connected = False
        self._reconnect_task: asyncio.Task | None = None

        self.serial: str | None = None
        self.model: str | None = None
        self.firmware: str | None = None
        self.devices: dict[str, dict] = {}
        self.items: dict[str, dict] = {}
        self._items_by_device: dict[str, list[dict]] = {}

    @property
    def connected(self) -> bool:
        return self._connected and self._ws is not None

    def add_listener(self, callback: Callable) -> Callable:
        """Register a broadcast listener. Returns a remove callable."""
        self._listeners.append(callback)
        def remove():
            self._listeners.remove(callback)
        return remove

    async def connect(self) -> None:
        """Connect to the hub, trying plain ws:// first then wss://."""
        connect_kwargs = {"ping_interval": 30, "ping_timeout": 10, "close_timeout": 5}

        for scheme in ("ws", "wss"):
            uri = f"{scheme}://{self.host}:{self.port}"
            kwargs = dict(connect_kwargs)
            if scheme == "wss":
                ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
                ssl_ctx.check_hostname = False
                ssl_ctx.verify_mode = ssl.CERT_NONE
                kwargs["ssl"] = ssl_ctx
            try:
                _LOGGER.debug("Trying %s connection to Ezlo hub", uri)
                self._ws = await asyncio.wait_for(
                    websockets.connect(uri, **kwargs), timeout=10
                )
                _LOGGER.info("Connected to Ezlo hub at %s", uri)
                break
            except Exception:
                _LOGGER.debug("Connection via %s failed, trying next", scheme)
                continue
        else:
            raise ConnectionError(
                f"Cannot connect to Ezlo hub at {self.host}:{self.port}"
            )
        self._connected = True
        self._listen_task = asyncio.create_task(self._listen_loop())

        info = await self.send(METHOD_HUB_INFO)
        self.serial = info.get("serial")
        self.model = info.get("model")
        self.firmware = info.get("firmware")
        _LOGGER.info(
            "Connected to hub %s (model=%s, fw=%s)",
            self.serial, self.model, self.firmware,
        )

    async def disconnect(self) -> None:
        """Close connection."""
        self._connected = False
        if self._listen_task:
            self._listen_task.cancel()
            self._listen_task = None
        if self._reconnect_task:
            self._reconnect_task.cancel()
            self._reconnect_task = None
        if self._ws:
            await self._ws.close()
            self._ws = None

    async def send(self, method: str, params: dict | None = None) -> dict:
        """Send a request and wait for its response."""
        if not self._ws:
            raise ConnectionError("Not connected to hub")
        self._msg_id += 1
        msg_id = str(self._msg_id)
        msg = {"method": method, "id": msg_id, "params": params or {}}

        future: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending[msg_id] = future
        await self._ws.send(json.dumps(msg))
        try:
            return await asyncio.wait_for(future, timeout=30)
        finally:
            self._pending.pop(msg_id, None)

    async def _listen_loop(self) -> None:
        """Listen for incoming messages."""
        try:
            async for raw in self._ws:
                data = json.loads(raw)
                msg_id = data.get("id")

                if msg_id and msg_id != "ui_broadcast" and msg_id in self._pending:
                    error = data.get("error")
                    if error:
                        self._pending[msg_id].set_exception(
                            RuntimeError(f"Hub error: {error}")
                        )
                    else:
                        self._pending[msg_id].set_result(data.get("result", {}))
                elif msg_id == "ui_broadcast":
                    self._handle_broadcast(data)
        except websockets.ConnectionClosed:
            _LOGGER.warning("WebSocket connection lost, scheduling reconnect")
            self._connected = False
            self._reconnect_task = asyncio.create_task(self._reconnect())
        except asyncio.CancelledError:
            pass

    async def _reconnect(self) -> None:
        """Reconnect with exponential backoff."""
        delay = 5
        while not self._connected:
            _LOGGER.info("Reconnecting in %ds...", delay)
            await asyncio.sleep(delay)
            try:
                await self.connect()
                await self.refresh_devices()
                _LOGGER.info("Reconnected to hub %s", self.serial)
                return
            except Exception:
                delay = min(delay * 2, 120)
                _LOGGER.debug("Reconnect failed, retrying in %ds", delay)

    def _handle_broadcast(self, data: dict) -> None:
        """Process a broadcast message."""
        subclass = data.get("msg_subclass", "")
        result = data.get("result", {})

        if subclass == BROADCAST_ITEM_UPDATED:
            item_id = result.get("_id")
            if item_id and item_id in self.items:
                self.items[item_id].update(result)

        if subclass == BROADCAST_DEVICE_ADDED:
            _LOGGER.info("Device added: %s", result.get("_id"))
        elif subclass == BROADCAST_DEVICE_REMOVED:
            dev_id = result.get("_id")
            _LOGGER.info("Device removed: %s", dev_id)
            self.devices.pop(dev_id, None)

        for listener in self._listeners:
            try:
                listener(subclass, result)
            except Exception:
                _LOGGER.exception("Error in broadcast listener")

    async def refresh_devices(self) -> None:
        """Fetch all devices and items from the hub."""
        dev_result = await self.send(METHOD_DEVICES_LIST)
        device_list = dev_result.get("devices", [])
        self.devices = {d["_id"]: d for d in device_list}

        items_result = await self.send(METHOD_ITEMS_LIST)
        item_list = items_result.get("items", [])
        self.items = {i["_id"]: i for i in item_list}

        self._items_by_device = {}
        for item in item_list:
            dev_id = item.get("deviceId")
            self._items_by_device.setdefault(dev_id, []).append(item)

    def get_items_for_device(self, device_id: str) -> list[dict]:
        """Get all items for a device."""
        return self._items_by_device.get(device_id, [])

    def get_item(self, device_id: str, name: str) -> dict | None:
        """Get a specific item by name for a device."""
        for item in self.get_items_for_device(device_id):
            if item.get("name") == name:
                return item
        return None

    async def set_item_value(self, item_id: str, value: Any) -> dict:
        """Set the value of an item."""
        return await self.send(METHOD_ITEM_VALUE_SET, {"_id": item_id, "value": value})

    async def zwave_include(self) -> dict:
        """Start Z-Wave inclusion mode."""
        return await self.send(METHOD_PLUGIN_RUN, {"script": SCRIPT_ZWAVE_INCLUDE})

    async def zwave_stop_include(self) -> dict:
        """Stop Z-Wave inclusion mode."""
        return await self.send(METHOD_PLUGIN_RUN, {"script": SCRIPT_ZWAVE_STOP_INCLUDE})

    async def zwave_exclude(self) -> dict:
        """Start Z-Wave exclusion mode."""
        return await self.send(METHOD_PLUGIN_RUN, {"script": SCRIPT_ZWAVE_EXCLUDE})

    async def zwave_stop_exclude(self) -> dict:
        """Stop Z-Wave exclusion mode."""
        return await self.send(METHOD_PLUGIN_RUN, {"script": SCRIPT_ZWAVE_STOP_EXCLUDE})

    async def device_force_remove(self, device_id: str) -> dict:
        """Force-remove a device from the hub."""
        return await self.send(METHOD_DEVICE_FORCE_REMOVE, {"_id": device_id})
