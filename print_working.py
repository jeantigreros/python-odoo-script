from flask import Flask, request, Response
from escpos.printer import Usb
import xml.etree.ElementTree as ET
import base64
from PIL import Image, ImageChops
from io import BytesIO
from escpos.printer import Usb

app = Flask(__name__)

# Configure your printer USB Vendor ID and Product ID
VENDOR_ID = 0x0483  # Example: Epson Vendor ID
PRODUCT_ID = 0x5743 # Example: Epson TM-T20II Product ID

@app.route('/cgi-bin/epos/service.cgi', methods=['POST'])
def epos_handler():
    xml_data = request.data.decode('utf-8', errors='ignore')
    print("📥 Received ePOS XML")

    try:
        # Parse the XML
        root = ET.fromstring(xml_data)
        ns = {
            's': 'http://schemas.xmlsoap.org/soap/envelope/',
            'e': 'http://www.epson-pos.com/schemas/2011/03/epos-print'
        }

        image_elem = root.find('.//e:image', ns)
        image_b64 = image_elem.text.strip()
        width = int(image_elem.attrib.get('width'))
        height = int(image_elem.attrib.get('height'))

        # Cut type (default to feed)
        cut_elem = root.find('.//e:cut', ns)
        cut_type = cut_elem.attrib.get('type', 'feed') if cut_elem is not None else 'feed'

        print(f"🖼️ Decoding and inverting image: {width}x{height}")
        image_data = base64.b64decode(image_b64)

        # Convert from raw raster bytes to image
        image = Image.frombytes('1', (width, height), image_data)

        # Invert image
        inverted = ImageChops.invert(image.convert("L")).convert("1")

        # Print
        printer = Usb(VENDOR_ID, PRODUCT_ID)
        printer.image(inverted)
        printer.cut(mode='FULL')
        printer.close()

        # Response
        response_xml = '''<?xml version="1.0" encoding="UTF-8"?>
<response>
  <success>true</success>
</response>'''
        return Response(response_xml, mimetype='text/xml', status=200)

    except Exception as e:
        print(f"❌ Error: {e}")
        error_response = '''<?xml version="1.0" encoding="UTF-8"?>
<response>
  <success>false</success>
  <code>EPOS_PRINT_ERROR</code>
  <message>Printer Error</message>
</response>'''
        return Response(error_response, mimetype='text/xml', status=500)



if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, ssl_context=('cert.pem', 'key.pem'))