"""Tests for the Windows RAW printing layer (print_raw).

All seven win32print entry points are mocked — a physical printer is never
touched.  These tests verify the spooler protocol: open -> start RAW doc ->
write bytes -> close, including byte-count validation and cleanup on error.
"""

import pytest

import main


DATA = b"\x1D\x76\x30\x00\x01\x00\x01\x00\xA5"


def test_print_raw_happy_path(mock_win32print, monkeypatch):
    monkeypatch.setattr(main, "PRINTER_NAME", "TestPrinter")
    mock_win32print["WritePrinter"].return_value = len(DATA)

    main.print_raw(DATA)

    mock_win32print["OpenPrinter"].assert_called_once_with("TestPrinter")
    # A RAW print job is started with the Odoo receipt doc info.
    args = mock_win32print["StartDocPrinter"].call_args[0]
    assert args[0] == "MOCK_HANDLE"
    assert args[2] == ("Odoo POS Receipt", None, "RAW")
    mock_win32print["StartPagePrinter"].assert_called_once_with("MOCK_HANDLE")
    # WritePrinter() receives the generated ESC/POS bytes verbatim.
    mock_win32print["WritePrinter"].assert_called_once_with(
        "MOCK_HANDLE", DATA
    )
    mock_win32print["EndPagePrinter"].assert_called_once_with("MOCK_HANDLE")
    mock_win32print["EndDocPrinter"].assert_called_once_with("MOCK_HANDLE")
    mock_win32print["ClosePrinter"].assert_called_once_with("MOCK_HANDLE")


def test_print_raw_empty_data_raises_without_touching_printer(mock_win32print):
    with pytest.raises(ValueError, match="No printer data"):
        main.print_raw(b"")
    mock_win32print["OpenPrinter"].assert_not_called()


def test_print_raw_short_write_raises(mock_win32print):
    # WritePrinter() reports fewer bytes than expected -> IOError.
    mock_win32print["WritePrinter"].return_value = len(DATA) - 1
    with pytest.raises(IOError, match="accepted only"):
        main.print_raw(DATA)
    # Resources are still released despite the failure.
    mock_win32print["EndPagePrinter"].assert_called_once()
    mock_win32print["EndDocPrinter"].assert_called_once()
    mock_win32print["ClosePrinter"].assert_called_once()


def test_print_raw_write_error_still_closes_printer(mock_win32print):
    mock_win32print["WritePrinter"].side_effect = RuntimeError("spooler down")
    with pytest.raises(RuntimeError, match="spooler down"):
        main.print_raw(DATA)
    mock_win32print["EndPagePrinter"].assert_called_once()
    mock_win32print["EndDocPrinter"].assert_called_once()
    mock_win32print["ClosePrinter"].assert_called_once_with("MOCK_HANDLE")


def test_print_raw_open_failure_does_not_close(mock_win32print):
    mock_win32print["OpenPrinter"].side_effect = RuntimeError("no printer")
    with pytest.raises(RuntimeError, match="no printer"):
        main.print_raw(DATA)
    # Nothing was opened, so there is nothing to close.
    mock_win32print["ClosePrinter"].assert_not_called()
