from flask import Flask, request, Response
from flask_cors import CORS
import base64
import binascii
import html
import logging
import os
import threading
import xml.etree.ElementTree as ET

import win32print


# ------------------------------------------------------------
# Configuration
# ------------------------------------------------------------

HOST = "0.0.0.0"
PORT = 5000

# Better to explicitly configure the Windows printer queue.
# Falls back to the Windows default printer if not defined.
PRINTER_NAME = os.getenv("POS_PRINTER_NAME") or win32print.GetDefaultPrinter()

# Set this to the printable width of your POS-80.
#
# Typical values:
#   384 -> ~58 mm class printers
#   576 -> ~80 mm class printers
#
# Verify this against your actual POS-80.
PRINTER_WIDTH_DOTS = int(
    os.getenv("POS_PRINTER_WIDTH_DOTS", "576")
)

# Odoo sends align="center".
CENTER_IMAGES = True

# Serialize access to the Windows printer queue.
# Useful if two requests arrive at nearly the same time.
printer_lock = threading.Lock()


# ------------------------------------------------------------
# Flask
# ------------------------------------------------------------

app = Flask(__name__)

# Development configuration.
# In production, restrict this to your Odoo origin.
CORS(app)


logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)


# ------------------------------------------------------------
# ePOS XML helpers
# ------------------------------------------------------------

EPOS_NS = "http://www.epson-pos.com/schemas/2011/03/epos-print"
SOAP_NS = "http://schemas.xmlsoap.org/soap/envelope/"


def local_name(element):
    """
    Return the XML local name regardless of namespace.

    Example:
        {namespace}image -> image
    """
    return element.tag.rsplit("}", 1)[-1]


def find_element(root, name):
    """
    Find first element by local XML name.
    """
    for element in root.iter():
        if local_name(element) == name:
            return element

    return None


def find_elements(root, name):
    """
    Find all elements by local XML name.
    """
    return [
        element
        for element in root.iter()
        if local_name(element) == name
    ]


# ------------------------------------------------------------
# ePOS responses
# ------------------------------------------------------------

def create_response(success=True, code="0"):
    """
    Odoo 18 expects:
        <response success="true" code="0"/>

    wrapped in the ePOS SOAP structure.
    """

    success_value = "true" if success else "false"

    code = html.escape(str(code), quote=True)

    response_xml = f"""<?xml version="1.0" encoding="utf-8"?>
<s:Envelope xmlns:s="{SOAP_NS}">
    <s:Body>
        <epos-print xmlns="{EPOS_NS}">
            <response success="{success_value}" code="{code}"/>
        </epos-print>
    </s:Body>
</s:Envelope>"""

    return response_xml


# ------------------------------------------------------------
# Base64 raster extraction
# ------------------------------------------------------------

def extract_raster(root):
    """
    Extract Odoo's <image> element.

    Returns:
        width
        height
        raster_bytes
        alignment
    """

    image = find_element(root, "image")

    if image is None:
        raise ValueError("No <image> element found")

    if not image.text:
        raise ValueError("The <image> element is empty")

    try:
        raster = base64.b64decode(
            "".join(image.text.split()),
            validate=True,
        )
    except binascii.Error as exc:
        raise ValueError(
            "Invalid base64 raster data"
        ) from exc

    try:
        width = int(image.attrib["width"])
        height = int(image.attrib["height"])
    except (KeyError, ValueError) as exc:
        raise ValueError(
            "Invalid image width/height"
        ) from exc

    alignment = image.attrib.get("align", "left")

    if width <= 0 or height <= 0:
        raise ValueError("Invalid image dimensions")

    source_row_bytes = (width + 7) // 8

    expected_size = source_row_bytes * height

    if len(raster) != expected_size:
        raise ValueError(
            f"Raster size mismatch: "
            f"expected {expected_size}, got {len(raster)}"
        )

    return width, height, raster, alignment


# ------------------------------------------------------------
# Raster conversion
# ------------------------------------------------------------

def add_left_padding(raster, width, height, padding_pixels):
    """
    Add horizontal white padding to each raster row.

    This lets us emulate Odoo's align="center" behavior.

    Returns:
        padded_raster
        new_width
    """

    if padding_pixels <= 0:
        return raster, width

    if padding_pixels % 8 != 0:
        raise ValueError("Padding must be a multiple of 8 pixels")

    source_row_bytes = (width + 7) // 8
    padding_bytes = b"\x00" * (padding_pixels // 8)

    padded_rows = []

    for y in range(height):
        start = y * source_row_bytes
        end = start + source_row_bytes

        row = raster[start:end]

        padded_rows.append(
            padding_bytes + row
        )

    new_width = width + padding_pixels

    return b"".join(padded_rows), new_width


def prepare_raster(
    raster,
    width,
    height,
    alignment="left",
):
    """
    Convert the ePOS raster into the raster we want to send
    through ESC/POS.

    Odoo normally sends align="center".
    """

    if width > PRINTER_WIDTH_DOTS:
        raise ValueError(
            f"Receipt width {width}px exceeds printer width "
            f"{PRINTER_WIDTH_DOTS}px"
        )

    if PRINTER_WIDTH_DOTS % 8 != 0:
        raise ValueError(
            "PRINTER_WIDTH_DOTS must be divisible by 8"
        )

    if width % 8 != 0:
        raise ValueError(
            "Source image width must be divisible by 8"
        )

    if alignment == "center" and CENTER_IMAGES:
        remaining = PRINTER_WIDTH_DOTS - width

        left_padding = remaining // 2

        # Raster commands work in whole bytes.
        left_padding -= left_padding % 8

        raster, width = add_left_padding(
            raster,
            width,
            height,
            left_padding,
        )

        # Pad the right side so the final raster width is exactly
        # PRINTER_WIDTH_DOTS.

        right_padding = PRINTER_WIDTH_DOTS - width

        if right_padding:
            raster, width = add_left_padding(
                raster,
                width,
                height,
                0,
            )

            row_bytes = width // 8
            right_bytes = right_padding // 8

            rows = []

            for y in range(height):
                start = y * row_bytes
                end = start + row_bytes

                rows.append(
                    raster[start:end] +
                    b"\x00" * right_bytes
                )

            raster = b"".join(rows)
            width = PRINTER_WIDTH_DOTS

    return raster, width


# ------------------------------------------------------------
# ESC/POS
# ------------------------------------------------------------

def build_raster_command(
    raster,
    width,
    height,
):
    """
    Build:

        GS v 0 m xL xH yL yH d1...dk

    using normal density.

    The ePOS raster is already MSB-first, one bit per pixel,
    which maps naturally to ESC/POS raster data.
    """

    width_bytes = (width + 7) // 8

    if width_bytes > 0xFFFF:
        raise ValueError("Image is too wide")

    if height > 0xFFFF:
        raise ValueError("Image is too tall")

    expected_size = width_bytes * height

    if len(raster) != expected_size:
        raise ValueError(
            f"ESC/POS raster size mismatch: "
            f"expected {expected_size}, got {len(raster)}"
        )

    command = bytes(
        [
            0x1D,  # GS
            0x76,  # v
            0x30,  # 0
            0x00,  # normal density

            width_bytes & 0xFF,
            (width_bytes >> 8) & 0xFF,

            height & 0xFF,
            (height >> 8) & 0xFF,
        ]
    )

    return command + raster


def build_cut_command():
    """
    Full cut.

    Your current POS-80 command was:
        GS V 0

    Keep that initially because you already know it works.
    """

    return b"\x1D\x56\x00"


def build_cash_drawer_command():
    """
    ESC p 0 25 250

    Typical cash drawer pulse.
    Verify against the POS-80 if you use a drawer.
    """

    return b"\x1B\x70\x00\x19\xFA"


# ------------------------------------------------------------
# Windows RAW printing
# ------------------------------------------------------------

def print_raw(data):
    """
    Send printer-ready bytes directly to the Windows spooler.
    """

    if not data:
        raise ValueError("No printer data")

    with printer_lock:

        hprinter = None

        try:
            logger.info(
                "Opening printer: %s",
                PRINTER_NAME,
            )

            hprinter = win32print.OpenPrinter(
                PRINTER_NAME
            )

            win32print.StartDocPrinter(
                hprinter,
                1,
                (
                    "Odoo POS Receipt",
                    None,
                    "RAW",
                ),
            )

            try:
                win32print.StartPagePrinter(
                    hprinter
                )

                try:
                    written = win32print.WritePrinter(
                        hprinter,
                        data,
                    )

                    if written != len(data):
                        raise IOError(
                            f"Printer accepted only "
                            f"{written}/{len(data)} bytes"
                        )

                finally:
                    win32print.EndPagePrinter(
                        hprinter
                    )

            finally:
                win32print.EndDocPrinter(
                    hprinter
                )

            logger.info(
                "RAW print job sent: %d bytes",
                len(data),
            )

        finally:
            if hprinter:
                win32print.ClosePrinter(
                    hprinter
                )


# ------------------------------------------------------------
# ePOS → ESC/POS translation
# ------------------------------------------------------------

def translate_epos_to_escpos(xml_data):
    """
    Translate the subset of ePOS commands used by Odoo 18 POS.

    Current Odoo Epson POS flow:
        <image ...>
        <cut .../>

    Cash drawer:
        <pulse/>
    """

    root = ET.fromstring(xml_data)

    printer_data = bytearray()

    image = find_element(root, "image")

    if image is not None:

        width, height, raster, alignment = extract_raster(
            root
        )

        logger.info(
            "Received raster: %dx%d, align=%s, %d bytes",
            width,
            height,
            alignment,
            len(raster),
        )

        raster, final_width = prepare_raster(
            raster,
            width,
            height,
            alignment,
        )

        printer_data.extend(
            build_raster_command(
                raster,
                final_width,
                height,
            )
        )

    # Odoo's openCashbox() sends <pulse/>.
    pulse = find_element(root, "pulse")

    if pulse is not None:
        printer_data.extend(
            build_cash_drawer_command()
        )

    # Respect an explicit cut command.
    cut = find_element(root, "cut")

    if cut is not None:
        printer_data.extend(
            build_cut_command()
        )

    if not printer_data:
        raise ValueError(
            "No supported ePOS print command found"
        )

    return bytes(printer_data)


# ------------------------------------------------------------
# Endpoint
# ------------------------------------------------------------

@app.route(
    "/cgi-bin/epos/service.cgi",
    methods=["POST"],
)
def epos_service():

    try:

        logger.info(
            "Received ePOS print request"
        )

        xml_data = request.data

        logger.info(
            "Request size: %d bytes",
            len(xml_data),
        )

        escpos_data = translate_epos_to_escpos(
            xml_data
        )

        print_raw(
            escpos_data
        )

        return Response(
            create_response(
                success=True,
                code="0",
            ),
            status=200,
            mimetype="text/xml",
        )

    except ET.ParseError as exc:

        logger.exception(
            "Invalid XML"
        )

        return Response(
            create_response(
                success=False,
                code="INVALID_XML",
            ),
            status=200,
            mimetype="text/xml",
        )

    except Exception as exc:

        logger.exception(
            "Printing failed"
        )

        return Response(
            create_response(
                success=False,
                code="BRIDGE_ERROR",
            ),
            status=200,
            mimetype="text/xml",
        )


# ------------------------------------------------------------
# Main
# ------------------------------------------------------------

if __name__ == "__main__":

    logger.info(
        "Starting Odoo ePOS → ESC/POS bridge"
    )

    logger.info(
        "Printer: %s",
        PRINTER_NAME,
    )

    logger.info(
        "Printer width: %d dots",
        PRINTER_WIDTH_DOTS,
    )

    app.run(
        host=HOST,
        port=PORT,
        debug=False,
    )
