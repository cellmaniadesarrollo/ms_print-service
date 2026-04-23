"""
Construye y envía los comandos ESC/POS a la impresora.

Se generan dos tickets por orden:
    1. print_customer_ticket()  → copia para el CLIENTE
    2. print_workshop_ticket()  → copia interna para el TALLER
"""

from pathlib import Path
from PIL import Image
import qrcode
import base64
from io import BytesIO
from PIL import Image
from app.config import AppConfig
from app.printer.image_builder import (
    build_pattern_image,
    build_side_by_side,
    build_footer_image,
    build_company_name_image,
    build_text_image,
)
from app.constants import LOGO_TEAMCELL_PERSONALIZADO_B64

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
    print(f"DEBUG: Tipo de orden detectado: '{data.get('order_type')}'")
    feat   = config.features
    ticket = config.ticket
    layout = config.ticket.layout
    total_width = layout.total_width_override or config.paper_px
    
# --- LÓGICA DE PARCHE (v1.1.3) ---
    es_teamcell = data.get('company_name') == "TEAMCELLMANIA"
    es_personalizado = data.get('order_type') == "PERSONALIZADO"

    if es_teamcell and es_personalizado:
        try:
            img_data = base64.b64decode(LOGO_TEAMCELL_PERSONALIZADO_B64)
            img = Image.open(BytesIO(img_data)).convert("RGB")

            # ── Redimensionar al 80% del ancho del ticket ──
            scale = 0.4
            target_width = int(total_width * scale)
            ratio = target_width / img.width
            img = img.resize((target_width, int(img.height * ratio)), Image.LANCZOS)

            # ── Centrar pegando sobre fondo blanco del ancho total ──
            canvas = Image.new("RGB", (total_width, img.height), (255, 255, 255))
            offset_x = (total_width - img.width) // 2
            canvas.paste(img, (offset_x, 0))

            printer.image(canvas, center=False)
            # printer.text("\n")
# --- NUEVO: Texto debajo del logo especial ---
            # Aquí puedes poner el eslogan o nombre de la campaña
            text_img = build_text_image(
                text="HAZLO UNICO, HAZLO TUYO", 
                total_width=total_width, 
                font_size=10, # Más grande para que destaque
                bold=True
            )
            printer.image(text_img, center=False)
        except Exception as e:
            print(f"✗ Error al procesar imagen base64: {e}")
    else:
        company_img = build_company_name_image(data['company_name'], total_width, font_size=72)
        printer.image(company_img, center=True)
        # printer.text("\n")


    es_miercoles = data['entry_dt'].weekday() == 2
    # 2. ¿Es Servicio Técnico? (Cuidado con las tildes, mejor usar .upper())
    es_servicio_tecnico = data.get('order_type') == "SERVICIO TECNICO"
    if feat.print_wednesday_promo and es_miercoles and es_servicio_tecnico and ticket.wednesday_promo: 
        printer.set(align="center", bold=False, font='b', width=1, height=1)
        printer.text(f"{ticket.wednesday_promo}\n") 

    printer.set(align="center", bold=True, font='b', width=1, height=1)
    printer.text(f"{data['entry_date_str']} | No. {data['order_number']}\n")

    printer.set(align="center", bold=False, font='b')
    printer.text(f" {data.get('order_type', 'N/A')}\n")

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
    # printer.text("\n")

    if data['motivo']:
        printer.text("Motivo de ingreso:\n")
        for i in range(0, len(data['motivo']), 64):
            printer.text(data['motivo'][i:i+64] + "\n")
        # printer.text("\n")

    if data['received_by']:
        printer.set(align="center", font='b', width=1, height=1, bold=False)
        line = f"Recibido por: {data['received_by']}"
        if data['received_phone']:
            line += f" - {data['received_phone']}"
        printer.text(line + "\n")

    # QR — el cliente sí necesita la explicación
    if feat.print_qr and data['qr_url']:
        printer.set(align="center", font='b', width=1, height=1, bold=False)
        printer.text("Escanee el codigo QR para ver el estado.")
        printer.qr(data['qr_url'], size=3)

   
    printer.set(align="left")
    footer_img = build_footer_image(config.paper_px, width_scale=1.2,es_servicio_tecnico=es_servicio_tecnico)
    printer.image(footer_img, center=False)
    printer.text("\n") 
    printer.text("\n") 

    printer.cut()


# ─────────────────────────────────────────────────────────────────────────────
# Ticket 2 de 2 — copia interna del TALLER
# ─────────────────────────────────────────────────────────────────────────────

def print_workshop_ticket(printer, data: dict, config: AppConfig) -> None:
    feat   = config.features
    layout = config.ticket.layout
    total_width = layout.total_width_override or config.paper_px

# --- LÓGICA DE PARCHE (v1.1.3) ---
    es_teamcell = data.get('company_name') == "TEAMCELLMANIA"
    es_personalizado = data.get('order_type') == "PERSONALIZADO"

    if es_teamcell and es_personalizado:
        try:
            img_data = base64.b64decode(LOGO_TEAMCELL_PERSONALIZADO_B64)
            img = Image.open(BytesIO(img_data)).convert("RGB")

            # ── Redimensionar al 80% del ancho del ticket ──
            scale = 0.4
            target_width = int(total_width * scale)
            ratio = target_width / img.width
            img = img.resize((target_width, int(img.height * ratio)), Image.LANCZOS)

            # ── Centrar pegando sobre fondo blanco del ancho total ──
            canvas = Image.new("RGB", (total_width, img.height), (255, 255, 255))
            offset_x = (total_width - img.width) // 2
            canvas.paste(img, (offset_x, 0))

            printer.image(canvas, center=False)
            # printer.text("\n")
            print("DEBUG: Impreso logo especial de parche para TEAMCELLMANIA")
        except Exception as e:
            print(f"✗ Error al procesar imagen base64: {e}")
    else:
        company_img = build_company_name_image(data['company_name'], total_width, font_size=72)
        printer.image(company_img, center=True)
        # printer.text("\n")

    # ==================== CABECERA CON SUCURSAL ====================
    printer.set(align="center", bold=False, font='b', width=1, height=1)
    printer.text(f"{data['entry_date_str']} | No: {data['order_number']}\n")
    
    printer.set(align="center", bold=False, font='b')
    printer.text(f"{data['branch_name']} | {data['order_type']}\n")
 

    # ←←← NUEVO: Nombre de la sucursal ←←←
  

    # ==================== DATOS DEL TICKET ====================
    text_lines = []
    if data['customer_name']:
        text_lines.append(f"Cliente: {data['customer_name']}")
    
    # Todos los números MÓVIL del cliente
    for phone in data['mobile_phones']:
        text_lines.append(f"Movil: {phone}")
    
    if data['device_model']:
        text_lines.append(f"Equipo: {data['device_model'][:28]}")
    
    if data.get('imei'):
        text_lines.append(f"IMEI: {data['imei']}")
    
    if data['password']:
        text_lines.append(f"Pass: {data['password']}")
    
    if data['patron']:
        text_lines.append(f"Patron: {data['patron']}")
    
    if data['received_by']:
        text_lines.append(f"Recibe: {data['received_by']}")

    has_patron = bool(data['patron'])

    if has_patron:
        right_img = build_pattern_image(data['patron'])
    elif feat.print_qr and data['qr_url']:
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
    # printer.text("\n")

    if data['motivo']:
        printer.set(align="left", bold=False, font='b', width=1, height=1)
        printer.text("Motivo de ingreso:\n")
        for i in range(0, len(data['motivo']), 64):
            printer.text(data['motivo'][i:i+64] + "\n")
        printer.text("\n")

    if has_patron and feat.print_qr and data['qr_url']:
        printer.set(align="center", font='b', width=1, height=1, bold=False)
        printer.qr(data['qr_url'], size=3)
        printer.text("\n")

    printer.cut()