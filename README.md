# Odoo ePOS → ESC/POS Bridge

A lightweight Windows print bridge that receives **Odoo POS ePOS XML requests over HTTP**, converts the embedded receipt raster image into **ESC/POS commands**, and sends the resulting raw print data directly to a Windows thermal printer.

The bridge is designed for environments where Odoo POS communicates using the Epson ePOS protocol, while the physical POS printer is exposed through the Windows printing subsystem.

## Features

-  **Odoo POS ePOS compatibility**
  - Accepts requests at `/cgi-bin/epos/service.cgi`.
  - Supports Odoo's raster-based receipt output.
-  **ePOS → ESC/POS conversion**
  - Extracts `<image>` raster data from ePOS XML.
  - Converts the raster into `GS v 0` ESC/POS commands.
  - Sends printer-ready RAW bytes to Windows.
-  **Receipt scaling**
  - Independent horizontal and vertical scaling.
  - Defaults to `1.0x` horizontal and `1.50x` vertical scaling.
  - Allows receipt text to be made taller without increasing its width.
- ↔ **Receipt centering**
  - Supports Odoo's `align="center"` attribute.
  - Automatically adds the required horizontal padding.
-  **Cash drawer support**
  - Translates ePOS `<pulse/>` requests into an ESC/POS cash-drawer pulse.
-  **Automatic cutting**
  - Supports ePOS `<cut/>`.
  - Adds configurable blank lines before the cut.
-  **Printer locking**
  - Uses a thread lock to prevent simultaneous RAW jobs from interfering with each other.
-  **CORS enabled**
  - Allows requests from Odoo POS environments that require cross-origin access.
-  **Windows RAW printing**
  - Uses `pywin32` and the Windows spooler.
  - Does not require a vendor-specific Windows print driver for the receipt formatting itself.
-  **Linux/CI-friendly imports**
  - The application can be imported without `pywin32`.
  - Actual printing correctly reports that Windows/pywin32 is required.

---

 ## Architecture

 The bridge follows this flow:

```
┌─────────────────┐
│    Odoo POS     │
└────────┬────────┘
         │
         │ ePOS XML / HTTP POST
         ▼
┌─────────────────────────────┐
│     Flask Print Bridge      │
│                             │
│  /cgi-bin/epos/service.cgi  │
└─────────────┬───────────────┘
              │
              ▼
┌─────────────────────────────┐
│     ePOS XML Parser         │
│                             │
│  <image>                    │
│  <pulse>                    │
│  <cut>                      │
└─────────────┬───────────────┘
              │
              ▼
┌─────────────────────────────┐
│   Raster Processing         │
│                             │
│  • Base64 decode             │
│  • Scaling                   │
│  • Centering                 │
│  • Validation                │
└─────────────┬───────────────┘
              │
              ▼
┌─────────────────────────────┐
│      ESC/POS Builder        │
│                             │
│  GS v 0                     │
│  ESC p                      │
│  GS V                       │
└─────────────┬───────────────┘
              │
              ▼
┌─────────────────────────────┐
│    Windows Print Spooler    │
│         RAW job             │
└─────────────┬───────────────┘
              │
              ▼
       ┌─────────────┐
       │ POS Printer │
       └─────────────┘
```

---

 ## Requirements

 ### Operating system

 The bridge is intended to run on **Windows**, because it uses the Windows printing API through `pywin32`.

 ### Python

 Recommended:

```
Python 3.10+
```

 ### Python packages

 Install the required dependencies:

```
pip install -r requirements.txt
```


 ## Printer Configuration

 The bridge communicates with the Windows printer using its configured printer name.

 By default, the application attempts to determine the printer in this order:

1. `POS_PRINTER_NAME`
2. `POS-80`
3. Windows default printer

 The recommended approach is to explicitly configure the printer.

 Make sure the printer name exactly matches the printer installed in Windows.

 You can find the installed printer name under:

 **Windows Settings → Bluetooth & devices → Printers & scanners**

---

 ## Configuration

 The bridge is configured primarily through environment variables.

 | Variable | Default | Description |
| --- | --- | --- |
| `POS_PRINTER_NAME` | Windows default / `POS-80` | Windows printer name |
| `POS_PRINTER_WIDTH_DOTS` | `576` | Maximum printer width in dots |
| `POS_RASTER_SCALE_X` | `1.0` | Horizontal raster scale |
| `POS_RASTER_SCALE_Y` | `1.50` | Vertical raster scale |
| `POS_END_BLANK_LINES` | `2` | Blank lines before cutting |

### Example configuration

```
$env:POS_PRINTER_NAME="POS-80"
$env:POS_PRINTER_WIDTH_DOTS="576"
$env:POS_RASTER_SCALE_X="1.0"
$env:POS_RASTER_SCALE_Y="1.50"
$env:POS_END_BLANK_LINES="2"

python main.py
```

 ## Raster Scaling

 Odoo sends the receipt as a 1-bit bitmap.

 The bridge can resize this bitmap before converting it into ESC/POS raster commands.

 ### Horizontal scaling

```
POS_RASTER_SCALE_X=1.0
```

 The default keeps the receipt at its original width.

 This is intentional because increasing horizontal scaling can cause the receipt to exceed the printer's printable area.

 ### Vertical scaling

```
POS_RASTER_SCALE_Y=1.50
```

 The default configuration makes the receipt approximately **50% taller** while maintaining its horizontal size.

 For example:

```
1.00 = original height
1.10 = 10% taller
1.20 = 20% taller
1.50 = 50% taller
2.00 = 100% taller
```

 Example:

```
$env:POS_RASTER_SCALE_Y="1.20"
```

 If the printed receipt appears too stretched, reduce the value.

 If the receipt text appears too short vertically, increase it.

---

 ## Centering

 Odoo may send an image with:

```
<image align="center" ...>
```

 When `CENTER_IMAGES = True`, the bridge calculates the available space and adds left-side padding so the receipt is centered on the configured printer width.

 For example:

```
Printer width: 576 dots
Receipt width:  512 dots

Remaining:       64 dots
Left padding:    32 dots
```

 The resulting ESC/POS raster is padded to the full printer width.

---

 ## Supported ePOS Commands

 The bridge currently supports the subset of ePOS commands required by the Odoo POS printing flow implemented by this application.

 ### Image

```
<image
    width="..."
    height="..."
    align="center">
    BASE64_RASTER_DATA
</image>
```

 The image is:

1. Extracted from the XML.
2. Base64 decoded.
3. Validated.
4. Optionally scaled.
5. Centered.
6. Converted to ESC/POS raster data.
7. Sent to the printer.

 ### Cash drawer

```
<pulse/>
```

 This is translated into:

```
ESC p 0 25 250
```

 which generates a typical cash-drawer pulse.

 The exact electrical pulse requirements depend on the connected printer and drawer hardware.

 ### Cut

```
<cut/>
```

 The bridge first sends the configured number of line feeds and then sends:

```
GS V 0
```

 The current implementation uses a full-cut command.

---

 ## HTTP Endpoint

 The service listens on:

```
http://127.0.0.1:5000
```

 The ePOS endpoint is:

```
/cgi-bin/epos/service.cgi
```

 Therefore the complete endpoint is:

```
http://127.0.0.1:5000/cgi-bin/epos/service.cgi
```

 The endpoint accepts:

```
POST
```

 requests containing ePOS XML.

---

 ## ePOS Response

 A successful request returns an ePOS-compatible XML response similar to:

```
<?xml version="1.0" encoding="utf-8"?>
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">
    <s:Body>
        <epos-print xmlns="http://www.epson-pos.com/schemas/2011/03/epos-print">
            <response success="true" code="0"/>
        </epos-print>
    </s:Body>
</s:Envelope>
```

 For errors, the bridge returns:

```
<response success="false" code="BRIDGE_ERROR"/>
```

 Invalid XML produces:

```
<response success="false" code="INVALID_XML"/>
```

 HTTP status remains `200` so that the ePOS client can process the XML response itself.

---

 ## Running the Bridge

 Start the application with:

```
python app.py
```

 Expected logging includes:

```
Starting Odoo ePOS -> ESC/POS bridge
Printer: POS-80
Printer width: 576 dots
Raster scale X: 1.00x
Raster scale Y: 1.50x
End blank lines: 2
Listening on http://127.0.0.1:5000
ePOS endpoint: /cgi-bin/epos/service.cgi
```

 The application uses **Waitress** rather than Flask's development server.

---

 ## Testing the Endpoint

 You can test that the service is reachable with a simple HTTP request.

 For example, using PowerShell:

```
Invoke-WebRequest `
    -Uri "http://127.0.0.1:5000/cgi-bin/epos/service.cgi" `
    -Method POST `
    -ContentType "text/xml" `
    -Body "<test/>"
```

 A request such as this will not produce a successful print because `<test/>` does not contain a supported ePOS command, but it can be useful for verifying that the HTTP service is running.

 For actual printer testing, use an ePOS XML request containing a valid `<image>` raster.

---

 ## Logging

 The bridge uses Python's standard `logging` module.

 Example:

```
2026-09-20 13:00:00 [INFO] Received ePOS print request
2026-09-20 13:00:00 [INFO] Request size: 12345 bytes
2026-09-20 13:00:00 [INFO] Received raster: 576x1200, align=center, 86400 bytes
2026-09-20 13:00:00 [INFO] Scaling raster X=1.00x Y=1.50x
2026-09-20 13:00:00 [INFO] Scaled raster: 576x1800
2026-09-20 13:00:01 [INFO] Cut requested; adding 2 blank lines
2026-09-20 13:00:01 [INFO] RAW print job sent: 130000 bytes
```

 These logs are particularly useful when diagnosing:

- Incorrect printer names.
- Invalid XML.
- Invalid Base64 data.
- Raster dimension mismatches.
- Printer width problems.
- Windows spooler failures.
- Receipt scaling issues.

---


 ## Performance and Concurrency

 The application runs under Waitress with:

```
threads=8
```

 However, actual printer access is serialized using:

```
printer_lock = threading.Lock()
```

 This prevents multiple requests from simultaneously writing to the same Windows printer.

 The architecture therefore allows concurrent HTTP handling while protecting the printer spool operation.

---


 ## License


```
MIT License
```
