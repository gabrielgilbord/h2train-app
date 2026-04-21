# Device Bridge — Versión Python

Misma funcionalidad que la app Electron (UART + Bluetooth BLE) pero **todo en Python**. Pensada para cuando vayáis a integrar mucha lógica en Python (scripts, análisis, ML, etc.).

## Ventajas de la versión Python

- **Todo en Python**: fácil añadir librerías (numpy, pandas, scipy, etc.) y lógica propia.
- **Menos peso**: no usa Electron ni Node.js.
- **Misma experiencia**: UART (PySerial) y BLE (Bleak), interfaz con Tkinter.

## Requisitos

- **Python 3.8+** (recomendado 3.10+).
- En **Linux/Raspbian**: permisos para serial y Bluetooth (igual que en la versión Electron; ver el README de `desktop-app`).

## Instalación

```bash
cd desktop-app-python
python3 -m venv venv
# En Windows:
venv\Scripts\activate
# En Linux/macOS:
source venv/bin/activate

pip install -r requirements.txt
```

## Ejecutar

```bash
python app.py
```

(O con el venv activado: `python app.py`.)

## Uso

- **UART**: pestaña "UART / Serial" → Actualizar lista → elegir puerto y baudios → Abrir. Enviar y ver datos en el log.
- **BLE**: pestaña "Bluetooth (BLE)" → Escanear → Conectar al dispositivo → Leer o activar notificaciones con los UUID de servicio y característica.

## Estructura

- `app.py` — Ventana principal (Tkinter), pestañas UART y BLE.
- `serial_handler.py` — Puerto serie con PySerial.
- `ble_handler.py` — Bluetooth BLE con Bleak (async en un hilo).
- `requirements.txt` — PySerial y Bleak.

Podéis importar estos módulos desde otros scripts Python (por ejemplo un proceso que lea UART/BLE y envíe datos a tu backend o a un dashboard).

## Raspbian

Mismos permisos que la app Electron:

- **Serial**: `sudo usermod -a -G dialout $USER` y cerrar sesión.
- **Bluetooth**: `sudo apt install libbluetooth-dev` y `sudo setcap cap_net_raw+eip $(readlink -f $(which python3))` (o la ruta del python del venv si usas venv).

## Generar aplicación de escritorio para Linux

Puedes **generar un ejecutable** para Linux para que los usuarios no tengan que instalar Python ni dependencias. Se usa **PyInstaller**.

### Pasos (en una máquina Linux, p. ej. tu Raspberry o un PC con Ubuntu)

1. Instalar dependencias del proyecto y de build:
   ```bash
   cd desktop-app-python
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   pip install -r requirements-build.txt
   ```

2. Generar la aplicación:
   ```bash
   chmod +x build_linux.sh
   ./build_linux.sh
   ```
   Si sale **"intérprete erróneo"** o **`/bin/bash^M`**, el script tiene finales de línea Windows. Arregla con:
   ```bash
   tr -d '\r' < build_linux.sh > build_linux_fixed.sh && chmod +x build_linux_fixed.sh && mv build_linux_fixed.sh build_linux.sh
   ./build_linux.sh
   ```
   O haz el build sin el script: `pyinstaller --clean --noconfirm app.spec`

3. Resultado en **`dist/DeviceBridge/`**: ejecutable **`DeviceBridge`** y carpeta con librerías.

Puedes **copiar toda la carpeta `dist/DeviceBridge`** a otra Linux (misma arquitectura). El usuario solo ejecuta `./DeviceBridge` (no necesita Python instalado).

### Si sale "Failed to execute script 'app'" o errores de serial_handler/import (Linux)

El spec ya incluye todos los submódulos de `serial` y `bleak`. Vuelve a compilar con el `app.spec` actualizado. Si sigue fallando, en `app.spec` cambia `console=False` por `console=True`, recompila y ejecuta `./DeviceBridge` desde la terminal para ver el traceback.

### .deb opcional (Linux)

Para instalar en `/opt` y un lanzador en el menú, empaqueta `dist/DeviceBridge` en un .deb con `dpkg-deb` o `fpm`.

---

## Generar aplicación de escritorio para Windows

Tienes que compilar **en Windows** (el mismo proyecto, mismo `app.spec`).

1. En **Windows**, abre PowerShell o CMD y:
   ```cmd
   cd desktop-app-python
   python -m venv venv
   venv\Scripts\activate
   pip install -r requirements.txt
   pip install -r requirements-build.txt
   ```

2. Generar la aplicación:
   ```cmd
   build_windows.bat
   ```
   O manualmente:
   ```cmd
   python -m PyInstaller --clean --noconfirm app.spec
   ```

3. Resultado en **`dist\DeviceBridge\`**: **`DeviceBridge.exe`** y la carpeta con las DLL. Puedes copiar toda la carpeta a otro Windows; el usuario ejecuta `DeviceBridge.exe` (no necesita Python instalado).

Si en Windows sale error al ejecutar el .exe, en `app.spec` pon `console=True`, recompila y ejecuta `DeviceBridge.exe` desde CMD para ver el mensaje de error.

---

## Electron vs Python

| | Electron (`desktop-app`) | Python (`desktop-app-python`) |
|---|---|---|
| Lenguaje | JavaScript/Node | Python |
| UART | serialport | PySerial |
| BLE | @abandonware/noble | Bleak |
| GUI | HTML/CSS/JS | Tkinter |
| Distribución | .deb / AppImage (electron-builder) | Ejecutable Linux con PyInstaller |

Para una app de escritorio para Linux basada en Python, genera el ejecutable con los pasos de arriba y distribuye la carpeta `dist/DeviceBridge`.
