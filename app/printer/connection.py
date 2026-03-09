import usb.core
import usb.util
import usb.backend.libusb1

try:
    import libusb_package
    _BACKEND = usb.backend.libusb1.get_backend(
        find_library=libusb_package.find_library
    )
except ImportError:
    _BACKEND = None

from escpos.printer import Network, Usb
from app.config import AppConfig


def _has_printer_interface(device: usb.core.Device) -> bool:
    """Verifica si es una impresora (clase oficial o vendor-specific)."""
    if device is None:
        return False
    try:
        for cfg in device:
            for intf in cfg:
                if intf.bInterfaceClass in {0x07, 0xFF}:  # Printer o Vendor-specific
                    return True
    except:
        pass
    return False


def _has_bulk_out_endpoint(device: usb.core.Device) -> bool:
    """Fallback: busca cualquier endpoint OUT bulk (muy común en térmicas chinas)."""
    try:
        for cfg in device:
            for intf in cfg:
                for ep in intf:
                    if (usb.util.endpoint_type(ep.bmAttributes) == usb.util.ENDPOINT_TYPE_BULK and
                            usb.util.endpoint_direction(ep.bEndpointAddress) == usb.util.ENDPOINT_OUT):
                        return True
    except:
        pass
    return False


def _find_usb_printer() -> usb.core.Device:
    """Auto-detecta la primera impresora USB conectada."""
    # 1. Buscar por clase de impresora (la forma más limpia)
    for device in usb.core.find(find_all=True, backend=_BACKEND):
        if _has_printer_interface(device):
            print(f"[USB] Impresora detectada por clase → VID={hex(device.idVendor)} PID={hex(device.idProduct)}")
            return device

    # 2. Fallback: cualquier dispositivo con endpoint OUT bulk
    for device in usb.core.find(find_all=True, backend=_BACKEND):
        if _has_bulk_out_endpoint(device):
            print(f"[USB] Impresora detectada por fallback (bulk OUT) → VID={hex(device.idVendor)} PID={hex(device.idProduct)}")
            return device

    raise RuntimeError("No se encontró ninguna impresora USB conectada. Conecta la impresora y reinicia el servicio.")


def _find_usb_endpoints(vid: int, pid: int) -> tuple[int, int]:
    """Detecta automáticamente los endpoints OUT e IN correctos."""
    device = usb.core.find(idVendor=vid, idProduct=pid, backend=_BACKEND)
    if device is None:
        raise RuntimeError(f"Impresora USB no encontrada VID={hex(vid)} PID={hex(pid)}")

    out_ep = None
    in_ep = None

    for config in device:
        for intf in config:
            for ep in intf:
                addr = ep.bEndpointAddress
                direction = usb.util.endpoint_direction(addr)
                if direction == usb.util.ENDPOINT_OUT and out_ep is None:
                    out_ep = addr
                if direction == usb.util.ENDPOINT_IN and in_ep is None:
                    in_ep = addr

    if out_ep is None:
        raise RuntimeError("No se encontró endpoint OUT en la impresora USB")

    print(f"[USB] Endpoints detectados → OUT={hex(out_ep)} IN={hex(in_ep) if in_ep else 'N/A'}")
    return out_ep, in_ep


def open_printer(config: AppConfig):
    """Abre la conexión (network o USB con auto-detección)."""
    if config.connection == "network":
        net = config.network
        printer = Network(net.ip, port=net.port, timeout=10)
        printer.open()
        print(f"✓ Conectado por red a {net.ip}:{net.port}")
        return printer

    # ==================== MODO USB (con o sin VID/PID) ====================
    usb_cfg = getattr(config, "usb", None)
    if usb_cfg and getattr(usb_cfg, "vid", 0) > 0 and getattr(usb_cfg, "pid", 0) > 0:
        vid = usb_cfg.vid
        pid = usb_cfg.pid
        print(f"[USB] Usando VID/PID del config → {hex(vid)} / {hex(pid)}")
    else:
        # AUTO-DETECCIÓN (cuando borras la sección "usb" del JSON)
        device = _find_usb_printer()
        vid = device.idVendor
        pid = device.idProduct

    out_ep, in_ep = _find_usb_endpoints(vid, pid)

    printer = Usb(
        vid,
        pid,
        out_ep=out_ep,
        in_ep=in_ep,
        backend=_BACKEND,
    )
    printer.open()
    print(f"✓ Conectado por USB VID={hex(vid)} PID={hex(pid)}")
    return printer