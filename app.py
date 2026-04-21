#!/usr/bin/env python3
"""
H2TRAIN Device Bridge \u2014 UART + Bluetooth (BLE).
Todo en Python: PySerial, Bleak, Tkinter.
Ejecutar: python app.py
"""
import base64
import csv
from collections import deque
import ctypes
from datetime import datetime
import json
import os
import queue
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
from typing import Optional
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from math import log2

try:
    # Cifrado simétrico real (AES-128) para los segmentos de ECG.
    from Crypto.Cipher import AES  # type: ignore
except Exception:  # pragma: no cover - entorno sin pycryptodome
    AES = None

from serial_handler import SerialHandler, list_ports
from ble_handler import BLEHandler

APP_VERSION = "v1.4.38"

def _load_env_file_into_process(path: str, only_prefix: str = "H2T_") -> None:
    """
    Carga un env file tipo systemd/dotenv (KEY=VALUE por línea) en os.environ.
    Solo inyecta claves que empiecen por `only_prefix` y que aún no existan.
    """
    try:
        if not path:
            return
        if not os.path.exists(path):
            return
        with open(path, "r", encoding="utf-8") as f:
            for raw in f.read().splitlines():
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip()
                if not k or not k.startswith(only_prefix):
                    continue
                # Si el proceso ya tiene la clave pero vacía (por ejemplo por systemd),
                # permitimos que el env file la sobrescriba.
                if k in os.environ and str(os.environ.get(k, "")).strip() != "":
                    continue
                # systemd EnvironmentFile permite comillas; soportamos lo básico.
                if (len(v) >= 2) and ((v[0] == v[-1]) and v[0] in ("\"", "'")):
                    v = v[1:-1]
                os.environ[k] = v
    except Exception:
        # No romper la app si el env file está corrupto.
        return

# Si systemd --user no inyecta EnvironmentFile, leemos nosotros.
_load_env_file_into_process(os.environ.get("H2T_ENV_FILE", "/etc/h2train-app.env"))

def _load_poppins():
    """Register Poppins font files so Tkinter can use them."""
    if getattr(sys, 'frozen', False):
        base = sys._MEIPASS
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    fonts_dir = os.path.join(base, "fonts")
    if not os.path.isdir(fonts_dir):
        return
    for fname in os.listdir(fonts_dir):
        if not fname.lower().endswith(".ttf"):
            continue
        path = os.path.join(fonts_dir, fname)
        if sys.platform == "win32":
            try:
                ctypes.windll.gdi32.AddFontResourceExW(path, 0x10, 0)
            except Exception:
                pass
        else:
            try:
                import subprocess
                home_fonts = os.path.expanduser("~/.local/share/fonts")
                os.makedirs(home_fonts, exist_ok=True)
                dst = os.path.join(home_fonts, fname)
                if not os.path.exists(dst):
                    import shutil
                    shutil.copy2(path, dst)
                subprocess.run(["fc-cache", "-f"], capture_output=True, timeout=10)
            except Exception:
                pass

_load_poppins()

H2TRAIN_LOGO_B64 = (
    "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"
    "NaowrMIBAP8DDaZ0YyR1KekAAAAASUVORK5CYII="
)

H2TRAIN_ICON_B64 = (
    "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"
    "RU5ErkJggg=="
)


class MiniPlot(tk.Canvas):
    def __init__(self, parent, title: str, bg="#0b1220", autoscale_lo=0.02, autoscale_hi=0.98, **kwargs):
        super().__init__(parent, bg=bg, highlightthickness=0, **kwargs)
        self._title = title
        self._series = []
        self._scale_min = None
        self._scale_max = None
        self._external_scale = None  # (min, max) compartido opcional
        # Mostramos más historial: hasta ~6000 muestras por gráfica.
        self._autoscale_window = 6000
        self._autoscale_lo = autoscale_lo
        self._autoscale_hi = autoscale_hi
        self.bind("<Configure>", lambda _: self.redraw())

    def set_series(self, series):
        self._series = series

    def set_external_scale(self, scale: Optional[tuple[float, float]]):
        """
        Permite fijar manualmente el rango Y (min, max) para sincronizar
        varios gráficos. Si scale es None, se vuelve al autoscale normal.
        """
        self._external_scale = scale
        if scale is None:
            self.reset_scale()
        else:
            self._scale_min, self._scale_max = scale

    def reset_scale(self):
        self._scale_min = None
        self._scale_max = None

    def redraw(self):
        self.delete("all")
        w = max(1, self.winfo_width())
        h = max(1, self.winfo_height())
        self.create_text(8, 8, anchor=tk.NW, text=self._title, fill="#94a3b8", font=("Poppins", 9, "bold"))
        self.create_rectangle(1, 1, w - 1, h - 1, outline="#334155")
        self.create_line(0, h // 2, w, h // 2, fill="#1e293b")
        if not self._series:
            return

        prepared = []
        all_values = []
        window = self._autoscale_window
        for values, color in self._series:
            if not values:
                continue
            data = list(values)[-window:]
            start_sample = max(0, window - len(data))
            prepared.append((data, color, start_sample))
            all_values.extend(data)

        if not prepared or not all_values:
            return

        # Robust autoscale (LabVIEW-like): ignore extreme outliers, salvo que
        # tengamos un rango externo forzado.
        if self._external_scale is not None:
            target_min, target_max = self._external_scale
        else:
            values_sorted = sorted(all_values)
            n = len(values_sorted)
            lo_idx = int((n - 1) * self._autoscale_lo)
            hi_idx = int((n - 1) * self._autoscale_hi)
            min_v = values_sorted[lo_idx]
            max_v = values_sorted[hi_idx]
            if max_v <= min_v:
                min_v = min(values_sorted)
                max_v = max(values_sorted)
            if max_v <= min_v:
                max_v = min_v + 1.0

            span = max_v - min_v
            pad = max(1.0, span * 0.10)
            target_min = min_v - pad
            target_max = max_v + pad

        if target_max <= target_min:
            target_max = target_min + 1.0

        # Smooth the Y-range to avoid jittering.
        if self._scale_min is None or self._scale_max is None:
            self._scale_min = target_min
            self._scale_max = target_max
        else:
            a = 0.35
            self._scale_min = (1 - a) * self._scale_min + a * target_min
            self._scale_max = (1 - a) * self._scale_max + a * target_max
            if self._scale_max <= self._scale_min:
                self._scale_max = self._scale_min + 1.0

        min_v = self._scale_min
        max_v = self._scale_max

        top = 20
        bottom = h - 6
        usable_h = max(1, bottom - top)
        for data, color, start_sample in prepared:
            if len(data) == 1:
                sample_idx = start_sample
                x = 4 + (sample_idx * (w - 8) / max(1, window - 1))
                y = bottom - int((data[0] - min_v) * usable_h / (max_v - min_v))
                self.create_oval(x - 2, y - 2, x + 2, y + 2, fill=color, outline=color)
                continue
            pts = []
            for i, v in enumerate(data):
                sample_idx = start_sample + i
                x = 4 + (sample_idx * (w - 8) / max(1, window - 1))
                y = bottom - int((v - min_v) * usable_h / (max_v - min_v))
                pts.extend((x, y))
            self.create_line(*pts, fill=color, width=1.5, smooth=False)

        self.create_text(
            w - 8,
            8,
            anchor=tk.NE,
            text=f"{int(min_v)} .. {int(max_v)}",
            fill="#64748b",
            font=("Poppins", 8),
        )
        self.create_text(6, h - 2, anchor=tk.SW, text="0", fill="#64748b", font=("Poppins", 8))
        self.create_text(
            w - 8,
            h - 2,
            anchor=tk.SE,
            text=f"{window} muestras",
            fill="#64748b",
            font=("Poppins", 8),
        )


class FlowDiagram(tk.Canvas):
    def __init__(self, parent, bg="#020617", **kwargs):
        super().__init__(parent, bg=bg, highlightthickness=0, **kwargs)
        self._items = []  # lista de diccionarios con idx, key_short, entropy
        self._blink_on = True
        self._has_active = False
        self._key_hit_regions: list[dict] = []  # zonas clicables de bloques de clave
        self.bind("<Configure>", lambda _e: self.redraw())
        self.bind("<Double-Button-1>", self._on_double_click)
        self.after(500, self._blink_tick)

    def set_flow(self, items):
        self._items = list(items or [])
        self._has_active = any(bool(it.get("active")) for it in self._items)
        self.redraw()

    def _blink_tick(self):
        # Pequeño "latido" visual para el segmento activo en flujo en vivo.
        self._blink_on = not self._blink_on
        if self._has_active:
            self.redraw()
        self.after(500, self._blink_tick)

    def _on_double_click(self, event):
        """
        Al hacer doble clic sobre un bloque de clave, mostramos un diálogo
        con TODAS las claves candidatas HKDF (incluidas las descartadas) y
        sus entropías, marcando claramente la elegida.
        """
        x, y = event.x, event.y
        target = None
        for region in self._key_hit_regions:
            x0, y0, x1, y1 = region["bbox"]
            if x0 <= x <= x1 and y0 <= y <= y1:
                target = region.get("item")
                break
        if not target:
            return

        cands = target.get("candidates") or []
        if not cands:
            return

        # Información de la clave final usada para cifrar (ya mezclada con la
        # clave inicial si aplica).
        final_key_short = target.get("key_short", "")
        final_ent = float(target.get("entropy", 0.0))
        mixed = bool(target.get("mixed"))

        best_ent = max(float(c.get("entropy", 0.0)) for c in cands)
        best_idx = target.get("best_idx", None)
        idx = target.get("idx", "?")

        top = self.winfo_toplevel()
        win = tk.Toplevel(top)
        win.title(f"Detalles de candidatos HKDF para Key {idx}")
        win.configure(bg="#020617")

        text = scrolledtext.ScrolledText(
            win,
            width=80,
            height=20,
            bg="#020617",
            fg="#e5e7eb",
            insertbackground="#e5e7eb",
            font=("Consolas", 9),
        )
        text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        text.insert(
            tk.END,
            f"Key {idx} — clave FINAL usada para cifrar (tras mezclar ECG"
            f"{' + clave inicial' if mixed else ''}):\n"
            f"  key_final[0..7] = {final_key_short}   H_norm_final = {final_ent:.3f}\n\n",
        )
        text.insert(
            tk.END,
            "Candidatos HKDF a partir del ECG (★ = base de la clave final antes de mezclar):\n\n",
        )
        for c in cands:
            e = float(c.get("entropy", 0.0))
            ctr = int(c.get("idx", 0))
            key_hex = c.get("key_short", "")
            is_best = best_idx is not None and ctr == int(best_idx)
            prefix = "★" if is_best else "·"
            line = f"{prefix} ctr={ctr:02d}  H_norm={e:.3f}  key[0..7]={key_hex}\n"
            text.insert(tk.END, line)

        text.config(state=tk.DISABLED)

    def redraw(self):
        self.delete("all")
        w = max(1, self.winfo_width())
        h = max(1, self.winfo_height())
        self._key_hit_regions.clear()

        self.create_text(
            8,
            8,
            anchor=tk.NW,
            text="Cadena de ventanas TD8-ECG (segmento → clave → cifrado siguiente segmento)",
            fill="#e5e7eb",
            font=("Poppins", 9, "bold"),
        )

        if not self._items:
            self.create_text(
                w // 2,
                h // 2,
                text="Sin datos de flujo todavía. Pulsa 'Simular flujo por ventanas'.",
                fill="#64748b",
                font=("Poppins", 9),
            )
            return

        top = 26
        height = h - top - 10
        n = len(self._items)
        if n <= 0 or height <= 0:
            return

        seg_width = max(80, (w - 40) // n)
        for i, it in enumerate(self._items):
            x0 = 20 + i * seg_width
            x1 = x0 + seg_width - 10
            y_mid = top + height // 2

            # Segmento ECG_i (izquierda)
            ecg_box_w = (x1 - x0) * 0.35
            key_box_w = (x1 - x0) * 0.35
            enc_box_w = (x1 - x0) * 0.35
            gap = (x1 - x0 - ecg_box_w - key_box_w - enc_box_w) / 4.0

            ecg_x0 = x0 + gap
            ecg_x1 = ecg_x0 + ecg_box_w
            key_x0 = ecg_x1 + gap
            key_x1 = key_x0 + key_box_w
            enc_x0 = key_x1 + gap
            enc_x1 = enc_x0 + enc_box_w

            # ECG_i (hacen los bloques más altos para mejorar legibilidad).
            self.create_rectangle(
                ecg_x0,
                y_mid - 28,
                ecg_x1,
                y_mid + 28,
                outline="#22c55e",
                fill="#022c22",
            )
            ecg_label_idx = 0 if it.get("init") else it["idx"]
            self.create_text(
                (ecg_x0 + ecg_x1) / 2,
                y_mid,
                text=f"ECG {ecg_label_idx}",
                fill="#bbf7d0",
                font=("Poppins", 9),
            )

            # Colores de clave según entropía (salud de la clave).
            ent = float(it.get("entropy", 0.0))
            if ent >= 0.85:
                key_fill = "#022c22"   # verde oscuro
                key_outline = "#22c55e"
                key_text = "#bbf7d0"
            elif ent >= 0.7:
                key_fill = "#422006"   # ámbar
                key_outline = "#facc15"
                key_text = "#fef9c3"
            else:
                key_fill = "#450a0a"   # rojo
                key_outline = "#f97373"
                key_text = "#fee2e2"

            # Clave_i (bloque alto pero compacto para ver resumen + muestra
            # representativa de candidatos sin solaparse con otros textos).
            key_y0 = y_mid - 55
            key_y1 = y_mid + 55
            key_rect_id = self.create_rectangle(
                key_x0,
                key_y0,
                key_x1,
                key_y1,
                outline=key_outline,
                fill=key_fill,
            )
            # Guardamos región clicable para doble clic.
            self._key_hit_regions.append(
                {
                    "bbox": (key_x0, key_y0, key_x1, key_y1),
                    "item": it,
                }
            )
            # Título y resumen siempre en la mitad superior del bloque.
            key_title = "Key init" if it.get("init") else f"Key {it['idx']}"
            self.create_text(
                (key_x0 + key_x1) / 2,
                y_mid - 20,
                text=key_title,
                fill=key_text,
                font=("Poppins", 8, "bold"),
            )
            self.create_text(
                (key_x0 + key_x1) / 2,
                y_mid - 6,
                text=f"{it['key_short']} | H={it['entropy']:.2f}",
                fill=key_text,
                font=("Poppins", 8),
            )

            # Lista compacta de candidatos HKDF (incluyendo descartados) en la
            # parte inferior del bloque de clave. Por limitaciones de espacio
            # mostramos sólo los primeros N en fuente más grande; la clave
            # elegida va claramente resaltada.
            cands = it.get("candidates") or []
            best_idx = it.get("best_idx", None)
            if cands:
                # Mostramos unas pocas filas siempre en la mitad inferior del
                # bloque, empezando justo por debajo del resumen para evitar
                # solapes. La lista completa sigue en el diálogo de doble clic.
                max_rows = min(len(cands), 4)
                line_h = 12
                base_y = y_mid + 6
                for j, c in enumerate(cands[:max_rows]):
                    e = float(c.get("entropy", 0.0))
                    idx_c = int(c.get("idx", j))
                    # Marcamos con "★" sólo la clave elegida (ctr == best_idx).
                    is_best = best_idx is not None and idx_c == int(best_idx)
                    prefix = "★" if is_best else "·"
                    # Texto compacto para que no se solape horizontalmente con
                    # otros bloques: sólo contador y entropía.
                    txt = f"{prefix} c={idx_c:02d} H={e:.2f}"
                    self.create_text(
                        (key_x0 + key_x1) / 2,
                        base_y + j * line_h,
                        text=txt,
                        fill=key_text,
                        font=("Poppins", 8),
                    )

            # Indicador de "liveness" parpadeante sobre la clave activa de flujo en vivo.
            if it.get("active") and it.get("live"):
                r = 4
                cx = (key_x0 + key_x1) / 2
                cy = y_mid - 22
                color = "#22c55e" if self._blink_on else "#1e293b"
                self.create_oval(cx - r, cy - r, cx + r, cy + r, fill=color, outline="")

            # ECG_{i+1} cifrado
            self.create_rectangle(
                enc_x0,
                y_mid - 18,
                enc_x1,
                y_mid + 18,
                outline="#f97316",
                fill="#451a03",
            )
            enc_label_idx = 0 if it.get("init") else (it["idx"] + 1)
            self.create_text(
                (enc_x0 + enc_x1) / 2,
                y_mid,
                text=f"ECG {enc_label_idx} cifrada",
                fill="#fed7aa",
                font=("Poppins", 8),
            )

            # Flechas
            self.create_line(ecg_x1, y_mid, key_x0, y_mid, fill="#e5e7eb", arrow=tk.LAST)
            self.create_line(key_x1, y_mid, enc_x0, y_mid, fill="#e5e7eb", arrow=tk.LAST)


class DeviceBridgeApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("H2TRAIN \u2014 Device Bridge")
        self.root.minsize(850, 620)
        self.root.geometry("950x680")
        self._set_icon()

        self._serial: Optional[SerialHandler] = None
        self._ble: Optional[BLEHandler] = None
        self._ble_info: Optional[dict] = None
        self._update_queue: queue.Queue = queue.Queue()
        self._uart_pending_raw = bytearray()
        self._uart_pending_lock = threading.Lock()
        self._uart_parse_scheduled = False
        self._after_id: Optional[str] = None
        self._plot_after_id: Optional[str] = None
        self._uart_rx_buffer = bytearray()
        self._uart_h2t_mirror_buffer = bytearray()
        self._uart_packets_ok = 0
        self._uart_packets_crc_err = 0
        self._uart_raw17_ok = 0
        self._uart_raw17_sync_err = 0
        self._uart_ecg_packets_ok = 0
        self._uart_rx_zero_streak = 0
        self._uart_zero_diag_done = False
        self._parser_mode = "h2t30"
        self._raw17_header = 0x02
        self._raw17_byteorder = "big"
        self._raw17_signed = False
        self._raw17_autodetect = False
        self._raw17_auto_packets = 0
        self._raw17_auto_target = 120
        self._raw17_auto_metrics = {}
        self._signal_filter_enabled = True
        # Endianness 4404: muchos firmwares envían int24 en big-endian.
        self._byteorder_4404 = "big"
        self._bo_auto = True
        self._bo_score = {"little": 0.0, "big": 0.0}
        self._bo_packets = 0

        # Más historial para ECG y señales ópticas.
        self._series_3bx = deque(maxlen=6000)
        self._series_h = [deque(maxlen=1200) for _ in range(6)]
        self._series_H = [deque(maxlen=1200) for _ in range(6)]
        self._series_h_d6_ac = deque(maxlen=1200)
        self._series_H_d6_ac = deque(maxlen=1200)
        self._h_d6_base: Optional[float] = None
        self._H_d6_base: Optional[float] = None
        self._series_h_red = deque(maxlen=1200)
        self._series_h_ir = deque(maxlen=1200)
        self._series_H_red = deque(maxlen=1200)
        self._series_H_ir = deque(maxlen=1200)
        self._selected_4404_channel = 5  # D6 por defecto
        self._raw17_red_base: Optional[float] = None
        self._raw17_ir_base: Optional[float] = None
        self._ecg_lp: Optional[float] = None
        self._ecg_base: Optional[float] = None
        self._ecg_amp: Optional[float] = None
        self._ecg_last_tick: Optional[int] = None
        # Estado del filtro notch 50 Hz para ECG (3bx), fs ≈ 800 Hz.
        self._ecg_notch_x1: float = 0.0
        self._ecg_notch_x2: float = 0.0
        self._ecg_notch_y1: float = 0.0
        self._ecg_notch_y2: float = 0.0
        # Segundo low-pass suave para completar un band-pass efectivo 0.5–35 Hz.
        self._ecg_bp_lp2: Optional[float] = None
        self._h_d6_lp: Optional[float] = None
        self._H_d6_lp: Optional[float] = None
        self._raw17_red_lp: Optional[float] = None
        self._raw17_ir_lp: Optional[float] = None

        # Buffers para demo de flujo por ventanas TD8-ECG.
        self._flow_ecg = deque(maxlen=12000)
        self._flow_enc = deque(maxlen=12000)
        self._flow_pairs_all = []
        self._td8_auto_flow_job: Optional[str] = None
        # Estado del modo acumulativo 11 bits por muestra.
        self._bit11_reserve_bits = ""
        self._bit11_invalid_pool = []
        self._last_keyset_report = None
        self._last_batch_results = []
        self._api_server = None
        self._api_thread = None

        self._setup_style()
        self._build_ui()
        self._apply_env_overrides()
        self._start_command_api_server()
        self._process_queue()
        self._refresh_uart_plots()

    def _apply_env_overrides(self):
        """
        Permite configurar parámetros clave vía variables de entorno para
        automatización/operación remota (p.ej. desde Pi-Dashboard + pi-mqtt-agent).

        Keys soportadas (prefijo H2T_):
          - UART RAW17:
              H2T_UART_RAW17_ENDIAN = big|little
              H2T_UART_RAW17_SIGNED_INT24 = 0|1|true|false
          - TD8-ECG Keys / pipeline:
              H2T_TD8_PIPELINE = "RNS+HKDF (actual)" | "Acumulativo 11 bits/muestra"
              H2T_TD8_ECG_SOURCE = "ECG 3bx en vivo" | "ECG sintético (función)"
              H2T_TD8_ENTROPY_THRESHOLD = float (0..0.99)
              H2T_TD8_INVALID_POLICY = "Descartar no válidas" | "Guardar para recombinar"
              H2T_TD8_RECOMBINE_STRATEGY = "Mitad + mitad" | "Alternar bits" | "XOR + SHA256"
              H2T_TD8_MAX_INVALID_POOL = int
              H2T_TD8_KEEP_TAIL_BITS = 0|1|true|false
              H2T_TD8_ANALYSIS_WINDOW_SAMPLES = int
              H2T_TD8_SCAN_MODE = "No solapado (128b)" | "Desplazamiento 11b" | "Desplazamiento 1b (máximo)"
              H2T_TD8_KEY_128_HEX = 32 bytes hex (sin 0x, 32 chars) o vacío
              H2T_TD8_WINDOW_LEN = int (tamaño ventana para flujo por ventanas)
              H2T_TD8_AUTO_EVERY_2S = 0|1|true|false
        """

        # Ensure we read the latest written env file too.
        _load_env_file_into_process(os.environ.get("H2T_ENV_FILE", "/etc/h2train-app.env"))

        def _env_str(key: str) -> Optional[str]:
            v = os.environ.get(key)
            if v is None:
                return None
            v = str(v).strip()
            return v if v != "" else ""

        def _env_bool(key: str) -> Optional[bool]:
            v = _env_str(key)
            if v is None:
                return None
            vv = v.lower()
            if vv in ("1", "true", "yes", "y", "on"):
                return True
            if vv in ("0", "false", "no", "n", "off"):
                return False
            return None

        def _env_int(key: str) -> Optional[int]:
            v = _env_str(key)
            if v is None or v == "":
                return None
            try:
                return int(v)
            except Exception:
                return None

        def _env_float(key: str) -> Optional[float]:
            v = _env_str(key)
            if v is None or v == "":
                return None
            try:
                return float(v)
            except Exception:
                return None

        # --- UART RAW17
        bo = _env_str("H2T_UART_RAW17_ENDIAN")
        if bo in ("big", "little") and hasattr(self, "uart_raw17_bo_var"):
            try:
                self.uart_raw17_bo_var.set(bo)
            except Exception:
                pass
        sgn = _env_bool("H2T_UART_RAW17_SIGNED_INT24")
        if sgn is not None and hasattr(self, "uart_raw17_signed_var"):
            try:
                self.uart_raw17_signed_var.set(bool(sgn))
            except Exception:
                pass
        # Reaplica configuración del parser si la UI ya existe.
        if hasattr(self, "_on_uart_parser_changed"):
            try:
                self._on_uart_parser_changed()
            except Exception:
                pass

        # --- TD8-ECG Keys
        pipe = _env_str("H2T_TD8_PIPELINE")
        if pipe is not None and hasattr(self, "key_pipeline_var"):
            try:
                self.key_pipeline_var.set(pipe)
            except Exception:
                pass

        src = _env_str("H2T_TD8_ECG_SOURCE")
        if src is not None and hasattr(self, "ecg_source_var"):
            try:
                self.ecg_source_var.set(src)
            except Exception:
                pass

        thr = _env_float("H2T_TD8_ENTROPY_THRESHOLD")
        if thr is not None and hasattr(self, "key_entropy_threshold_var"):
            try:
                self.key_entropy_threshold_var.set(max(0.0, min(0.99, float(thr))))
            except Exception:
                pass

        inv = _env_str("H2T_TD8_INVALID_POLICY")
        if inv is not None and hasattr(self, "invalid_policy_var"):
            try:
                self.invalid_policy_var.set(inv)
            except Exception:
                pass

        rec = _env_str("H2T_TD8_RECOMBINE_STRATEGY")
        if rec is not None and hasattr(self, "recombine_strategy_var"):
            try:
                self.recombine_strategy_var.set(rec)
            except Exception:
                pass

        mp = _env_int("H2T_TD8_MAX_INVALID_POOL")
        if mp is not None and hasattr(self, "max_invalid_pool_var"):
            try:
                self.max_invalid_pool_var.set(int(mp))
            except Exception:
                pass

        kt = _env_bool("H2T_TD8_KEEP_TAIL_BITS")
        if kt is not None and hasattr(self, "keep_tail_bits_var"):
            try:
                self.keep_tail_bits_var.set(bool(kt))
            except Exception:
                pass

        aw = _env_int("H2T_TD8_ANALYSIS_WINDOW_SAMPLES")
        if aw is not None and hasattr(self, "analysis_window_var"):
            try:
                self.analysis_window_var.set(int(aw))
            except Exception:
                pass

        sm = _env_str("H2T_TD8_SCAN_MODE")
        if sm is not None and hasattr(self, "analysis_scan_mode_var"):
            try:
                self.analysis_scan_mode_var.set(sm)
            except Exception:
                pass

        khex = _env_str("H2T_TD8_KEY_128_HEX")
        if khex is not None and hasattr(self, "key_hex_var"):
            try:
                self.key_hex_var.set(khex.strip())
            except Exception:
                pass

        wl = _env_int("H2T_TD8_WINDOW_LEN")
        if wl is not None and hasattr(self, "window_len_var"):
            try:
                self.window_len_var.set(int(wl))
            except Exception:
                pass

        af = _env_bool("H2T_TD8_AUTO_EVERY_2S")
        if af is not None and hasattr(self, "auto_flow_var"):
            try:
                self.auto_flow_var.set(bool(af))
                self._on_auto_flow_changed()
            except Exception:
                pass

        # Startup visibility: log which env we ended up with.
        try:
            effective = {k: os.environ.get(k) for k in sorted(os.environ.keys()) if k.startswith("H2T_")}
            print("[h2train-app] effective H2T_*:", json.dumps(effective, ensure_ascii=False))
        except Exception:
            pass

    def _invoke_on_ui_thread(self, fn, timeout: float = 15.0):
        done = threading.Event()
        box = {"value": None, "error": None}

        def _runner():
            try:
                box["value"] = fn()
            except Exception as e:
                box["error"] = e
            finally:
                done.set()

        self.root.after(0, _runner)
        if not done.wait(timeout):
            raise TimeoutError("Tiempo de espera agotado al ejecutar comando en UI.")
        if box["error"] is not None:
            raise box["error"]
        return box["value"]

    def _start_command_api_server(self):
        if os.environ.get("H2TRAIN_API_ENABLED", "1").strip() in ("0", "false", "False"):
            return

        host = os.environ.get("H2TRAIN_API_HOST", "127.0.0.1")
        try:
            port = int(os.environ.get("H2TRAIN_API_PORT", "8099"))
        except Exception:
            port = 8099

        app = self

        class _ApiHandler(BaseHTTPRequestHandler):
            def _send_json(self, status: int, payload: dict):
                raw = json.dumps(payload, ensure_ascii=True).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def _read_json(self):
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                except Exception:
                    length = 0
                body = self.rfile.read(length) if length > 0 else b"{}"
                if not body:
                    return {}
                return json.loads(body.decode("utf-8"))

            def do_GET(self):
                if self.path == "/api/health":
                    self._send_json(
                        200,
                        {
                            "ok": True,
                            "ts": time.time(),
                            "api": "h2train-command-api",
                            "last_report": app._last_keyset_report is not None,
                        },
                    )
                    return
                if self.path == "/api/keyset/report":
                    report = app._last_keyset_report or {}
                    self._send_json(200, {"ok": True, "report": report})
                    return
                self._send_json(404, {"ok": False, "error": "Ruta no encontrada"})

            def do_POST(self):
                if self.path != "/api/command":
                    self._send_json(404, {"ok": False, "error": "Ruta no encontrada"})
                    return
                try:
                    payload = self._read_json()
                    command = str(payload.get("command", "")).strip()
                    params = payload.get("params", {}) or {}

                    if command == "analyze_keyset":
                        def _run():
                            return app._analyze_keyset_limit_internal(params=params, update_ui=True, show_modal=False)

                        result = app._invoke_on_ui_thread(_run)
                        self._send_json(200, {"ok": True, "command": command, "result": result})
                        return

                    if command == "generate_key":
                        app._invoke_on_ui_thread(app._on_generate_ecg_key)
                        self._send_json(
                            200,
                            {
                                "ok": True,
                                "command": command,
                                "key_hex": app.key_hex_var.get(),
                                "entropy_label": app.key_entropy_var.get(),
                                "status": app.key_status_var.get(),
                            },
                        )
                        return

                    self._send_json(400, {"ok": False, "error": f"Comando no soportado: {command}"})
                except Exception as e:
                    self._send_json(500, {"ok": False, "error": str(e)})

            def log_message(self, _format, *_args):
                return

        try:
            server = ThreadingHTTPServer((host, port), _ApiHandler)
            server.timeout = 0.5
            self._api_server = server

            def _serve():
                while self._api_server is server:
                    server.handle_request()

            t = threading.Thread(target=_serve, daemon=True, name="h2train-command-api")
            t.start()
            self._api_thread = t
            self.key_status_var.set(f"API comandos activa en http://{host}:{port}/api/health")
        except OSError as e:
            self._api_server = None
            self._api_thread = None
            self.key_status_var.set(f"No se pudo iniciar API de comandos: {e}")

    def _set_icon(self):
        try:
            self._icon = tk.PhotoImage(data=base64.b64decode(H2TRAIN_ICON_B64))
            self.root.iconphoto(True, self._icon)
        except Exception:
            pass

    def _setup_style(self):
        BG = "#0f172a"
        BG2 = "#1e293b"
        PRIMARY = "#2563eb"
        PRIMARY_D = "#1d4ed8"
        PRIMARY_DD = "#1e40af"
        ACCENT = "#3b82f6"
        TEXT = "#e2e8f0"
        TEXT_DIM = "#94a3b8"
        FIELD = "#0f172a"

        self.root.configure(bg=BG)
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        font_ui = ("Poppins", 10)
        font_title = ("Poppins", 11, "bold")
        style.configure(".", font=font_ui, padding=4, background=BG, foreground=TEXT)
        style.configure("TNotebook", background=BG, borderwidth=0)
        style.configure("TNotebook.Tab", font=font_title, padding=(16, 8),
                        background=BG2, foreground=TEXT_DIM)
        style.map("TNotebook.Tab",
                  background=[("selected", PRIMARY)],
                  foreground=[("selected", "white")])
        style.configure("TFrame", background=BG)
        style.configure("TLabel", background=BG, foreground=TEXT, font=font_ui)
        style.configure("TLabelframe", background=BG, foreground=TEXT)
        style.configure("TLabelframe.Label", background=BG, foreground=ACCENT, font=font_title)
        style.configure("TButton", font=font_ui, padding=(14, 8),
                        background=PRIMARY, foreground="white")
        style.map("TButton",
                  background=[("active", PRIMARY_D), ("pressed", PRIMARY_DD)],
                  foreground=[("active", "white"), ("disabled", TEXT_DIM)])
        style.configure("Danger.TButton", background="#dc2626")
        style.map("Danger.TButton",
                  background=[("active", "#b91c1c"), ("pressed", "#991b1b")])
        style.configure("Success.TButton", background="#16a34a")
        style.map("Success.TButton",
                  background=[("active", "#15803d"), ("pressed", "#166534")])

        # Campos de texto / numéricos.
        style.configure("TEntry", fieldbackground=FIELD, foreground=TEXT,
                        insertcolor=ACCENT, padding=6)
        style.configure("TSpinbox", fieldbackground=FIELD, foreground=TEXT, padding=6,
                        arrowsize=12)

        # Combobox: fondo azul/gris oscuro tanto en el campo como en el desplegable.
        style.configure(
            "TCombobox",
            fieldbackground=BG2,
            background=BG2,
            foreground=TEXT,
            arrowcolor=ACCENT,
            padding=6,
        )
        style.map(
            "TCombobox",
            fieldbackground=[
                ("readonly", BG2),
                ("active", PRIMARY_D),
                ("pressed", PRIMARY_D),
                ("disabled", "#111827"),
            ],
            background=[
                ("readonly", BG2),
                ("active", PRIMARY_D),
                ("pressed", PRIMARY_D),
                ("disabled", "#111827"),
            ],
            foreground=[
                ("disabled", TEXT_DIM),
                ("!disabled", TEXT),
            ],
        )
        style.configure("TCheckbutton", background=BG, foreground=TEXT)
        style.configure("TScrollbar", background=BG2, troughcolor=BG, borderwidth=0)
        self.root.option_add("*Text.background", BG2)
        self.root.option_add("*Text.foreground", TEXT)
        self.root.option_add("*Text.insertBackground", ACCENT)
        self.root.option_add("*Text.font", ("Poppins", 9))
        self.root.option_add("*Text.relief", "flat")
        self.root.option_add("*Text.borderWidth", 0)
        self.root.option_add("*Listbox.background", BG2)
        self.root.option_add("*Listbox.foreground", TEXT)
        self.root.option_add("*Listbox.selectBackground", PRIMARY)
        self.root.option_add("*Listbox.selectForeground", "white")
        self.root.option_add("*Listbox.font", font_ui)
        self.root.option_add("*Listbox.relief", "flat")
        self.root.option_add("*Listbox.borderWidth", 0)

        # Menús desplegables de combobox (lista interna).
        self.root.option_add("*TCombobox*Listbox.background", BG2)
        self.root.option_add("*TCombobox*Listbox.foreground", TEXT)
        self.root.option_add("*TCombobox*Listbox.selectBackground", PRIMARY)
        self.root.option_add("*TCombobox*Listbox.selectForeground", "white")

    # --- Diálogos personalizados (evitar texto blanco sobre fondo blanco) ---
    def _show_dialog(self, title: str, message: str, kind: str = "info"):
        top = tk.Toplevel(self.root)
        top.title(title)
        top.configure(bg="#020617")
        top.transient(self.root)
        top.grab_set()

        frame = tk.Frame(top, bg="#020617", padx=16, pady=12)
        frame.pack(fill=tk.BOTH, expand=True)

        colors = {
            "info": "#38bdf8",
            "warning": "#facc15",
            "error": "#f97373",
        }
        color = colors.get(kind, "#38bdf8")

        tk.Label(
            frame,
            text=title,
            fg=color,
            bg="#020617",
            font=("Poppins", 11, "bold"),
        ).pack(anchor=tk.W, pady=(0, 8))
        tk.Label(
            frame,
            text=message,
            fg="#e5e7eb",
            bg="#020617",
            font=("Poppins", 10),
            justify=tk.LEFT,
            wraplength=360,
        ).pack(anchor=tk.W)

        btn_row = tk.Frame(frame, bg="#020617")
        btn_row.pack(anchor=tk.E, pady=(12, 0))
        ttk.Button(btn_row, text="Cerrar", command=top.destroy).pack()

        top.update_idletasks()
        w = top.winfo_width()
        h = top.winfo_height()
        sw = top.winfo_screenwidth()
        sh = top.winfo_screenheight()
        x = (sw - w) // 2
        y = (sh - h) // 3
        top.geometry(f"+{x}+{y}")

    def _show_warning(self, title: str, message: str):
        self._show_dialog(title, message, kind="warning")

    def _show_error(self, title: str, message: str):
        self._show_dialog(title, message, kind="error")

    def _build_ui(self):
        HEADER_BG = "#1e293b"

        header = tk.Frame(self.root, bg=HEADER_BG, height=72)
        header.pack(fill=tk.X, side=tk.TOP)
        header.pack_propagate(False)

        try:
            self._header_logo = tk.PhotoImage(data=base64.b64decode(H2TRAIN_LOGO_B64))
            tk.Label(header, image=self._header_logo, bg=HEADER_BG, bd=0).pack(
                side=tk.LEFT, padx=(20, 12), pady=12)
        except Exception:
            pass

        title_frame = tk.Frame(header, bg=HEADER_BG)
        title_frame.pack(side=tk.LEFT, pady=12)
        tk.Label(title_frame, text="Device Bridge", font=("Poppins", 14),
                 fg="#94a3b8", bg=HEADER_BG).pack(anchor=tk.W)

        tk.Label(header, text=APP_VERSION, font=("Poppins", 9),
                 fg="#475569", bg=HEADER_BG).pack(side=tk.RIGHT, padx=(0, 20), pady=12)

        tk.Frame(self.root, bg="#2563eb", height=3).pack(fill=tk.X)

        nb = ttk.Notebook(self.root)
        # Ocupamos prácticamente todo el ancho/alto de la ventana.
        nb.pack(fill=tk.BOTH, expand=True, padx=4, pady=(6, 10))

        # --- UART tab ---
        # Hacemos la pestaña UART desplazable en vertical para poder ver
        # cómodamente el log y las gráficas aunque la ventana sea pequeña.
        uart_container = ttk.Frame(nb)
        nb.add(uart_container, text="  UART / Serial  ")

        uart_canvas = tk.Canvas(uart_container, bg="#0f172a", highlightthickness=0)
        uart_canvas.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)
        uart_scroll = ttk.Scrollbar(uart_container, orient=tk.VERTICAL, command=uart_canvas.yview)
        uart_scroll.pack(fill=tk.Y, side=tk.RIGHT)
        uart_canvas.configure(yscrollcommand=uart_scroll.set)

        uart_frame = ttk.Frame(uart_canvas, padding=14)
        uart_window = uart_canvas.create_window((0, 0), window=uart_frame, anchor="nw")

        def _uart_on_configure(_e):
            uart_canvas.configure(scrollregion=uart_canvas.bbox("all"))

        uart_frame.bind("<Configure>", _uart_on_configure)

        def _uart_canvas_configure(e):
            uart_canvas.itemconfigure(uart_window, width=e.width)

        uart_canvas.bind("<Configure>", _uart_canvas_configure)

        conn_frame = ttk.LabelFrame(uart_frame, text="Conexi\u00f3n", padding=10)
        conn_frame.grid(row=0, column=0, sticky=tk.EW, pady=(0, 8))

        ttk.Label(conn_frame, text="Puerto:").grid(row=0, column=0, sticky=tk.W, pady=4)
        self.uart_port_var = tk.StringVar()
        self.uart_combo = ttk.Combobox(conn_frame, textvariable=self.uart_port_var, width=38)
        self.uart_combo.grid(row=0, column=1, padx=6, pady=4)
        ttk.Label(conn_frame, text="Baudios:").grid(row=0, column=2, sticky=tk.W, padx=(12, 0))
        self.uart_baud_var = tk.StringVar(value="9600")
        ttk.Spinbox(conn_frame, from_=300, to=2000000, textvariable=self.uart_baud_var,
                    width=10).grid(row=0, column=3, padx=4, pady=4)

        btn_row = ttk.Frame(conn_frame)
        btn_row.grid(row=1, column=0, columnspan=4, sticky=tk.W, pady=(6, 0))
        ttk.Button(btn_row, text="\u21bb Actualizar", command=self._uart_refresh).pack(
            side=tk.LEFT, padx=(0, 6))
        ttk.Button(btn_row, text="Conectar", command=self._uart_open,
                   style="Success.TButton").pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_row, text="Reabrir (aplicar baudios)", command=self._uart_reopen).pack(
            side=tk.LEFT, padx=4
        )
        self.uart_close_btn = ttk.Button(btn_row, text="Desconectar", command=self._uart_close,
                                         state=tk.DISABLED, style="Danger.TButton")
        self.uart_close_btn.pack(side=tk.LEFT, padx=4)
        self.uart_status_var = tk.StringVar(value="\u25cf Desconectado")
        ttk.Label(btn_row, textvariable=self.uart_status_var).pack(side=tk.LEFT, padx=(16, 0))
        # Nucleo F411RE: el COM suele ser "ST-Link Virtual COM"; no filtramos por nombre.
        # Forzar DTR/RTS a veces molesta con ST-Link; Bluepill/CH340 suele ir bien con DTR/RTS.
        self.uart_nucleo_stlink_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            btn_row,
            text="Nucleo ST-Link: sin forzar DTR/RTS",
            variable=self.uart_nucleo_stlink_var,
        ).pack(side=tk.LEFT, padx=(12, 0))

        parser_row = ttk.Frame(conn_frame)
        parser_row.grid(row=2, column=0, columnspan=4, sticky=tk.W, pady=(8, 0))
        ttk.Label(parser_row, text="Parser:").pack(side=tk.LEFT, padx=(0, 4))
        self.uart_parser_var = tk.StringVar(value="H2T 30B + CRC")
        self.uart_parser_combo = ttk.Combobox(
            parser_row,
            textvariable=self.uart_parser_var,
            width=20,
            state="readonly",
            values=["H2T 30B + CRC", "LabVIEW RAW17 (0x02)"],
        )
        self.uart_parser_combo.pack(side=tk.LEFT, padx=(0, 10))
        self.uart_parser_combo.bind("<<ComboboxSelected>>", lambda _e: self._on_uart_parser_changed())

        ttk.Label(parser_row, text="Endian RAW17:").pack(side=tk.LEFT, padx=(0, 4))
        self.uart_raw17_bo_var = tk.StringVar(value="big")
        self.uart_raw17_bo_combo = ttk.Combobox(
            parser_row,
            textvariable=self.uart_raw17_bo_var,
            width=7,
            state="readonly",
            values=["big", "little"],
        )
        self.uart_raw17_bo_combo.pack(side=tk.LEFT, padx=(0, 10))
        self.uart_raw17_bo_combo.bind("<<ComboboxSelected>>", lambda _e: self._on_uart_parser_changed())

        self.uart_raw17_signed_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            parser_row,
            text="RAW17 signed int24",
            variable=self.uart_raw17_signed_var,
            command=self._on_uart_parser_changed,
        ).pack(side=tk.LEFT)
        self.uart_raw17_auto_btn = ttk.Button(
            parser_row,
            text="Auto detect RAW17",
            command=self._start_raw17_autodetect,
        )
        self.uart_raw17_auto_btn.pack(side=tk.LEFT, padx=(10, 0))
        self.uart_raw17_auto300_btn = ttk.Button(
            parser_row,
            text="Auto x300",
            command=lambda: self._start_raw17_autodetect(300),
        )
        self.uart_raw17_auto300_btn.pack(side=tk.LEFT, padx=(6, 0))
        self.uart_filter_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            parser_row,
            text="Filtro señal",
            variable=self.uart_filter_var,
            command=self._on_uart_filter_changed,
        ).pack(side=tk.LEFT, padx=(10, 0))
        chan_row = ttk.Frame(conn_frame)
        chan_row.grid(row=3, column=0, columnspan=4, sticky=tk.W, pady=(8, 0))
        ttk.Label(chan_row, text="Canal 4404:").pack(side=tk.LEFT, padx=(0, 6))
        self.uart_ch_var = tk.IntVar(value=6)
        for ch in range(1, 7):
            ttk.Radiobutton(
                chan_row,
                text=f"D{ch}",
                value=ch,
                variable=self.uart_ch_var,
                command=self._on_4404_channel_changed,
            ).pack(side=tk.LEFT, padx=(0, 6))
        conn_frame.columnconfigure(1, weight=1)

        send_frame = ttk.LabelFrame(uart_frame, text="Enviar datos", padding=10)
        send_frame.grid(row=1, column=0, sticky=tk.EW, pady=(0, 8))
        send_row1 = ttk.Frame(send_frame)
        send_row1.pack(fill=tk.X)
        self.uart_send_var = tk.StringVar()
        self.uart_send_entry = ttk.Entry(send_row1, textvariable=self.uart_send_var, width=50)
        self.uart_send_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
        ttk.Button(send_row1, text="Enviar \u27a4", command=self._uart_send).pack(side=tk.LEFT)
        ttk.Button(send_row1, text="Enviar A (stream)", command=self._uart_send_cmd_a).pack(
            side=tk.LEFT, padx=(6, 0)
        )
        send_row2 = ttk.Frame(send_frame)
        send_row2.pack(fill=tk.X, pady=(8, 0))
        ttk.Label(send_row2, text="Sufijo tras 'A' (si el firmware lo pide):").pack(side=tk.LEFT, padx=(0, 6))
        self.uart_stream_suffix_var = tk.StringVar(value="Ninguno")
        ttk.Combobox(
            send_row2,
            textvariable=self.uart_stream_suffix_var,
            state="readonly",
            width=12,
            values=["Ninguno", "CR (\\r)", "LF (\\n)", "CRLF"],
        ).pack(side=tk.LEFT, padx=(0, 12))
        ttk.Label(
            send_frame,
            text=(
                "Nucleo F411: el 'A' debe entrar por USART2 (PA3=RX). Si solo ves 0x00 y los LEDs SpO2 no "
                "reaccionan, el micro no está recibiendo el comando o no envía H2T: revisa baud, CubeMX "
                "y que TX de la placa vaya al ST-Link."
            ),
            wraplength=720,
            foreground="#555",
        ).pack(anchor=tk.W, pady=(8, 0))

        ttk.Label(uart_frame, text="Datos recibidos").grid(
            row=2, column=0, sticky=tk.W, pady=(4, 2))
        # Hacemos el área de "Datos recibidos" más alta para ver mejor el tráfico.
        self.uart_log = scrolledtext.ScrolledText(
            uart_frame, height=14, width=80, state=tk.DISABLED)
        self.uart_log.grid(row=3, column=0, sticky=tk.NSEW, pady=(0, 4))
        plot_frame = ttk.LabelFrame(uart_frame, text="Gráficas UART (H2T)", padding=8)
        plot_frame.grid(row=4, column=0, sticky=tk.NSEW, pady=(6, 0))
        ttk.Label(
            plot_frame,
            text="3bx: 800 Hz | 4404: selector D1..D6 | SpO2 con D2(IR), D3(Red), D4(Ambient)",
        ).grid(row=0, column=0, sticky=tk.W, pady=(0, 4))
        self.plot_3bx = MiniPlot(plot_frame, "3bx ECG (QRS)", autoscale_lo=0.002, autoscale_hi=0.998)
        self.plot_3bx.grid(row=1, column=0, sticky=tk.EW, pady=2)
        self.plot_h = MiniPlot(plot_frame, "4404 h (derecha) D6")
        self.plot_h.grid(row=2, column=0, sticky=tk.EW, pady=2)
        self.plot_H = MiniPlot(plot_frame, "4404 H (izquierda) D6")
        self.plot_H.grid(row=3, column=0, sticky=tk.EW, pady=2)
        self.uart_packet_stats_var = tk.StringVar(value="Paquetes H2T: OK=0 | CRC_ERR=0")
        ttk.Label(plot_frame, textvariable=self.uart_packet_stats_var).grid(
            row=4, column=0, sticky=tk.W, pady=(4, 0)
        )
        self.uart_spo2_var = tk.StringVar(value="SpO2 estimado: h=--% | H=--%")
        ttk.Label(plot_frame, textvariable=self.uart_spo2_var).grid(
            row=5, column=0, sticky=tk.W, pady=(2, 0)
        )
        plot_frame.columnconfigure(0, weight=1)
        uart_frame.columnconfigure(0, weight=1)
        uart_frame.rowconfigure(3, weight=1)
        uart_frame.rowconfigure(4, weight=1)
        self._on_uart_parser_changed()

        # --- BLE tab ---
        ble_frame = ttk.Frame(nb, padding=14)
        nb.add(ble_frame, text="  Bluetooth (BLE)  ")

        scan_frame = ttk.LabelFrame(ble_frame, text="Escaneo", padding=10)
        scan_frame.grid(row=0, column=0, sticky=tk.EW, pady=(0, 8))
        scan_btns = ttk.Frame(scan_frame)
        scan_btns.pack(fill=tk.X)
        ttk.Button(scan_btns, text="\U0001f50d Escanear dispositivos",
                   command=self._ble_scan_start).pack(side=tk.LEFT, padx=(0, 6))
        self.ble_stop_btn = ttk.Button(scan_btns, text="Detener",
                                       command=self._ble_scan_stop, state=tk.DISABLED,
                                       style="Danger.TButton")
        self.ble_stop_btn.pack(side=tk.LEFT, padx=4)

        ttk.Label(scan_frame, text="Dispositivos encontrados:").pack(anchor=tk.W, pady=(8, 2))
        list_frame = ttk.Frame(scan_frame)
        list_frame.pack(fill=tk.BOTH, expand=True)
        self.ble_listbox = tk.Listbox(list_frame, height=5, width=70)
        self.ble_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.ble_listbox.yview)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.ble_listbox.config(yscrollcommand=scroll.set)
        self.ble_addresses: list = []

        ttk.Button(scan_frame, text="Conectar al seleccionado",
                   command=self._ble_connect, style="Success.TButton").pack(
            anchor=tk.W, pady=(8, 0))

        self.ble_connected_frame = ttk.LabelFrame(
            ble_frame, text="Dispositivo conectado", padding=10)
        self.ble_connected_frame.grid(row=1, column=0, sticky=tk.EW, pady=(0, 8))
        self.ble_connected_label = ttk.Label(self.ble_connected_frame, text="\u2014")
        self.ble_connected_label.pack(anchor=tk.W)
        self.ble_chars_label = ttk.Label(self.ble_connected_frame, text="", justify=tk.LEFT)
        self.ble_chars_label.pack(anchor=tk.W)
        uuid_row = ttk.Frame(self.ble_connected_frame)
        uuid_row.pack(fill=tk.X, pady=(6, 0))
        ttk.Label(uuid_row, text="Servicio:").pack(side=tk.LEFT)
        self.ble_svc_entry = ttk.Entry(uuid_row, width=36)
        self.ble_svc_entry.pack(side=tk.LEFT, padx=(4, 12))
        ttk.Label(uuid_row, text="Caracter\u00edstica:").pack(side=tk.LEFT)
        self.ble_char_entry = ttk.Entry(uuid_row, width=36)
        self.ble_char_entry.pack(side=tk.LEFT, padx=4)
        action_row = ttk.Frame(self.ble_connected_frame)
        action_row.pack(fill=tk.X, pady=(8, 0))
        ttk.Button(action_row, text="Leer", command=self._ble_read).pack(
            side=tk.LEFT, padx=(0, 6))
        ttk.Button(action_row, text="Activar notificaciones",
                   command=self._ble_notify).pack(side=tk.LEFT, padx=4)
        ttk.Button(action_row, text="Desconectar", command=self._ble_disconnect,
                   style="Danger.TButton").pack(side=tk.LEFT, padx=4)
        self.ble_connected_frame.grid_remove()

        ttk.Label(ble_frame, text="Datos recibidos").grid(
            row=2, column=0, sticky=tk.W, pady=(4, 2))
        self.ble_log = scrolledtext.ScrolledText(
            ble_frame, height=10, width=80, state=tk.DISABLED)
        self.ble_log.grid(row=3, column=0, sticky=tk.NSEW, pady=(0, 4))
        ble_frame.columnconfigure(0, weight=1)
        ble_frame.rowconfigure(3, weight=1)

        # --- TD8-ECG Key Generator tab ---
        keys_frame = ttk.Frame(nb, padding=14)
        nb.add(keys_frame, text="  TD8-ECG Keys  ")
        self._build_keys_tab(keys_frame)

    def _build_keys_tab(self, parent: ttk.Frame):
        # Hacemos la pestaña TD8-ECG desplazable en vertical para que se vean
        # bien todas las gráficas incluso en pantallas pequeñas o con ventana reducida.
        canvas = tk.Canvas(parent, bg="#0f172a", highlightthickness=0)
        canvas.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)
        vscroll = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=canvas.yview)
        vscroll.pack(fill=tk.Y, side=tk.RIGHT)
        canvas.configure(yscrollcommand=vscroll.set)

        content = ttk.Frame(canvas)
        window_id = canvas.create_window((0, 0), window=content, anchor="nw")

        def _on_configure(_e):
            canvas.configure(scrollregion=canvas.bbox("all"))

        content.bind("<Configure>", _on_configure)
        # Hacemos que el frame interno siempre tenga el mismo ancho que el canvas,
        # así todo el contenido (incluidas las gráficas) aprovecha el ancho completo.
        def _on_canvas_configure(e):
            canvas.itemconfigure(window_id, width=e.width)

        canvas.bind("<Configure>", _on_canvas_configure)
        canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(int(-1 * (e.delta / 120)), "units"))

        info_frame = ttk.LabelFrame(content, text="Generador de claves TD8-ECG", padding=12)
        info_frame.grid(row=0, column=0, sticky=tk.EW, pady=(0, 10))

        ttk.Label(
            info_frame,
            text=(
                "Esta pestaña implementa un flujo estilo TD8-ECG:\n"
                "ECG \u2192 Conversión RNS (p,q) \u2192 Rdp/Rdq/Cdp/Cdq \u2192 RdS/CdD \u2192 "
                "Función de composición \u2192 Analizador de entropía \u2192 HMAC-SHA-128 (HKDF)."
            ),
            justify=tk.LEFT,
            wraplength=640,
        ).grid(row=0, column=0, sticky=tk.W)

        self.key_status_var = tk.StringVar(value="Esperando datos ECG en la pestaña UART o señal sintética.")
        self.key_hex_var = tk.StringVar(value="")
        self.key_entropy_var = tk.StringVar(value="Entropía: --")
        self.key_pipeline_var = tk.StringVar(value="RNS+HKDF (actual)")
        self.comp_mode_var = tk.StringVar(value="CRT (Teorema Chino del Resto)")
        self.ecg_source_var = tk.StringVar(value="ECG 3bx en vivo")
        self.initial_key_as_seed_var = tk.BooleanVar(value=False)  # False = solo primer segmento; True = mezclar siempre
        self.key_entropy_threshold_var = tk.DoubleVar(value=0.85)
        self.invalid_policy_var = tk.StringVar(value="Descartar no válidas")
        self.recombine_strategy_var = tk.StringVar(value="Mitad + mitad")
        self.keep_tail_bits_var = tk.BooleanVar(value=True)
        self.max_invalid_pool_var = tk.IntVar(value=24)
        self.analysis_window_var = tk.IntVar(value=2048)
        self.analysis_scan_mode_var = tk.StringVar(value="Desplazamiento 1b (máximo)")
        self.ecg_db_input_csv_var = tk.StringVar(value="ecg_signals_db.csv")
        self.ecg_db_output_csv_var = tk.StringVar(value="ecg_key_results.csv")

        controls = ttk.Frame(content)
        controls.grid(row=1, column=0, sticky=tk.EW, pady=(0, 10))

        ttk.Button(
            controls,
            text="Generar clave desde ECG actual",
            command=self._on_generate_ecg_key,
            style="Success.TButton",
        ).pack(side=tk.LEFT)
        ttk.Label(controls, text="Pipeline:").pack(side=tk.LEFT, padx=(14, 4))
        ttk.Combobox(
            controls,
            textvariable=self.key_pipeline_var,
            state="readonly",
            width=26,
            values=[
                "RNS+HKDF (actual)",
                "Acumulativo 11 bits/muestra",
            ],
        ).pack(side=tk.LEFT)

        ttk.Label(controls, text="Fuente ECG:").pack(side=tk.LEFT, padx=(16, 4))
        ttk.Combobox(
            controls,
            textvariable=self.ecg_source_var,
            state="readonly",
            width=20,
            values=[
                "ECG 3bx en vivo",
                "ECG sintético (función)",
            ],
        ).pack(side=tk.LEFT)

        ttk.Label(controls, text="Función de composición:").pack(side=tk.LEFT, padx=(16, 4))
        ttk.Combobox(
            controls,
            textvariable=self.comp_mode_var,
            state="readonly",
            width=28,
            values=[
                "CRT (Teorema Chino del Resto)",
                "XOR mezcla simple (RdS, CdD)",
                "Concat+SHA256 (RdS||CdD)",
                "Interleave bits (RdS, CdD)",
                "RNS parity mix (RdS, CdD)",
            ],
        ).pack(side=tk.LEFT)

        ttk.Label(controls, textvariable=self.key_entropy_var).pack(side=tk.LEFT, padx=(16, 0))

        cfg_frame = ttk.LabelFrame(content, text="Configuración pipeline 11 bits/muestra", padding=10)
        cfg_frame.grid(row=2, column=0, sticky=tk.EW, pady=(8, 0))
        ttk.Label(cfg_frame, text="Umbral entropía (0..0.99):").grid(row=0, column=0, sticky=tk.W, pady=2)
        ttk.Spinbox(
            cfg_frame,
            from_=0.50,
            to=0.99,
            increment=0.01,
            textvariable=self.key_entropy_threshold_var,
            width=6,
        ).grid(row=0, column=1, sticky=tk.W, padx=(4, 12), pady=2)
        ttk.Label(cfg_frame, text="No válidas:").grid(row=0, column=2, sticky=tk.W, pady=2)
        ttk.Combobox(
            cfg_frame,
            textvariable=self.invalid_policy_var,
            state="readonly",
            width=22,
            values=[
                "Descartar no válidas",
                "Guardar para recombinar",
            ],
        ).grid(row=0, column=3, sticky=tk.W, padx=(4, 12), pady=2)
        ttk.Label(cfg_frame, text="Recombinación:").grid(row=1, column=0, sticky=tk.W, pady=2)
        ttk.Combobox(
            cfg_frame,
            textvariable=self.recombine_strategy_var,
            state="readonly",
            width=22,
            values=[
                "Mitad + mitad",
                "Alternar bits",
                "XOR + SHA256",
            ],
        ).grid(row=1, column=1, sticky=tk.W, padx=(4, 12), pady=2)
        ttk.Label(cfg_frame, text="Pool no válidas (máx):").grid(row=1, column=2, sticky=tk.W, pady=2)
        ttk.Spinbox(
            cfg_frame,
            from_=2,
            to=128,
            increment=2,
            textvariable=self.max_invalid_pool_var,
            width=6,
        ).grid(row=1, column=3, sticky=tk.W, padx=(4, 12), pady=2)
        ttk.Checkbutton(
            cfg_frame,
            text="Conservar bits sobrantes para la próxima ejecución",
            variable=self.keep_tail_bits_var,
        ).grid(row=2, column=0, columnspan=4, sticky=tk.W, pady=(4, 0))
        ttk.Button(
            cfg_frame,
            text="Limpiar reserva/pool (11 bits)",
            command=self._clear_11bit_buffers,
        ).grid(row=2, column=3, sticky=tk.E, pady=(4, 0))
        ttk.Label(cfg_frame, text="Análisis conjunto (muestras):").grid(row=3, column=0, sticky=tk.W, pady=(8, 2))
        ttk.Spinbox(
            cfg_frame,
            from_=256,
            to=8192,
            increment=256,
            textvariable=self.analysis_window_var,
            width=7,
        ).grid(row=3, column=1, sticky=tk.W, padx=(4, 12), pady=(8, 2))
        ttk.Label(cfg_frame, text="Barrido 128b:").grid(row=3, column=2, sticky=tk.W, pady=(8, 2))
        ttk.Combobox(
            cfg_frame,
            textvariable=self.analysis_scan_mode_var,
            state="readonly",
            width=26,
            values=[
                "No solapado (128b)",
                "Desplazamiento 11b",
                "Desplazamiento 1b (máximo)",
            ],
        ).grid(row=3, column=3, sticky=tk.W, padx=(4, 12), pady=(8, 2))
        ttk.Button(
            cfg_frame,
            text="Analizar límite y entropía de conjunto",
            command=self._on_analyze_keyset_limit,
        ).grid(row=4, column=0, columnspan=4, sticky=tk.W, pady=(8, 0))
        ttk.Label(cfg_frame, text="DB ECG CSV (entrada):").grid(row=5, column=0, sticky=tk.W, pady=(8, 2))
        ttk.Entry(cfg_frame, textvariable=self.ecg_db_input_csv_var, width=42).grid(
            row=5, column=1, columnspan=2, sticky=tk.W, padx=(4, 12), pady=(8, 2)
        )
        ttk.Label(cfg_frame, text="CSV resultados:").grid(row=6, column=0, sticky=tk.W, pady=(2, 2))
        ttk.Entry(cfg_frame, textvariable=self.ecg_db_output_csv_var, width=42).grid(
            row=6, column=1, columnspan=2, sticky=tk.W, padx=(4, 12), pady=(2, 2)
        )
        ttk.Button(
            cfg_frame,
            text="Procesar DB ECG y exportar CSV",
            command=self._on_process_ecg_db_csv,
            style="Success.TButton",
        ).grid(row=6, column=3, sticky=tk.E, pady=(2, 2))

        status_frame = ttk.LabelFrame(content, text="Resultado de la clave", padding=10)
        status_frame.grid(row=3, column=0, sticky=tk.EW)

        ttk.Label(status_frame, text="Estado:").grid(row=0, column=0, sticky=tk.W)
        ttk.Label(status_frame, textvariable=self.key_status_var).grid(
            row=0, column=1, sticky=tk.W, padx=(4, 0)
        )

        ttk.Label(status_frame, text="Clave (128 bits, hex):").grid(
            row=1, column=0, sticky=tk.W, pady=(6, 0)
        )
        self.key_entry = ttk.Entry(status_frame, textvariable=self.key_hex_var, width=70)
        self.key_entry.grid(row=1, column=1, sticky=tk.W, padx=(4, 0), pady=(6, 0))

        details_frame = ttk.LabelFrame(content, text="Bloques intermedios (RNS / composición)", padding=10)
        details_frame.grid(row=4, column=0, sticky=tk.NSEW, pady=(10, 0))

        self.keys_details = scrolledtext.ScrolledText(
            details_frame, height=10, width=80, state=tk.DISABLED
        )
        self.keys_details.pack(fill=tk.BOTH, expand=True)

        # Gráficas de flujo por ventanas: ECG segmento i y segmento i+1 cifrado con la clave de i.
        flow_frame = ttk.LabelFrame(
            content,
            text="Flujo por ventanas (segmento ECG → clave → cifrado siguiente segmento)",
            padding=10,
        )
        flow_frame.grid(row=5, column=0, sticky=tk.NSEW, pady=(10, 0))

        flow_controls = ttk.Frame(flow_frame)
        flow_controls.grid(row=0, column=0, columnspan=2, sticky=tk.W)

        self.window_len_var = tk.IntVar(value=256)
        ttk.Label(flow_controls, text="Tamaño de ventana (muestras):").pack(side=tk.LEFT)
        ttk.Spinbox(flow_controls, from_=64, to=1024, increment=32, textvariable=self.window_len_var, width=6).pack(
            side=tk.LEFT, padx=(4, 12)
        )
        ttk.Button(
            flow_controls,
            text="Simular flujo por ventanas (ECG en vivo)",
            command=self._on_simulate_window_flow,
        ).pack(side=tk.LEFT, padx=(0, 12))

        # Auto-simulación cada pocos segundos para que el flujo se vaya
        # actualizando solo según llega nueva señal.
        self.auto_flow_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            flow_controls,
            text="Auto (cada 2 s)",
            variable=self.auto_flow_var,
            command=self._on_auto_flow_changed,
        ).pack(side=tk.LEFT, padx=(4, 0))

        ttk.Label(flow_controls, text="Clave inicial (hex, opcional):").pack(side=tk.LEFT)
        self.initial_key_hex_var = tk.StringVar(value="")
        ttk.Entry(flow_controls, textvariable=self.initial_key_hex_var, width=28).pack(side=tk.LEFT, padx=(4, 8))
        ttk.Checkbutton(
            flow_controls,
            text="Clave inicial como semilla (mezclar con todas las claves)",
            variable=self.initial_key_as_seed_var,
        ).pack(side=tk.LEFT, padx=(0, 4))

        # Diagrama lógico segmento → clave → cifrado siguiente segmento
        # a tamaño completo por encima de las gráficas.
        # Altura mayor para que los bloques de clave tengan espacio suficiente
        # y se lean bien los textos y TODOS los candidatos HKDF dentro del
        # propio bloque verde, aunque implique bloques muy altos.
        self.flow_diag = FlowDiagram(flow_frame, height=460)
        self.flow_diag.grid(row=1, column=0, columnspan=2, sticky=tk.EW, pady=(8, 8))

        # Columna izquierda: visión global (ECG completo y cifrado completo).
        self.flow_ecg_plot = MiniPlot(
            flow_frame,
            "ECG (segmentos usados para claves)",
            autoscale_lo=0.01,
            autoscale_hi=0.99,
            height=200,
        )
        self.flow_ecg_plot.grid(row=2, column=0, sticky=tk.EW, pady=(0, 4))

        self.flow_enc_plot = MiniPlot(
            flow_frame,
            "Segmentos cifrados (clave del segmento previo)",
            autoscale_lo=0.01,
            autoscale_hi=0.99,
            height=200,
        )
        self.flow_enc_plot.grid(row=3, column=0, sticky=tk.EW, pady=(4, 4))

        # Columna derecha: todas las ventanas (origen, cifrada, descifrada y error),
        # varios pares apilados por filas.
        pairs_col = ttk.Frame(flow_frame)
        pairs_col.grid(row=2, column=1, rowspan=2, sticky=tk.NSEW, padx=(10, 0))
        self.flow_pair_grid = []
        for row in range(4):
            row_frame = ttk.Frame(pairs_col)
            row_frame.grid(row=row, column=0, sticky=tk.EW, pady=(0, 6))
            plot_ecg = MiniPlot(
                row_frame,
                f"Ventana {row} (ECG origen)",
                autoscale_lo=0.01,
                autoscale_hi=0.99,
                height=80,
            )
            plot_ecg.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 3))
            plot_enc = MiniPlot(
                row_frame,
                f"Ventana {row+1} cifrada",
                autoscale_lo=0.01,
                autoscale_hi=0.99,
                height=80,
            )
            plot_enc.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(3, 3))
            plot_dec = MiniPlot(
                row_frame,
                f"Ventana {row+1} descifrada",
                autoscale_lo=0.01,
                autoscale_hi=0.99,
                height=80,
            )
            plot_dec.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(3, 3))
            plot_err = MiniPlot(
                row_frame,
                f"Error (descifrada - original)",
                autoscale_lo=0.01,
                autoscale_hi=0.99,
                height=80,
            )
            plot_err.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(3, 0))
            self.flow_pair_grid.append((plot_ecg, plot_enc, plot_dec, plot_err))
        pairs_col.columnconfigure(0, weight=1)

        flow_frame.columnconfigure(0, weight=3)
        flow_frame.columnconfigure(1, weight=2)

        content.columnconfigure(0, weight=1)
        content.rowconfigure(4, weight=1)
        content.rowconfigure(5, weight=1)

    def _on_generate_ecg_key(self):
        window = 256
        use_synth = self.ecg_source_var.get() == "ECG sintético (función)"
        if use_synth:
            samples = self._synthetic_ecg(window)
            src = "ECG sintético"
        else:
            if len(self._series_3bx) < window:
                self.key_status_var.set(
                    f"No hay suficientes muestras ECG (se necesitan {window}, hay {len(self._series_3bx)}). "
                    "Selecciona 'ECG sintético (función)' si quieres probar sin señal real."
                )
                return
            samples = list(self._series_3bx)[-window:]
            src = "ECG 3bx en vivo"

        key_bytes, entropy_norm, debug_text, _candidates, _best_idx = self._ecg_key_pipeline(samples)

        self.key_hex_var.set(key_bytes.hex())
        self.key_entropy_var.set(f"Entropía normalizada: {entropy_norm:.3f}")

        self.keys_details.config(state=tk.NORMAL)
        self.keys_details.delete("1.0", tk.END)
        self.keys_details.insert(tk.END, f"[Fuente ECG usada: {src}]\n\n")
        self.keys_details.insert(tk.END, debug_text)
        self.keys_details.config(state=tk.DISABLED)

        threshold = 0.85
        if hasattr(self, "key_entropy_threshold_var"):
            try:
                threshold = float(self.key_entropy_threshold_var.get())
            except Exception:
                threshold = 0.85
        # Mensaje de estado en función de la entropía observada.
        if entropy_norm >= threshold:
            self.key_status_var.set("Clave con entropía alta; adecuada para HMAC-SHA-128 (HKDF).")
        elif entropy_norm >= max(0.7, threshold - 0.12):
            self.key_status_var.set("Clave con entropía media; combinable con otros factores/contexto.")
        else:
            self.key_status_var.set("Clave con entropía baja; usar sólo como demo, no en producción.")

        # Cargar automáticamente la clave generada como clave inicial
        # para el flujo por ventanas.
        if hasattr(self, "initial_key_hex_var"):
            self.initial_key_hex_var.set(self.key_hex_var.get())

    def _clear_11bit_buffers(self):
        self._bit11_reserve_bits = ""
        self._bit11_invalid_pool = []
        self._uart_append_log("Pipeline 11 bits: reserva y pool limpiados.", None)
        self.key_status_var.set("Estado 11 bits limpiado (reserva/pool).")

    def _analyze_keyset_limit_internal(self, params: Optional[dict] = None, update_ui: bool = True, show_modal: bool = True):
        params = params or {}
        n = int(params.get("analysis_window", int(getattr(self, "analysis_window_var", tk.IntVar(value=2048)).get())))
        custom_samples = params.get("samples")
        if custom_samples is not None:
            samples = [float(v) for v in custom_samples]
            src = str(params.get("source_label", "ECG DB"))
        else:
            src_cfg = str(params.get("ecg_source", self.ecg_source_var.get())).strip()
            use_synth = src_cfg == "ECG sintético (función)"
            if use_synth:
                samples = self._synthetic_ecg(n)
                src = "ECG sintético"
            else:
                if len(self._series_3bx) < n:
                    self.key_status_var.set(
                        f"No hay suficientes muestras ECG para análisis ({n} requeridas, {len(self._series_3bx)} disponibles)."
                    )
                    return
                samples = list(self._series_3bx)[-n:]
                src = "ECG 3bx en vivo"

        min_v = min(samples)
        max_v = max(samples)
        span = max(max_v - min_v, 1e-6)
        norm = [int((s - min_v) * 1000.0 / span) for s in samples]

        # Extracción 11 bits por muestra (9 residuo + 2 cociente).
        p = 509
        q = 4
        bitstream = "".join(f"{(v % p):09b}{((v // p) % q):02b}" for v in norm)
        total_bits = len(bitstream)

        scan_mode = str(
            params.get(
                "scan_mode",
                getattr(self, "analysis_scan_mode_var", tk.StringVar(value="Desplazamiento 1b (máximo)")).get(),
            )
        )
        if scan_mode == "No solapado (128b)":
            stride = 128
        elif scan_mode == "Desplazamiento 11b":
            stride = 11
        else:
            stride = 1

        mode = getattr(self, "comp_mode_var", None)
        comp_mode = str(params.get("comp_mode", mode.get() if isinstance(mode, tk.StringVar) else "CRT (Teorema Chino del Resto)"))

        # Recorrido incremental para medir entropía local y de conjunto.
        keys = []
        local_ent = []
        byte_freq = [0] * 256
        total_bytes = 0
        global_progress = []
        unique = set()
        records = []

        ptr = 0
        idx = 0
        max_keys = 0
        if total_bits >= 128:
            max_keys = 1 + ((total_bits - 128) // stride)

        while ptr + 128 <= total_bits:
            block_bits = bitstream[ptr:ptr + 128]
            composed, _desc = self._compose_128_from_bits(block_bits, comp_mode)
            kb = composed.to_bytes(16, "big", signed=False)
            keys.append(kb)
            ent_local = self._normalized_entropy(kb)
            local_ent.append(ent_local)
            unique.add(kb)
            for b in kb:
                byte_freq[b] += 1
                total_bytes += 1
            # Entropía global del conjunto (sobre todos los bytes agregados).
            ent_global = self._global_entropy_norm_from_freq(byte_freq, total_bytes)
            global_progress.append(ent_global)
            src_i0 = max(0, ptr // 11)
            src_i1 = min(len(norm) - 1, (ptr + 127) // 11)
            records.append(
                {
                    "idx": idx,
                    "bit_start": ptr,
                    "bit_end": ptr + 127,
                    "sample_start": src_i0,
                    "sample_end": src_i1,
                    "key_hex": kb.hex(),
                    "local_entropy": ent_local,
                    "global_entropy": ent_global,
                    "bits_head": block_bits[:32],
                    "bits_tail": block_bits[-32:],
                }
            )
            idx += 1
            ptr += stride

        if not keys:
            self.key_status_var.set("No se pudieron construir claves de 128 bits con ese análisis.")
            return

        mean_local = sum(local_ent) / float(len(local_ent))
        min_local = min(local_ent)
        max_local = max(local_ent)
        final_global = global_progress[-1]
        uniq_ratio = len(unique) / float(len(keys))
        system_efficiency = uniq_ratio * final_global
        coverage_ratio = (len(keys) / float(max_keys)) if max_keys else 0.0

        # Puntos de evolución (muestreo) para no saturar salida.
        checkpoints = []
        for frac in (0.1, 0.25, 0.5, 0.75, 1.0):
            i = max(1, int(len(global_progress) * frac))
            checkpoints.append((i, global_progress[i - 1]))

        lines = []
        lines.append("=== Análisis límite de claves y entropía de conjunto ===")
        lines.append(f"Fuente: {src}")
        lines.append(f"Muestras usadas: {len(samples)}")
        lines.append(f"Bits extraídos: {total_bits} (11 por muestra)")
        lines.append(f"Modo barrido: {scan_mode} (stride={stride} bits)")
        lines.append(f"Composición 128b: {comp_mode}")
        lines.append(f"Máximo teórico de claves para este barrido: {max_keys}")
        lines.append(f"Número total de claves: {len(keys)}")
        lines.append(f"Claves únicas: {len(unique)} (ratio={uniq_ratio:.4f})")
        lines.append(f"Cobertura del barrido: {coverage_ratio * 100.0:.2f}%")
        lines.append(f"Eficiencia del sistema (unicidad x H_global): {system_efficiency * 100.0:.2f}%")
        lines.append("")
        lines.append("Entropía local por clave (normalizada):")
        lines.append(f"  min={min_local:.3f}  media={mean_local:.3f}  max={max_local:.3f}")
        lines.append("Entropía global del conjunto (acumulada, normalizada):")
        lines.append(f"  final={final_global:.3f}")
        lines.append("  evolución (n_claves -> H_global):")
        for i, h in checkpoints:
            lines.append(f"    {i:6d} -> {h:.3f}")
        lines.append("")
        lines.append("Primeras 10 claves (hex[0..15], H_local):")
        for i, kb in enumerate(keys[:10]):
            lines.append(f"  {i:02d}: {kb.hex()[:16]}...  H={local_ent[i]:.3f}")

        report = {
            "src": src,
            "samples": len(samples),
            "total_bits": total_bits,
            "scan_mode": scan_mode,
            "stride": stride,
            "comp_mode": comp_mode,
            "max_keys": max_keys,
            "generated": len(keys),
            "total_keys": len(keys),
            "unique": len(unique),
            "uniq_ratio": uniq_ratio,
            "coverage_ratio": coverage_ratio,
            "system_efficiency": system_efficiency,
            "h_local_min": min_local,
            "h_local_mean": mean_local,
            "h_local_max": max_local,
            "h_global_final": final_global,
            "checkpoints": checkpoints,
        }

        if update_ui:
            self.keys_details.config(state=tk.NORMAL)
            self.keys_details.delete("1.0", tk.END)
            self.keys_details.insert(tk.END, "\n".join(lines) + "\n")
            self.keys_details.config(state=tk.DISABLED)
            self.key_status_var.set(
                f"Análisis conjunto completado: {len(keys)} claves, H_global final={final_global:.3f}, únicas={len(unique)}."
            )
            if show_modal:
                self._show_keyset_analysis_modal(report, records, norm)

        self._last_keyset_report = report
        return report

    def _on_analyze_keyset_limit(self):
        self._analyze_keyset_limit_internal(update_ui=True, show_modal=True)

    @staticmethod
    def _parse_ecg_samples_from_row(row: dict) -> list[float]:
        # Formato preferido: columna "samples" con valores separados por ; , | o espacio.
        blob = str(row.get("samples", "")).strip()
        if blob:
            norm_blob = blob.replace("|", ";").replace(",", ";").replace("\t", ";").replace(" ", ";")
            vals = [x for x in (p.strip() for p in norm_blob.split(";")) if x]
            return [float(x) for x in vals]

        # Alternativa: columnas numéricas por muestra (s0,s1,... o cualquier nombre numérico).
        samples = []
        ignored = {"id", "signal_id", "ecg_id", "timestamp", "time", "date", "label", "patient_id"}
        for k, v in row.items():
            key = str(k).strip().lower()
            if key in ignored:
                continue
            txt = str(v).strip()
            if not txt:
                continue
            try:
                samples.append(float(txt))
            except Exception:
                continue
        return samples

    def _on_process_ecg_db_csv(self):
        in_path = self.ecg_db_input_csv_var.get().strip()
        out_path = self.ecg_db_output_csv_var.get().strip()
        if not in_path:
            self.key_status_var.set("Indica el CSV de entrada con señales ECG.")
            return
        if not out_path:
            self.key_status_var.set("Indica el CSV de salida para los resultados.")
            return

        try:
            with open(in_path, "r", encoding="utf-8", newline="") as f:
                rows = list(csv.DictReader(f))
        except Exception as e:
            self.key_status_var.set(f"No se pudo leer CSV de entrada: {e}")
            return

        if not rows:
            self.key_status_var.set("El CSV de entrada no contiene filas.")
            return

        results = []
        ok_count = 0
        min_len = 256
        for i, row in enumerate(rows):
            signal_id = str(row.get("signal_id") or row.get("id") or row.get("ecg_id") or f"signal_{i+1}")
            ts_signal = str(row.get("timestamp") or row.get("time") or row.get("date") or datetime.now().isoformat(timespec="seconds"))
            try:
                samples = self._parse_ecg_samples_from_row(row)
                if len(samples) < min_len:
                    raise ValueError(f"muestras insuficientes ({len(samples)}), mínimo {min_len}")

                key_bytes, entropy_norm, _dbg, _cand, _best = self._ecg_key_pipeline(samples[:min_len])
                report = self._analyze_keyset_limit_internal(
                    params={"samples": samples, "source_label": f"ECG DB:{signal_id}"},
                    update_ui=False,
                    show_modal=False,
                )
                if not report:
                    raise ValueError("no se pudo calcular el reporte de conjunto")

                result = {
                    "signal_id": signal_id,
                    "signal_timestamp": ts_signal,
                    "processed_at": datetime.now().isoformat(timespec="seconds"),
                    "samples_used_key": min_len,
                    "samples_available": len(samples),
                    "key_hex": key_bytes.hex(),
                    "key_entropy_norm": f"{entropy_norm:.6f}",
                    "total_keys": report.get("total_keys", report.get("generated", 0)),
                    "unique_keys": report.get("unique", 0),
                    "uniq_ratio": f"{float(report.get('uniq_ratio', 0.0)):.6f}",
                    "h_global_final": f"{float(report.get('h_global_final', 0.0)):.6f}",
                    "system_efficiency": f"{float(report.get('system_efficiency', 0.0)):.6f}",
                    "scan_mode": report.get("scan_mode", ""),
                    "comp_mode": report.get("comp_mode", ""),
                    "status": "ok",
                    "error": "",
                }
                ok_count += 1
            except Exception as e:
                result = {
                    "signal_id": signal_id,
                    "signal_timestamp": ts_signal,
                    "processed_at": datetime.now().isoformat(timespec="seconds"),
                    "samples_used_key": 0,
                    "samples_available": 0,
                    "key_hex": "",
                    "key_entropy_norm": "",
                    "total_keys": 0,
                    "unique_keys": 0,
                    "uniq_ratio": "",
                    "h_global_final": "",
                    "system_efficiency": "",
                    "scan_mode": "",
                    "comp_mode": "",
                    "status": "error",
                    "error": str(e),
                }
            results.append(result)

        fields = [
            "signal_id",
            "signal_timestamp",
            "processed_at",
            "samples_used_key",
            "samples_available",
            "key_hex",
            "key_entropy_norm",
            "total_keys",
            "unique_keys",
            "uniq_ratio",
            "h_global_final",
            "system_efficiency",
            "scan_mode",
            "comp_mode",
            "status",
            "error",
        ]
        try:
            with open(out_path, "w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=fields)
                writer.writeheader()
                writer.writerows(results)
        except Exception as e:
            self.key_status_var.set(f"No se pudo escribir CSV de salida: {e}")
            return

        self._last_batch_results = results
        self.key_status_var.set(f"Procesamiento DB ECG completado: {ok_count}/{len(results)} señales OK. CSV: {out_path}")

    def _show_keyset_analysis_modal(self, report: dict, records: list, norm_samples: list):
        top = tk.Toplevel(self.root)
        top.title("Análisis detallado de conjunto de claves")
        top.geometry("1180x760")
        top.minsize(1020, 640)
        top.configure(bg="#0f172a")

        # Estilo dedicado para asegurar contraste alto en la tabla del modal.
        style = ttk.Style(top)
        style.configure(
            "Analysis.Treeview",
            background="#111827",
            fieldbackground="#111827",
            foreground="#e5e7eb",
            rowheight=22,
            borderwidth=0,
        )
        style.map(
            "Analysis.Treeview",
            background=[("selected", "#2563eb")],
            foreground=[("selected", "#ffffff")],
        )
        style.configure(
            "Analysis.Treeview.Heading",
            background="#1f2937",
            foreground="#f8fafc",
            relief="flat",
            font=("Poppins", 9, "bold"),
        )
        style.map(
            "Analysis.Treeview.Heading",
            background=[("active", "#374151")],
            foreground=[("active", "#ffffff")],
        )

        container = ttk.Frame(top, padding=10)
        container.pack(fill=tk.BOTH, expand=True)
        container.columnconfigure(0, weight=1)
        container.columnconfigure(1, weight=1)
        container.rowconfigure(2, weight=1)

        summary = scrolledtext.ScrolledText(container, height=10, width=120)
        summary.grid(row=0, column=0, columnspan=2, sticky=tk.EW)
        summary_lines = [
            "=== Resumen del análisis de conjunto ===",
            f"Fuente: {report.get('src')}",
            f"Muestras: {report.get('samples')} | Bits extraídos: {report.get('total_bits')}",
            f"Barrido: {report.get('scan_mode')} (stride={report.get('stride')} bits)",
            f"Composición: {report.get('comp_mode')}",
            f"Máximo teórico: {report.get('max_keys')} | Generadas: {report.get('generated')}",
            f"Número total de claves: {report.get('total_keys', report.get('generated'))}",
            f"Claves únicas: {report.get('unique')} (ratio={report.get('uniq_ratio', 0.0):.4f})",
            f"Cobertura del barrido: {100.0 * report.get('coverage_ratio', 0.0):.2f}%",
            f"Eficiencia del sistema (unicidad x H_global): {100.0 * report.get('system_efficiency', 0.0):.2f}%",
            "Entropía local (min/media/max): "
            f"{report.get('h_local_min', 0.0):.3f} / {report.get('h_local_mean', 0.0):.3f} / {report.get('h_local_max', 0.0):.3f}",
            f"Entropía global final del conjunto: {report.get('h_global_final', 0.0):.3f}",
            "Evolución (n_claves -> H_global): "
            + ", ".join([f"{n}->{h:.3f}" for n, h in report.get("checkpoints", [])]),
        ]
        summary.insert(tk.END, "\n".join(summary_lines) + "\n")
        summary.config(state=tk.DISABLED)

        nav = ttk.Frame(container)
        nav.grid(row=1, column=0, columnspan=2, sticky=tk.EW, pady=(8, 8))
        nav.columnconfigure(4, weight=1)

        step_var = tk.IntVar(value=0)
        step_label_var = tk.StringVar(value="Paso 1/1")
        detail_var = tk.StringVar(value="")

        def _clamp(v):
            if not records:
                return 0
            return max(0, min(len(records) - 1, v))

        def _render_step(i):
            if not records:
                step_label_var.set("Sin registros")
                detail_var.set("No se pudo generar ninguna clave para mostrar.")
                step_plot.set_data([])
                return
            i = _clamp(i)
            step_var.set(i)
            rec = records[i]
            step_label_var.set(f"Paso {i+1}/{len(records)}")
            s0 = int(rec["sample_start"])
            s1 = int(rec["sample_end"])
            seg = norm_samples[s0:s1 + 1] if 0 <= s0 <= s1 < len(norm_samples) else []
            step_plot.set_data(seg)
            detail_var.set(
                f"bits[{rec['bit_start']}..{rec['bit_end']}], muestras[{s0}..{s1}], "
                f"key={rec['key_hex'][:16]}..., H_local={rec['local_entropy']:.3f}, "
                f"H_global={rec['global_entropy']:.3f}, bits_head={rec['bits_head']}..."
            )
            step_text.config(state=tk.NORMAL)
            step_text.delete("1.0", tk.END)
            step_text.insert(
                tk.END,
                f"Índice clave: {rec['idx']}\n"
                f"Rango de bits: {rec['bit_start']}..{rec['bit_end']}\n"
                f"Rango muestras aprox: {rec['sample_start']}..{rec['sample_end']}\n"
                f"Key hex: {rec['key_hex']}\n"
                f"H_local: {rec['local_entropy']:.3f}\n"
                f"H_global acumulada: {rec['global_entropy']:.3f}\n"
                f"Bits cabecera: {rec['bits_head']}\n"
                f"Bits cola: {rec['bits_tail']}\n"
            )
            step_text.config(state=tk.DISABLED)

        ttk.Button(nav, text="<<", command=lambda: _render_step(step_var.get() - 20)).grid(row=0, column=0, padx=(0, 4))
        ttk.Button(nav, text="<", command=lambda: _render_step(step_var.get() - 1)).grid(row=0, column=1, padx=(0, 8))
        ttk.Label(nav, textvariable=step_label_var).grid(row=0, column=2, padx=(0, 8))
        ttk.Button(nav, text=">", command=lambda: _render_step(step_var.get() + 1)).grid(row=0, column=3, padx=(0, 4))
        ttk.Button(nav, text=">>", command=lambda: _render_step(step_var.get() + 20)).grid(row=0, column=4, sticky=tk.W)
        ttk.Button(nav, text="Ir al último", command=lambda: _render_step(len(records) - 1)).grid(row=0, column=5, padx=(8, 0))

        scale_max = max(0, len(records) - 1)
        step_scale = tk.Scale(
            nav,
            from_=0,
            to=scale_max,
            orient=tk.HORIZONTAL,
            showvalue=False,
            command=lambda val: _render_step(int(float(val))),
        )
        step_scale.grid(row=1, column=0, columnspan=6, sticky=tk.EW, pady=(8, 0))

        left = ttk.Frame(container)
        left.grid(row=2, column=0, sticky=tk.NSEW, padx=(0, 6))
        left.rowconfigure(2, weight=1)
        left.columnconfigure(0, weight=1)

        ttk.Label(left, text="Paso actual (ventana y métricas)").grid(row=0, column=0, sticky=tk.W)
        step_plot = MiniPlot(left, "Ventana de muestras aproximada del paso", height=130)
        step_plot.grid(row=1, column=0, sticky=tk.EW, pady=(4, 6))
        ttk.Label(left, textvariable=detail_var).grid(row=2, column=0, sticky=tk.NW)
        step_text = scrolledtext.ScrolledText(left, height=10, width=56)
        step_text.grid(row=3, column=0, sticky=tk.NSEW, pady=(6, 0))

        right = ttk.Frame(container)
        right.grid(row=2, column=1, sticky=tk.NSEW, padx=(6, 0))
        right.rowconfigure(1, weight=1)
        right.columnconfigure(0, weight=1)

        ttk.Label(right, text="Listado de claves generadas (doble clic para ir al paso)").grid(row=0, column=0, sticky=tk.W)
        cols = ("idx", "bits", "samples", "h_local", "h_global", "key")
        tree = ttk.Treeview(right, columns=cols, show="headings", height=16, style="Analysis.Treeview")
        for c, title, w in [
            ("idx", "idx", 60),
            ("bits", "bits[ini..fin]", 140),
            ("samples", "muestras[ini..fin]", 150),
            ("h_local", "H_local", 90),
            ("h_global", "H_global", 90),
            ("key", "key hex (prefijo)", 220),
        ]:
            tree.heading(c, text=title)
            tree.column(c, width=w, stretch=False)
        tree.grid(row=1, column=0, sticky=tk.NSEW)
        ysb = ttk.Scrollbar(right, orient=tk.VERTICAL, command=tree.yview)
        ysb.grid(row=1, column=1, sticky=tk.NS)
        tree.configure(yscrollcommand=ysb.set)

        max_rows = min(len(records), 3000)
        for rec in records[:max_rows]:
            tree.insert(
                "",
                tk.END,
                iid=str(rec["idx"]),
                values=(
                    rec["idx"],
                    f"{rec['bit_start']}..{rec['bit_end']}",
                    f"{rec['sample_start']}..{rec['sample_end']}",
                    f"{rec['local_entropy']:.3f}",
                    f"{rec['global_entropy']:.3f}",
                    rec["key_hex"][:24] + "...",
                ),
            )
        if len(records) > max_rows:
            tree.insert("", tk.END, values=("...", "...", "...", "...", "...", f"Mostrando {max_rows}/{len(records)}"))

        def _on_tree_open(_e=None):
            sel = tree.selection()
            if not sel:
                return
            try:
                i = int(sel[0])
            except Exception:
                return
            _render_step(i)
            step_scale.set(i)

        tree.bind("<Double-1>", _on_tree_open)
        _render_step(0)

    def _on_simulate_window_flow(self):
        window = max(64, int(self.window_len_var.get() or 256))
        use_synth = self.ecg_source_var.get() == "ECG sintético (función)"
        if use_synth:
            # Construimos una señal sintética suficientemente larga para
            # obtener varias ventanas, independientemente del tamaño de ventana.
            segments_needed = 8  # hasta 7 flujos i->i+1
            total_len = window + (segments_needed - 1) * max(window // 2, 64)
            samples = self._synthetic_ecg(total_len)
            src = "ECG sintético"
        else:
            samples = list(self._series_3bx)
            if len(samples) < 2 * window:
                self.key_status_var.set(
                    f"Para simular flujo por ventanas se necesitan al menos {2 * window} muestras ECG; hay {len(samples)}. "
                    "Selecciona 'ECG sintético (función)' si quieres probar sin señal real."
                )
                return
            src = "ECG 3bx en vivo"

        # Usamos sliding windows con solapamiento fijo para que la cantidad
        # de ventanas y claves no dependa tanto del tamaño de ventana.
        max_segments = 6  # máximo nº de pares ventana/clave mostrados
        step = max(window // 2, 64)  # ~50% solapamiento, con mínimo absoluto

        # Recortamos a las últimas muestras suficientes para obtener varias ventanas.
        min_samples = window + (max_segments + 1) * step
        if len(samples) > min_samples:
            samples = samples[-min_samples:]

        segments = []
        i = 0
        while i + window <= len(samples):
            segments.append(samples[i : i + window])
            i += step

        if len(segments) < 2:
            self.key_status_var.set("No hay suficientes segmentos completos para simular el flujo.")
            return

        # Limpiamos buffers de flujo.
        self._flow_ecg.clear()
        self._flow_enc.clear()

        flow_log = []
        flow_log.append("=== Simulación flujo por ventanas TD8-ECG ===")
        flow_log.append(f"Fuente ECG = {src}")
        flow_log.append(f"Tamaño ventana = {window} muestras")
        flow_log.append(f"Nº de segmentos disponibles = {len(segments)}")
        flow_log.append("")

        # Clave inicial opcional definida por el usuario (hex).
        user_key_bytes = None
        key_hex_txt = (self.initial_key_hex_var.get() or "").strip()
        if key_hex_txt:
            try:
                kb = bytes.fromhex(key_hex_txt)
                if len(kb) != 16:
                    kb = hashlib.sha256(kb).digest()[:16]
                user_key_bytes = kb
                flow_log.append(f"Clave inicial definida por usuario (16B) = {user_key_bytes.hex()}")
                flow_log.append("")
            except Exception:
                flow_log.append("Advertencia: clave inicial inválida (hex); se ignora y se usan sólo claves derivadas del ECG.")
                flow_log.append("")

        # Paso 0 (opcional): si hay clave inicial de usuario, se usa para
        # cifrar el primer segmento (segmento 0). Si "clave como semilla siempre"
        # está activo, además se mezclará con cada clave derivada del ECG (HMAC).
        flow_meta = []
        self._flow_pairs_all = []
        use_initial_as_seed = getattr(self, "initial_key_as_seed_var", None)
        mix_with_user_key = (
            user_key_bytes is not None
            and use_initial_as_seed is not None
            and use_initial_as_seed.get()
        )
        # Semilla visual/log del paso inicial: cifrar segmento 0 con clave usuario (si existe).
        if user_key_bytes is not None:
            seg_plain0 = segments[0]
            enc0, dec0, err0 = self._encrypt_segment_for_plot(user_key_bytes, seg_plain0, window_index=-1)
            self._flow_ecg.extend(seg_plain0)
            self._flow_enc.extend(enc0)
            ent0 = self._normalized_entropy(user_key_bytes)
            flow_meta.append(
                {
                    "idx": -1,
                    "key_short": user_key_bytes.hex()[:8],
                    "entropy": ent0,
                    "candidates": [],
                    "best_idx": None,
                    "mixed": False,
                    "active": False,
                    "live": (src == "ECG 3bx en vivo"),
                    "init": True,
                }
            )
            self._flow_pairs_all.append(
                {
                    "idx": -1,
                    "plain": seg_plain0,
                    "enc": enc0,
                    "dec": dec0,
                    "err": err0,
                    "candidates": [],
                    "best_idx": None,
                    "entropy": ent0,
                    "init": True,
                }
            )
            flow_log.append("Paso inicial (sin análisis ECG previo):")
            flow_log.append(f"  Clave inicial usuario (hex) = {user_key_bytes.hex()}")
            flow_log.append("  → Se cifra el primer segmento (segmento 0) con esa clave.")
            flow_log.append("")

        # Para cada par (segmento i → Key_i derivada del ECG → cifrar segmento i+1).
        last_pair_idx = min(len(segments) - 1, max_segments) - 1
        for i in range(min(len(segments) - 1, max_segments)):
            seg_key = segments[i]
            seg_plain = segments[i + 1]

            key_bytes, ent, _dbg, candidates, best_idx = self._ecg_key_pipeline(seg_key)
            # Si "clave inicial como semilla siempre" está activo, mezclar con la clave del usuario.
            if mix_with_user_key:
                key_bytes = hmac.new(user_key_bytes, key_bytes, hashlib.sha256).digest()[:16]
                ent = self._normalized_entropy(key_bytes)

            # Cifrado real de la ventana (AES-128-CTR para forma de onda) +
            # reconstrucción de la señal descifrada y curvas de error para verificación.
            enc_q, dec_q, err_info = self._encrypt_segment_for_plot(key_bytes, seg_plain, i)

            # Cifrado autenticado AES-128-GCM (para dejar rastro criptográfico claro).
            gcm_info = self._encrypt_segment_aes_gcm(key_bytes, seg_plain, i)

            # Añadimos al flujo concatenado para las gráficas.
            self._flow_ecg.extend(seg_plain)
            self._flow_enc.extend(enc_q)

            flow_meta.append(
                {
                    "idx": i,
                    "key_short": key_bytes.hex()[:8],  # clave final usada para cifrar
                    "entropy": ent,
                    "candidates": candidates,
                    "best_idx": best_idx,
                    "mixed": mix_with_user_key,
                    "active": (i == last_pair_idx),
                    "live": (src == "ECG 3bx en vivo"),
                }
            )

            self._flow_pairs_all.append(
                {
                    "idx": i,
                    "plain": seg_plain,
                    "enc": enc_q,
                    "dec": dec_q,
                    "err": err_info,
                    "candidates": candidates,
                    "best_idx": best_idx,
                    "entropy": ent,
                }
            )

            flow_log.append(f"Ventana {i} → clave para cifrar ventana {i+1}:")
            flow_log.append(f"  Key[{i}] (hex) = {key_bytes.hex()}")
            flow_log.append(f"  Entropía normalizada = {ent:.3f}")
            if gcm_info is not None:
                flow_log.append(f"  AES-GCM nonce[{i}] = {gcm_info['nonce']}")
                flow_log.append(f"  AES-GCM tag[{i}]   = {gcm_info['tag']}")
                flow_log.append(f"  AES-GCM ciphertext bytes[{i}] = {gcm_info['len']}")
            flow_log.append(
                f"  Primeros 4 valores cifrados ventana {i+1} = "
                f"{[round(enc_q[k], 2) for k in range(min(4, len(enc_q)))]}"
            )
            flow_log.append("")

        # Actualizamos gráficas de flujo.
        self.flow_ecg_plot.set_series([(self._flow_ecg, "#22c55e")])
        self.flow_enc_plot.set_series([(self._flow_enc, "#f97316")])
        self.flow_ecg_plot.redraw()
        self.flow_enc_plot.redraw()
        self.flow_diag.set_flow(flow_meta)
        # Actualizamos columna derecha con todos los pares visibles.
        if hasattr(self, "flow_pair_grid"):
            for idx, plots in enumerate(self.flow_pair_grid):
                # Soportamos tanto la versión antigua (2/3 plots) como la nueva (4 plots con error).
                plot_ecg = plot_enc = plot_dec = plot_err = None
                if len(plots) == 2:
                    plot_ecg, plot_enc = plots
                elif len(plots) == 3:
                    plot_ecg, plot_enc, plot_dec = plots
                elif len(plots) >= 4:
                    plot_ecg, plot_enc, plot_dec, plot_err = plots

                if idx < len(self._flow_pairs_all):
                    item = self._flow_pairs_all[idx]
                    seg_idx = item["idx"]
                    # En la columna derecha comparamos la ventana que se cifra
                    # (ECG original) con su versión cifrada y descifrada.
                    ecg_plain = item.get("plain") or item.get("ecg_key") or []
                    enc_vals = item.get("enc") or []
                    dec_vals = item.get("dec") or []

                    # Sincronizamos eje Y entre original/cifrada/descifrada.
                    combined = []
                    combined.extend(ecg_plain)
                    combined.extend(enc_vals)
                    combined.extend(dec_vals)
                    if combined and plot_ecg is not None and plot_enc is not None:
                        v_min = min(combined)
                        v_max = max(combined)
                        if v_max <= v_min:
                            v_max = v_min + 1.0
                        shared_scale = (v_min, v_max)
                        plot_ecg.set_external_scale(shared_scale)
                        plot_enc.set_external_scale(shared_scale)
                        if plot_dec is not None:
                            plot_dec.set_external_scale(shared_scale)

                    if plot_ecg is not None:
                        plot_ecg._title = f"Ventana {seg_idx+1} (ECG original)"
                        plot_ecg.set_series([(ecg_plain, "#22c55e")])
                    if plot_enc is not None:
                        plot_enc._title = f"Ventana {seg_idx+1} cifrada con Key {seg_idx}"
                        plot_enc.set_series([(enc_vals, "#f97316")])
                    if plot_dec is not None and dec_vals:
                        plot_dec._title = f"Ventana {seg_idx+1} descifrada"
                        plot_dec.set_series([(dec_vals, "#0ea5e9")])
                    if plot_err is not None and "err" in item:
                        plot_err._title = "Errores (total, cuantización, cifrado)"
                        err_info = item["err"]
                        series = []
                        if isinstance(err_info, dict):
                            if err_info.get("total"):
                                series.append((err_info["total"], "#ef4444"))  # rojo: error total
                            if err_info.get("quant"):
                                series.append((err_info["quant"], "#fde047"))  # amarillo: cuantización
                            if err_info.get("crypto"):
                                series.append((err_info["crypto"], "#22d3ee"))  # cian: cifrado
                        else:
                            # Soportar versiones antiguas donde sólo había una curva.
                            series.append((err_info, "#ef4444"))
                        plot_err.set_series(series)

                else:
                    if plot_ecg is not None:
                        plot_ecg.set_external_scale(None)
                        plot_ecg.set_series([])
                    if plot_enc is not None:
                        plot_enc.set_external_scale(None)
                        plot_enc.set_series([])
                    if plot_dec is not None:
                        plot_dec.set_external_scale(None)
                        plot_dec.set_series([])
                    if plot_err is not None:
                        plot_err.set_series([])

                if plot_ecg is not None:
                    plot_ecg.redraw()
                if plot_enc is not None:
                    plot_enc.redraw()
                if plot_dec is not None:
                    plot_dec.redraw()
                if plot_err is not None:
                    plot_err.redraw()
        # Añadimos log detallado al cuadro de texto.
        self.keys_details.config(state=tk.NORMAL)
        self.keys_details.insert(tk.END, "\n".join(flow_log) + "\n")
        self.keys_details.config(state=tk.DISABLED)

        # Si está activado el modo automático, programamos la siguiente simulación.
        if getattr(self, "auto_flow_var", None) is not None and self.auto_flow_var.get():
            self._schedule_auto_flow()

    def _on_auto_flow_changed(self):
        if self.auto_flow_var.get():
            self._schedule_auto_flow()
        else:
            if self._td8_auto_flow_job is not None:
                try:
                    self.root.after_cancel(self._td8_auto_flow_job)
                except Exception:
                    pass
                self._td8_auto_flow_job = None

    def _schedule_auto_flow(self):
        # Cancelamos cualquier programación anterior y lanzamos una nueva
        # simulación dentro de 2000 ms.
        if self._td8_auto_flow_job is not None:
            try:
                self.root.after_cancel(self._td8_auto_flow_job)
            except Exception:
                pass
        self._td8_auto_flow_job = self.root.after(2000, self._auto_flow_tick)

    def _auto_flow_tick(self):
        # Solo seguimos si el modo auto sigue activo.
        if not getattr(self, "auto_flow_var", None) or not self.auto_flow_var.get():
            self._td8_auto_flow_job = None
            return
        # Reejecutamos la simulación con las últimas muestras disponibles.
        self._on_simulate_window_flow()

    def _encrypt_segment_for_plot(self, key_bytes: bytes, seg_plain, window_index: int):
        """
        Cifra un segmento de ECG con AES-128 en modo CTR (si está disponible)
        y devuelve:
          - señal cifrada (centrada)
          - señal descifrada reconstruida al dominio ECG (centrada)
          - un diccionario con distintas curvas de error (todas centradas):
              * 'total'  : descifrada - original
              * 'quant'  : reconstrucción ideal desde la cuantización - original
              * 'crypto' : descifrada - reconstrucción ideal (error puro de cifrado)
        Si AES no está disponible (no está instalado pycryptodome),
        se recurre al XOR de demostración.
        """
        if not seg_plain or not key_bytes:
            return [], [], {}

        # Cuantizamos la señal a enteros de 16 bits para empaquetarla en bytes.
        min_v = min(seg_plain)
        max_v = max(seg_plain)
        span = max(max_v - min_v, 1e-6)
        plain_q = [int((s - min_v) * 1000.0 / span) & 0xFFFF for s in seg_plain]

        plain_bytes = bytearray()
        for v in plain_q:
            plain_bytes.extend(int(v).to_bytes(2, byteorder="little", signed=False))

        enc_vals = []
        dec_vals = []

        if AES is not None and len(key_bytes) == 16:
            # Nonce derivado de la clave y del índice de ventana para que
            # sea determinista pero distinto por ventana.
            nonce = hashlib.sha256(key_bytes + window_index.to_bytes(4, "big")).digest()[:8]
            cipher_enc = AES.new(key_bytes, AES.MODE_CTR, nonce=nonce)
            enc_bytes = cipher_enc.encrypt(bytes(plain_bytes))

            # En CTR, cifrado y descifrado son la misma operación; usamos una
            # segunda instancia sólo para dejar claro el flujo.
            cipher_dec = AES.new(key_bytes, AES.MODE_CTR, nonce=nonce)
            dec_bytes = cipher_dec.decrypt(enc_bytes)

            enc_vals = [
                int.from_bytes(enc_bytes[i : i + 2], "little", signed=False)
                for i in range(0, len(enc_bytes), 2)
            ]
            dec_vals = [
                int.from_bytes(dec_bytes[i : i + 2], "little", signed=False)
                for i in range(0, len(dec_bytes), 2)
            ]
        else:
            # Fallback de demostración: XOR pseudo-aleatorio con la clave.
            for j, v in enumerate(plain_q):
                k = key_bytes[j % len(key_bytes)]
                enc_vals.append(v ^ k)
                dec_vals.append((v ^ k) ^ k)  # vuelve al original

        if not enc_vals:
            return [], [], {}

        # Convertimos a flotantes centrados para que las formas de onda
        # se vean bien en pantalla.
        mean_enc = sum(enc_vals) / float(len(enc_vals))
        enc_centered = [float(v - mean_enc) for v in enc_vals]

        # Reconstruimos la señal descifrada al dominio original (ECG) usando
        # la inversa aproximada de la cuantización.
        dec_reconstructed = [
            (float(v) / 1000.0) * span + min_v for v in dec_vals
        ]
        mean_dec = sum(dec_reconstructed) / float(len(dec_reconstructed))
        dec_centered = [v - mean_dec for v in dec_reconstructed]

        # Reconstrucción ideal desde la cuantización original (sin pasar por AES).
        recon_plain = [
            (float(v) / 1000.0) * span + min_v for v in plain_q
        ]

        n = min(len(dec_reconstructed), len(seg_plain), len(recon_plain))
        if n <= 0:
            return enc_centered, dec_centered, {}

        # Error total en el dominio original (ECG): incluye cuantización + cifrado.
        err_total = [
            dec_reconstructed[i] - float(seg_plain[i]) for i in range(n)
        ]
        mean_total = sum(err_total) / float(len(err_total))
        err_total_c = [v - mean_total for v in err_total]

        # Error debido sólo a cuantización: reconstrucción ideal - original.
        err_quant = [
            recon_plain[i] - float(seg_plain[i]) for i in range(n)
        ]
        mean_quant = sum(err_quant) / float(len(err_quant))
        err_quant_c = [v - mean_quant for v in err_quant]

        # Error debido sólo al cifrado: descifrada - reconstrucción ideal.
        err_crypto = [
            dec_reconstructed[i] - recon_plain[i] for i in range(n)
        ]
        mean_crypto = sum(err_crypto) / float(len(err_crypto))
        err_crypto_c = [v - mean_crypto for v in err_crypto]

        err_dict = {
            "total": err_total_c,
            "quant": err_quant_c,
            "crypto": err_crypto_c,
        }

        return enc_centered, dec_centered, err_dict

    def _ecg_notch_50hz(self, v: float) -> float:
        """
        Filtro IIR notch en 50 Hz para ECG 3bx.
        Diseño biquad para fs ≈ 800 Hz, f0 = 50 Hz, Q ≈ 30.
        Coeficientes precomputados (normalizados):
          y[n] = b0*x[n] + b1*x[n-1] + b2*x[n-2] - a1*y[n-1] - a2*y[n-2]
        """
        # Coeficientes calculados offline:
        b0 = 0.9937
        b1 = -1.8361
        b2 = 0.9937
        a1 = -1.8361
        a2 = 0.9873

        x0 = v
        y0 = (
            b0 * x0
            + b1 * self._ecg_notch_x1
            + b2 * self._ecg_notch_x2
            - a1 * self._ecg_notch_y1
            - a2 * self._ecg_notch_y2
        )

        # Actualizar estado
        self._ecg_notch_x2 = self._ecg_notch_x1
        self._ecg_notch_x1 = x0
        self._ecg_notch_y2 = self._ecg_notch_y1
        self._ecg_notch_y1 = y0

        return y0

    def _encrypt_segment_aes_gcm(self, key_bytes: bytes, seg_plain, window_index: int):
        """
        Cifra el mismo segmento con AES-128-GCM para mostrar en el log
        los parámetros criptográficos reales (nonce, tag, longitud del
        ciphertext). No se usa para las gráficas, sólo como evidencia
        de un cifrado autenticado.
        """
        if AES is None or not seg_plain or not key_bytes or len(key_bytes) != 16:
            return None

        # Reutilizamos la misma cuantización que para las gráficas.
        min_v = min(seg_plain)
        max_v = max(seg_plain)
        span = max(max_v - min_v, 1e-6)
        plain_q = [int((s - min_v) * 1000.0 / span) & 0xFFFF for s in seg_plain]

        plain_bytes = bytearray()
        for v in plain_q:
            plain_bytes.extend(int(v).to_bytes(2, byteorder="little", signed=False))

        nonce = hashlib.sha256(b"GCM" + key_bytes + window_index.to_bytes(4, "big")).digest()[:12]
        cipher = AES.new(key_bytes, AES.MODE_GCM, nonce=nonce)
        ciphertext, tag = cipher.encrypt_and_digest(bytes(plain_bytes))
        return {
            "nonce": nonce.hex(),
            "tag": tag.hex(),
            "len": len(ciphertext),
        }

    @staticmethod
    def _compose_128_from_bits(bitstream_128: str, mode_val: str) -> tuple[int, str]:
        bits = (bitstream_128 or "").strip()
        if len(bits) < 128:
            bits = bits.ljust(128, "0")
        elif len(bits) > 128:
            bits = bits[:128]

        if mode_val == "XOR mezcla simple (RdS, CdD)":
            a = int(bits[:64], 2)
            b = int(bits[64:128], 2)
            composed = ((a << 64) ^ b) & ((1 << 128) - 1)
            return composed, "XOR simple entre mitades de 64 bits"
        if mode_val == "Concat+SHA256 (RdS||CdD)":
            raw = int(bits, 2).to_bytes(16, "big", signed=False)
            digest = hashlib.sha256(raw).digest()
            return int.from_bytes(digest[:16], "big", signed=False), "SHA-256(bitstream128) truncado"
        if mode_val == "Interleave bits (RdS, CdD)":
            a = bits[:64]
            b = bits[64:128]
            inter = []
            for i in range(64):
                inter.append(a[i])
                inter.append(b[i])
            return int("".join(inter), 2), "Interleave entre dos mitades de 64 bits"
        if mode_val == "RNS parity mix (RdS, CdD)":
            a = int(bits[:64], 2)
            b = int(bits[64:128], 2)
            mixed = ((a << 64) | b) ^ (a ^ b)
            mixed ^= ((a & 1) << 127)
            mixed ^= ((b & 1) << 126)
            return mixed & ((1 << 128) - 1), "XOR + bits de paridad de mitades"
        return int(bits, 2), "Concatenación directa de 128 bits"

    @staticmethod
    def _recombine_invalid_pair(k1: bytes, k2: bytes, strategy: str) -> tuple[bytes, str]:
        if strategy == "Alternar bits":
            a = int.from_bytes(k1, "big", signed=False)
            b = int.from_bytes(k2, "big", signed=False)
            out = 0
            for i in range(128):
                src = a if (i % 2 == 0) else b
                out = (out << 1) | ((src >> (127 - i)) & 1)
            return out.to_bytes(16, "big", signed=False), "Alternar bits(k1,k2)"
        if strategy == "XOR + SHA256":
            x = bytes([a ^ b for a, b in zip(k1, k2)])
            digest = hashlib.sha256(x).digest()
            return digest[:16], "SHA256(k1 XOR k2)[:16]"
        return k1[:8] + k2[8:], "Mitad(k1)+Mitad(k2)"

    def _ecg_key_pipeline(self, samples):
        pipeline_mode = getattr(self, "key_pipeline_var", None)
        if isinstance(pipeline_mode, tk.StringVar) and pipeline_mode.get() == "Acumulativo 11 bits/muestra":
            return self._ecg_key_pipeline_11bit(samples)

        # Normalización sencilla: centrado y re-escalado a enteros positivos.
        min_v = min(samples)
        max_v = max(samples)
        span = max(max_v - min_v, 1e-6)
        norm = [int((s - min_v) * 1000.0 / span) for s in samples]

        # Agregado determinista de la ventana ECG a un entero grande (para el bloque RNS).
        acc = 0
        mod_acc = 1 << 128
        for v in norm:
            acc = (acc * 257 + v) % mod_acc

        # Parámetros RNS (p, q) coprimos.
        p = 4294967291  # ~2^32, primo
        q = 4294967311  # otro primo, gcd(p, q) = 1

        # Bloques RNS básicos.
        rdp = acc % p
        rdq = acc % q
        cdp = sum(norm) % p
        cdq = sum((i + 1) * v for i, v in enumerate(norm)) % q

        # RdS/CdD: acumulados para composición posterior.
        rds = (rdp + (rdq % p)) % p
        cdd = ((cdp % q) - cdq) % q

        # Función de composición seleccionable.
        mode = getattr(self, "comp_mode_var", None)
        mode_val = mode.get() if isinstance(mode, tk.StringVar) else "CRT (Teorema Chino del Resto)"

        if mode_val == "XOR mezcla simple (RdS, CdD)":
            composed = ((rds << 64) ^ (cdd & ((1 << 64) - 1))) & ((1 << 128) - 1)
            comp_desc = "XOR mezcla simple sobre RdS/CdD"
        elif mode_val == "Concat+SHA256 (RdS||CdD)":
            concat = rds.to_bytes(8, "big", signed=False) + cdd.to_bytes(8, "big", signed=False)
            digest = hashlib.sha256(concat).digest()
            composed = int.from_bytes(digest[:16], "big", signed=False)
            comp_desc = "SHA-256(RdS||CdD) → 128 bits"
        elif mode_val == "Interleave bits (RdS, CdD)":
            a = int(rds) & ((1 << 64) - 1)
            b = int(cdd) & ((1 << 64) - 1)
            inter = 0
            for i in range(64):
                inter |= ((a >> i) & 1) << (2 * i)
                inter |= ((b >> i) & 1) << (2 * i + 1)
            composed = inter & ((1 << 128) - 1)
            comp_desc = "Interleave bits(RdS,CdD)"
        elif mode_val == "RNS parity mix (RdS, CdD)":
            mixed = (rds ^ cdd) & ((1 << 128) - 1)
            mixed ^= ((rds & 1) << 127)
            mixed ^= ((cdd & 1) << 126)
            composed = mixed & ((1 << 128) - 1)
            comp_desc = "XOR + paridad(RdS,CdD)"
        else:
            inv_p_mod_q = pow(p, -1, q)
            composed = (rds + p * (((cdd - rds) * inv_p_mod_q) % q)) % (p * q)
            comp_desc = "CRT clásico (p,q)"

        composed_bytes = composed.to_bytes(16, byteorder="big", signed=False)

        # Para maximizar entropía: hash directo de todas las muestras normalizadas.
        buf = bytearray()
        for v in norm:
            buf.extend(int(v & 0xFFFF).to_bytes(2, byteorder="little", signed=False))
        raw_hash = hashlib.sha256(buf).digest()  # 256 bits casi uniformes
        # HKDF con SHA-256, truncado a 128 bits (HMAC-SHA-128 lógico).
        # IKM = combinación de la parte RNS y del hash de las muestras,
        # con un contador interno; exploramos varios candidatos para poder
        # comparar entropías y elegir el mejor.
        salt = b"TD8-ECG-SALT"
        info = b"TD8-ECG-HMAC-SHA-128"
        best_key = None
        best_ent = -1.0
        best_idx = None
        candidates = []
        for counter in range(32):
            ctr = counter.to_bytes(1, "big")
            ikm = composed_bytes + raw_hash + ctr
            candidate = self._hkdf_sha256(ikm, salt, info, length=16)
            ent = self._normalized_entropy(candidate)
            candidates.append(
                {
                    "idx": counter,
                    "entropy": ent,
                    "key_short": candidate.hex()[:8],
                }
            )
            if ent > best_ent:
                best_ent = ent
                best_key = candidate
                best_idx = counter
        key_bytes = best_key
        entropy_norm = best_ent

        debug_lines = []
        debug_lines.append("=== TD8-ECG Key Generation ===")
        debug_lines.append(f"Ventana ECG: {len(samples)} muestras")
        debug_lines.append(f"ECG normalizado [0..1000]: min={min(norm)}, max={max(norm)}")
        debug_lines.append("")
        debug_lines.append("RNS (p, q) con gcd(p,q)=1:")
        debug_lines.append(f"  p = {p}")
        debug_lines.append(f"  q = {q}")
        debug_lines.append("")
        debug_lines.append("Bloques RNS de la figura:")
        debug_lines.append(f"  Rdp = {rdp}")
        debug_lines.append(f"  Rdq = {rdq}")
        debug_lines.append(f"  Cdp = {cdp}")
        debug_lines.append(f"  Cdq = {cdq}")
        debug_lines.append("")
        debug_lines.append("Bloques combinados:")
        debug_lines.append(f"  RdS = (Rdp + Cdp) mod p = {rds}")
        debug_lines.append(f"  CdD = (Rdq - Cdq) mod q = {cdd}")
        debug_lines.append("")
        debug_lines.append("Función de composición:")
        debug_lines.append(f"  Modo = {comp_desc}")
        debug_lines.append(f"  Composed = {composed}")
        debug_lines.append("")
        debug_lines.append("HKDF (HMAC-SHA-256) \u2192 clave 128 bits:")
        debug_lines.append(f"  Key (hex) = {key_bytes.hex()}")
        debug_lines.append(f"  Entropía normalizada (mejor) = {entropy_norm:.3f}")
        debug_lines.append("")
        debug_lines.append("Candidatos HKDF por contador (idx, H_norm, key[0..7]):")
        for c in candidates:
            debug_lines.append(
                f"  ctr={c['idx']:02d}  H={c['entropy']:.3f}  key={c['key_short']}"
            )

        return key_bytes, entropy_norm, "\n".join(debug_lines) + "\n", candidates, best_idx

    def _ecg_key_pipeline_11bit(self, samples):
        min_v = min(samples)
        max_v = max(samples)
        span = max(max_v - min_v, 1e-6)
        norm = [int((s - min_v) * 1000.0 / span) for s in samples]

        p = 509  # residuo ~ 9 bits
        q = 4    # cociente ~ 2 bits
        chunks = []
        for v in norm:
            r = v % p
            c = (v // p) % q
            bits11 = f"{r:09b}{c:02b}"
            chunks.append({"v": v, "r": r, "c": c, "bits11": bits11})

        keep_tail = bool(getattr(self, "keep_tail_bits_var", tk.BooleanVar(value=True)).get())
        reserve = self._bit11_reserve_bits if keep_tail else ""
        stream = reserve + "".join(ch["bits11"] for ch in chunks)

        mode = getattr(self, "comp_mode_var", None)
        mode_val = mode.get() if isinstance(mode, tk.StringVar) else "CRT (Teorema Chino del Resto)"
        threshold_var = getattr(self, "key_entropy_threshold_var", None)
        ent_threshold = float(threshold_var.get()) if isinstance(threshold_var, tk.Variable) else 0.85
        ent_threshold = max(0.0, min(0.99, ent_threshold))
        policy_var = getattr(self, "invalid_policy_var", None)
        invalid_policy = policy_var.get() if isinstance(policy_var, tk.StringVar) else "Descartar no válidas"
        recomb_var = getattr(self, "recombine_strategy_var", None)
        recomb_strategy = recomb_var.get() if isinstance(recomb_var, tk.StringVar) else "Mitad + mitad"

        candidates = []
        valid_keys = []
        used_blocks = 0
        ptr = 0
        while ptr + 128 <= len(stream):
            block_bits = stream[ptr:ptr + 128]
            composed, comp_desc = self._compose_128_from_bits(block_bits, mode_val)
            key_bytes = composed.to_bytes(16, byteorder="big", signed=False)
            ent = self._normalized_entropy(key_bytes)
            ok = ent >= ent_threshold
            candidates.append(
                {
                    "idx": len(candidates),
                    "entropy": ent,
                    "key_short": key_bytes.hex()[:8],
                    "accepted": ok,
                    "origin": "raw11",
                }
            )
            if ok:
                valid_keys.append(key_bytes)
            elif invalid_policy == "Guardar para recombinar":
                self._bit11_invalid_pool.append(key_bytes)
            ptr += 128
            used_blocks += 1

        max_pool_var = getattr(self, "max_invalid_pool_var", None)
        max_pool = int(max_pool_var.get()) if isinstance(max_pool_var, tk.Variable) else 24
        max_pool = max(2, min(256, max_pool))
        if len(self._bit11_invalid_pool) > max_pool:
            self._bit11_invalid_pool = self._bit11_invalid_pool[-max_pool:]

        recombined = 0
        if not valid_keys and invalid_policy == "Guardar para recombinar" and len(self._bit11_invalid_pool) >= 2:
            pool = self._bit11_invalid_pool[:]
            for i in range(0, len(pool) - 1, 2):
                rk, origin_desc = self._recombine_invalid_pair(pool[i], pool[i + 1], recomb_strategy)
                ent = self._normalized_entropy(rk)
                ok = ent >= ent_threshold
                recombined += 1
                candidates.append(
                    {
                        "idx": len(candidates),
                        "entropy": ent,
                        "key_short": rk.hex()[:8],
                        "accepted": ok,
                        "origin": f"recomb:{origin_desc}",
                    }
                )
                if ok:
                    valid_keys.append(rk)

        if keep_tail:
            self._bit11_reserve_bits = stream[ptr:]
        else:
            self._bit11_reserve_bits = ""

        if valid_keys:
            # Elegimos la de mayor entropía entre las válidas.
            key_bytes = max(valid_keys, key=lambda k: self._normalized_entropy(k))
            entropy_norm = self._normalized_entropy(key_bytes)
        else:
            # Fallback determinista para no romper el flujo: hash del stream acumulado.
            fallback = hashlib.sha256(stream.encode("ascii")).digest()[:16]
            key_bytes = fallback
            entropy_norm = self._normalized_entropy(key_bytes)

        best_idx = 0
        for i, c in enumerate(candidates):
            if c["key_short"] == key_bytes.hex()[:8]:
                best_idx = i
                break

        debug_lines = []
        debug_lines.append("=== TD8-ECG Key Generation (11 bits/muestra) ===")
        debug_lines.append(f"Ventana ECG: {len(samples)} muestras")
        debug_lines.append(f"Normalización [0..1000]: min={min(norm)}, max={max(norm)}")
        debug_lines.append(f"Extracción por muestra: residuo 9b (mod {p}) + cociente 2b (//{p} mod {q})")
        debug_lines.append(f"Política no válidas: {invalid_policy}")
        debug_lines.append(f"Estrategia recombinación: {recomb_strategy}")
        debug_lines.append(f"Umbral entropía: {ent_threshold:.2f}")
        debug_lines.append(f"Composición 128 bits: {mode_val}")
        debug_lines.append(f"Bloques de 128 bits procesados: {used_blocks}")
        debug_lines.append(f"Recombinaciones intentadas: {recombined}")
        debug_lines.append(f"Pool no válidas (actual): {len(self._bit11_invalid_pool)}")
        debug_lines.append(f"Bits sobrantes reservados: {len(self._bit11_reserve_bits)}")
        debug_lines.append("")
        debug_lines.append("Primeras muestras -> bloques de 11 bits:")
        for it in chunks[:8]:
            debug_lines.append(
                f"  v={it['v']:4d}  r={it['r']:3d}  c={it['c']}  bits={it['bits11']}"
            )
        if len(chunks) > 8:
            debug_lines.append("  ...")
        debug_lines.append("")
        debug_lines.append(f"Clave final (hex): {key_bytes.hex()}")
        debug_lines.append(f"Entropía final: {entropy_norm:.3f}")
        debug_lines.append("")
        debug_lines.append("Candidatas evaluadas (idx, H_norm, key[0..7], estado, origen):")
        for c in candidates[:64]:
            status = "OK" if c.get("accepted") else "NO"
            debug_lines.append(
                f"  idx={c['idx']:02d}  H={c['entropy']:.3f}  key={c['key_short']}  {status}  {c.get('origin','raw11')}"
            )

        return key_bytes, entropy_norm, "\n".join(debug_lines) + "\n", candidates, best_idx

    @staticmethod
    def _synthetic_ecg(n: int):
        """
        Genera una señal ECG sintética sencilla (onda tipo P-QRS-T repetida)
        para poder probar el pipeline sin necesidad de datos 3bx reales.
        """
        import math
        out = []
        bpm = 70.0
        fs = 800.0  # mismo orden que 3bx
        period = int(fs * 60.0 / bpm)
        if period <= 0:
            period = 800
        for i in range(n):
            t = i % period
            x = t / period
            # P pequeña
            p = math.exp(-((x - 0.15) ** 2) / 0.0008) * 0.3
            # QRS agudo
            qrs = math.exp(-((x - 0.30) ** 2) / 0.00002) * 1.5
            # T más ancha
            t_w = math.exp(-((x - 0.55) ** 2) / 0.0006) * 0.5
            noise = 0.05 * math.sin(2 * math.pi * 12 * x)  # algo de ruido
            v = (p + qrs + t_w + noise) * 1000.0
            out.append(v)
        return out

    @staticmethod
    def _hkdf_sha256(ikm: bytes, salt: bytes, info: bytes, length: int) -> bytes:
        prk = hmac.new(salt, ikm, hashlib.sha256).digest()
        t = b""
        okm = b""
        counter = 1
        while len(okm) < length:
            t = hmac.new(prk, t + info + bytes([counter]), hashlib.sha256).digest()
            okm += t
            counter += 1
        return okm[:length]

    @staticmethod
    def _normalized_entropy(data: bytes) -> float:
        if not data:
            return 0.0
        freq = {}
        for b in data:
            freq[b] = freq.get(b, 0) + 1
        total = float(len(data))
        h = 0.0
        for c in freq.values():
            p = c / total
            h -= p * log2(p)
        # Entropía máxima observable con N muestras es log2(N) (no 8*N).
        # Normalizamos H por ese máximo teórico y acotamos ligeramente < 1.
        max_h = log2(min(256.0, total)) if total > 1 else 1.0
        if max_h <= 0:
            return 0.0
        norm = h / max_h
        return max(0.0, min(0.99, norm))

    @staticmethod
    def _global_entropy_norm_from_freq(freq, total_count: int) -> float:
        if total_count <= 0:
            return 0.0
        h = 0.0
        for c in freq:
            if c <= 0:
                continue
            p = c / float(total_count)
            h -= p * log2(p)
        # Entropía por byte normalizada en [0,1] (max 8 bits).
        return max(0.0, min(0.99, h / 8.0))

    # --- Queue processing ---
    def _process_queue(self):
        try:
            while True:
                cb = self._update_queue.get_nowait()
                try:
                    cb()
                except Exception as e:
                    try:
                        self._uart_append_log(f"ERROR callback UI: {e}", None)
                    except Exception:
                        print(f"ERROR callback UI: {e}")
        except queue.Empty:
            pass
        self._after_id = self.root.after(30, self._process_queue)

    def _schedule(self, cb):
        self._update_queue.put(cb)

    def _enqueue_uart_raw(self, raw: bytes):
        if not raw:
            return
        with self._uart_pending_lock:
            self._uart_pending_raw.extend(raw)
            if self._uart_parse_scheduled:
                return
            self._uart_parse_scheduled = True
        self._schedule(self._drain_uart_raw)

    def _drain_uart_raw(self):
        while True:
            with self._uart_pending_lock:
                if not self._uart_pending_raw:
                    self._uart_parse_scheduled = False
                    return
                chunk = bytes(self._uart_pending_raw)
                self._uart_pending_raw.clear()
            self._safe_handle_uart_bytes(chunk)

    # --- UART ---
    def _uart_refresh(self):
        ports = list_ports()

        def _fmt_port(p):
            tail = (p.get("description") or p.get("manufacturer") or "").strip()
            vid, pid = p.get("vid") or "", p.get("pid") or ""
            extra = f" [{vid}/{pid}]" if vid and pid else ""
            return f"{p['path']} \u2014 {tail}{extra}"

        self.uart_combo["values"] = [_fmt_port(p) for p in ports]
        if ports and not self.uart_port_var.get().strip():
            self.uart_port_var.set(ports[0]["path"])

    def _uart_open(self):
        port = self.uart_port_var.get().split(" \u2014 ")[0].strip() or self.uart_port_var.get()
        if not port:
            self._show_warning("UART", "Selecciona un puerto.")
            return
        try:
            baud = int(self.uart_baud_var.get())
        except ValueError:
            baud = 9600
        try:
            # Si ya hay un puerto abierto, lo reabrimos con la nueva configuración
            # (sin necesidad de desconectar físicamente el USB).
            if self._serial and self._serial.is_open:
                try:
                    self._serial.close()
                except Exception:
                    pass
                self._serial = None
            def on_data(text: str, hex_str: str, raw: bytes):
                # Evita saturar UI con miles de callbacks al conectar.
                self._enqueue_uart_raw(raw)
            nucleo = getattr(self, "uart_nucleo_stlink_var", None)
            no_dtr = nucleo is not None and nucleo.get()
            self._serial = SerialHandler(on_data=on_data)
            self._serial.open(port, baud, assert_dtr_rts=not no_dtr)
            self.uart_status_var.set(f"\u25cf Conectado: {port}")
            self.uart_close_btn.config(state=tk.NORMAL)
            mode = "ST-Link (sin DTR/RTS forzados)" if no_dtr else "DTR/RTS activos"
            self._uart_rx_zero_streak = 0
            self._uart_zero_diag_done = False
            self._uart_append_log(f"Puerto abierto: {port} @ {baud} baud — {mode}", None)
        except Exception as e:
            self._show_error("UART", str(e))
            self.uart_status_var.set(f"\u25cf Error: {e}")

    def _uart_reopen(self):
        # Reaplicar puerto/baudios actuales sin tocar el cable USB.
        self._uart_open()

    def _safe_handle_uart_bytes(self, raw: bytes):
        try:
            if raw:
                only_zero = all(b == 0 for b in raw)
                if only_zero:
                    self._uart_rx_zero_streak += len(raw)
                else:
                    self._uart_rx_zero_streak = 0
                    self._uart_zero_diag_done = False
                if self._uart_rx_zero_streak >= 30 and not self._uart_zero_diag_done:
                    self._uart_zero_diag_done = True
                    self._uart_append_log(
                        "ADVERTENCIA: solo llegan bytes 0x00. Suele indicar: (1) baud distinto al del "
                        "firmware, (2) USART equivocado en el micro (Nucleo: datos por PA2/PA3↔ST-Link), "
                        "(3) el firmware no está transmitiendo H2T. Los LEDs SpO2 solo encienden si el "
                        "firmware recibe 'A' por el UART correcto y arranca el stream.",
                        None,
                    )
                # Evitar inundar el log si solo hay ceros tras el aviso
                log_rx = True
                if only_zero and self._uart_zero_diag_done and self._uart_rx_zero_streak > 35:
                    log_rx = (self._uart_rx_zero_streak % 50 == 0)
                if log_rx:
                    preview = raw[:24].hex()
                    self._uart_append_log(f"RX UART ({len(raw)} bytes)", preview)
            self._handle_uart_bytes(raw)
        except Exception as e:
            self._uart_append_log(f"ERROR parse UART: {e}", None)

    def _uart_close(self):
        if self._serial:
            self._serial.close()
            self._serial = None
        with self._uart_pending_lock:
            self._uart_pending_raw.clear()
            self._uart_parse_scheduled = False
        self._uart_rx_buffer.clear()
        self._uart_h2t_mirror_buffer.clear()
        self._uart_packets_ok = 0
        self._uart_packets_crc_err = 0
        self._uart_raw17_ok = 0
        self._uart_raw17_sync_err = 0
        self._uart_ecg_packets_ok = 0
        self._uart_rx_zero_streak = 0
        self._uart_zero_diag_done = False
        self._raw17_autodetect = False
        self._raw17_auto_packets = 0
        self._series_3bx.clear()
        for q in self._series_h:
            q.clear()
        for q in self._series_H:
            q.clear()
        self._series_h_red.clear()
        self._series_h_ir.clear()
        self._series_H_red.clear()
        self._series_H_ir.clear()
        self._series_h_d6_ac.clear()
        self._series_H_d6_ac.clear()
        self._h_d6_base = None
        self._H_d6_base = None
        self._raw17_red_base = None
        self._raw17_ir_base = None
        self._ecg_lp = None
        self._ecg_base = None
        self._ecg_amp = None
        self._ecg_last_tick = None
        self._h_d6_lp = None
        self._H_d6_lp = None
        self._raw17_red_lp = None
        self._raw17_ir_lp = None
        self._ecg_bp_lp2 = None
        if hasattr(self, "uart_raw17_auto_btn"):
            self.uart_raw17_auto_btn.config(text="Auto detect RAW17")
        if hasattr(self, "uart_raw17_auto300_btn"):
            self.uart_raw17_auto300_btn.config(text="Auto x300")
        self.uart_status_var.set("\u25cf Desconectado")
        self.uart_close_btn.config(state=tk.DISABLED)
        self._uart_append_log("Puerto cerrado", None)

    def _on_uart_parser_changed(self):
        mode_text = self.uart_parser_var.get() if hasattr(self, "uart_parser_var") else "H2T 30B + CRC"
        self._parser_mode = "labview_raw17" if "RAW17" in mode_text else "h2t30"
        if hasattr(self, "uart_raw17_bo_var"):
            self._raw17_byteorder = self.uart_raw17_bo_var.get() or "big"
        if hasattr(self, "uart_raw17_signed_var"):
            self._raw17_signed = bool(self.uart_raw17_signed_var.get())
        self._uart_rx_buffer.clear()
        self._uart_h2t_mirror_buffer.clear()
        self._raw17_red_base = None
        self._raw17_ir_base = None
        self._ecg_lp = None
        self._ecg_base = None
        self._ecg_amp = None
        self._ecg_last_tick = None
        self._h_d6_lp = None
        self._H_d6_lp = None
        self._raw17_red_lp = None
        self._raw17_ir_lp = None
        if self._parser_mode == "labview_raw17":
            self.plot_h._title = "RAW17 RED AC"
            self.plot_H._title = "RAW17 IR AC"
        else:
            self._raw17_autodetect = False
            self._raw17_auto_packets = 0
            ch = self._selected_4404_channel + 1
            self.plot_h._title = f"4404 h (derecha) D{ch}"
            self.plot_H._title = f"4404 H (izquierda) D{ch}"
        if hasattr(self, "uart_raw17_auto_btn"):
            self.uart_raw17_auto_btn.config(
                state=(tk.NORMAL if self._parser_mode == "labview_raw17" else tk.DISABLED)
            )
            if hasattr(self, "uart_raw17_auto300_btn"):
                self.uart_raw17_auto300_btn.config(
                    state=(tk.NORMAL if self._parser_mode == "labview_raw17" else tk.DISABLED)
                )
            if self._parser_mode != "labview_raw17":
                self.uart_raw17_auto_btn.config(text="Auto detect RAW17")
                if hasattr(self, "uart_raw17_auto300_btn"):
                    self.uart_raw17_auto300_btn.config(text="Auto x300")
        self._uart_append_log(
            f"Parser UART: {self._parser_mode} | raw17_endian={self._raw17_byteorder} | raw17_signed={self._raw17_signed}",
            None,
        )

    def _on_4404_channel_changed(self):
        ch = int(self.uart_ch_var.get()) if hasattr(self, "uart_ch_var") else 6
        self._selected_4404_channel = max(0, min(5, ch - 1))
        # Al cambiar canal, limpiamos histórico para mostrar sólo datos nuevos.
        for q in self._series_h:
            q.clear()
        for q in self._series_H:
            q.clear()
        self._series_h_red.clear()
        self._series_h_ir.clear()
        self._series_H_red.clear()
        self._series_H_ir.clear()
        self.plot_h.reset_scale()
        self.plot_H.reset_scale()
        if self._parser_mode != "labview_raw17":
            self.plot_h._title = f"4404 h (derecha) D{self._selected_4404_channel + 1}"
            self.plot_H._title = f"4404 H (izquierda) D{self._selected_4404_channel + 1}"

    def _on_uart_filter_changed(self):
        self._signal_filter_enabled = bool(self.uart_filter_var.get()) if hasattr(self, "uart_filter_var") else True
        self._ecg_lp = None
        self._ecg_base = None
        self._ecg_amp = None
        self._ecg_last_tick = None
        self._ecg_bp_lp2 = None
        self._h_d6_lp = None
        self._H_d6_lp = None
        self._raw17_red_lp = None
        self._raw17_ir_lp = None
        self._uart_append_log(f"Filtro señal: {'ON' if self._signal_filter_enabled else 'OFF'}", None)

    def _start_raw17_autodetect(self, target_packets: Optional[int] = None):
        if self._parser_mode != "labview_raw17":
            self._show_warning("UART", "Activa primero el parser LabVIEW RAW17.")
            return
        if target_packets:
            self._raw17_auto_target = int(target_packets)
        self._raw17_autodetect = True
        self._raw17_auto_packets = 0
        self._raw17_auto_metrics = {
            ("big", False): {"score": 0.0, "base_r": None, "base_i": None, "prev_r": None, "prev_i": None},
            ("big", True): {"score": 0.0, "base_r": None, "base_i": None, "prev_r": None, "prev_i": None},
            ("little", False): {"score": 0.0, "base_r": None, "base_i": None, "prev_r": None, "prev_i": None},
            ("little", True): {"score": 0.0, "base_r": None, "base_i": None, "prev_r": None, "prev_i": None},
        }
        self.uart_raw17_auto_btn.config(text="Detectando...", state=tk.DISABLED)
        if hasattr(self, "uart_raw17_auto300_btn"):
            self.uart_raw17_auto300_btn.config(text="Detectando...", state=tk.DISABLED)
        self._uart_append_log(
            f"Auto RAW17 iniciado ({self._raw17_auto_target} paquetes): probando big/little + signed/unsigned",
            None,
        )

    def _score_raw17_combo(self, packet: bytes, byteorder: str, signed: bool):
        if signed:
            red_raw = self._int24_signed(packet[6:9], byteorder)
            ir_raw = self._int24_signed(packet[9:12], byteorder)
            amb_raw = self._int24_signed(packet[12:15], byteorder)
        else:
            red_raw = self._int24_unsigned(packet[6:9], byteorder)
            ir_raw = self._int24_unsigned(packet[9:12], byteorder)
            amb_raw = self._int24_unsigned(packet[12:15], byteorder)
        return float(red_raw - amb_raw), float(ir_raw - amb_raw)

    def _consume_raw17_autodetect(self, packet: bytes):
        alpha = 0.03
        for key, m in self._raw17_auto_metrics.items():
            bo, signed = key
            r, i = self._score_raw17_combo(packet, bo, signed)
            if m["base_r"] is None:
                m["base_r"] = r
                m["base_i"] = i
                m["prev_r"] = r
                m["prev_i"] = i
                continue
            m["base_r"] = (1.0 - alpha) * m["base_r"] + alpha * r
            m["base_i"] = (1.0 - alpha) * m["base_i"] + alpha * i
            ac = abs(r - m["base_r"]) + abs(i - m["base_i"])
            dv = abs(r - m["prev_r"]) + abs(i - m["prev_i"])
            # Señal buena: energía AC suficiente y transición suave.
            m["score"] += ac / (1.0 + 0.2 * dv)
            m["prev_r"] = r
            m["prev_i"] = i

        self._raw17_auto_packets += 1
        if self._raw17_auto_packets < self._raw17_auto_target:
            return

        best = max(self._raw17_auto_metrics.items(), key=lambda kv: kv[1]["score"])[0]
        self._raw17_byteorder, self._raw17_signed = best
        self.uart_raw17_bo_var.set(self._raw17_byteorder)
        self.uart_raw17_signed_var.set(self._raw17_signed)
        self._raw17_autodetect = False
        self.uart_raw17_auto_btn.config(text="Auto detect RAW17", state=tk.NORMAL)
        if hasattr(self, "uart_raw17_auto300_btn"):
            self.uart_raw17_auto300_btn.config(text="Auto x300", state=tk.NORMAL)
        self._on_uart_parser_changed()
        self._uart_append_log(
            f"Auto RAW17 completado: bo={self._raw17_byteorder} | signed={self._raw17_signed}",
            None,
        )

    def _uart_send(self):
        data = self.uart_send_var.get()
        if not data:
            return
        if not self._serial or not self._serial.is_open:
            self._show_warning("UART", "Abre el puerto antes de enviar.")
            return
        try:
            self._serial.write(data)
            self._uart_append_log(f"Enviado: {data}", None)
            self.uart_send_var.set("")
        except Exception as e:
            self._show_error("UART", str(e))

    def _uart_send_cmd_a(self):
        if not self._serial or not self._serial.is_open:
            self._show_warning("UART", "Abre el puerto antes de enviar.")
            return
        try:
            suf = getattr(self, "uart_stream_suffix_var", None)
            label = suf.get() if suf else "Ninguno"
            if label == "CR (\\r)":
                payload = b"A\r"
            elif label == "LF (\\n)":
                payload = b"A\n"
            elif label == "CRLF":
                payload = b"A\r\n"
            else:
                payload = b"A"
            self._serial.write(payload)
            self._uart_append_log(f"Enviado comando stream: {payload!r} (sufijo={label})", None)
        except Exception as e:
            self._show_error("UART", str(e))

    def _handle_uart_bytes(self, raw: bytes):
        if not raw:
            return
        self._uart_rx_buffer.extend(raw)
        self._uart_h2t_mirror_buffer.extend(raw)
        # Guard against pathological growth if stream gets corrupted.
        if len(self._uart_rx_buffer) > 8192:
            self._uart_rx_buffer = self._uart_rx_buffer[-512:]
        if len(self._uart_h2t_mirror_buffer) > 8192:
            self._uart_h2t_mirror_buffer = self._uart_h2t_mirror_buffer[-512:]

        if self._parser_mode == "labview_raw17":
            # En modo LabVIEW seguimos decodificando ECG (3bx) desde H2T en paralelo.
            while True:
                h2t_packet = self._extract_next_h2t_packet_from(
                    self._uart_h2t_mirror_buffer,
                    count_crc_errors=False,
                    validate_crc=False,
                )
                if h2t_packet is None:
                    break
                if h2t_packet[3] == ord("3"):
                    self._uart_ecg_packets_ok += 1
                    self._process_uart_packet(h2t_packet, include_4404=False)

            while True:
                packet = self._extract_next_raw17_packet()
                if packet is None:
                    break
                self._uart_raw17_ok += 1
                if self._raw17_autodetect:
                    self._consume_raw17_autodetect(packet)
                self._process_raw17_packet_labview(packet)
            self.uart_packet_stats_var.set(
                f"Parser: RAW17 | OK={self._uart_raw17_ok} | SYNC_ERR={self._uart_raw17_sync_err} | bo={self._raw17_byteorder} | signed={self._raw17_signed}"
                + f" | ECG(H2T)={self._uart_ecg_packets_ok}"
                + (f" | AUTO={self._raw17_auto_packets}/{self._raw17_auto_target}" if self._raw17_autodetect else "")
            )
            return

        while True:
            packet = self._extract_next_h2t_packet()
            if packet is None:
                break
            self._uart_packets_ok += 1
            self._process_uart_packet(packet)

        self.uart_packet_stats_var.set(
            f"Parser: H2T30 | OK={self._uart_packets_ok} | CRC_ERR={self._uart_packets_crc_err} | 4404:{self._byteorder_4404}"
        )

    def _extract_next_h2t_packet_from(
        self,
        rx_buffer: bytearray,
        count_crc_errors: bool = False,
        validate_crc: bool = True,
    ) -> Optional[bytes]:
        """
        Extrae un paquete H2T válido de 30 bytes.
        Si detecta corrupción/CRC inválido, re-sincroniza buscando la siguiente cabecera.
        """
        while len(rx_buffer) >= 30:
            idx = rx_buffer.find(b"H2T")
            if idx == -1:
                # Keep tail that could still start a partial header.
                rx_buffer[:] = rx_buffer[-2:]
                return None

            if idx > 0:
                # Drop everything before header candidate.
                del rx_buffer[:idx]

            if len(rx_buffer) < 30:
                return None

            packet = bytes(rx_buffer[:30])
            if (not validate_crc) or self._uart_crc_ok(packet):
                del rx_buffer[:30]
                return packet

            # CRC fail: aggressive re-sync to next header candidate.
            if count_crc_errors:
                self._uart_packets_crc_err += 1
            next_idx = rx_buffer.find(b"H2T", 1)
            if next_idx == -1:
                rx_buffer[:] = rx_buffer[-2:]
                return None
            del rx_buffer[:next_idx]
        return None

    def _extract_next_h2t_packet(self) -> Optional[bytes]:
        return self._extract_next_h2t_packet_from(self._uart_rx_buffer, count_crc_errors=True)

    def _extract_next_raw17_packet(self) -> Optional[bytes]:
        """
        Parser estilo LabVIEW:
        - paquetes fijos de 17 bytes
        - cabecera de 1 byte (por defecto 0x02)
        - resincronización agresiva cuando se pierde framing
        """
        packet_len = 17
        header = self._raw17_header
        while len(self._uart_rx_buffer) >= packet_len:
            if self._uart_rx_buffer[0] != header:
                idx = self._uart_rx_buffer.find(bytes([header]), 1)
                if idx == -1:
                    dropped = len(self._uart_rx_buffer) - 1
                    if dropped > 0:
                        self._uart_raw17_sync_err += dropped
                    self._uart_rx_buffer = self._uart_rx_buffer[-1:]
                    return None
                self._uart_raw17_sync_err += idx
                del self._uart_rx_buffer[:idx]
                continue
            packet = bytes(self._uart_rx_buffer[:packet_len])
            del self._uart_rx_buffer[:packet_len]
            return packet
        return None

    @staticmethod
    def _uart_crc_ok(packet: bytes) -> bool:
        if len(packet) != 30:
            return False
        return (sum(packet) & 0xFF) == 0

    @staticmethod
    def _int24_signed(b: bytes, byteorder: str = "little") -> int:
        """
        Int24 con signo (complemento a 2).
        byteorder puede ser 'little' o 'big' según firmware.
        """
        if len(b) != 3:
            return 0
        v = int.from_bytes(b, byteorder=byteorder, signed=False)
        if v & 0x800000:
            v -= 1 << 24
        return v

    @staticmethod
    def _int24_unsigned(b: bytes, byteorder: str = "little") -> int:
        if len(b) != 3:
            return 0
        return int.from_bytes(b, byteorder=byteorder, signed=False)

    def _decode_4404_payload(self, payload: bytes, byteorder: Optional[str] = None) -> Optional[dict]:
        """
        Payload 4404 (24 bytes):
        [0:4]   ticks (uint32)
        [4:7]   D1 (int24)
        [7:10]  D2 (int24) -> IR candidate
        [10:13] D3 (int24) -> Red candidate
        [13:16] D4 (int24) -> Ambient candidate
        [16:19] D5 (int24) -> Green/HRM candidate
        [19:22] D6 (int24)
        [22:24] padding/reserved
        """
        if len(payload) < 22:
            return None
        bo = byteorder or self._byteorder_4404
        ticks = int.from_bytes(payload[0:4], byteorder=bo, signed=False)
        d1 = self._int24_signed(payload[4:7], byteorder=bo)
        d2 = self._int24_signed(payload[7:10], byteorder=bo)
        d3 = self._int24_signed(payload[10:13], byteorder=bo)
        d4 = self._int24_signed(payload[13:16], byteorder=bo)
        d5 = self._int24_signed(payload[16:19], byteorder=bo)
        d6 = self._int24_signed(payload[19:22], byteorder=bo)
        return {
            "ticks": ticks,
            "d": [d1, d2, d3, d4, d5, d6],
            "ir": d2,
            "red": d3,
            "ambient": d4,
            "green": d5,
        }

    @staticmethod
    def _decode_energy(decoded: dict) -> float:
        # Energía de canales relevantes para decidir endianness útil.
        d = decoded["d"]
        return float(abs(d[1]) + abs(d[2]) + abs(d[4]))

    @staticmethod
    def _estimate_spo2_from_corrected(red_series: deque, ir_series: deque) -> Optional[float]:
        """
        SpO2 estimado por ratio de ratios:
          R = (AC_red/DC_red) / (AC_ir/DC_ir)
          SpO2 ~= 110 - 25*R (aprox sin calibración clínica)
        """
        n = min(len(red_series), len(ir_series), 250)
        if n < 50:
            return None
        red = list(red_series)[-n:]
        ir = list(ir_series)[-n:]
        dc_red = sum(red) / n
        dc_ir = sum(ir) / n
        if abs(dc_red) < 1e-6 or abs(dc_ir) < 1e-6:
            return None
        ac_red = max(1.0, (max(red) - min(red)) / 2.0)
        ac_ir = max(1.0, (max(ir) - min(ir)) / 2.0)
        r = (ac_red / abs(dc_red)) / (ac_ir / abs(dc_ir))
        spo2 = 110.0 - 25.0 * r
        return max(70.0, min(100.0, spo2))

    def _process_uart_packet(self, packet: bytes, include_4404: bool = True):
        sensor_type = chr(packet[3])
        payload = packet[5:29]
        if sensor_type == "3":
            try:
                self._ecg_last_tick = int.from_bytes(payload[18:22], "little", signed=False)
            except Exception:
                pass
            for i in range(4):
                base = i * 6
                raw_val = int.from_bytes(payload[base + 4: base + 6], "little", signed=True)
                v = float(raw_val)
                if self._signal_filter_enabled:
                    # 1) Notch IIR 50 Hz para eliminar interferencia de red (fs ≈ 800 Hz).
                    v = self._ecg_notch_50hz(v)

                    # 2) Filtro suavizado + eliminación de línea base para resaltar QRS.
                    a_lp = 0.28
                    a_base = 0.004
                    if self._ecg_lp is None:
                        self._ecg_lp = v
                    if self._ecg_base is None:
                        self._ecg_base = v
                    self._ecg_lp = (1.0 - a_lp) * self._ecg_lp + a_lp * v
                    self._ecg_base = (1.0 - a_base) * self._ecg_base + a_base * self._ecg_lp
                    v = self._ecg_lp - self._ecg_base
                    # 3) Low-pass adicional suave para atenuar armónicos >~35–40 Hz
                    #    (efecto band-pass 0.5–35 Hz junto con la eliminación de
                    #    línea base previa).
                    a_bp2 = 0.15
                    if self._ecg_bp_lp2 is None:
                        self._ecg_bp_lp2 = v
                    self._ecg_bp_lp2 = (1.0 - a_bp2) * self._ecg_bp_lp2 + a_bp2 * v
                    v = self._ecg_bp_lp2
                self._series_3bx.append(v)
        elif sensor_type in ("h", "H") and include_4404:
            dst = self._series_h if sensor_type == "h" else self._series_H
            if self._bo_auto:
                dec_l = self._decode_4404_payload(payload, "little")
                dec_b = self._decode_4404_payload(payload, "big")
                if not dec_l or not dec_b:
                    return
                self._bo_score["little"] += self._decode_energy(dec_l)
                self._bo_score["big"] += self._decode_energy(dec_b)
                self._bo_packets += 1
                if self._bo_packets >= 30:
                    l = self._bo_score["little"]
                    b = self._bo_score["big"]
                    if b > l * 1.15:
                        self._byteorder_4404 = "big"
                    elif l > b * 1.15:
                        self._byteorder_4404 = "little"
                    # Lock once selected to avoid oscillations by noise.
                    self._bo_auto = False
                    self._bo_packets = 0
                    self._bo_score = {"little": 0.0, "big": 0.0}
                decoded = dec_b if self._byteorder_4404 == "big" else dec_l
            else:
                decoded = self._decode_4404_payload(payload)
            if not decoded:
                return
            d = decoded["d"]
            for ch in range(6):
                dst[ch].append(d[ch])

            # D6 visualización en AC (sin componente DC) para que responda al dedo.
            d6 = float(d[5])
            alpha = 0.01  # baseline lento, estilo "linea base" de LabVIEW
            if sensor_type == "h":
                if self._h_d6_base is None:
                    self._h_d6_base = d6
                self._h_d6_base = (1.0 - alpha) * self._h_d6_base + alpha * d6
                d6_ac = d6 - self._h_d6_base
                if self._signal_filter_enabled:
                    a_lp = 0.20
                    if self._h_d6_lp is None:
                        self._h_d6_lp = d6_ac
                    self._h_d6_lp = (1.0 - a_lp) * self._h_d6_lp + a_lp * d6_ac
                    d6_ac = self._h_d6_lp
                self._series_h_d6_ac.append(d6_ac)
            else:
                if self._H_d6_base is None:
                    self._H_d6_base = d6
                self._H_d6_base = (1.0 - alpha) * self._H_d6_base + alpha * d6
                d6_ac = d6 - self._H_d6_base
                if self._signal_filter_enabled:
                    a_lp = 0.20
                    if self._H_d6_lp is None:
                        self._H_d6_lp = d6_ac
                    self._H_d6_lp = (1.0 - a_lp) * self._H_d6_lp + a_lp * d6_ac
                    d6_ac = self._H_d6_lp
                self._series_H_d6_ac.append(d6_ac)

            # SpO2 uses D2(IR) & D3(Red) corrected by ambient D4.
            red_corr = decoded["red"] - decoded["ambient"]
            ir_corr = decoded["ir"] - decoded["ambient"]
            if sensor_type == "h":
                self._series_h_red.append(red_corr)
                self._series_h_ir.append(ir_corr)
            else:
                self._series_H_red.append(red_corr)
                self._series_H_ir.append(ir_corr)

    def _process_raw17_packet_labview(self, packet: bytes):
        """
        Lectura binaria directa (sin hex string), al estilo LabVIEW:
        red[6:9], ir[9:12], ambient[12:15].
        """
        bo = self._raw17_byteorder
        if self._raw17_signed:
            red_raw = self._int24_signed(packet[6:9], bo)
            ir_raw = self._int24_signed(packet[9:12], bo)
            amb_raw = self._int24_signed(packet[12:15], bo)
        else:
            red_raw = self._int24_unsigned(packet[6:9], bo)
            ir_raw = self._int24_unsigned(packet[9:12], bo)
            amb_raw = self._int24_unsigned(packet[12:15], bo)

        red_corr = float(red_raw - amb_raw)
        ir_corr = float(ir_raw - amb_raw)

        # High-pass suave para visualizar componente AC (similar al comportamiento de LabVIEW).
        alpha = 0.05
        if self._raw17_red_base is None:
            self._raw17_red_base = red_corr
        if self._raw17_ir_base is None:
            self._raw17_ir_base = ir_corr
        self._raw17_red_base = (1.0 - alpha) * self._raw17_red_base + alpha * red_corr
        self._raw17_ir_base = (1.0 - alpha) * self._raw17_ir_base + alpha * ir_corr
        red_ac = red_corr - self._raw17_red_base
        ir_ac = ir_corr - self._raw17_ir_base

        if self._signal_filter_enabled:
            a_lp = 0.20
            if self._raw17_red_lp is None:
                self._raw17_red_lp = red_ac
            if self._raw17_ir_lp is None:
                self._raw17_ir_lp = ir_ac
            self._raw17_red_lp = (1.0 - a_lp) * self._raw17_red_lp + a_lp * red_ac
            self._raw17_ir_lp = (1.0 - a_lp) * self._raw17_ir_lp + a_lp * ir_ac
            red_ac = self._raw17_red_lp
            ir_ac = self._raw17_ir_lp

        # Reutilizamos los dos plots inferiores para RED e IR en modo RAW17.
        self._series_h_d6_ac.append(red_ac)
        self._series_H_d6_ac.append(ir_ac)
        self._series_h_red.append(red_corr)
        self._series_h_ir.append(ir_corr)
        self._series_H_red.append(red_corr)
        self._series_H_ir.append(ir_corr)

    def _refresh_uart_plots(self):
        self.plot_3bx.set_series([(self._series_3bx, "#60a5fa")])
        if self._parser_mode == "labview_raw17":
            self.plot_h.set_series([(self._series_h_d6_ac, "#a855f7")])
            self.plot_H.set_series([(self._series_H_d6_ac, "#a855f7")])
        else:
            ch = self._selected_4404_channel
            self.plot_h.set_series([(self._series_h[ch], "#a855f7")])
            self.plot_H.set_series([(self._series_H[ch], "#a855f7")])
        self.plot_3bx.redraw()
        self.plot_h.redraw()
        self.plot_H.redraw()

        spo2_h = self._estimate_spo2_from_corrected(self._series_h_red, self._series_h_ir)
        spo2_H = self._estimate_spo2_from_corrected(self._series_H_red, self._series_H_ir)
        txt_h = f"{spo2_h:.1f}%" if spo2_h is not None else "--%"
        txt_H = f"{spo2_H:.1f}%" if spo2_H is not None else "--%"
        self.uart_spo2_var.set(f"SpO2 estimado: h={txt_h} | H={txt_H}")
        self._plot_after_id = self.root.after(120, self._refresh_uart_plots)

    def _uart_append_log(self, text: str, hex_str: Optional[str]):
        self.uart_log.config(state=tk.NORMAL)
        from datetime import datetime
        ts = datetime.now().strftime("%H:%M:%S")
        self.uart_log.insert(tk.END, f"[{ts}] {text}\n")
        if hex_str:
            self.uart_log.insert(tk.END, f"[{ts}] RX (hex): {hex_str}\n")
        self.uart_log.see(tk.END)
        self.uart_log.config(state=tk.DISABLED)

    # --- BLE ---
    def _get_ble(self) -> BLEHandler:
        if self._ble is None:
            def on_device(addr: str, name: str, rssi: int):
                self._schedule(lambda: self._ble_add_device(addr, name, rssi))
            def on_data(svc: str, char: str, hex_str: str, text: str):
                self._schedule(lambda: self._ble_append_log(svc, char, hex_str, text))
            self._ble = BLEHandler(on_scan_result=on_device, on_ble_data=on_data)
        return self._ble

    def _ble_scan_start(self):
        try:
            self._get_ble().start_scan()
            self.ble_stop_btn.config(state=tk.NORMAL)
            self.ble_listbox.delete(0, tk.END)
            self.ble_addresses.clear()
        except Exception as e:
            self._show_error("BLE", str(e))

    def _ble_add_device(self, addr: str, name: str, rssi: int):
        if addr in self.ble_addresses:
            return
        self.ble_addresses.append(addr)
        self.ble_listbox.insert(tk.END, f"{name} \u2014 {addr} (RSSI: {rssi})")

    def _ble_scan_stop(self):
        if self._ble:
            self._ble.stop_scan()
        self.ble_stop_btn.config(state=tk.DISABLED)

    def _ble_connect(self):
        sel = self.ble_listbox.curselection()
        if not sel:
            self._show_warning("BLE", "Selecciona un dispositivo de la lista.")
            return
        idx = int(sel[0])
        if idx >= len(self.ble_addresses):
            return
        address = self.ble_addresses[idx]
        try:
            self._ble_scan_stop()
            info = self._get_ble().connect(address)
            self._ble_info = info
            self.ble_connected_label.config(text=f"Conectado: {info.get('name', address)}")
            chars_text = "Servicios y caracter\u00edsticas:\n"
            for c in info.get("characteristics", []):
                chars_text += f"  {c['serviceUuid']} / {c['uuid']} {c.get('properties', [])}\n"
            self.ble_chars_label.config(text=chars_text)
            self.ble_connected_frame.grid()
            self._ble_append_log(
                f"Conectado: {info.get('name', address)}", None, None, None)
        except Exception as e:
            self._show_error("BLE", str(e))

    def _ble_append_log(self, svc: Optional[str], char: Optional[str],
                        hex_str: Optional[str], text: Optional[str]):
        self.ble_log.config(state=tk.NORMAL)
        from datetime import datetime
        ts = datetime.now().strftime("%H:%M:%S")
        if hex_str is not None or text is not None:
            self.ble_log.insert(tk.END, f"[{ts}] Notify {char or ''}: {text or hex_str}\n")
        elif svc is not None:
            self.ble_log.insert(tk.END, f"[{ts}] {svc}\n")
        self.ble_log.see(tk.END)
        self.ble_log.config(state=tk.DISABLED)

    def _ble_read(self):
        if not self._ble or not self._ble_info:
            return
        su = self.ble_svc_entry.get().strip()
        cu = self.ble_char_entry.get().strip()
        if not su or not cu:
            self._show_warning("BLE", "Indica UUID de servicio y caracter\u00edstica.")
            return
        try:
            data = self._ble.read_characteristic(su, cu)
            self._ble_append_log(su, cu, data, None)
        except Exception as e:
            self._show_error("BLE", str(e))

    def _ble_notify(self):
        if not self._ble or not self._ble_info:
            return
        su = self.ble_svc_entry.get().strip()
        cu = self.ble_char_entry.get().strip()
        if not su or not cu:
            self._show_warning("BLE", "Indica UUID de servicio y caracter\u00edstica.")
            return
        try:
            self._ble.start_notify(su, cu)
            self._ble_append_log(None, cu, None, f"Notificaciones activadas para {cu}")
        except Exception as e:
            self._show_error("BLE", str(e))

    def _ble_disconnect(self):
        if self._ble:
            self._ble.disconnect()
        self._ble_info = None
        self.ble_connected_frame.grid_remove()
        self._ble_append_log("Desconectado", None, None, None)

    # --- Lifecycle ---
    def run(self):
        self._uart_refresh()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.mainloop()

    def _on_close(self):
        if self._api_server:
            try:
                self._api_server.server_close()
            except Exception:
                pass
            self._api_server = None
        if self._serial and self._serial.is_open:
            self._serial.close()
        if self._ble:
            try:
                self._ble.disconnect()
            except Exception:
                pass
        if self._after_id:
            self.root.after_cancel(self._after_id)
        if self._plot_after_id:
            self.root.after_cancel(self._plot_after_id)
        self.root.destroy()


def main():
    app = DeviceBridgeApp()
    app.run()


if __name__ == "__main__":
    main()
