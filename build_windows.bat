@echo off
REM Build odoo-epos-bridge.exe on Windows.
REM Requires Python 3.11+ 64-bit installed with "Add python.exe to PATH" checked.
REM Run by double-clicking this file, or:  build_windows.bat

setlocal
cd /d "%~dp0"

python --version || (echo ERROR: Python not found in PATH. & pause & exit /b 1)

python -m pip install --upgrade pip
pip install -r requirements.txt

pyinstaller --noconfirm main.spec || (echo ERROR: PyInstaller build failed. & pause & exit /b 1)

echo.
echo Build OK: dist\odoo-epos-bridge.exe
echo Run it with: dist\odoo-epos-bridge.exe
echo Configure printer with: set POS_PRINTER_NAME=Your-Printer-Name
pause
