#!/bin/bash
# Genera la aplicación de escritorio para Linux (ejecutable + carpeta en dist/).
# Ejecutar desde desktop-app-python con el venv activado (o pip install pyinstaller).

set -e
cd "$(dirname "$0")"

if ! command -v pyinstaller &>/dev/null; then
  echo "Instalando PyInstaller..."
  python3 -m pip install pyinstaller
fi

echo "Construyendo aplicación para Linux..."
python3 -m PyInstaller --clean --noconfirm app.spec

echo ""
echo "Listo. Salida en: dist/DeviceBridge/"
echo "Ejecutable: dist/DeviceBridge/DeviceBridge"
echo "Puedes copiar la carpeta 'DeviceBridge' a otra máquina Linux (misma arquitectura)."
