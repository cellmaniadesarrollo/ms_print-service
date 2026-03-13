"""
Construye y envía los comandos ESC/POS a la impresora.

Se generan dos tickets por orden:
    1. print_customer_ticket()  → copia para el CLIENTE
    2. print_workshop_ticket()  → copia interna para el TALLER
"""

from pathlib import Path
from PIL import Image
import qrcode

from app.config import AppConfig
from app.printer.image_builder import (
    build_pattern_image,
    build_side_by_side,
    build_footer_image,
    build_company_name_image,
)


def _assets_path() -> Path:
    return Path(__file__).parent.parent.parent / "assets"


def _build_qr_image(url: str) -> Image.Image:
    """
    Genera una imagen PIL del QR lista para pasarla a build_side_by_side.
    Devuelve una imagen en modo RGB.
    """
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=8,
        border=1,
    )
    qr.add_data(url)
    qr.make(fit=True)
    return qr.make_image(fill_color="black", back_color="white").convert("RGB")


# ─────────────────────────────────────────────────────────────────────────────
# Ticket 1 de 2 — copia del CLIENTE
# ─────────────────────────────────────────────────────────────────────────────

def print_customer_ticket(printer, data: dict, config: AppConfig) -> None:
    feat   = config.features
    ticket = config.ticket
    layout = config.ticket.layout
    total_width = layout.total_width_override or config.paper_px

    company_img = build_company_name_image(data['company_name'], total_width, font_size=72)
    printer.image(company_img, center=True)
    printer.text("\n")

    if feat.print_wednesday_promo and data['entry_dt'].weekday() == 2 and ticket.wednesday_promo:
        printer.set(align="center", bold=False, font='b', width=1, height=1)
        printer.text(f"{ticket.wednesday_promo}\n")

    printer.set(align="center", bold=True, font='b', width=1, height=1)
    printer.text(f"{data['entry_date_str']} | No. {data['order_number']}\n\n")

    printer.set(align="left", bold=False, font='b', width=1, height=1)
    if data['customer_name']:
        printer.text(f"{'Cliente:':<14}{data['customer_name'][:45]}\n")
    if data['customer_ci']:
        printer.text(f"{'C.I.:':<14}{data['customer_ci']}\n")
    # ── Teléfono eliminado del ticket cliente ──
    if data['device_model']:
        printer.text(f"{'Dispositivo:':<14}{data['device_model'][:45]}\n")
    if data['imei']:
        printer.text(f"{'IMEI:':<14}{data['imei']}\n")
    printer.text("\n")

    if data['motivo']:
        printer.text("Motivo de ingreso:\n")
        for i in range(0, len(data['motivo']), 64):
            printer.text(data['motivo'][i:i+64] + "\n")
        printer.text("\n")

    if data['received_by']:
        printer.set(align="center", font='b', width=1, height=1, bold=False)
        line = f"Recibido por: {data['received_by']}"
        if data['received_phone']:
            line += f" - {data['received_phone']}"
        printer.text(line + "\n\n")

    # QR — el cliente sí necesita la explicación
    if feat.print_qr and data['qr_url']:
        printer.set(align="center", font='b', width=1, height=1, bold=False)
        printer.text("Escanee el codigo QR para ver el estado.\n")
        printer.qr(data['qr_url'], size=3)

    printer.set(align="left")
    footer_img = build_footer_image(ticket.footer_lines, config.paper_px, width_scale=1.2)
    printer.image(footer_img, center=False)
    printer.text("\n")

    printer.cut()


# ─────────────────────────────────────────────────────────────────────────────
# Ticket 2 de 2 — copia interna del TALLER
# ─────────────────────────────────────────────────────────────────────────────

def print_workshop_ticket(printer, data: dict, config: AppConfig) -> None:
    feat   = config.features
    layout = config.ticket.layout
    total_width = layout.total_width_override or config.paper_px

    printer.set(align="center", bold=False, font='b', width=1, height=1)
    printer.text(f"{data['entry_date_str']} | No: {data['order_number']}\n")

    text_lines = []
    if data['customer_name']:
        text_lines.append(f"Cliente: {data['customer_name']}")
    # ── Todos los números MÓVIL del cliente ──
    for phone in data['mobile_phones']:
        text_lines.append(f"Movil: {phone}")
    if data['device_model']:
        text_lines.append(f"Equipo: {data['device_model'][:28]}")
    if data['imei']:
        text_lines.append(f"IMEI: {data['imei']}")
    if data['password']:
        text_lines.append(f"Pass: {data['password']}")
    if data['patron']:
        text_lines.append(f"Patron: {data['patron']}")
    if data['received_by']:
        text_lines.append(f"Recibe: {data['received_by']}")

    has_patron = bool(data['patron'])

    if has_patron:
        # Columna derecha = dibujo del patrón
        right_img = build_pattern_image(data['patron'])
    elif feat.print_qr and data['qr_url']:
        # Columna derecha = imagen QR (misma posición que el patrón)
        right_img = _build_qr_image(data['qr_url'])
    else:
        right_img = None

    combined = build_side_by_side(
        pattern_img=right_img,
        text_lines=text_lines,
        total_width=total_width,
        text_pct=layout.text_pct if has_patron else 75,
    )
    printer.set(align="left")
    printer.image(combined, center=False)
    printer.text("\n")

    if data['motivo']:
        printer.set(align="left", bold=False, font='b', width=1, height=1)
        printer.text("Motivo de ingreso:\n")
        for i in range(0, len(data['motivo']), 64):
            printer.text(data['motivo'][i:i+64] + "\n")
        printer.text("\n")

    # QR cuando SÍ había patrón — ya se mostró el QR en la columna derecha
    # cuando no había patrón, así que aquí solo aplica al caso con patrón.
    # Sin texto explicativo — los técnicos lo saben.
    if has_patron and feat.print_qr and data['qr_url']:
        printer.set(align="center", font='b', width=1, height=1, bold=False)
        printer.qr(data['qr_url'], size=3)
        printer.text("\n")

    printer.cut()