import serial
from PIL import Image
import os
import math

def print_image_with_pyserial(com_port, image_path):
    """
    Prints a PNG file as a raster bit image using the GS v 0 command.

    Args:
        com_port (str): The serial port (e.g., 'COM3').
        image_path (str): The path to the image file.
    """
    try:
        # Open the image and convert to 1-bit black and white
        # This conversion is crucial as the printer expects a monochrome bitmap
        img = Image.open(image_path).convert('1')
        
        # Get image dimensions
        width, height = img.size
        
        # Calculate the number of bytes per line (width divided by 8)
        bytes_per_line = math.ceil(width / 8)

        # Open the serial port
        ser = serial.Serial(
            port=com_port,
            baudrate=9600,  # Ensure this matches your printer's settings
            timeout=1
        )
        
        print(f"Connected to printer on {com_port}")

        # --- GS v 0 Command Structure ---
        # The command is: GS v 0 m xL xH yL yH d1...dk
        # Hexadecimal: 1D 76 30 m xL xH yL yH d1...dk

        # m (raster bit-image mode): Use a value like 0x00 for standard mode
        m = b'\x00'

        # xL, xH (horizontal data bits): Width in bytes
        xL = bytes([bytes_per_line % 256])
        xH = bytes([int(bytes_per_line / 256)])

        # yL, yH (vertical data bits): Height in dots
        yL = bytes([height % 256])
        yH = bytes([int(height / 256)])

        # Send the command header
        ser.write(b'\x1D\x76\x30' + m + xL + xH + yL + yH)
        
        # Get the raw byte data from the image
        img_bytes = img.tobytes()

        # Send the image data
        ser.write(img_bytes)

        # Cut the paper (optional, depends on your printer's commands)
        ser.write(b'\x1D\x56\x41') 
        ser.write(b'\x00') # Full cut command

        # Close the serial port
        ser.close()
        
        print(f"Successfully sent '{image_path}' to the printer.")

    except serial.SerialException as e:
        print(f"Error: Could not open serial port {com_port}. Please check the port name and if the device is connected: {e}")
    except FileNotFoundError:
        print(f"Error: The file '{image_path}' was not found.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

# Example usage
if __name__ == "__main__":
    com_port = win32print.GetDefaultPrinter()  # Replace with your printer's COM port
    image_file = 'output.png'
    print_image_with_pyserial(com_port, image_file)
