"""Unit tests for ESC/POS command generation.

Protocol reference (all integers little-endian):

    GS v 0 m xL xH yL yH d1...dk
    1D 76 30 m  xL xH yL yH payload

- m    : density mode (0x00 == normal).
- xL,xH: (width in BYTES, not pixels) as uint16 LE.
- yL,yH: height in dots (rows) as uint16 LE.
"""

import pytest

import main


def header(width_bytes: int, height: int, mode: int = 0x00) -> bytes:
    """Expected 8-byte GS v 0 header for the given dimensions."""
    return bytes([
        0x1D, 0x76, 0x30, mode,  # GS v 0 — raster bit image, normal density.
        width_bytes & 0xFF, (width_bytes >> 8) & 0xFF,
        height & 0xFF, (height >> 8) & 0xFF,
    ])


# ---------------------------------------------------------------------------
# build_raster_command()
# ---------------------------------------------------------------------------

def test_raster_header_starts_with_gs_v_0():
    data = main.build_raster_command(bytes([0xA5]), 8, 1)
    # GS v 0 — raster bit image.
    assert data.startswith(b"\x1D\x76\x30")
    # Normal density mode byte.
    assert data[3:4] == b"\x00"


def test_small_raster_exact_bytes():
    # 8px x 1 row: 1 byte wide, 1 row tall, payload 0xA5.
    data = main.build_raster_command(bytes([0xA5]), 8, 1)
    assert data == b"\x1D\x76\x30\x00" + bytes([0x01, 0x00, 0x01, 0x00]) + b"\xA5"


def test_full_width_raster_width_in_bytes():
    # 576px == 72 bytes per row; xL=72 (0x48), xH=0.
    raster = bytes([0x11]) * 72
    data = main.build_raster_command(raster, 576, 1)
    assert data[:8] == header(72, 1)
    assert data[4:6] == b"\x48\x00"
    assert data[8:] == raster


def test_multiple_rows_height_encoding():
    # 8px x 3 rows: height yL=3, yH=0.
    raster = bytes([0xAA, 0x55, 0xFF])
    data = main.build_raster_command(raster, 8, 3)
    assert data[:8] == header(1, 3)
    assert data[6:8] == b"\x03\x00"
    assert data[8:] == raster


def test_width_in_bytes_rounds_up_partial_byte():
    # 9px needs 2 bytes per row; xL must be 2, not 9.
    raster = bytes([0xFF, 0x00])
    data = main.build_raster_command(raster, 9, 1)
    assert data[4:6] == b"\x02\x00"
    assert data[8:] == raster


def test_tall_image_height_little_endian():
    # height=300 == 0x012C -> yL=0x2C, yH=0x01.
    raster = bytes([0x00]) * 300  # 8px wide x 300 rows.
    data = main.build_raster_command(raster, 8, 300)
    assert data[6:8] == b"\x2C\x01"
    assert len(data) == 8 + 300


def test_raster_payload_preserved_verbatim():
    raster = bytes([0x80, 0x01, 0xFE])
    data = main.build_raster_command(raster, 8, 3)
    assert data[8:] == raster


def test_raster_too_short_raises():
    with pytest.raises(ValueError, match="mismatch"):
        main.build_raster_command(bytes([0x00]), 8, 2)  # needs 2 bytes.


def test_raster_too_long_raises():
    with pytest.raises(ValueError, match="mismatch"):
        main.build_raster_command(bytes([0x00, 0x00, 0x00]), 8, 2)


def test_image_too_wide_raises():
    # width_bytes > 0xFFFF requires width > 524280px.
    with pytest.raises(ValueError, match="too wide"):
        main.build_raster_command(b"", 8 * 0x10000, 1)


def test_image_too_tall_raises():
    with pytest.raises(ValueError, match="too tall"):
        main.build_raster_command(b"", 8, 0x10000)


# ---------------------------------------------------------------------------
# build_cut_command() / build_cash_drawer_command()
# ---------------------------------------------------------------------------

def test_cut_command_exact_bytes():
    # GS V 0 — full cut (the command already proven on the POS-80).
    assert main.build_cut_command() == b"\x1D\x56\x00"


def test_cash_drawer_command_exact_bytes():
    # ESC p m=0 (pin 2) t1=25 t2=250 — standard drawer pulse.
    assert main.build_cash_drawer_command() == b"\x1B\x70\x00\x19\xFA"
