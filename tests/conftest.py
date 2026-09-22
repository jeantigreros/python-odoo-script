"""Shared pytest fixtures for the ePOS -> ESC/POS bridge test suite.

The production module (``main.py``) imports ``win32print`` at module load
time and resolves the default printer eagerly.  Neither Windows nor a
physical printer may be required for the normal test suite, so a lightweight
``win32print`` stub is installed in ``sys.modules`` *before* ``main`` is
imported.  Individual tests patch ``main.win32print.<func>`` or
``main.print_raw`` to observe / control printer behaviour.
"""

import base64
import os
import sys
import types
import xml.etree.ElementTree as ET
from unittest import mock

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# ---------------------------------------------------------------------------
# win32print stub (Linux / CI friendly)
# ---------------------------------------------------------------------------

try:  # pragma: no cover - only taken on Windows
    import win32print  # noqa: F401
except ImportError:  # Linux / macOS: provide a stub so `import main` works.
    stub = types.ModuleType("win32print")
    stub.GetDefaultPrinter = mock.MagicMock(return_value="MockPrinter")
    stub.OpenPrinter = mock.MagicMock(return_value="MOCK_HANDLE")
    stub.StartDocPrinter = mock.MagicMock()
    stub.StartPagePrinter = mock.MagicMock()
    stub.WritePrinter = mock.MagicMock(return_value=0)
    stub.EndPagePrinter = mock.MagicMock()
    stub.EndDocPrinter = mock.MagicMock()
    stub.ClosePrinter = mock.MagicMock()
    sys.modules["win32print"] = stub

import main  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers (kept module-level so every test module can import them)
# ---------------------------------------------------------------------------

def encode_raster(raster: bytes) -> str:
    """Base64-encode raw raster bytes for embedding in ePOS XML."""
    return base64.b64encode(raster).decode("ascii")


def build_image_xml(
    raster: bytes,
    width: int,
    height: int,
    align: str | None = "center",
    namespaced: bool = False,
    extra_elements: str = "",
) -> bytes:
    """Build a minimal ePOS document containing one <image> element.

    Args:
        raster: raw MSB-first 1bpp raster bytes.
        width: value for the ``width`` attribute.
        height: value for the ``height`` attribute.
        align: value for the ``align`` attribute, or None to omit it.
        namespaced: wrap the document in the real SOAP/ePOS namespaces.
        extra_elements: additional raw XML (e.g. ``<cut/>``) appended
            after the ``<image>`` element.
    """
    payload = encode_raster(raster)
    align_attr = "" if align is None else f' align="{align}"'
    image_el = (
        f'<image width="{width}" height="{height}"{align_attr}>'
        f"{payload}</image>"
    )
    if namespaced:
        return (
            f'<?xml version="1.0" encoding="utf-8"?>'
            f'<s:Envelope xmlns:s="{main.SOAP_NS}">'
            f"<s:Body>"
            f'<epos-print xmlns="{main.EPOS_NS}">'
            f"{image_el}{extra_elements}"
            f"</epos-print>"
            f"</s:Body>"
            f"</s:Envelope>"
        ).encode("utf-8")
    return (
        f"<epos-print>{image_el}{extra_elements}</epos-print>"
    ).encode("utf-8")


def parse_response_xml(body: bytes) -> ET.Element:
    """Parse a bridge SOAP response body into an Element."""
    return ET.fromstring(body)


def response_success(body: bytes) -> str | None:
    """Return the ``success`` attribute of the <response> element."""
    root = parse_response_xml(body)
    el = main.find_element(root, "response")
    assert el is not None, "response XML has no <response> element"
    return el.attrib.get("success")


def response_code(body: bytes) -> str | None:
    """Return the ``code`` attribute of the <response> element."""
    root = parse_response_xml(body)
    el = main.find_element(root, "response")
    assert el is not None, "response XML has no <response> element"
    return el.attrib.get("code")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def neutral_scaling(monkeypatch):
    """Deterministic raster pipeline: tests assume no scaling."""
    monkeypatch.setattr(main, "RASTER_SCALE_X", 1.0)
    monkeypatch.setattr(main, "RASTER_SCALE_Y", 1.0)
    monkeypatch.setattr(main, "END_BLANK_LINES", 2)


@pytest.fixture()
def app():
    """Flask application with TESTING enabled."""
    main.app.config.update(TESTING=True)
    return main.app


@pytest.fixture()
def client(app):
    """Flask test client (no network, no Windows required)."""
    return app.test_client()


@pytest.fixture()
def printer_width(monkeypatch):
    """Set main.PRINTER_WIDTH_DOTS for a single test.

    Usage::

        def test_something(printer_width):
            printer_width(576)
    """
    def _set(width: int):
        monkeypatch.setattr(main, "PRINTER_WIDTH_DOTS", width)
        return width

    return _set


@pytest.fixture()
def mock_win32print(monkeypatch):
    """Patch all seven win32print entry points used by print_raw.

    Returns a dict of MagicMocks keyed by function name.  WritePrinter
    defaults to reporting a full write; tests may override its
    ``return_value`` / ``side_effect``.
    """
    calls = {}
    for name in (
        "OpenPrinter",
        "StartDocPrinter",
        "StartPagePrinter",
        "WritePrinter",
        "EndPagePrinter",
        "EndDocPrinter",
        "ClosePrinter",
    ):
        m = mock.MagicMock(name=f"win32print.{name}")
        monkeypatch.setattr(main.win32print, name, m)
        calls[name] = m
    calls["OpenPrinter"].return_value = "MOCK_HANDLE"
    return calls


@pytest.fixture()
def receipt_xml_bytes() -> bytes:
    """Raw bytes of the realistic Odoo receipt fixture."""
    path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "fixtures", "receipt.xml"
    )
    with open(path, "rb") as fh:
        return fh.read()
