# app/printer/connection.py
from escpos.printer import Network, Usb
from escpos.exceptions import Error, DeviceNotFoundError
from app.config import AppConfig


def open_printer(config: AppConfig):
    """
    Abre y retorna la conexión con la impresora
    según la configuración (network o usb).
    """
    if config.connection == "network":
        net     = config.network
        printer = Network(net.ip, port=net.port, timeout=10)
        printer.open()
        print(f"✓ Conectado por red a {net.ip}:{net.port}")

    else:
        usb     = config.usb
        printer = Usb(usb.vid, usb.pid)
        printer.open()
        print(f"✓ Conectado por USB VID={hex(usb.vid)} PID={hex(usb.pid)}")

    return printer