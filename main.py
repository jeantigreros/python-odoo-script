from flask import Flask, request, Response
import base64
import xml.etree.ElementTree as ET
from PIL import Image
import win32print
import pytesseract
import numpy as np

# output network de odoo
# https://192.168.18.101/cgi-bin/epos/service.cgi?devid=local_printer 
app = Flask(__name__)

@app.route('/cgi-bin/epos/service.cgi', methods=['POST'])

def print_receipt():
    # get raw data from odoo
    xml_data = request.data.decode('utf-8', errors='ignore')
    root = ET.fromstring(xml_data)

    # Define namespaces from the XML
    ns = {
        "s": "http://schemas.xmlsoap.org/soap/envelope/",
        "epos": "http://www.epson-pos.com/schemas/2011/03/epos-print"
    }

    # Find <image> inside the Epson namespace
    image_element = root.find(".//epos:image", ns)

    if image_element is not None and image_element.text:
        base64_data = image_element.text.strip()
        image_bytes = base64.b64decode(base64_data)

        # Extract attributes for width/height
        width = int(image_element.attrib.get("width", 384))  # default 384 px
        height = int(image_element.attrib.get("height", len(image_bytes) * 8 // width))

        # Convert ESC/POS raster (1 bit/pixel) into numpy array
        row_bytes = (width + 7) // 8  # bytes per row
        bitmap = np.zeros((height, width), dtype=np.uint8)

        for y in range(height):
            row_start = y * row_bytes
            row_data = image_bytes[row_start:row_start + row_bytes]
            for x_byte, byte in enumerate(row_data):
                for bit in range(8):
                    x = x_byte * 8 + (7 - bit)  # MSB first
                    if x < width:
                        bitmap[y, x] = 0 if (byte >> bit) & 1 else 255

        # Create and save image
        img = Image.fromarray(bitmap, mode="L")
        img.save("output.png")
        print("✅ ESC/POS raster image saved as output.png")
    else:
        print("❌ No <image> tag found in XML or it was empty")

    return Response(status=200)



# Load the receipt image
img = Image.open("output.png")

# Run OCR (Spanish language)
text = pytesseract.image_to_string(img, lang="spa")

# Save to text file
with open("output.txt", "w", encoding="utf-8") as f:
    f.write(text)

text_to_print = text

# ESC/POS commands
INIT = b"\x1B\x40"        # Initialize
FEED = b"\n\n\n"          # Feed 3 lines
CUT  = b"\x1D\x56\x00"    # Full cut

try:
    printer_name = win32print.GetDefaultPrinter()
    hPrinter = win32print.OpenPrinter(printer_name)
    hJob = win32print.StartDocPrinter(hPrinter, 1, ("My Document", None, "RAW"))
    win32print.StartPagePrinter(hPrinter)

    # Convert text to bytes (use cp437 for ESC/POS printers)
    data_bytes = text_to_print.encode("cp437", errors="replace")

    # Send to printer: initialize + text + feed + cut
    win32print.WritePrinter(hPrinter, INIT + data_bytes + FEED + FEED + CUT)
    win32print.EndPagePrinter(hPrinter)
    win32print.EndDocPrinter(hPrinter)
    win32print.ClosePrinter(hPrinter)

    print("✅ Receipt sent with feed & cut")

except Exception as e:
    print(f"❌ An error occurred: {e}")


if __name__ == '__main__':
    print("Iniciando Servidor de Impresión ESC/POS para Odoo Online...")
    app.run(host='0.0.0.0', port=5000)
