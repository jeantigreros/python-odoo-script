from flask import Flask, request, Response
import base64
import xml.etree.ElementTree as ET
from PIL import Image
import win32print
import pytesseract
import numpy as np
import io
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

def extract_image_from_xml(xml_data):
    """Extract and decode image from XML data"""
    try:
        root = ET.fromstring(xml_data)
        
        # Define namespaces from the XML
        ns = {
            "s": "http://schemas.xmlsoap.org/soap/envelope/",
            "epos": "http://www.epson-pos.com/schemas/2011/03/epos-print"
        }

        # Find <image> inside the Epson namespace
        image_element = root.find(".//epos:image", ns)

        if image_element is None or not image_element.text:
            logger.error("No <image> tag found in XML or it was empty")
            return None

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

        # Create and return image
        return Image.fromarray(bitmap, mode="L")
        
    except Exception as e:
        logger.error(f"Error extracting image from XML: {e}")
        return None

def extract_text_from_image(img):
    """Extract text from image using OCR"""
    try:
        # Run OCR (Spanish language)
        return pytesseract.image_to_string(img, lang="spa")
    except Exception as e:
        logger.error(f"Error extracting text from image: {e}")
        return None

def print_text(text):
    """Print text to the default printer using ESC/POS commands"""
    try:
        # ESC/POS commands
        INIT = b"\x1B\x40"        # Initialize
        FEED = b"\n\n\n"          # Feed 3 lines
        CUT  = b"\x1D\x56\x00"    # Full cut

        printer_name = win32print.GetDefaultPrinter()
        hPrinter = win32print.OpenPrinter(printer_name)
        hJob = win32print.StartDocPrinter(hPrinter, 1, ("Receipt Print", None, "RAW"))
        win32print.StartPagePrinter(hPrinter)

        # Convert text to bytes (use cp437 for ESC/POS printers)
        data_bytes = text.encode("cp437", errors="replace")

        # Send to printer: initialize + text + feed + cut
        win32print.WritePrinter(hPrinter, INIT + data_bytes + FEED + FEED + CUT)
        win32print.EndPagePrinter(hPrinter)
        win32print.EndDocPrinter(hPrinter)
        win32print.ClosePrinter(hPrinter)

        logger.info("✅ Receipt sent with feed & cut")
        return True
        
    except Exception as e:
        logger.error(f"Printing error: {e}")
        return False

@app.route('/cgi-bin/epos/service.cgi', methods=['POST'])
def print_receipt():
    """Handle receipt printing requests from Odoo"""
    try:
        # Get raw data from Odoo
        xml_data = request.data.decode('utf-8', errors='ignore')
        logger.info("Received print request from Odoo")
        
        # Extract image from XML
        img = extract_image_from_xml(xml_data)
        if img is None:
            return Response(status=400, response="Failed to extract image from request")
            
        # Save image for debugging (optional)
        img.save("output.png")
        logger.info("✅ ESC/POS raster image saved as output.png")
        
        # Extract text from image
        text = extract_text_from_image(img)
        if text is None:
            return Response(status=400, response="Failed to extract text from image")
            
        # Save text for debugging (optional)
        with open("output.txt", "w", encoding="utf-8") as f:
            f.write(text)
            
        # Print the text
        if print_text(text):
            return Response(status=200, response="Print successful")
        else:
            return Response(status=500, response="Printing failed")
            
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return Response(status=500, response=f"Server error: {str(e)}")

if __name__ == '__main__':
    logger.info("Iniciando Servidor de Impresión ESC/POS para Odoo Online...")
    app.run(host='0.0.0.0', port=5000)
