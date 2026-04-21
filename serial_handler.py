"""Manejo de puerto serie (UART).

Compatible con placas USB-CDC/CH340 (p. ej. Bluepill) y con Nucleo STM32
(ST-Link Virtual COM Port). El listado prioriza puertos ST-Link para que
no queden ocultos entre muchos COM. La opción assert_dtr_rts=False ayuda
en algunos entornos Nucleo donde forzar DTR/RTS no es deseable.
"""
import re
import threading
from typing import Any, Callable, Dict, List, Optional, Union

import serial
import serial.tools.list_ports


def _port_info_dict(p: Any) -> Dict[str, Any]:
    desc = (p.description or "").strip()
    mfr = (p.manufacturer or "").strip()
    vid = getattr(p, "vid", None)
    pid = getattr(p, "pid", None)
    hwid = getattr(p, "hwid", None) or ""
    vid_hex = f"0x{vid:04X}" if isinstance(vid, int) else ""
    pid_hex = f"0x{pid:04X}" if isinstance(pid, int) else ""
    blob = f"{desc} {mfr} {hwid}".upper()
    # Nucleo F411RE y similares: VCP del ST-Link
    is_st_link = (
        "ST-LINK" in blob
        or "STLINK" in blob
        or ("STMICRO" in blob and "VIRTUAL COM" in blob)
        or ("STM32" in blob and "VIRTUAL" in blob)
    )
    # Adaptadores USB-serial típicos (Bluepill externo, etc.)
    is_usb_serial = bool(
        re.search(r"CH340|CH341|CP210|FTDI|FT232|USB SERIAL|CDC", blob)
    )
    return {
        "path": p.device,
        "description": desc,
        "manufacturer": mfr,
        "hwid": hwid,
        "vid": vid_hex,
        "pid": pid_hex,
        "is_st_link": is_st_link,
        "is_usb_serial": is_usb_serial,
    }


def list_ports() -> List[dict]:
    """Lista puertos serie. ST-Link / STMicro VCP primero, luego el resto por nombre."""
    raw = list(serial.tools.list_ports.comports())
    infos = [_port_info_dict(p) for p in raw]

    def sort_key(d: dict) -> tuple:
        # 0 = ST-Link (Nucleo), 1 = otros USB-serial conocidos, 2 = resto
        if d.get("is_st_link"):
            tier = 0
        elif d.get("is_usb_serial"):
            tier = 1
        else:
            tier = 2
        return (tier, str(d["path"]).upper())

    infos.sort(key=sort_key)
    # Solo exponer campos estables para el resto de la app
    return [
        {
            "path": i["path"],
            "description": i["description"],
            "manufacturer": i["manufacturer"],
            "hwid": i["hwid"],
            "vid": i["vid"],
            "pid": i["pid"],
        }
        for i in infos
    ]


class SerialHandler:
    def __init__(self, on_data: Optional[Callable[..., None]] = None):
        self._port: Optional[serial.Serial] = None
        self._on_data = on_data or (lambda text, hex_str: None)
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

    @property
    def is_open(self) -> bool:
        return self._port is not None and self._port.is_open

    def open(
        self,
        port: str,
        baudrate: int = 9600,
        *,
        assert_dtr_rts: bool = True,
    ) -> None:
        """
        Abre 8N1, sin control de flujo por hardware en el driver.

        assert_dtr_rts=True (por defecto): fuerza DTR/RTS altos tras abrir;
        suele ir bien con CH340/FTDI y muchas placas.

        assert_dtr_rts=False: no toca DTR/RTS; recomendable si usas el
        puerto Virtual COM del ST-Link (Nucleo F411RE, etc.) y notas resets
        o datos erróneos al conectar.
        """
        if self._port and self._port.is_open:
            self.close()

        self._port = serial.Serial(
            port=port,
            baudrate=baudrate,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=0.05,
            write_timeout=1.0,
            xonxoff=False,
            rtscts=False,
            dsrdtr=False,
        )
        if assert_dtr_rts:
            try:
                self._port.setDTR(True)
                self._port.setRTS(True)
            except Exception:
                pass
        try:
            self._port.reset_input_buffer()
            self._port.reset_output_buffer()
        except Exception:
            pass

        self._stop.clear()
        self._thread = threading.Thread(target=self._read_loop, daemon=True)
        self._thread.start()

    def close(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1.0)
            self._thread = None
        if self._port and self._port.is_open:
            self._port.close()
        self._port = None

    def _read_loop(self) -> None:
        while not self._stop.is_set() and self._port and self._port.is_open:
            try:
                if self._port.in_waiting:
                    data = self._port.read(self._port.in_waiting)
                    text = data.decode("utf-8", errors="replace")
                    hex_str = data.hex()
                    try:
                        self._on_data(text, hex_str, data)
                    except TypeError:
                        self._on_data(text, hex_str)
            except (OSError, serial.SerialException) as e:
                try:
                    self._on_data(f"ERROR UART: {e}", "", b"")
                except Exception:
                    pass
                break
            self._stop.wait(0.05)

    def write(self, data: Union[str, bytes]) -> None:
        if not self._port or not self._port.is_open:
            raise RuntimeError("Puerto serie no abierto")
        if isinstance(data, str):
            data = data.encode("utf-8")
        self._port.write(data)
        try:
            self._port.flush()
        except Exception:
            pass
