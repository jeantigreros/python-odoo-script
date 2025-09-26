# Odoo python script

This script basically creates a flask server, then "capture" the odoo calls that are xmls, extract and decode the xml data, convert esc/pos raster to numpy array, creates and return the image, run OCR tesseract to read the image and send ESC/POS commands to initialize the printer, feed 3 lines, and cut
