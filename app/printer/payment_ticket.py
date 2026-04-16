# app/printer/payment_ticket.py
"""
Imprime el comprobante de abono/adelanto en la impresora térmica.

Función pública:
    print_payment_ticket(printer, data, config) -> None

`data` es el dict ya extraído/normalizado que produce _extract_payment().
No recibe el JSON crudo; eso lo hace printer_service antes de llamar aquí.
"""

from __future__ import annotations

from datetime import timezone

from app.config import AppConfig
from app.printer.image_builder import build_company_name_image, build_footer_image
from app.printer.schemas import PaymentTicketRequest


# ─────────────────────────────────────────────────────────────────────────────
# Extracción y normalización
# ─────────────────────────────────────────────────────────────────────────────

def _extract_payment(req: PaymentTicketRequest) -> dict:
    """
    Transforma el modelo Pydantic en un dict plano listo para imprimir.
    Toda la lógica de formato de fechas/strings vive aquí.
    """
    # Convertir fechas UTC → local naive para mostrar
    def _fmt_dt(dt) -> str:
        """'2026-04-15T22:20:55Z' → '15/04/2026  22:20'"""
        if dt is None:
            return ""
        # Si tiene timezone, convertir a local naive
        if dt.tzinfo is not None:
            dt = dt.astimezone().replace(tzinfo=None)
        return dt.strftime("%d/%m/%Y  %H:%M")

    order = req.order
    received = req.receivedBy

    return {
        # Cabecera
        "company_name":   order.company.name,

        # Orden
        "order_number":   order.order_number,
        "entry_date_str": _fmt_dt(order.entry_date),
        "status_name":    order.currentStatus.name,

        # === DISPOSITIVO (MARCA + MODELO) ===
        "device": (
            f"{order.device.model.brand.brands_name} {order.device.model.models_name}"
            if order.device and order.device.model and order.device.model.brand
            else "Sin dispositivo"
        ), 

        # Pago
        "paid_at_str":    _fmt_dt(req.paid_at),
        "amount":         f"${float(req.amount):,.2f}",
        "payment_type":   req.paymentType.name,
        "payment_method": req.paymentMethod.name,
        "reference":      req.reference or "",
        "observation":    req.observation or "",
        "flow_type":      req.flow_type,

        # Recibido por
        "received_by":    f"{received.first_name} {received.last_name}",
        "received_phone": received.phone or "",

        # Cliente
        "customer": f"{order.customer.firstName} {order.customer.lastName}",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Impresión
# ─────────────────────────────────────────────────────────────────────────────

def print_payment_ticket(printer, req: PaymentTicketRequest, config: AppConfig) -> None:
    """
    Imprime un comprobante de abono/adelanto.

    Diseño solicitado:
        [Imagen del nombre de empresa CENTRADA]
        ── COMPROBANTE DE ABONO ──
        Cliente: ...
        Orden No. ...
        Dispositivo: ...
        Fecha ingreso: ...    Fecha pago: ...
        ────────────────────────────────
        MONTO destacado
        Método de pago
        ────────────────────────────────
        Recibido por: ...
        Observación (si existe)
        [Corte]
    """
    data = _extract_payment(req)
    
    # Usamos guiones normales "-" (más compatibles con todas las impresoras térmicas)
    # en vez del carácter Unicode "─" que a veces no se imprime correctamente.
    sep  = "-" * 42   # más largo para que se vea mejor como separador

    layout  = config.ticket.layout
    total_width = layout.total_width_override or config.paper_px

    # ── Cabecera: nombre de empresa (imagen centrada) ───────────────────────
    company_img = build_company_name_image(data["company_name"], total_width, font_size=72)
    printer.image(company_img, center=True)   # ya estaba centrada, pero lo confirmamos
    printer.text("\n")

    # ── Título del comprobante ───────────────────────────────────────────────
    printer.set(align="center", bold=True, font="b", width=1, height=1)
    printer.text("COMPROBANTE DE ABONO\n")
    printer.text(f"Cliente: {data['customer']}\n")

    # ── Datos de la orden ────────────────────────────────────────────────────
    printer.set(align="center", bold=False, font="b", width=1, height=1)
    printer.text(f"Orden No. {data['order_number']}\n")
    printer.text(f"Dispositivo: {data['device']}\n")
    printer.text(f"Fecha ingreso: {data['entry_date_str']}\n")
    printer.text(f"Fecha pago:    {data['paid_at_str']}\n")
    printer.text(f"{sep}\n")

    # ── Monto (destacado) ────────────────────────────────────────────────────
    printer.set(align="center", bold=True, font="a", width=2, height=2)
    printer.text(f"{data['amount']}\n")
    printer.set(align="center", bold=False, font="b", width=1, height=1)
    printer.text(f"{data['payment_method']}\n")
    printer.text(f"{sep}\n")

    # ── Recibido por ─────────────────────────────────────────────────────────
    printer.set(align="left", bold=False, font="b", width=1, height=1)
    line = f"Recibido por: {data['received_by']}"
    if data["received_phone"]:
        line += f"  {data['received_phone']}"
    printer.text(line + "\n")

    # ── Observación (opcional) ───────────────────────────────────────────────
    if data["observation"]:
        printer.set(align="left", bold=False, font="b", width=1, height=1)
        obs = data["observation"]
        for i in range(0, len(obs), 54):
            printer.text(obs[i : i + 54] + "\n")

    # ── Corte ────────────────────────────────────────────────────────────────
    printer.cut()