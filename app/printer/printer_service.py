# app/printer/printer_service.py
"""
Orquestador del servicio de impresión.

Responsabilidades (en orden de ejecución):
    1. Validar campos mínimos del payload
    2. Extraer y normalizar los datos del JSON
    3. Abrir conexión con la impresora
    4. Imprimir ticket cliente + ticket taller
    5. Manejar errores y retornar respuesta

Flujo completo:
    POST /print
        → PrinterService.print_receipt(data)
            → _validate(data)           devuelve error o None
            → _extract(data)            devuelve dict normalizado o error
            → open_printer(config)      abre la conexión
            → print_customer_ticket()   ticket del cliente
            → print_workshop_ticket()   ticket del taller
"""

from datetime import datetime

from app.config import AppConfig
from app.printer.connection import open_printer
from app.printer.ticket_builder import print_customer_ticket, print_workshop_ticket

from escpos.exceptions import Error, DeviceNotFoundError


# ─────────────────────────────────────────────────────────────────────────────
# Campos obligatorios en el payload
# ─────────────────────────────────────────────────────────────────────────────

REQUIRED_FIELDS = ["order_number", "entry_date", "customer", "device", "public_id"]


def _validate(data: dict) -> str | None:
    """
    Verifica que el payload tenga los campos mínimos para imprimir.

    Returns:
        str  con mensaje de error si algo falta
        None si todo está bien
    """
    if not data:
        return "No se recibieron datos para imprimir."

    missing = [f for f in REQUIRED_FIELDS if not data.get(f)]
    if missing:
        return f"Faltan campos obligatorios: {', '.join(missing)}"

    if not (data.get("company") or {}).get("name", "").strip():
        return "Falta company.name en los datos."

    return None


def _extract(data: dict, qr_base_url: str) -> tuple[dict | None, str | None]:
    """
    Extrae y normaliza los campos del payload JSON.

    Centraliza la transformación del JSON crudo a un dict limpio
    que ticket_builder.py puede usar directamente sin conocer
    la estructura original del payload.

    Args:
        data:         payload JSON crudo del endpoint
        qr_base_url:  URL base para construir el link del QR
                      (viene de config.json → ticket.qrBaseUrl)

    Returns:
        (dict_normalizado, None)  si todo fue bien
        (None, mensaje_error)     si hubo un error
    """
    entry_date_raw = data["entry_date"]
    try:
        entry_dt = datetime.fromisoformat(entry_date_raw.replace("Z", "+00:00"))
    except Exception:
        return None, f"entry_date con formato inválido: '{entry_date_raw}'"

    company    = data.get("company")   or {}
    customer   = data.get("customer")  or {}
    device     = data.get("device")    or {}
    created_by = data.get("createdBy") or {}
    contacts   = customer.get("contacts") or []

    # Modelo del dispositivo puede llegar como objeto o como string
    model_info   = device.get("model") or {}
    device_model = (
        model_info.get("models_name") if isinstance(model_info, dict) else str(model_info)
    ).strip()

    imeis      = device.get("imeis") or [{}]
    order_num  = data["order_number"]
    public_id = (data.get("public_id") or "").strip()
    # Construir URL del QR: usa qr_url del payload si viene, si no construye con base
    qr_url = (data.get("qr_url") or "").strip()
    if not qr_url and qr_base_url:
        qr_url = f"{qr_base_url}/{public_id}"

    return {
        # Orden
        "order_number":   order_num,
        "entry_dt":       entry_dt,
        "entry_date_str": entry_dt.strftime("%d/%m/%Y %H:%M"),
        "public_id": public_id,
        # Empresa
        "company_name":  company.get("name", "").strip().upper(),

        # Cliente
        "customer_name": (
            f"{customer.get('firstName','').strip()} "
            f"{customer.get('lastName','').strip()}"
        ).strip().upper(),
        "customer_ci":   customer.get("idNumber", ""),
        "primary_phone": next(
            (c.get("value") for c in contacts if c.get("isPrimary")), ""
        ),

        # Dispositivo
        "device_model": device_model,
        "imei":         imeis[0].get("imei_number", ""),

        # Detalles
        "motivo":   (data.get("detalleIngreso") or "").strip().upper(),
        "patron": (data.get("patron") or "").strip(),
        "password": data.get("password", "").strip(),
        "qr_url":   qr_url,

        # Técnico
        "received_by":    created_by.get("first_name", "").strip(),
        "received_phone": created_by.get("phone",       "").strip(),
    }, None


# ─────────────────────────────────────────────────────────────────────────────
# Servicio principal
# ─────────────────────────────────────────────────────────────────────────────

class PrinterService:
    """
    Orquesta el proceso completo de impresión.

    Se instancia una sola vez al arrancar la app (singleton en main.py),
    recibiendo AppConfig como dependencia (inyección de dependencias).

    Uso en main.py:
        config          = load_config()
        printer_service = PrinterService(config)
    """

    def __init__(self, config: AppConfig):
        self.config = config

    def print_receipt(self, data: dict) -> dict:
        """
        Punto de entrada público. Valida, extrae e imprime.

        Args:
            data: payload JSON del endpoint POST /print

        Returns:
            {"success": True,  "message": "..."}
            {"success": False, "message": "..."}
        """
        # 1. Validar campos obligatorios
        error = _validate(data)
        if error:
            return {"success": False, "message": error}

        # 2. Extraer y normalizar — pasamos qr_base_url desde config
        extracted, error = _extract(data, self.config.ticket.qr_base_url)
        if error:
            return {"success": False, "message": error}

        # 3. Conectar e imprimir
        printer = None
        try:
            printer = open_printer(self.config)

            printer._raw(b'\x1B\x21\x01')   # modo condensado ON
            printer._raw(b'\x0F')

            # Ambos tickets reciben el config completo
            print_customer_ticket(printer, extracted, self.config)
            print_workshop_ticket(printer, extracted, self.config)

            printer._raw(b'\x12')            # modo condensado OFF
            printer._raw(b'\x1B\x21\x00')

            printer.close()
            print("✓ Impresion completada")
            return {"success": True, "message": "Ticket impreso con exito"}

        except (DeviceNotFoundError, Error) as e:
            print(f"✗ Error de impresora: {e}")
            return {"success": False, "message": str(e)}

        except Exception as e:
            import traceback
            traceback.print_exc()
            return {"success": False, "message": str(e)}

        finally:
            if printer:
                try:
                    printer.close()
                except Exception:
                    pass