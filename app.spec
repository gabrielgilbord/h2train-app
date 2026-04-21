# PyInstaller spec: genera la app de escritorio para Linux (y otros SO).
# Uso: pyinstaller app.spec
# Salida: dist/DeviceBridge/ con el ejecutable "DeviceBridge" y las librerías

# -*- mode: python ; coding: utf-8 -*-
import sys
from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

# Incluir todos los submódulos de serial (pyserial) y bleak para evitar fallos al ejecutar
_serial_imports = collect_submodules('serial')
_bleak_imports = collect_submodules('bleak')
# dbus_fast solo en Linux (BLE con BlueZ); en Windows no existe
_dbus_imports = collect_submodules('dbus_fast') if sys.platform != 'win32' else []

a = Analysis(
    ['app.py'],
    pathex=['.'],
    binaries=[],
    datas=[('fonts', 'fonts')],
    hiddenimports=[
        'serial_handler',
        'ble_handler',
    ] + _serial_imports + _bleak_imports + _dbus_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# Carpeta con ejecutable + dependencias (recomendado para Linux; más estable con BLE/DBus)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='DeviceBridge',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon='app_icon.ico' if sys.platform == 'win32' else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='DeviceBridge',
)
