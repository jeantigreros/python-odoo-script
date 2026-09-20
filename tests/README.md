# Test suite — ePOS → ESC/POS bridge (`main.py`)

Automated `pytest` suite for the Windows printing bridge that translates
Odoo 18 POS ePOS XML into ESC/POS and spools it as RAW. Focus: the
**ePOS parsing → Method A raster centering → ESC/POS generation** pipeline.

## Run

```bash
pip install pytest flask flask-cors
pytest -q            # full suite, from the repo root
pytest tests/test_raster.py -q   # one layer at a time
```

## Design principles

- **No Windows, no printer, no Odoo, no network.** `tests/conftest.py`
  installs a `win32print` stub in `sys.modules` *before* importing `main`
  (which imports `win32print` and resolves the default printer at load
  time). Spooler calls are observed via mocks, never executed.
- **Deterministic fixtures.** Most tests use an 8×2 image
  (`bytes([0x80, 0x01])` — MSB set, then LSB set) so expected bytes can be
  written out by hand and failures are easy to diagnose.
- **Exact byte assertions** for protocol behavior
  (e.g. `assert data.startswith(b"\x1D\x76\x30")  # GS v 0 raster`),
  with a comment naming each command.
- **One behavior per test**, descriptive names, no coupling to
  implementation details beyond the public function contract.
- Production code is **not** modified by this suite (`git status` shows only
  the new `tests/` directory).

## Layout

```text
tests/
├── conftest.py          # win32print stub, Flask client, shared helpers/fixtures
├── fixtures/
│   └── receipt.xml      # realistic Odoo receipt: 384px center image + <cut/>
├── test_epos.py         # ePOS XML parsing (extract_raster)
├── test_raster.py       # Method A centering (add_left_padding, prepare_raster)
├── test_escpos.py       # ESC/POS bytes (raster, cut, drawer)
├── test_translation.py  # ePOS → ESC/POS translation + end-to-end fixture test
├── test_app.py          # Flask endpoint (mocked printer layer)
└── test_print.py        # Windows RAW layer (mocked win32print)
```

`conftest.py` provides: `build_image_xml()` (plain or SOAP-namespaced
documents with optional `<cut/>`/`<pulse/>` extras), `encode_raster()`,
`response_success()` / `response_code()` (read the `<response>` attrs),
and fixtures `client`, `printer_width` (monkeypatches
`PRINTER_WIDTH_DOTS` per test), `mock_win32print` (seven mocked spooler
entry points), `receipt_xml_bytes`.

## Method A (raster centering) — the core rule

Odoo sends narrow, center-aligned rasters; the bridge widens them to the
full printer width with white (`0x00`) pixels, in whole bytes:

```text
left_padding = (printer_width - receipt_width) // 2, floored to 8 px
```

`test_raster.py` pins this down case by case (printer = 576):

| receipt | remaining | left → bytes | right → bytes | final |
| ------- | --------- | ------------ | ------------- | ----- |
| 384 px  | 192       | 96 px → 12 B | 96 px → 12 B  | 576   |
| 576 px  | 0         | none         | none           | 576   |
| 392 px  | 184 (÷16 ✗) | 92→**88** px → 11 B | 96 px → 12 B | 576 |
| 8 px ×2 (`80 01`) | 568 | 284→**280** px → 35 B | 288 px → 36 B | 576 |

Also covered: padding applied independently per row (boundaries preserved),
input never mutated, `left` alignment / `CENTER_IMAGES=False` skip
centering, and errors for oversize / non-8px source / non-8px printer width.

## Per-file coverage

### `test_epos.py` — parsing (`extract_raster`), 21 tests

Happy paths: valid XML, SOAP/ePOS-namespaced XML, explicit-namespace
`<image>`, `width`/`height`/`align="center"`, missing `align` → `"left"`,
base64 split across lines. Error paths (all `ValueError`): missing
`<image>`, empty element/text, invalid base64, invalid/missing
width/height, zero/negative dimensions (parametrized), raster too
short/long vs. `width × height`.

### `test_escpos.py` — command bytes, 13 tests

`GS v 0` raster (`1D 76 30`, mode `00` normal density, `xL xH` = width in
**bytes** LE, `yL yH` = height LE): exact-bytes small raster
(`…01 00 01 00 A5`), full-width 576 px (`xL=0x48`), multi-row height,
partial-byte rounding (9 px → 2 B), tall image (`300 → 2C 01`), verbatim
payload, short/long mismatch, too-wide/too-tall. Plus exact bytes for cut
(`1D 56 00`, GS V 0 full cut) and drawer (`1B 70 00 19 FA`, ESC p m=0).

### `test_translation.py` — `translate_epos_to_escpos`, 10 tests

Image+cut (raster first, cut last, exact concat), image-only (no cut
smuggled in), `<pulse/>` → drawer bytes, image+pulse+cut ordering,
namespaced ≡ plain output, unsupported/empty → `ValueError`, invalid XML →
`ParseError`, malformed raster → `ValueError`. Integration test on
`fixtures/receipt.xml` asserts the whole pipeline: `GS v 0` header,
single trailing cut, `48 00 04 00` dims (72 B × 4 rows), 12-white/48-data/
12-white first row.

### `test_app.py` — Flask `POST /cgi-bin/epos/service.cgi`, 6 tests

`print_raw` mocked. Success → HTTP 200, XML content type (never HTML),
`<response success="true" code="0"/>`, spooler got the exact translation
bytes. Failures → HTTP 200 + `<response success="false" …/>` with
`INVALID_XML` (bad XML) or `BRIDGE_ERROR` (bad raster, unsupported command,
printer `IOError`); printer not called when translation never succeeded.

### `test_print.py` — `print_raw` spooler protocol, 5 tests

Happy path asserts the full sequence (`OpenPrinter` → `StartDocPrinter`
with `("Odoo POS Receipt", None, "RAW")` → `StartPage` → `WritePrinter`
with verbatim bytes → `EndPage` → `EndDoc` → `ClosePrinter`), empty data
rejected before touching the spooler, short write (`written < len`)
→ `IOError`, and `EndPage/EndDoc/Close` still run on write failure
(but no `ClosePrinter` when `OpenPrinter` itself fails).

## Last result

```text
Tests added:    71 (21 + 16 + 13 + 10 + 6 + 5)
Tests executed: pytest -q
Result:         71 passed, 0 failed, 0 skipped
Production changes: none
```

## Explicitly out of scope

Physical-printer output on Windows is **not** covered here and must be
validated separately as a Windows integration test.
