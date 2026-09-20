"""Unit tests for Method A (raster centering).

Method A centers the Odoo raster by prepending whole bytes of white pixels
(0x00) on the left and appending white pixels on the right so the final
raster is exactly PRINTER_WIDTH_DOTS wide:

    left_padding = (printer_width - receipt_width) // 2   (floored to 8px)

Padding is byte-oriented: 8 pixels == 1 zero byte.  White == 0x00 because
ESC/POS raster bits are 1 == black dot, 0 == white (no dot).
"""

import pytest

import main


# ---------------------------------------------------------------------------
# add_left_padding() — the primitive Method A builds on
# ---------------------------------------------------------------------------

def test_add_left_padding_single_row_exact_bytes():
    raster = bytes([0x80])  # 8px wide, 1 row.
    padded, new_width = main.add_left_padding(raster, 8, 1, 8)
    assert new_width == 16
    assert padded == b"\x00\x80"  # 1 white byte, then original row.


def test_add_left_padding_applies_to_every_row():
    raster = bytes([0xAA, 0x55])  # 8px wide, 2 rows.
    padded, new_width = main.add_left_padding(raster, 8, 2, 8)
    assert new_width == 16
    assert padded == b"\x00\xaa\x00\x55"


def test_add_left_padding_zero_is_noop():
    raster = bytes([0x80, 0x01])
    padded, new_width = main.add_left_padding(raster, 8, 2, 0)
    assert new_width == 8
    assert padded == raster


def test_add_left_padding_non_multiple_of_8_raises():
    with pytest.raises(ValueError, match="multiple of 8"):
        main.add_left_padding(bytes([0x80]), 8, 1, 4)


def test_add_left_padding_does_not_mutate_input():
    original = bytearray(b"\x80\x01")
    snapshot = bytes(original)
    main.add_left_padding(bytes(original), 8, 2, 16)
    assert bytes(original) == snapshot


# ---------------------------------------------------------------------------
# prepare_raster() — Method A centering (printer_width = 576)
# ---------------------------------------------------------------------------

def test_exact_centered_case_384_on_576(printer_width):
    """printer=576, receipt=384 -> left=96px, right=96px."""
    printer_width(576)
    row = bytes([0xAB]) * 48  # 384px == 48 bytes per row.
    raster = row  # height == 1.
    out, final_width = main.prepare_raster(raster, 384, 1, "center")

    assert final_width == 576
    assert len(out) == 72  # 576 / 8.
    # Left padding: 96 white pixels == 12 zero bytes.
    assert out[:12] == b"\x00" * 12
    # Original raster data remains unchanged in the middle.
    assert out[12:60] == row
    # Right padding mirrors the left.
    assert out[60:] == b"\x00" * 12


def test_already_full_width_image_gets_no_padding(printer_width):
    """printer=576, receipt=576 -> nothing to center."""
    printer_width(576)
    raster = bytes([0xCD]) * 72  # 576px == 72 bytes, 1 row.
    out, final_width = main.prepare_raster(raster, 576, 1, "center")

    assert final_width == 576
    assert out == raster  # no padding added, content unchanged.


def test_non_8_aligned_available_space(printer_width):
    """printer=576, receipt=392: remaining=184, not divisible by 16.

    left_raw = 184 // 2 = 92 -> floored to whole bytes -> 88px (11 bytes).
    right = 576 - (392 + 88) = 96px (12 bytes).
    """
    printer_width(576)
    original_row = bytes([0x5A]) * 49  # 392px == 49 bytes per row.
    out, final_width = main.prepare_raster(
        original_row, 392, 1, "center"
    )

    assert final_width == 576
    assert len(out) == 72
    # Left padding follows the byte-alignment rule (88px, not 92px).
    assert out[:11] == b"\x00" * 11
    assert out[11:60] == original_row
    assert out[60:] == b"\x00" * 12


def test_narrow_image_exact_output_bytes(printer_width):
    """width=8, height=2, raster 0x80/0x01 on a 576-dot printer.

    remaining = 568, left = 284 -> floored to 280px (35 bytes).
    right = 576 - (8 + 280) = 288px (36 bytes).
    """
    printer_width(576)
    raster = bytes([0x80, 0x01])
    out, final_width = main.prepare_raster(raster, 8, 2, "center")

    assert final_width == 576
    expected = (
        b"\x00" * 35 + b"\x80" + b"\x00" * 36
        + b"\x00" * 35 + b"\x01" + b"\x00" * 36
    )
    assert out == expected
    assert len(out) == 144  # 2 rows x 72 bytes.


def test_padding_added_independently_to_every_row(printer_width):
    """Row boundaries must survive centering: each row keeps its bytes."""
    printer_width(576)
    # 16px wide -> 2 bytes per row, 3 rows with distinct content.
    rows = [bytes([0xAA, 0x55]), bytes([0xFF, 0x00]), bytes([0x01, 0x80])]
    raster = b"".join(rows)
    # remaining = 560, left = right = 280px == 35 bytes.
    out, final_width = main.prepare_raster(raster, 16, 3, "center")

    assert final_width == 576
    assert len(out) == 3 * 72
    for i, row in enumerate(rows):
        chunk = out[i * 72:(i + 1) * 72]
        assert chunk[:35] == b"\x00" * 35
        assert chunk[35:37] == row  # original row bytes preserved.
        assert chunk[37:] == b"\x00" * 35


def test_prepare_raster_does_not_mutate_input(printer_width):
    printer_width(576)
    raster = bytes([0xAB]) * 48
    snapshot = bytes(raster)
    main.prepare_raster(raster, 384, 1, "center")
    assert raster == snapshot


def test_left_alignment_skips_centering(printer_width):
    printer_width(576)
    raster = bytes([0xAB]) * 48
    out, final_width = main.prepare_raster(raster, 384, 1, "left")
    assert final_width == 384
    assert out == raster


def test_centering_disabled_skips_padding(printer_width, monkeypatch):
    printer_width(576)
    monkeypatch.setattr(main, "CENTER_IMAGES", False)
    raster = bytes([0xAB]) * 48
    out, final_width = main.prepare_raster(raster, 384, 1, "center")
    assert final_width == 384
    assert out == raster


def test_receipt_wider_than_printer_raises(printer_width):
    printer_width(576)
    with pytest.raises(ValueError, match="exceeds printer width"):
        main.prepare_raster(bytes([0xFF]) * 73, 584, 1, "center")


def test_source_width_not_divisible_by_8_raises(printer_width):
    printer_width(576)
    # 10px -> 2 bytes per row; Method A requires byte-exact widths.
    with pytest.raises(ValueError, match="divisible by 8"):
        main.prepare_raster(bytes([0x00, 0x00]), 10, 1, "center")


def test_printer_width_not_divisible_by_8_raises(printer_width):
    printer_width(575)
    with pytest.raises(ValueError, match="divisible by 8"):
        main.prepare_raster(bytes([0x80]), 8, 1, "center")
