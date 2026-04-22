# app/printer/printer_service.py
"""
Orquestador del servicio de impresión de tickets.

Flujo principal:
    1. Validar campos mínimos del payload
    2. Normalizar y extraer datos útiles
    3. Conectar con la impresora
    4. Imprimir ticket cliente + ticket taller
    5. Manejar errores y retornar respuesta estandarizada

Uso típico (en endpoint):
    printer_service.print_receipt(payload_json) → {"success": bool, "message": str}
"""

from datetime import datetime, timezone, timedelta
import traceback

from app.config import AppConfig
from app.printer.connection import open_printer
from app.printer.ticket_builder import print_customer_ticket, print_workshop_ticket

from app.printer.payment_ticket import print_payment_ticket
from app.printer.schemas import PaymentTicketRequest 

from escpos.exceptions import Error as EscposError, DeviceNotFoundError

TZ_EC = timezone(timedelta(hours=-5))
# Campos estrictamente necesarios en el payload
REQUIRED_FIELDS = [
    "order_number",
    "entry_date",
    "customer",     
    "public_id",
]


def safe_str(value: any) -> str:
    """Convierte a string, quita espacios sobrantes y maneja None"""
    return str(value or "").strip()


def _validate(data: dict) -> str | None:
    """
    Verifica que el payload tenga la estructura mínima esperada.
    Retorna mensaje de error o None si está correcto.
    """
    if not data or not isinstance(data, dict):
        return "No se recibieron datos válidos para imprimir."

    missing = [f for f in REQUIRED_FIELDS if f not in data or not data[f]]
    if missing:
        return f"Faltan campos obligatorios: {', '.join(missing)}"

    company_name = safe_str((data.get("company") or {}).get("name"))
    if not company_name:
        return "Falta o está vacío: company.name"

    return None


def _extract(data: dict, qr_base_url: str) -> tuple[dict | None, str | None]:
    """
    Transforma el payload crudo en un diccionario limpio y normalizado
    que ticket_builder puede usar directamente.
    """
    # Parseo de fecha de ingreso
    entry_date_raw = data.get("entry_date", "")
    try:
        # Soporta ISO con Z (UTC) → lo convertimos a objeto datetime
        entry_dt_utc = datetime.fromisoformat(entry_date_raw.replace("Z", "+00:00"))
        entry_dt = entry_dt_utc.astimezone(TZ_EC)
    except (ValueError, TypeError) as e:
        return None, f"Formato inválido en entry_date: '{entry_date_raw}' → {e}"

    # Accesos seguros a estructuras anidadas
    company    = data.get("company")    or {}
    customer   = data.get("customer")   or {}
    device     = data.get("device")     or {}
    branch     = data.get("branch")     or {}
    created_by = data.get("createdBy")  or {}
    contacts   = customer.get("contacts") or []

    # Modelo del equipo (puede venir como str o como dict)
    model_info = device.get("model") or {}
    device_model = (
        model_info.get("models_name") if isinstance(model_info, dict) else safe_str(model_info)
    )

    imeis = device.get("imeis") or [{}]

    public_id = safe_str(data.get("public_id"))
    qr_url = safe_str(data.get("qr_url"))
    if not qr_url and qr_base_url and public_id:
        qr_url = f"{qr_base_url.rstrip('/')}/{public_id}"
    order_type = (data.get("type") or {}).get("name", "").upper()
    # Construimos el diccionario final normalizado
    return {
        # Orden / identificación
        "order_number":   safe_str(data.get("order_number")),
        "entry_dt":       entry_dt,
        "entry_date_str": entry_dt.strftime("%d/%m/%Y %H:%M"),
        "public_id":      public_id,
        "qr_url":         qr_url,

        # Empresa
        "company_name":   company.get("name", "").strip().upper(),
        "branch_name":    branch.get("name", "").strip().upper(),

        # Cliente
        "customer_name":  (
            f"{safe_str(customer.get('firstName'))} "
            f"{safe_str(customer.get('lastName'))}"
        ).strip().upper(),
        "customer_ci":    safe_str(customer.get("idNumber")),
        # Todos los números MÓVIL del cliente (para el ticket de taller)
        "mobile_phones":  [
            safe_str(c.get("value"))
            for c in contacts
            if c.get("typeName") == "MÓVIL" and c.get("value")
        ],

        # Equipo
        "device_model":   device_model,
        "imei":           safe_str(imeis[0].get("imei_number") if imeis else ""),

        # Detalles del ingreso
        "motivo":         safe_str(data.get("detalleIngreso")).upper(),
        "patron":         safe_str(data.get("patron")),
        "password":       safe_str(data.get("password")),

        # Quién recibió
        "received_by":    safe_str(created_by.get("first_name")),
        "received_phone": safe_str(created_by.get("phone")),

        "order_type": order_type
    }, None


class PrinterService:
    """
    Servicio que orquesta la impresión de tickets.
    Se instancia una vez al iniciar la aplicación.
    """

    def __init__(self, config: AppConfig):
        self.config = config

    def print_receipt(self, data: dict) -> dict:
        """
        Punto de entrada principal para imprimir tickets.

        Returns:
            dict con formato:
            {"success": True,  "message": "Ticket impreso con éxito"}
            {"success": False, "message": "explicación del error"}
        """
        # ── 1. Validación rápida ────────────────────────────────────────
        error = _validate(data)
        if error:
            return {"success": False, "message": error}

        # ── 2. Extracción y normalización ───────────────────────────────
        extracted, error = _extract(data, self.config.ticket.qr_base_url)
        if error:
            return {"success": False, "message": error}

        # ── 3. Impresión real ───────────────────────────────────────────
        printer = None
        try:
            printer = open_printer(self.config)

            # Configuración inicial del modo de impresión
            printer._raw(b'\x1B\x21\x01')   # Negrita + doble altura (ajusta según ticket_builder)
            printer._raw(b'\x0F')           # Modo condensado (más caracteres por línea)

            print_customer_ticket(printer, extracted, self.config)
            print_workshop_ticket(printer, extracted, self.config)

            # Restaurar modo normal y cortar (si la impresora lo soporta)
            printer._raw(b'\x12')           # Cancelar condensado
            printer._raw(b'\x1B\x21\x00')   # Resetear formato

            #printer.cut()                   # Corte de papel (recomendado)

            print("✓ Impresión REAL completada")
            return {"success": True, "message": "Ticket impreso con éxito"}

        except (DeviceNotFoundError, EscposError) as e:
            msg = f"No se pudo conectar con la impresora: {e}"
            print(f"✗ {msg}")
            return {"success": False, "message": msg}

        except Exception as e:
            traceback.print_exc()
            msg = f"Error inesperado durante la impresión: {str(e)}"
            print(f"✗ {msg}")
            return {"success": False, "message": msg}

        finally:
            if printer is not None:
                try:
                    printer.close()
                except Exception:
                    pass


    def print_payment(self, data: dict) -> dict:
        """
        Imprime un comprobante de abono/adelanto.
 
        Valida el dict de entrada con Pydantic antes de tocar la impresora.
 
        Returns:
            {"success": True,  "message": "Comprobante impreso con éxito"}
            {"success": False, "message": "explicación del error"}
        """
        # ── 1. Validación con Pydantic ───────────────────────────────────────
        try:
            req = PaymentTicketRequest(**data)
        except Exception as e:
            return {"success": False, "message": f"Datos de pago inválidos: {e}"}
 
        # ── 2. Impresión ─────────────────────────────────────────────────────
        printer = None
        try:
            printer = open_printer(self.config)
 
            printer._raw(b'\x1B\x21\x01')  # Negrita + doble altura
            printer._raw(b'\x0F')          # Modo condensado
 
            print_payment_ticket(printer, req, self.config)
 
            printer._raw(b'\x12')          # Cancelar condensado
            printer._raw(b'\x1B\x21\x00')  # Resetear formato
 
            print("✓ Comprobante de abono impreso")
            return {"success": True, "message": "Comprobante impreso con éxito"}
 
        except (DeviceNotFoundError, EscposError) as e:
            msg = f"No se pudo conectar con la impresora: {e}"
            print(f"✗ {msg}")
            return {"success": False, "message": msg}
 
        except Exception as e:
            traceback.print_exc()
            msg = f"Error inesperado al imprimir comprobante: {str(e)}"
            print(f"✗ {msg}")
            return {"success": False, "message": msg}
 
        finally:
            if printer is not None:
                try:
                    printer.close()
                except Exception:
                    pass   