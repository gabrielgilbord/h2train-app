"""Manejo de Bluetooth BLE con Bleak (async). Se ejecuta en un hilo con asyncio."""
import asyncio
import threading
from typing import Callable, List, Optional

try:
    from bleak import BleakClient, BleakScanner
    from bleak.backends.characteristic import BleakGATTCharacteristic
except ImportError:
    BleakClient = None
    BleakScanner = None
    BleakGATTCharacteristic = None


def _check_bleak() -> None:
    if BleakScanner is None:
        raise RuntimeError("Instala bleak: pip install bleak")


def _run_async(coro):
    """Ejecuta una corutina en el event loop del hilo."""
    loop = asyncio.get_event_loop()
    return loop.run_until_complete(coro)


class BLEHandler:
    """Wrapper para usar Bleak desde un hilo con callbacks a la GUI."""

    def __init__(
        self,
        on_scan_result: Optional[Callable[[str, str, int], None]] = None,
        on_ble_data: Optional[Callable[[str, str, str, str], None]] = None,
    ):
        _check_bleak()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[object] = None
        self._scanner: Optional[object] = None
        self._client: Optional[BleakClient] = None
        self._on_scan_result = on_scan_result or (lambda addr, name, rssi: None)
        self._on_ble_data = on_ble_data or (lambda s, c, hex_str, text: None)
        self._devices: dict = {}  # address -> (name, rssi)
        self._characteristics: dict = {}  # (service_uuid, char_uuid) -> char
        self._scan_stop: Optional[asyncio.Event] = None

    def _get_loop(self) -> asyncio.AbstractEventLoop:
        if self._loop is None:
            self._loop = asyncio.new_event_loop()
            self._thread = threading_run_loop(self._loop)
            self._thread.start()
        return self._loop

    def start_scan(self, service_uuids: Optional[List[str]] = None) -> None:
        _check_bleak()
        self._scan_stop = asyncio.Event()
        loop = self._get_loop()
        asyncio.run_coroutine_threadsafe(
            self._scan_impl(service_uuids or []), loop
        )

    def _make_detection_callback(self):
        def callback(device, advertising_data):
            name = getattr(device, "name", None) or getattr(advertising_data, "local_name", None) or "Sin nombre"
            rssi = getattr(advertising_data, "rssi", None) or getattr(device, "rssi", None) or 0
            self._devices[device.address] = (name, rssi)
            self._on_scan_result(device.address, name, rssi)
        return callback

    async def _scan_impl(self, service_uuids: List[str]) -> None:
        self._devices.clear()
        kwargs = {"detection_callback": self._make_detection_callback()}
        if service_uuids:
            kwargs["service_uuids"] = service_uuids
        scanner = BleakScanner(**kwargs)
        await scanner.start()
        self._scanner = scanner
        try:
            await self._scan_stop.wait()
        finally:
            await scanner.stop()
            self._scanner = None

    def stop_scan(self) -> None:
        if hasattr(self, "_scan_stop") and self._scan_stop:
            self._scan_stop.set()
        self._scanner = None

    def get_discovered_addresses(self) -> List[str]:
        return list(self._devices.keys())

    def connect(self, address: str) -> dict:
        """Conecta al dispositivo y descubre servicios. Debe llamarse desde el hilo que tiene el event loop o con run_coroutine_threadsafe."""
        _check_bleak()
        loop = self._get_loop()
        future = asyncio.run_coroutine_threadsafe(
            self._connect_impl(address), loop
        )
        return future.result(timeout=30)

    async def _connect_impl(self, address: str) -> dict:
        if self._client and self._client.is_connected:
            await self._client.disconnect()
        self._client = BleakClient(address)
        await self._client.connect()
        name = self._devices.get(address, ("", 0))[0] or address
        services_info = []
        chars_info = []
        self._characteristics.clear()
        for service in self._client.services:
            for char in service.characteristics:
                key = (service.uuid, char.uuid)
                self._characteristics[key] = char
                chars_info.append(
                    {
                        "uuid": char.uuid,
                        "serviceUuid": service.uuid,
                        "properties": list(char.properties),
                    }
                )
            services_info.append({"uuid": service.uuid, "name": service.description or ""})
        return {
            "name": name,
            "address": address,
            "services": services_info,
            "characteristics": chars_info,
        }

    def disconnect(self) -> None:
        loop = self._get_loop()
        future = asyncio.run_coroutine_threadsafe(self._disconnect_impl(), loop)
        future.result(timeout=5)

    async def _disconnect_impl(self) -> None:
        if self._client and self._client.is_connected:
            await self._client.disconnect()
        self._client = None
        self._characteristics.clear()

    def read_characteristic(self, service_uuid: str, char_uuid: str) -> str:
        loop = self._get_loop()
        future = asyncio.run_coroutine_threadsafe(
            self._read_char_impl(service_uuid, char_uuid), loop
        )
        data = future.result(timeout=10)
        return data.hex() if data else ""

    async def _read_char_impl(self, service_uuid: str, char_uuid: str) -> bytes:
        if not self._client or not self._client.is_connected:
            raise RuntimeError("No conectado a BLE")
        key = (service_uuid, char_uuid)
        if key not in self._characteristics:
            raise RuntimeError("Característica no encontrada")
        return await self._client.read_gatt_char(self._characteristics[key])

    def start_notify(self, service_uuid: str, char_uuid: str) -> None:
        loop = self._get_loop()
        asyncio.run_coroutine_threadsafe(
            self._notify_impl(service_uuid, char_uuid), loop
        )

    async def _notify_impl(self, service_uuid: str, char_uuid: str) -> None:
        if not self._client or not self._client.is_connected:
            return
        key = (service_uuid, char_uuid)
        if key not in self._characteristics:
            return
        char = self._characteristics[key]

        def callback(_char: BleakGATTCharacteristic, data: bytearray) -> None:
            hex_str = bytes(data).hex()
            text = bytes(data).decode("utf-8", errors="replace")
            self._on_ble_data(service_uuid, char_uuid, hex_str, text)

        await self._client.start_notify(char, callback)


def threading_run_loop(loop: asyncio.AbstractEventLoop) -> threading.Thread:
    def run():
        asyncio.set_event_loop(loop)
        loop.run_forever()

    t = threading.Thread(target=run, daemon=True)
    return t
