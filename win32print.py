import base64
import xml.etree.ElementTree as ET
import win32print
import win32ui

# Example Epson XML image node
xml_data = """<epos:image width="384" height="200">BASE64DATA...</epos:image>"""
root = ET.fromstring(xml_data)

# Decode ESC/POS raster data
image_bytes = base64.b64decode(root.text.strip())

# Extract dimensions (not always required for raw printing)
width = int(root.attrib.get("width", 384))
height = int(root.attrib.get("height", len(image_bytes) * 8 // width))

# --- ESC/POS Commands ---
INIT = b"\x1B\x40"                 # ESC @  -> Initialize printer
FEED = b"\n\n\n"                   # Feed paper
CUT  = b"\x1D\x56\x00"             # Full cut

# Raster print command (GS v 0)
row_bytes = (width + 7) // 8
raster_header = (
    b"\x1D\x76\x30\x00" +
    bytes([
        row_bytes & 0xFF, (row_bytes >> 8) & 0xFF,
        height & 0xFF, (height >> 8) & 0xFF
    ])
)

# Build full job
job_data = INIT + raster_header + image_bytes + FEED + CUT

# --- Open Printer ---
printer_name = win32print.GetDefaultPrinter()   # or set manually
hPrinter = win32print.OpenPrinter(printer_name)
hJob = win32print.StartDocPrinter(hPrinter, 1, ("ESC/POS Receipt", None, "RAW"))
win32print.StartPagePrinter(hPrinter)

# --- Send raw bytes ---
win32print.WritePrinter(hPrinter, job_data)

# --- Close job ---
win32print.EndPagePrinter(hPrinter)
win32print.EndDocPrinter(hPrinter)
win32print.ClosePrinter(hPrinter)

print(f"✅ Sent image to printer: {printer_name}")
