# app/printer/printer_service.py
"""
Orquestador del servicio de impresión de tickets.

Flujo principal:
    1. Validar campos mínimos del payload
    2. Normalizar y extraer datos útiles
    3. Conectar con la impresora
    4. Imprimir ticket cliente + ticket taller / pagos / facturas
    5. Manejar errores y retornar respuesta estandarizada
"""

from datetime import datetime, timezone, timedelta
import traceback

from app.config import AppConfig
from app.printer.connection import open_printer
from app.printer.ticket_builder import print_customer_ticket, print_workshop_ticket
from app.printer.payment_ticket import print_payment_ticket
from app.printer.schemas import PaymentTicketRequest

# Importaciones para facturas/recibos
from app.printer.invoice_ticket import print_invoice_ticket
from app.printer.formatters.factura_formatter import formatear_factura_o_recibo
from app.printer.models.factura import FacturaPrintRequest

from escpos.exceptions import Error as EscposError, DeviceNotFoundError

TZ_EC = timezone(timedelta(hours=-5))

# Campos strictly necesarios en el payload de órdenes de servicio
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
    """Nombre (primer token) completo + Inicial del primer apellido."""
    fn_tokens = first_name.strip().upper().split()
    ln_tokens = last_name.strip().upper().split()

    if not fn_tokens:
        if ln_tokens:
            return f"{ln_tokens[0][0]}."
        return ""

    primer_nombre = fn_tokens[0]

    if ln_tokens:
        inicial_apellido = ln_tokens[0][0]
        return f"{primer_nombre} {inicial_apellido}."
    else:
        if len(fn_tokens) > 1:
            return f"{fn_tokens[0]} {fn_tokens[1][0]}."
        else:
            return primer_nombre


def _abbrev_tech(first_name: str, last_name: str) -> str:
    """Solo iniciales para técnicos: C. S."""
    fn = first_name.strip().upper()
    ln = last_name.strip().upper()
    if not fn or not ln:
        return _abbrev_name(first_name, last_name)
    return f"{fn[0]}. {ln[0]}."


def _extract(data: dict, qr_base_url: str) -> tuple[dict | None, str | None]:
    """Transforma el payload crudo en un diccionario limpio y normalizado."""
    entry_date_raw = data.get("entry_date", "")
    try:
        entry_dt_utc = datetime.fromisoformat(entry_date_raw.replace("Z", "+00:00"))
        entry_dt = entry_dt_utc.astimezone(TZ_EC)
    except (ValueError, TypeError) as e:
        return None, f"Formato inválido en entry_date: '{entry_date_raw}' → {e}"

    company    = data.get("company")    or {}
    customer   = data.get("customer")   or {}
    device     = data.get("device")     or {}
    branch     = data.get("branch")     or {}
    created_by = data.get("createdBy")  or {}
    contacts   = customer.get("contacts") or []

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

    technicians_abbrev: list[str] = [
        _abbrev_tech(
            safe_str(t.get("first_name")),
            safe_str(t.get("last_name")),
        )
        for t in (data.get("technicians") or [])
        if t.get("first_name") and t.get("last_name")
    ]
    is_copy = bool(data.get("is_copy", False))

    return {
        "order_number":       safe_str(data.get("order_number")),
        "entry_dt":           entry_dt,
        "entry_date_str":     entry_dt.strftime("%d/%m/%Y %H:%M"),
        "public_id":          public_id,
        "qr_url":             qr_url,
        "company_name":       company.get("name", "").strip().upper(),
        "branch_name":        branch.get("name", "").strip().upper(),
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
        "device_model":       device_model,
        "device_type":        safe_str((device.get("type") or {}).get("name")).upper(),
        "imei":               safe_str(imeis[0].get("imei_number") if imeis else ""),
        "observations":       safe_str(device.get("observations")).upper() or None,     
        "motivo":             safe_str(data.get("detalleIngreso")).upper(),
        "patron":             safe_str(data.get("patron")),
        "password":           safe_str(data.get("password")),
        "received_by":        _abbrev_name(
                                  safe_str(created_by.get("first_name")),
                                  safe_str(created_by.get("last_name")),
                              ),
        "received_phone":     safe_str(created_by.get("phone")),
        "technicians_abbrev": technicians_abbrev,
        "is_copy":            is_copy,
        "printed_by":         safe_str(data.get("printed_by")) if is_copy else "",
        "requested_by":       safe_str(data.get("requested_by")) if is_copy else "",
        "copy_printed_at":    datetime.now(TZ_EC).strftime("%d/%m/%Y %H:%M") if is_copy else "",
        "order_type":         order_type,
    }, None

    def generate_invoice_preview(self, invoice_data: dict) -> dict:
        """
        Genera una vista previa en imagen (PNG Base64) de la factura
        sin enviarla a la impresora física.
        """
        try:
            # 1. Llama a tu método interno que genera el lienzo / PIL.Image de la factura
            # Nota: Reemplaza '_render_invoice_image' por el nombre de tu método real de dibujado
            if hasattr(self, "_render_invoice_image"):
                img: Image.Image = self._render_invoice_image(invoice_data)
            else:
                # Si tu print_invoice llama a un renderer, úsalo aquí. 
                # Ejemplo de fallback usando la lógica de dibujado:
                img = self.invoice_renderer.render(invoice_data)

            # 2. Convertir la imagen PIL a Base64 (PNG)
            buffer = io.BytesIO()
            img.save(buffer, format="PNG")
            img_str = base64.b64encode(buffer.getvalue()).decode("utf-8")

            return {
                "success": True,
                "mime_type": "image/png",
                "image_base64": f"data:image/png;base64,{img_str}"
            }

        except Exception as e:
            return {
                "success": False,
                "message": f"Error al generar la vista previa: {str(e)}"
            }


class PrinterService:
    """
    Servicio que orquesta la impresión de tickets.
    Se instancia una vez al iniciar la aplicación.
    """

    def __init__(self, config: AppConfig):
        self.config = config

    def print_receipt(self, data: dict) -> dict:
        """Imprime ticket de orden de servicio (cliente / taller)."""
        error = _validate(data)
        if error:
            return {"success": False, "message": error}

        extracted, error = _extract(data, self.config.ticket.qr_base_url)
        if error:
            return {"success": False, "message": error}

        ticket_type = (data.get("ticket_type") or "both").lower()
        if ticket_type not in ("customer", "workshop", "both"):
            ticket_type = "both"

        printer = None
        try:
            printer = open_printer(self.config)

            printer._raw(b'\x1B\x21\x01')
            printer._raw(b'\x0F')

            if ticket_type in ("customer", "both"):
                print_customer_ticket(printer, extracted, self.config)
            if ticket_type in ("workshop", "both"):
                print_workshop_ticket(printer, extracted, self.config)

            printer._raw(b'\x12')
            printer._raw(b'\x1B\x21\x00')

            print(f"✓ Impresión REAL completada ({ticket_type})")
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
        """Imprime un comprobante de abono/adelanto."""
        try:
            req = PaymentTicketRequest(**data)
        except Exception as e:
            return {"success": False, "message": f"Datos de pago inválidos: {e}"}

        copies = req.copies if req.copies and req.copies > 0 else 2
        copies = max(1, min(copies, 5))

        printer = None
        try:
            printer = open_printer(self.config)

            printer._raw(b'\x1B\x21\x01')
            printer._raw(b'\x0F')

            for _ in range(copies):
                print_payment_ticket(printer, req, self.config)

            printer._raw(b'\x12')
            printer._raw(b'\x1B\x21\x00')

            print(f"✓ Comprobante de abono impreso ({copies}x)")
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

    def print_invoice(self, data: dict) -> dict:
        """
        Imprime una Factura o Recibo fiscal a partir de un dict o FacturaPrintRequest.
        """
        try:
            # Si se pasa un dict, se valida y parsea al modelo Pydantic
            req = data if isinstance(data, FacturaPrintRequest) else FacturaPrintRequest(**data)
        except Exception as e:
            return {"success": False, "message": f"Datos de factura inválidos: {e}"}

        printer = None
        try:
            # 1. Generar comandos de escape de la factura
            raw_bytes = formatear_factura_o_recibo(req)

            # 2. Abrir la impresora e imbinar el búfer
            printer = open_printer(self.config)

            # Modo condensado inicial opcional
            printer._raw(b'\x1B\x21\x01')
            printer._raw(b'\x0F')

            # Enviar el stream de bytes generado por Dummy()
            printer._raw(raw_bytes)

            # Restaurar fuente original
            printer._raw(b'\x12')
            printer._raw(b'\x1B\x21\x00')

            num_doc = req.numero_factura or ""
            print(f"✓ Factura/Recibo {num_doc} impreso con éxito")
            return {"success": True, "message": "Factura/Recibo impreso con éxito"}

        except (DeviceNotFoundError, EscposError) as e:
            msg = f"No se pudo conectar con la impresora: {e}"
            print(f"✗ {msg}")
            return {"success": False, "message": msg}

        except Exception as e:
            traceback.print_exc()
            msg = f"Error inesperado al imprimir factura: {str(e)}"
            print(f"✗ {msg}")
            return {"success": False, "message": msg}

        finally:
            if printer is not None:
                try:
                    printer.close()
                except Exception:
                    pass