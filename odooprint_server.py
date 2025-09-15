from flask import Flask, request, Response
import escpos.printer as printer
from escpos import exceptions as escpos_exceptions
import usb.core

# output network de odoo
# https://192.168.18.101/cgi-bin/epos/service.cgi?devid=local_printer 
app = Flask(__name__)

# cambiar esto al puerto del a impresora
PIRNTER_PORT = "lmao"

# buscar la impresora
def find_jaltech_printer():
    common_escpos_devices = [
        {'vendor_id': 0x0416, 'product_id': 0x5011},  # Ejemplo genérico 1
        {'vendor_id': 0x1504, 'product_id': 0x0006},  # Ejemplo genérico 2
        {'vendor_id': 0x0483, 'product_id': 0x5740},  # Ejemplo genérico 3
    ]

    for device_info in common_escpos_devices:
        dev = usb.core.find(idVendor=device_info['vendor_id'], idPorduct=device_info['product_id'])
        if dev is not None:
            print(f"¡Impresora encontrada! Vendor ID: {device_info['vendor_id']:04x}, Product ID: {device_info['product_id']:04x}")
            try:
                # Intentar crear una instancia de la impresora con los IDs encontrados
                usb_printer = printer.Usb(device_info['vendor_id'], device_info['product_id'])
                print("Conexión establecida con la impresora.")
                return usb_printer
            except escpos_exceptions.USBNotFoundError:
                print("Se encontró el dispositivo USB, pero no se pudo inicializar como impresora.")
                continue
        return None

jaltech_printer = find_jaltech_printer()

@app.route('/print-receipt', methods=['POST'])
def print_receipt():
    if jaltech_printer is None:
        return Response("Error: Verificar USB", status=500)

    try:
        # get raw data from odoo
        escpos_data = request.data

        # print raw
        jaltech_printer._raw(escpos_data)

        jaltech_printer.control('LF', count=2)
        jaltech_printer.cut()

        return Response(status=200)

    
    except escpos_exceptions.USBNotFoundError:
        print("Error: Se perdió la conexión con la impresora USB.")
        return Response("Error de conexión con la impresora.", status=500)
    except Exception as e:
        print(f"Error inesperado: {e}")
        return Response(f"Error del servidor: {e}", status=500)

if __name__ == '__main__':
    print("Iniciando Servidor de Impresión ESC/POS para Odoo Online...")
    if jaltech_printer:
        print("La impresora JALTECH está conectada y lista.")
    else:
        print("ADVERTENCIA: No se pudo encontrar una impresora ESC/POS al inicio.")
        print("Conecte la impresora y reinicie el script, o envíe un trabajo de prueba.")
    # Ejecutar el servidor en el puerto 3000.
    app.run(host='0.0.0.0', port=3000, debug=True)



