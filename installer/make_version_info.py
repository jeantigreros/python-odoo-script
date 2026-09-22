"""Generate version_info.txt for PyInstaller from version.py (run in CI)."""
import sys

sys.path.insert(0, ".")
from version import __version__

parts = (__version__.split("-")[0].split(".") + ["0", "0", "0"])[:4]
nums = tuple(int(p) if p.isdigit() else 0 for p in parts)

tpl = f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={nums}, prodvers={nums}, mask=0x3F,
    flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[StringFileInfo([StringTable('040904B0', [
    StringStruct('CompanyName', 'OdooPrinter'),
    StringStruct('FileDescription', 'Odoo POS ePOS bridge'),
    StringStruct('FileVersion', '{__version__}'),
    StringStruct('InternalName', 'odoo-epos-bridge'),
    StringStruct('OriginalFilename', 'odoo-epos-bridge.exe'),
    StringStruct('ProductName', 'OdooPrinter'),
    StringStruct('ProductVersion', '{__version__}')])]),
  VarFileInfo([VarStruct('Translation', [1033, 1200])])]
)
"""
with open("version_info.txt", "w", encoding="utf-8") as fh:
    fh.write(tpl)
print(f"wrote version_info.txt for {__version__}")
