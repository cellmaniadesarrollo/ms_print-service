# app/printer/ticket_builder.py
"""
Construye y envía los comandos ESC/POS a la impresora.

Se generan dos tickets por orden:
    1. print_customer_ticket()  → copia para el CLIENTE
    2. print_workshop_ticket()  → copia interna para el TALLER

El comportamiento de cada sección se controla desde config.json
a través de los objetos TicketConfig y Features.
"""

from pathlib import Path
from PIL import Image

from app.config import AppConfig
from app.printer.image_builder import (
    build_pattern_image,
    build_side_by_side,
    build_footer_image,
)
from app.printer.image_builder import build_company_name_image

def _assets_path() -> Path:
    """Retorna la ruta a assets/ en la raíz del proyecto."""
    return Path(__file__).parent.parent.parent / "assets"


# ─────────────────────────────────────────────────────────────────────────────
# Ticket 1 de 2 — copia del CLIENTE
# ─────────────────────────────────────────────────────────────────────────────

def print_customer_ticket(printer, data: dict, config: AppConfig) -> None:
    """
    Imprime el ticket que se entrega al cliente.

    Secciones controladas por config.json → features:
        printWednesdayPromo          → promo del miércoles
        printAnalysisImage           → imagen assets/analisis.png
        printPatternOnCustomerTicket → patrón en texto
        printQr                      → código QR

    Args:
        printer: instancia escpos conectada
        data:    dict normalizado por _extract() en printer_service.py
        config:  AppConfig con features y ticket config
    """
    feat   = config.features
    ticket = config.ticket
    layout = config.ticket.layout
    total_width = layout.total_width_override or config.paper_px
    # Encabezado empresa
    company_img = build_company_name_image(data['company_name'], total_width  , font_size=72)
    printer.image(company_img, center=True )
    printer.text("\n")

    # Promo del miércoles (weekday 2 = miércoles)
    if feat.print_wednesday_promo and data['entry_dt'].weekday() == 2 and ticket.wednesday_promo:
        printer.set(align="center", bold=False, font='b', width=1, height=1)
        printer.text(f"{ticket.wednesday_promo}\n")

    # Fecha y número de orden
    printer.set(align="center", bold=True, font='b', width=1, height=1)
    printer.text(f"{data['entry_date_str']} | No. {data['order_number']}\n\n")

    # Datos del cliente y dispositivo (omite líneas vacías)
    printer.set(align="left", bold=False, font='b', width=1, height=1)
    if data['customer_name']:
        printer.text(f"{'Cliente:':<14}{data['customer_name'][:45]}\n")
    if data['customer_ci']:
        printer.text(f"{'C.I.:':<14}{data['customer_ci']}\n")
    if data['primary_phone']:
        printer.text(f"{'Telefono:':<14}{data['primary_phone']}\n")
    if data['device_model']:
        printer.text(f"{'Dispositivo:':<14}{data['device_model'][:45]}\n")
    if data['imei']:
        printer.text(f"{'IMEI:':<14}{data['imei']}\n")
    printer.text("\n")

    # Motivo de ingreso
    if data['motivo']:
        printer.text("Motivo de ingreso:\n")
        for i in range(0, len(data['motivo']), 64):
            printer.text(data['motivo'][i:i+64] + "\n")
        printer.text("\n")
 
    # Técnico que recibió el equipo
    if data['received_by']:
        printer.set(align="center", font='b', width=1, height=1, bold=False)
        line = f"Recibido por: {data['received_by']}"
        if data['received_phone']:
            line += f" - {data['received_phone']}"
        printer.text(line + "\n\n")

    # QR de seguimiento (feature flag: printQr)
    if feat.print_qr and data['qr_url']:
        printer.set(align="center", font='b', width=1, height=1, bold=False)
        printer.text("Escanee el codigo QR para ver el estado.\n")
        printer.qr(data['qr_url'], size=3)

    # Footer con términos (imagen para evitar problemas de encoding)
    printer.set(align="left")
    footer_img = build_footer_image(ticket.footer_lines, config.paper_px, width_scale=1.2)
    printer.image(footer_img, center=False)
    printer.text("\n")
 
    printer.cut()


# ─────────────────────────────────────────────────────────────────────────────
# Ticket 2 de 2 — copia interna del TALLER
# ─────────────────────────────────────────────────────────────────────────────

def print_workshop_ticket(printer, data: dict, config: AppConfig) -> None:
    """
    Imprime el ticket interno para el taller.

    Layout del bloque central (proporciones desde config.json):
        ┌──────────────────────────┬───────────┐
        │ Equipo: Samsung A54      │  [patrón] │
        │ IMEI:   123456789012345  │   3 × 3   │
        │ Pass:   1234             │   grid    │
        │ Recibe: Juan             │           │
        └──────────────────────────┴───────────┘
         ← textPct % →              ← resto →

    Ancho controlado por:
        config.json → ticket.workshopLayout.totalWidthOverride  (fijo en px)
        Si es null, usa paper_px calculado desde paperWidth.

    Proporción texto/patrón:
        config.json → ticket.workshopLayout.textPct  (default 80)

    Args:
        printer: instancia escpos conectada
        data:    dict normalizado por _extract() en printer_service.py
        config:  AppConfig con layout y features
    """
    layout = config.ticket.layout
    total_width = layout.total_width_override or config.paper_px
    # Encabezado empresa
    company_img = build_company_name_image(data['company_name'], total_width , font_size=72)
    printer.image(company_img, center=True)
    printer.text("\n")

    # Fecha y número de orden
    printer.set(align="center", bold=False, font='b', width=1, height=1)
    printer.text(f"{data['entry_date_str']} | No: {data['order_number']}\n")

    # Líneas de datos (solo las que tienen valor)
    text_lines = []
    if data['device_model']:
        text_lines.append(f"Equipo: {data['device_model'][:28]}")
    if data['imei']:
        text_lines.append(f"IMEI: {data['imei']}")
    if data['password']:
        text_lines.append(f"Pass: {data['password']}")
    if data['received_by']:
        text_lines.append(f"Recibe: {data['received_by']}\n")
     
 

    # Ancho: usa override si está configurado, si no usa paper_px automático
    

    pattern_img = build_pattern_image(data['patron'])
    combined    = build_side_by_side(
        pattern_img=pattern_img,
        text_lines=text_lines,
        total_width=total_width,       # ← config.json: totalWidthOverride o paper_px
        text_pct=layout.text_pct,      # ← config.json: textPct
    )

    printer.set(align="left")
    printer.image(combined, center=False)
    printer.text("\n\n")

    printer.cut()