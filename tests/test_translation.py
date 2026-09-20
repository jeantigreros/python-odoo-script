"""Unit + integration tests for ePOS -> ESC/POS translation.

Covers translate_epos_to_escpos() with small XML fixtures plus one
integration-style test driven by tests/fixtures/receipt.xml that walks the
full pipeline:

    ePOS XML -> extract raster -> Method A centering
             -> ESC/POS raster command -> cut command
"""

import xml.etree.ElementTree as ET

import pytest

import main
from conftest import build_image_xml


WIDTH = 8
HEIGHT = 2
RASTER = bytes([0x80, 0x01])


def expected_image_bytes(
    raster: bytes = RASTER, width: int = WIDTH, height: int = HEIGHT
) -> bytes:
    """Run the production pipeline stages to build the expected raster blob."""
    centered, final_width = main.prepare_raster(raster, width, height, "center")
    return main.build_raster_command(centered, final_width, height)


# ---------------------------------------------------------------------------
# Translation cases
# ---------------------------------------------------------------------------

def test_image_plus_cut_orders_raster_before_cut(printer_width):
    printer_width(576)
    xml = build_image_xml(
        RASTER, WIDTH, HEIGHT, align="center",
        extra_elements='<cut type="feed"/>',
    )
    out = main.translate_epos_to_escpos(xml)

    expected = expected_image_bytes() + main.build_cut_command()
    assert out == expected
    # GS v 0 — raster bit image comes first...
    assert out.startswith(b"\x1D\x76\x30")
    # ...and the full-cut command closes the job.
    assert out.endswith(b"\x1D\x56\x00")


def test_image_only_adds_no_cut(printer_width):
    printer_width(576)
    xml = build_image_xml(RASTER, WIDTH, HEIGHT, align="center")
    out = main.translate_epos_to_escpos(xml)

    assert out == expected_image_bytes()
    assert not out.endswith(main.build_cut_command())
    assert main.build_cut_command() not in out


def test_pulse_generates_cash_drawer_command():
    xml = b"<epos-print><pulse/></epos-print>"
    out = main.translate_epos_to_escpos(xml)
    assert out == main.build_cash_drawer_command()


def test_image_pulse_cut_appear_in_order(printer_width):
    printer_width(576)
    xml = build_image_xml(
        RASTER, WIDTH, HEIGHT, align="center",
        extra_elements="<pulse/><cut type='feed'/>",
    )
    out = main.translate_epos_to_escpos(xml)

    expected = (
        expected_image_bytes()
        + main.build_cash_drawer_command()
        + main.build_cut_command()
    )
    assert out == expected

    raster_end = len(expected_image_bytes())
    drawer_end = raster_end + len(main.build_cash_drawer_command())
    assert out[:raster_end].startswith(b"\x1D\x76\x30")  # raster first.
    assert out[raster_end:drawer_end] == b"\x1B\x70\x00\x19\xFA"  # drawer.
    assert out[drawer_end:] == b"\x1D\x56\x00"  # cut last.


def test_namespaced_translation_matches_plain(printer_width):
    printer_width(576)
    plain = build_image_xml(
        RASTER, WIDTH, HEIGHT, align="center",
        extra_elements='<cut type="feed"/>',
    )
    namespaced = build_image_xml(
        RASTER, WIDTH, HEIGHT, align="center",
        namespaced=True, extra_elements='<cut type="feed"/>',
    )
    assert main.translate_epos_to_escpos(namespaced) == (
        main.translate_epos_to_escpos(plain)
    )


def test_unsupported_request_raises():
    with pytest.raises(ValueError, match="No supported ePOS"):
        main.translate_epos_to_escpos(b"<epos-print><text>Hello</text></epos-print>")


def test_empty_request_raises():
    with pytest.raises(ValueError, match="No supported ePOS"):
        main.translate_epos_to_escpos(b"<epos-print/>")


def test_invalid_xml_raises_parse_error():
    with pytest.raises(ET.ParseError):
        main.translate_epos_to_escpos(b"<epos-print><image>")


def test_malformed_raster_raises_value_error():
    xml = (
        b"<epos-print><image width='8' height='2'>"
        b"!!!not-base64!!!</image></epos-print>"
    )
    with pytest.raises(ValueError):
        main.translate_epos_to_escpos(xml)


# ---------------------------------------------------------------------------
# Integration-style test with a realistic Odoo fixture
# ---------------------------------------------------------------------------

def test_realistic_receipt_fixture_end_to_end(printer_width, receipt_xml_bytes):
    """receipt.xml: 384px center-aligned image + <cut type='feed'/>."""
    printer_width(576)
    out = main.translate_epos_to_escpos(receipt_xml_bytes)

    # Pipeline property 1: starts with the raster command...
    # GS v 0 — raster bit image, normal density.
    assert out.startswith(b"\x1D\x76\x30\x00")

    # Pipeline property 2: ...and ends with exactly one cut command.
    assert out.endswith(main.build_cut_command())
    assert out.count(main.build_cut_command()) == 1

    # Pipeline property 3: Method A widened 384px -> 576px == 72 bytes/row.
    # xL=72 (0x48), xH=0, yL=4, yH=0 for the 4-row fixture image.
    assert out[4:8] == bytes([0x48, 0x00, 0x04, 0x00])

    # Pipeline property 4: payload length matches 72 bytes x 4 rows.
    raster_section = out[:8 + 72 * 4]
    assert len(raster_section) == 8 + 288
    assert out == raster_section + main.build_cut_command()

    # Pipeline property 5: left padding is white (zeros), original row0
    # was solid black (0xFF...), so it must appear after 12 zero bytes.
    first_row = out[8:80]
    assert first_row[:12] == b"\x00" * 12
    assert first_row[12:60] == b"\xFF" * 48
    assert first_row[60:] == b"\x00" * 12
