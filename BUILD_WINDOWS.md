# Build Windows .exe

`main.py` is Windows `.exe` ready. 71 tests pass.

## What was fixed in `main.py`

- Removed `from app import app` (no such module, crashed on startup).
- Now uses `serve(app, host=127.0.0.1, port=5000, threads=8)` instead of `app.run()`.
- Added `multiprocessing.freeze_support()` + `main()` entry point for PyInstaller.
- `win32print` import is now safe (clear error if run off-Windows); printer from `POS_PRINTER_NAME` env or Windows default.

## Files added

- `main.spec` — PyInstaller one-file build → `dist\odoo-epos-bridge.exe` (console kept for logs).
- `build_windows.bat` — double-click build script.
- `requirements.txt` — added `waitress`, `pywin32; sys_platform=="win32"`, `pyinstaller`.
- `.github/workflows/build-windows-exe.yml` — auto-builds the `.exe` on push.

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

## Configure

```bat
set POS_PRINTER_NAME=POS-80
set POS_PRINTER_WIDTH_DOTS=576
dist\odoo-epos-bridge.exe
```

Endpoint: `http://127.0.0.1:5000/cgi-bin/epos/service.cgi`
