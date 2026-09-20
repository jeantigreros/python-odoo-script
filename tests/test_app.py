"""Flask endpoint tests for POST /cgi-bin/epos/service.cgi.

The Windows printer function is mocked so no printer (and no Windows) is
required.  Failure responses must stay Odoo-compatible XML — never an HTML
Flask error page.
"""

from unittest import mock

import main
from conftest import (
    build_image_xml,
    response_code,
    response_success,
)

URL = "/cgi-bin/epos/service.cgi"
RASTER = bytes([0x80, 0x01])


def post(client, body: bytes, content_type: str = "text/xml"):
    return client.post(URL, data=body, content_type=content_type)


def test_valid_request_returns_success_xml(client, printer_width):
    printer_width(576)
    xml = build_image_xml(
        RASTER, 8, 2, align="center", extra_elements='<cut type="feed"/>'
    )
    with mock.patch.object(main, "print_raw") as print_raw:
        resp = post(client, xml)

    assert resp.status_code == 200
    assert "xml" in resp.content_type  # Content-Type is XML, not HTML/JSON.
    assert b"<html" not in resp.data.lower()
    # Odoo-compatible success structure.
    assert response_success(resp.data) == "true"
    assert response_code(resp.data) == "0"
    # The generated ESC/POS bytes reached the printer layer exactly once.
    print_raw.assert_called_once()
    sent = print_raw.call_args[0][0]
    assert sent.startswith(b"\x1D\x76\x30")  # GS v 0 raster first.
    assert sent.endswith(b"\x1D\x56\x00")  # cut last.


def test_printer_receives_translation_output(client, printer_width):
    printer_width(576)
    xml = build_image_xml(RASTER, 8, 2, align="center")
    with mock.patch.object(main, "print_raw") as print_raw:
        post(client, xml)
    expected = main.translate_epos_to_escpos(xml)
    assert print_raw.call_args[0][0] == expected


def test_invalid_xml_returns_error_xml_not_html(client):
    with mock.patch.object(main, "print_raw") as print_raw:
        resp = post(client, b"<epos-print><image>")

    assert resp.status_code == 200
    assert "xml" in resp.content_type
    assert b"<html" not in resp.data.lower()
    assert response_success(resp.data) == "false"
    assert response_code(resp.data) == "INVALID_XML"
    print_raw.assert_not_called()


def test_malformed_raster_returns_bridge_error(client):
    xml = (
        b"<epos-print><image width='8' height='2'>"
        b"!!!not-base64!!!</image></epos-print>"
    )
    with mock.patch.object(main, "print_raw"):
        resp = post(client, xml)

    assert resp.status_code == 200
    assert "xml" in resp.content_type
    assert response_success(resp.data) == "false"
    assert response_code(resp.data) == "BRIDGE_ERROR"


def test_unsupported_command_returns_bridge_error(client):
    with mock.patch.object(main, "print_raw") as print_raw:
        resp = post(client, b"<epos-print><text>Hello</text></epos-print>")

    assert resp.status_code == 200
    assert response_success(resp.data) == "false"
    assert response_code(resp.data) == "BRIDGE_ERROR"
    print_raw.assert_not_called()


def test_printer_failure_returns_bridge_error(client, printer_width):
    printer_width(576)
    xml = build_image_xml(RASTER, 8, 2, align="center")
    with mock.patch.object(
        main, "print_raw", side_effect=IOError("spooler offline")
    ):
        resp = post(client, xml)

    assert resp.status_code == 200
    assert "xml" in resp.content_type
    assert b"<html" not in resp.data.lower()
    assert response_success(resp.data) == "false"
    assert response_code(resp.data) == "BRIDGE_ERROR"
