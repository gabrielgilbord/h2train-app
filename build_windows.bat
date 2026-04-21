@echo off
REM Genera la app de escritorio para Windows (DeviceBridge.exe en dist\DeviceBridge\)
REM Ejecutar desde desktop-app-python con el venv activado.

cd /d "%~dp0"

where pyinstaller >nul 2>nul
if errorlevel 1 (
    echo Instalando PyInstaller...
    python -m pip install pyinstaller
)

echo Construyendo aplicacion para Windows...
python -m PyInstaller --clean --noconfirm app.spec

echo.
echo Listo. Salida en: dist\DeviceBridge\
echo Ejecutable: dist\DeviceBridge\DeviceBridge.exe
echo.
pause
