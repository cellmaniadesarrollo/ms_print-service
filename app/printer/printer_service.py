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


def _abbrev_name(first_name: str, last_name: str = "") -> str:
    """
    Inicial del primer nombre + primer apellido.
    Ignora segundos nombres y segundos apellidos.

    Casos soportados:
        ("CHRISTIAN MICHAEL", "SUAREZ PESANTEZ") → "C. SUAREZ"
        ("CHRISTIAN",         "SUAREZ PESANTEZ") → "C. SUAREZ"
        ("CHRISTIAN MICHAEL", "SUAREZ")          → "C. SUAREZ"
        ("CHRISTIAN",         "SUAREZ")          → "C. SUAREZ"
        ("MARIA CHRISTIAN",   "")                → "M. CHRISTIAN"  ← apellido vacío: usa 2º token del first_name
        ("TEAMCELLMANIA_admin","")               → "TEAMCELLMANIA_ADMIN"  ← sin espacios: sin cambio
    """
    fn_tokens = first_name.strip().upper().split()
    ln_tokens = last_name.strip().upper().split()

    if not fn_tokens:
        return last_name.strip().upper() or ""

    inicial = fn_tokens[0][0]

    if ln_tokens:
        # Caso normal: hay apellido → inicial + primer apellido
        return f"{inicial}. {ln_tokens[0]}"
    elif len(fn_tokens) > 1:
        # Sin apellido pero hay segundo nombre → inicial + segundo nombre
        # (ej. "MARIA CHRISTIAN" que llega todo en first_name)
        return f"{inicial}. {fn_tokens[1]}"
    else:
        # Solo un token sin apellido → username sin espacios, devolver tal cual
        return fn_tokens[0]


def _abbrev_tech(first_name: str, last_name: str) -> str:
    """
    Solo iniciales para técnicos: C. S.

        ("Andrés Santiago", "Vásquez Cedeño") → "A. V."
        ("Diego Armando",   "Molina Espinoza") → "D. M."
    """
    fn = first_name.strip().upper()
    ln = last_name.strip().upper()
    if not fn or not ln:
        return _abbrev_name(first_name, last_name)  # fallback al helper general
    return f"{fn[0]}. {ln[0]}."


def _extract(data: dict, qr_base_url: str) -> tuple[dict | None, str | None]:
    """
    Transforma el payload crudo en un diccionario limpio y normalizado
    que ticket_builder puede usar directamente.
    """
    # Parseo de fecha de ingreso
    entry_date_raw = data.get("entry_date", "")
    try:
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
    model_info   = device.get("model") or {}
    device_model = (
        model_info.get("models_name") if isinstance(model_info, dict) else safe_str(model_info)
    )

    imeis     = device.get("imeis") or [{}]
    public_id = safe_str(data.get("public_id"))
    qr_url    = safe_str(data.get("qr_url"))
    if not qr_url and qr_base_url and public_id:
        qr_url = f"{qr_base_url.rstrip('/')}/{public_id}"
    order_type = (data.get("type") or {}).get("name", "").upper()

    # ── Técnicos asignados → solo iniciales (ej. "A. V.") ────────────────────
    technicians_abbrev: list[str] = [
        _abbrev_tech(
            safe_str(t.get("first_name")),
            safe_str(t.get("last_name")),
        )
        for t in (data.get("technicians") or [])
        if t.get("first_name") and t.get("last_name")
    ]

    return {
        # Orden / identificación
        "order_number":       safe_str(data.get("order_number")),
        "entry_dt":           entry_dt,
        "entry_date_str":     entry_dt.strftime("%d/%m/%Y %H:%M"),
        "public_id":          public_id,
        "qr_url":             qr_url,

        # Empresa
        "company_name":       company.get("name", "").strip().upper(),
        "branch_name":        branch.get("name", "").strip().upper(),

        # Cliente
        "customer_name":      (
            f"{safe_str(customer.get('firstName'))} "
            f"{safe_str(customer.get('lastName'))}"
        ).strip().upper(),
        "customer_ci":        safe_str(customer.get("idNumber")),
        "mobile_phones":      [
            safe_str(c.get("value"))
            for c in contacts
            if c.get("typeName") == "MÓVIL" and c.get("value")
        ],

        # Equipo
        "device_model":       device_model,
        "imei":               safe_str(imeis[0].get("imei_number") if imeis else ""),

        # Detalles del ingreso
        "motivo":             safe_str(data.get("detalleIngreso")).upper(),
        "patron":             safe_str(data.get("patron")),
        "password":           safe_str(data.get("password")),

        # Quién recibió (abreviado) + técnicos asignados
        "received_by":        _abbrev_name(
                                  safe_str(created_by.get("first_name")),
                                  safe_str(created_by.get("last_name")),
                              ),
        "received_phone":     safe_str(created_by.get("phone")),
        "technicians_abbrev": technicians_abbrev,

        "order_type":         order_type,
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
        # ── 1. Validación rápida ─────────────────────────────────────────────
        error = _validate(data)
        if error:
            return {"success": False, "message": error}

        # ── 2. Extracción y normalización ────────────────────────────────────
        extracted, error = _extract(data, self.config.ticket.qr_base_url)
        if error:
            return {"success": False, "message": error}

        # ── 3. Impresión real ────────────────────────────────────────────────
        printer = None
        try:
            printer = open_printer(self.config)

            printer._raw(b'\x1B\x21\x01')  # Negrita + doble altura
            printer._raw(b'\x0F')          # Modo condensado

            print_customer_ticket(printer, extracted, self.config)
            print_workshop_ticket(printer, extracted, self.config)

            printer._raw(b'\x12')          # Cancelar condensado
            printer._raw(b'\x1B\x21\x00')  # Resetear formato

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