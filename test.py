
import win32print
from PIL import Image
import pytesseract

# Load the receipt image
img = Image.open("output.png")

# Run OCR (Spanish language)
text = pytesseract.image_to_string(img, lang="spa")

# Save to text file
with open("output.txt", "w", encoding="utf-8") as f:
    f.write(text)

text_to_print = text

# ESC/POS commands
INIT = b"\x1B\x40"        # Initialize
FEED = b"\n\n\n"          # Feed 3 lines
CUT  = b"\x1D\x56\x00"    # Full cut

try:
    printer_name = win32print.GetDefaultPrinter()
    hPrinter = win32print.OpenPrinter(printer_name)
    hJob = win32print.StartDocPrinter(hPrinter, 1, ("My Document", None, "RAW"))
    win32print.StartPagePrinter(hPrinter)

    # Convert text to bytes (use cp437 for ESC/POS printers)
    data_bytes = text_to_print.encode("cp437", errors="replace")

    # Send to printer: initialize + text + feed + cut
    win32print.WritePrinter(hPrinter, INIT + data_bytes + FEED + FEED + CUT)
    win32print.EndPagePrinter(hPrinter)
    win32print.EndDocPrinter(hPrinter)
    win32print.ClosePrinter(hPrinter)

    print("✅ Receipt sent with feed & cut")

except Exception as e:
    print(f"❌ An error occurred: {e}")
