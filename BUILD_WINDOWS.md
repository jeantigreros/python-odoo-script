# Build Windows Service

`main.py` is ready to be packaged as a Windows service by NSSM. 71 tests pass.

## What was fixed in `main.py`

- Removed `from app import app` (no such module, crashed on startup).
- Now uses `serve(app, host=127.0.0.1, port=5000, threads=8)` instead of `app.run()`.
- Added `multiprocessing.freeze_support()` + `main()` entry point for PyInstaller.
- `win32print` import is now safe (clear error if run off-Windows); printer from `POS_PRINTER_NAME` env or Windows default.

## Files added

- `main.spec` — PyInstaller one-file build → `dist\odoo-epos-bridge.exe` (console kept for logs).
- `build_windows.bat` — double-click build script.
- `install_windows_service.ps1` — installs the EXE as a Windows service using NSSM.
- `requirements.txt` — added `waitress`, `pywin32; sys_platform=="win32"`, `pyinstaller`.
- `.github/workflows/build-windows-exe.yml` — builds a ZIP bundle with the EXE, NSSM, and installer script.

## Build on Windows

Must build on Windows — Linux can't cross-build a Windows `.exe`.

```bat
build_windows.bat
```

Or manually:

```bat
pip install -r requirements.txt
pyinstaller --noconfirm main.spec
dist\odoo-epos-bridge.exe
```

## Install as a Windows service with NSSM

From a Windows machine with Administrator rights:

```powershell
.\install_windows_service.ps1 -ServiceName OdooPrinter -DisplayName "Odoo Printer"
```

This will:

- find the bundled `odoo-epos-bridge.exe`
- install it as an NSSM-managed service
- start the service automatically

## Configure

```bat
set POS_PRINTER_NAME=POS-80
set POS_PRINTER_WIDTH_DOTS=576
dist\odoo-epos-bridge.exe
```

Endpoint: `http://127.0.0.1:5000/cgi-bin/epos/service.cgi`
