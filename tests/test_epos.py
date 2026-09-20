"""Unit tests for ePOS XML parsing (extract_raster).

No printer, no Odoo, no network required.  All fixtures are small and
deterministic: an 8x2 image is two bytes, one byte per row.
"""

import base64
import xml.etree.ElementTree as ET

import pytest

import main
from conftest import build_image_xml


# 8px wide, 2 rows -> 1 byte per row, 2 bytes total.
WIDTH = 8
HEIGHT = 2
RASTER = bytes([0x80, 0x01])  # visually obvious: MSB set, then LSB set.


def parse(xml_bytes: bytes) -> ET.Element:
    return ET.fromstring(xml_bytes)


# ---------------------------------------------------------------------------
# Happy paths
# ---------------------------------------------------------------------------

def test_extract_valid_xml():
    root = parse(build_image_xml(RASTER, WIDTH, HEIGHT, align="center"))
    width, height, raster, alignment = main.extract_raster(root)
    assert width == WIDTH
    assert height == HEIGHT
    assert raster == RASTER
    assert alignment == "center"


def test_extract_namespaced_xml():
    root = parse(
        build_image_xml(RASTER, WIDTH, HEIGHT, align="center", namespaced=True)
    )
    width, height, raster, alignment = main.extract_raster(root)
    assert (width, height, raster, alignment) == (WIDTH, HEIGHT, RASTER, "center")


def test_extract_explicit_namespaced_image_tag():
    # Namespace-qualified <image> must still be found via local-name lookup.
    payload = base64.b64encode(RASTER).decode()
    xml = (
        f'<epos-print xmlns="{main.EPOS_NS}">'
        f'<image xmlns="{main.EPOS_NS}" width="8" height="2">'
        f"{payload}</image></epos-print>"
    ).encode()
    width, height, raster, _ = main.extract_raster(ET.fromstring(xml))
    assert (width, height, raster) == (WIDTH, HEIGHT, RASTER)


def test_extract_width_and_height_attributes():
    raster = bytes([0xFF]) * 48  # 384px wide, 1 row.
    root = parse(build_image_xml(raster, 384, 1, align="left"))
    width, height, out, _ = main.extract_raster(root)
    assert width == 384
    assert height == 1
    assert out == raster


def test_extract_align_center():
    root = parse(build_image_xml(RASTER, WIDTH, HEIGHT, align="center"))
    _, _, _, alignment = main.extract_raster(root)
    assert alignment == "center"


def test_extract_missing_align_defaults_to_left():
    root = parse(build_image_xml(RASTER, WIDTH, HEIGHT, align=None))
    _, _, _, alignment = main.extract_raster(root)
    assert alignment == "left"


def test_extract_base64_with_whitespace_is_tolerated():
    # Odoo / SOAP stacks may wrap base64 in newlines; the parser strips it.
    payload = base64.b64encode(RASTER).decode()
    wrapped = "\n  " + payload[:4] + "\n  " + payload[4:] + "\n"
    xml = (
        f'<epos-print><image width="8" height="2">{wrapped}</image>'
        f"</epos-print>"
    ).encode()
    _, _, raster, _ = main.extract_raster(ET.fromstring(xml))
    assert raster == RASTER


# ---------------------------------------------------------------------------
# Error paths — every one must raise ValueError (never return garbage)
# ---------------------------------------------------------------------------

def test_missing_image_raises():
    root = ET.fromstring(b"<epos-print><cut type='feed'/></epos-print>")
    with pytest.raises(ValueError, match="No <image>"):
        main.extract_raster(root)


def test_empty_image_element_raises():
    root = ET.fromstring(
        b"<epos-print><image width='8' height='2'/></epos-print>"
    )
    with pytest.raises(ValueError, match="empty"):
        main.extract_raster(root)


def test_empty_image_text_raises():
    root = ET.fromstring(
        b"<epos-print><image width='8' height='2'></image></epos-print>"
    )
    with pytest.raises(ValueError, match="empty"):
        main.extract_raster(root)


def test_invalid_base64_raises():
    xml = (
        b"<epos-print><image width='8' height='2'>"
        b"!!!not-base64!!!</image></epos-print>"
    )
    with pytest.raises(ValueError, match="base64"):
        main.extract_raster(ET.fromstring(xml))


def test_invalid_width_raises():
    payload = base64.b64encode(RASTER).decode()
    xml = (
        f"<epos-print><image width='wide' height='2'>{payload}</image>"
        f"</epos-print>"
    ).encode()
    with pytest.raises(ValueError, match="width/height"):
        main.extract_raster(ET.fromstring(xml))


def test_invalid_height_raises():
    payload = base64.b64encode(RASTER).decode()
    xml = (
        f"<epos-print><image width='8' height='tall'>{payload}</image>"
        f"</epos-print>"
    ).encode()
    with pytest.raises(ValueError, match="width/height"):
        main.extract_raster(ET.fromstring(xml))


def test_missing_width_raises():
    payload = base64.b64encode(RASTER).decode()
    xml = (
        f"<epos-print><image height='2'>{payload}</image></epos-print>"
    ).encode()
    with pytest.raises(ValueError, match="width/height"):
        main.extract_raster(ET.fromstring(xml))


def test_missing_height_raises():
    payload = base64.b64encode(RASTER).decode()
    xml = (
        f"<epos-print><image width='8'>{payload}</image></epos-print>"
    ).encode()
    with pytest.raises(ValueError, match="width/height"):
        main.extract_raster(ET.fromstring(xml))


@pytest.mark.parametrize("width,height", [(0, 2), (8, 0), (-8, 2), (8, -1)])
def test_zero_or_negative_dimensions_raise(width, height):
    payload = base64.b64encode(b"\x00").decode()
    xml = (
        f"<epos-print><image width='{width}' height='{height}'>{payload}"
        f"</image></epos-print>"
    ).encode()
    with pytest.raises(ValueError, match="dimensions"):
        main.extract_raster(ET.fromstring(xml))


def test_raster_too_short_raises():
    # Declares 8x2 (2 bytes) but only supplies 1 byte.
    payload = base64.b64encode(bytes([0x80])).decode()
    xml = (
        f"<epos-print><image width='8' height='2'>{payload}</image>"
        f"</epos-print>"
    ).encode()
    with pytest.raises(ValueError, match="mismatch"):
        main.extract_raster(ET.fromstring(xml))


def test_raster_too_long_raises():
    # Declares 8x2 (2 bytes) but supplies 3 bytes.
    payload = base64.b64encode(bytes([0x80, 0x01, 0xFF])).decode()
    xml = (
        f"<epos-print><image width='8' height='2'>{payload}</image>"
        f"</epos-print>"
    ).encode()
    with pytest.raises(ValueError, match="mismatch"):
        main.extract_raster(ET.fromstring(xml))
