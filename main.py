from flask import Flask, request, Response
from waitress import serve
from flask_cors import CORS
import base64
import binascii
import html
import logging
import multiprocessing
import os
import threading
import xml.etree.ElementTree as ET

try:
    import win32print
except ImportError:  # Linux/CI: allow import; print_raw() raises a clear error.
    win32print = None  # type: ignore[assignment]


# ------------------------------------------------------------
# Configuration
# ------------------------------------------------------------

HOST = "127.0.0.1"
PORT = 5000


def _default_printer_name():
    for env_key in ("POS_PRINTER_NAME", "POS-80"):
        value = os.getenv(env_key)
        if value:
            return value

    if win32print is not None:
        try:
            return win32print.GetDefaultPrinter()
        except Exception:
            pass

    return "POS-80"


PRINTER_NAME = _default_printer_name()


# ------------------------------------------------------------
# Printer configuration
# ------------------------------------------------------------

# Typical values:
#
#   384 -> ~58 mm class printers
#   576 -> ~80 mm class printers
#
PRINTER_WIDTH_DOTS = int(
    os.getenv("POS_PRINTER_WIDTH_DOTS", "576")
)


# Odoo sends align="center".
CENTER_IMAGES = True


# ------------------------------------------------------------
# Receipt scaling
# ------------------------------------------------------------

# IMPORTANT:
#
# The Odoo receipt arrives as a bitmap.
#
# We keep the horizontal size at 100% so it does not exceed
# the 576-dot printer width.
#
# We enlarge ONLY vertically.
#
# 1.00 = original height
# 1.10 = 10% taller
# 1.20 = 20% taller
# 1.30 = 30% taller
#
# Default: 1.20
#
RASTER_SCALE_X = float(
    os.getenv("POS_RASTER_SCALE_X", "1.0")
)

RASTER_SCALE_Y = float(
    os.getenv("POS_RASTER_SCALE_Y", "1.50")
)


# Number of blank lines before cutting.
END_BLANK_LINES = int(
    os.getenv("POS_END_BLANK_LINES", "2")
)


# ------------------------------------------------------------
# Printer locking
# ------------------------------------------------------------

printer_lock = threading.Lock()


# ------------------------------------------------------------
# Flask
# ------------------------------------------------------------

app = Flask(__name__)

CORS(app)


logger = logging.getLogger(__name__)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)


# ------------------------------------------------------------
# ePOS XML helpers
# ------------------------------------------------------------

EPOS_NS = (
    "http://www.epson-pos.com/schemas/2011/03/epos-print"
)

SOAP_NS = (
    "http://schemas.xmlsoap.org/soap/envelope/"
)


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

    success_value = (
        "true"
        if success
        else "false"
    )

    code = html.escape(
        str(code),
        quote=True,
    )

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

    image = find_element(
        root,
        "image",
    )

    if image is None:
        raise ValueError(
            "No <image> element found"
        )

    if not image.text:
        raise ValueError(
            "The <image> element is empty"
        )

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
        width = int(
            image.attrib["width"]
        )

        height = int(
            image.attrib["height"]
        )

    except (KeyError, ValueError) as exc:
        raise ValueError(
            "Invalid image width/height"
        ) from exc

    alignment = image.attrib.get(
        "align",
        "left",
    )

    if width <= 0 or height <= 0:
        raise ValueError(
            "Invalid image dimensions"
        )

    source_row_bytes = (
        width + 7
    ) // 8

    expected_size = (
        source_row_bytes * height
    )

    if len(raster) != expected_size:
        raise ValueError(
            f"Raster size mismatch: "
            f"expected {expected_size}, "
            f"got {len(raster)}"
        )

    return (
        width,
        height,
        raster,
        alignment,
    )


# ------------------------------------------------------------
# Raster scaling
# ------------------------------------------------------------

def scale_raster(
    raster,
    width,
    height,
    scale_x,
    scale_y,
):
    """
    Scale a 1-bit MSB-first raster.

    Horizontal scaling is normally kept at 1.0.

    Vertical scaling can be increased to make the
    receipt text taller without exceeding the printer
    width.

    Example:

        scale_x = 1.0
        scale_y = 1.2

    keeps the same width and makes the receipt 20% taller.
    """

    if scale_x <= 0:
        raise ValueError(
            "RASTER_SCALE_X must be greater than 0"
        )

    if scale_y <= 0:
        raise ValueError(
            "RASTER_SCALE_Y must be greater than 0"
        )

    if (
        scale_x == 1.0
        and scale_y == 1.0
    ):
        return (
            raster,
            width,
            height,
        )

    source_row_bytes = (
        width + 7
    ) // 8

    # Calculate new dimensions.
    new_width = int(
        width * scale_x
    )

    new_height = int(
        height * scale_y
    )

    if new_width <= 0 or new_height <= 0:
        raise ValueError(
            "Scaled raster dimensions are invalid"
        )

    # ESC/POS raster data is byte based.
    # Round width up to nearest 8 pixels.
    new_width = (
        (new_width + 7) // 8
    ) * 8

    new_row_bytes = (
        new_width // 8
    )

    output = bytearray(
        new_row_bytes * new_height
    )

    def get_pixel(x, y):
        byte_index = (
            y * source_row_bytes
            + (x // 8)
        )

        bit_index = (
            7 - (x % 8)
        )

        return (
            raster[byte_index]
            >> bit_index
        ) & 1

    def set_pixel(x, y):
        byte_index = (
            y * new_row_bytes
            + (x // 8)
        )

        bit_index = (
            7 - (x % 8)
        )

        output[byte_index] |= (
            1 << bit_index
        )

    for new_y in range(new_height):

        source_y = min(
            int(new_y / scale_y),
            height - 1,
        )

        for new_x in range(new_width):

            source_x = min(
                int(new_x / scale_x),
                width - 1,
            )

            if get_pixel(
                source_x,
                source_y,
            ):
                set_pixel(
                    new_x,
                    new_y,
                )

    return (
        bytes(output),
        new_width,
        new_height,
    )


# ------------------------------------------------------------
# Raster centering
# ------------------------------------------------------------

def add_left_padding(
    raster,
    width,
    height,
    padding_pixels,
):
    """
    Add horizontal white padding to each
    raster row.

    This lets us emulate Odoo's
    align="center" behavior.
    """

    if padding_pixels <= 0:
        return (
            raster,
            width,
        )

    if padding_pixels % 8 != 0:
        raise ValueError(
            "Padding must be a multiple of 8 pixels"
        )

    source_row_bytes = (
        width + 7
    ) // 8

    padding_bytes = (
        b"\x00"
        * (padding_pixels // 8)
    )

    padded_rows = []

    for y in range(height):

        start = (
            y * source_row_bytes
        )

        end = (
            start
            + source_row_bytes
        )

        row = raster[
            start:end
        ]

        padded_rows.append(
            padding_bytes + row
        )

    new_width = (
        width
        + padding_pixels
    )

    return (
        b"".join(padded_rows),
        new_width,
    )


def prepare_raster(
    raster,
    width,
    height,
    alignment="left",
):
    """
    Convert the ePOS raster into the raster
    we want to send through ESC/POS.

    Odoo normally sends align="center".
    """

    if width > PRINTER_WIDTH_DOTS:
        raise ValueError(
            f"Receipt width {width}px "
            f"exceeds printer width "
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

    if (
        alignment == "center"
        and CENTER_IMAGES
    ):

        remaining = (
            PRINTER_WIDTH_DOTS
            - width
        )

        left_padding = (
            remaining // 2
        )

        # Raster commands work in whole bytes.
        left_padding -= (
            left_padding % 8
        )

        raster, width = (
            add_left_padding(
                raster,
                width,
                height,
                left_padding,
            )
        )

        # Pad right side so final raster
        # is exactly printer width.

        right_padding = (
            PRINTER_WIDTH_DOTS
            - width
        )

        if right_padding:

            row_bytes = (
                width // 8
            )

            right_bytes = (
                right_padding // 8
            )

            rows = []

            for y in range(height):

                start = (
                    y * row_bytes
                )

                end = (
                    start
                    + row_bytes
                )

                rows.append(
                    raster[start:end]
                    + b"\x00"
                    * right_bytes
                )

            raster = b"".join(
                rows
            )

            width = (
                PRINTER_WIDTH_DOTS
            )

    return (
        raster,
        width,
    )


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

    The ePOS raster is already MSB-first,
    one bit per pixel, which maps naturally
    to ESC/POS raster data.
    """

    width_bytes = (
        width + 7
    ) // 8

    if width_bytes > 0xFFFF:
        raise ValueError(
            "Image is too wide"
        )

    if height > 0xFFFF:
        raise ValueError(
            "Image is too tall"
        )

    expected_size = (
        width_bytes * height
    )

    if len(raster) != expected_size:
        raise ValueError(
            f"ESC/POS raster size mismatch: "
            f"expected {expected_size}, "
            f"got {len(raster)}"
        )

    command = bytes(
        [
            0x1D,  # GS
            0x76,  # v
            0x30,  # 0
            0x00,  # normal density

            width_bytes & 0xFF,
            (
                width_bytes >> 8
            ) & 0xFF,

            height & 0xFF,
            (
                height >> 8
            ) & 0xFF,
        ]
    )

    return (
        command
        + raster
    )


def build_cut_command():
    """
    Full cut.

    Your current POS-80 command was:

        GS V 0

    Keep that because you already
    know it works.
    """

    return b"\x1D\x56\x00"


def build_cash_drawer_command():
    """
    ESC p 0 25 250

    Typical cash drawer pulse.
    """

    return (
        b"\x1B"
        b"\x70"
        b"\x00"
        b"\x19"
        b"\xFA"
    )


# ------------------------------------------------------------
# Windows RAW printing
# ------------------------------------------------------------

def print_raw(data):
    """
    Send printer-ready bytes directly
    to the Windows spooler.
    """

    if not data:
        raise ValueError(
            "No printer data"
        )

    if win32print is None:
        raise RuntimeError(
            "win32print is not available. "
            "This bridge must run on Windows "
            "(pywin32 installed)."
        )

    with printer_lock:

        hprinter = None

        try:

            logger.info(
                "Opening printer: %s",
                PRINTER_NAME,
            )

            hprinter = (
                win32print.OpenPrinter(
                    PRINTER_NAME
                )
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

                    written = (
                        win32print.WritePrinter(
                            hprinter,
                            data,
                        )
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
# ePOS -> ESC/POS translation
# ------------------------------------------------------------

def translate_epos_to_escpos(
    xml_data,
):
    """
    Translate the subset of ePOS commands
    used by Odoo 18 POS.

    Current Odoo Epson POS flow:

        <image ...>
        <cut .../>

    Cash drawer:

        <pulse/>
    """

    root = ET.fromstring(
        xml_data
    )

    printer_data = bytearray()

    # --------------------------------------------------------
    # IMAGE
    # --------------------------------------------------------

    image = find_element(
        root,
        "image",
    )

    if image is not None:

        width, height, raster, alignment = (
            extract_raster(root)
        )

        logger.info(
            "Received raster: %dx%d, "
            "align=%s, %d bytes",
            width,
            height,
            alignment,
            len(raster),
        )

        # ----------------------------------------------------
        # Scale the raster.
        #
        # X stays at 1.0 by default.
        # Y is 1.20 by default.
        #
        # This makes text taller without making the receipt
        # wider than the printer.
        # ----------------------------------------------------

        if (
            RASTER_SCALE_X != 1.0
            or RASTER_SCALE_Y != 1.0
        ):

            logger.info(
                "Scaling raster X=%.2fx Y=%.2fx",
                RASTER_SCALE_X,
                RASTER_SCALE_Y,
            )

            raster, width, height = (
                scale_raster(
                    raster,
                    width,
                    height,
                    RASTER_SCALE_X,
                    RASTER_SCALE_Y,
                )
            )

            logger.info(
                "Scaled raster: %dx%d",
                width,
                height,
            )

        # ----------------------------------------------------
        # Make sure width still fits.
        # ----------------------------------------------------

        if width > PRINTER_WIDTH_DOTS:
            raise ValueError(
                f"Scaled receipt width "
                f"{width}px exceeds printer "
                f"width {PRINTER_WIDTH_DOTS}px"
            )

        # ----------------------------------------------------
        # Center the receipt.
        # ----------------------------------------------------

        raster, final_width = (
            prepare_raster(
                raster,
                width,
                height,
                alignment,
            )
        )

        printer_data.extend(
            build_raster_command(
                raster,
                final_width,
                height,
            )
        )

    # --------------------------------------------------------
    # CASH DRAWER
    # --------------------------------------------------------

    pulse = find_element(
        root,
        "pulse",
    )

    if pulse is not None:

        logger.info(
            "Cash drawer pulse requested"
        )

        printer_data.extend(
            build_cash_drawer_command()
        )

    # --------------------------------------------------------
    # CUT
    # --------------------------------------------------------

    cut = find_element(
        root,
        "cut",
    )

    if cut is not None:

        logger.info(
            "Cut requested; adding %d blank lines",
            END_BLANK_LINES,
        )

        # Two blank lines by default.
        #
        # ESC/POS LF = 0x0A
        if END_BLANK_LINES > 0:

            printer_data.extend(
                b"\x0A"
                * END_BLANK_LINES
            )

        printer_data.extend(
            build_cut_command()
        )

    if not printer_data:
        raise ValueError(
            "No supported ePOS print command found"
        )

    return bytes(
        printer_data
    )


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

        escpos_data = (
            translate_epos_to_escpos(
                xml_data
            )
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

    except ET.ParseError:

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

    except Exception:

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

def main():

    logger.info(
        "Starting Odoo ePOS -> ESC/POS bridge"
    )

    logger.info(
        "Printer: %s",
        PRINTER_NAME,
    )

    logger.info(
        "Printer width: %d dots",
        PRINTER_WIDTH_DOTS,
    )

    logger.info(
        "Raster scale X: %.2fx",
        RASTER_SCALE_X,
    )

    logger.info(
        "Raster scale Y: %.2fx",
        RASTER_SCALE_Y,
    )

    logger.info(
        "End blank lines: %d",
        END_BLANK_LINES,
    )

    logger.info(
        "Listening on http://%s:%d",
        HOST,
        PORT,
    )

    logger.info(
        "ePOS endpoint: "
        "/cgi-bin/epos/service.cgi"
    )

    serve(
        app,
        host=HOST,
        port=PORT,
        threads=8,
    )


if __name__ == "__main__":

    multiprocessing.freeze_support()

    main()