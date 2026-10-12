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
    build_copy_box_image,
    build_motivational_footer_image,
    build_acquired_banner_image,
    build_qr_with_phrase_image,
    REPUESTOS_FONTS,
)
from app.printer.copy_box_text import print_copy_box_text  
import random
from app.constants import LOGO_TEAMCELL_PERSONALIZADO_B64, MOTIVATIONAL_PHRASES
def _assets_path() -> Path:
    return Path(__file__).parent.parent.parent / "assets"

def _build_qr_sized(url: str, target_px: int) -> Image.Image:
    """
    QR de ~target_px de ancho, con módulos de tamaño entero (nítido para térmica).
    """
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=1,
        border=2,
    )
    qr.add_data(url)
    qr.make(fit=True)

    modules = qr.modules_count + 2 * qr.border
    qr.box_size = max(1, target_px // modules)

    return qr.make_image(fill_color="black", back_color="white").convert("RGB")

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

    # ── Encabezado (según tipo de orden) ──
    _print_header(printer, data, total_width, with_tagline=True)

    if data["is_copy"]:
        print_copy_box_text(
            printer,
            printed_by=data["printed_by"],
            copy_printed_at=data["copy_printed_at"],
            requested_by=data.get("requested_by", ""),
        )

    es_miercoles        = data['entry_dt'].weekday() == 2
    es_servicio_tecnico = data.get('order_type') == "SERVICIO TECNICO"
    es_repuestos        = data.get('order_type') == "PARA REPUESTOS"

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
    if data['device_model']:
        printer.text(f"{'Dispositivo:':<14}{data['device_model'][:45]}\n")
    if data['imei']:
        printer.text(f"{'IMEI:':<14}{data['imei']}\n")

    if data.get('observations'):
        printer.text("Observaciones:\n")
        for i in range(0, len(data['observations']), 64):
            printer.text(data['observations'][i:i+64] + "\n")

    if data['motivo']:
        printer.text("Motivo de ingreso:\n")
        for i in range(0, len(data['motivo']), 64):
            printer.text(data['motivo'][i:i+64] + "\n")

    if data['received_by']:
        printer.set(align="center", font='b', width=1, height=1, bold=False)
        line = f"Recibido por: {data['received_by']}"
        if data['received_phone']:
            line += f" - {data['received_phone']}"
        printer.text(line + "\n")

    # ── QR como imagen (+ frase al lado si NO es PARA REPUESTOS) ──
    phrase = None if es_repuestos else _get_customer_phrase(data)

    if feat.print_qr and data['qr_url']:
        printer.set(align="center", font='b', width=1, height=1, bold=False)
        printer.text("Escanee el codigo QR para ver el estado.\n")

        qr_img = _build_qr_sized(data['qr_url'], int(total_width * 0.40))
        combo  = build_qr_with_phrase_image(qr_img, phrase, total_width, font_size=22)
        printer.set(align="left")
        printer.image(combo, center=False)

    elif phrase:
        # Sin QR: la frase sola, como antes
        printer.set(align="left")
        phrase_img = build_motivational_footer_image(
            config.paper_px, font_size=24, width_scale=1.0, phrase=phrase
        )
        printer.image(phrase_img, center=False)

    # ── Footer (según tipo de orden) ──
    printer.set(align="left")
    if es_repuestos:
        frase_cliente, _ = _get_repuestos_phrases(data)
        footer_img = build_motivational_footer_image(
            config.paper_px, width_scale=1.0, phrase=frase_cliente
        )
    else:
        footer_img = build_footer_image(
            config.paper_px, width_scale=1.2, es_servicio_tecnico=es_servicio_tecnico
        )
    printer.image(footer_img, center=False)
    printer.text("\n")
    printer.text("\n")

    printer.cut()


# ─────────────────────────────────────────────────────────────────────────────
# Ticket 2 de 2 — copia interna del TALLER
# ─────────────────────────────────────────────────────────────────────────────
def print_workshop_ticket(printer, data: dict, config: AppConfig, acquired: bool = False) -> None:
    feat   = config.features
    layout = config.ticket.layout
    total_width = layout.total_width_override or config.paper_px
    es_repuestos = data.get('order_type') == "PARA REPUESTOS"

    # ── Encabezado (según tipo de orden; con corazones si es adquirido) ──
    _print_header(printer, data, total_width, with_tagline=False, force_hearts=acquired)

    # ── Banner ADQUIRIDO ──
    if acquired:
        printer.image(build_acquired_banner_image(total_width), center=False)

    if data["is_copy"]:
        print_copy_box_text(
            printer,
            printed_by=data["printed_by"],
            copy_printed_at=data["copy_printed_at"],
            requested_by=data.get("requested_by", ""),
        )

    # ==================== CABECERA CON SUCURSAL ====================
    printer.set(align="center", bold=False, font='b', width=1, height=1)
    printer.text(f"{data['entry_date_str']} | No: {data['order_number']}\n")

    printer.set(align="center", bold=False, font='b')
    printer.text(f"{data['branch_name']} | {data['order_type']}\n")

    # ==================== DATOS DEL TICKET ====================
    text_lines = []
    if data['customer_name']:
        text_lines.append(f"Cliente: {data['customer_name']}")

    for phone in data['mobile_phones']:
        text_lines.append(f"Movil: {phone}")

    if data['device_model']:
        device_line = data['device_model'][:28]
        if data.get('device_type'):
            device_line += f" ({data['device_type']})"
        text_lines.append(f"Equipo: {device_line}")
    if data.get('observations'):
        text_lines.append(f"Obs: {data['observations'][:40]}")
    if data.get('imei'):
        text_lines.append(f"IMEI: {data['imei']}")

    if data['password']:
        text_lines.append(f"Pass: {data['password']}")

    if data['patron']:
        text_lines.append(f"Patron: {data['patron']}")

    if data['received_by']:
        techs = " / ".join(data['technicians_abbrev'])
        recibe_line = f"Recibe: {data['received_by']}"
        if techs:
            recibe_line += f"  |{techs}"
        text_lines.append(recibe_line)

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

    # ── Footer motivacional solo para PARA REPUESTOS (frase distinta a la del cliente) ──
    if es_repuestos:
        _, frase_taller = _get_repuestos_phrases(data)
        footer_img = build_motivational_footer_image(
            total_width, font_size=22, width_scale=1.0, phrase=frase_taller
        )
        printer.set(align="left")
        printer.image(footer_img, center=False)
        printer.text("\n")

    printer.cut()



def _print_header(
    printer,
    data: dict,
    total_width: int,
    with_tagline: bool,
    force_hearts: bool = False,
) -> None:
    """
    Encabezado según el tipo de orden:
      - force_hearts o PARA REPUESTOS → nombre con otra fuente y corazones
      - TEAMCELLMANIA + PERSONALIZADO → logo especial (+ eslogan en cliente)
      - Resto                         → nombre con guiones (estilo normal)
    """
    es_teamcell      = data.get('company_name') == "TEAMCELLMANIA"
    es_personalizado = data.get('order_type') == "PERSONALIZADO"
    es_repuestos     = data.get('order_type') == "PARA REPUESTOS"

    if force_hearts or es_repuestos:
        company_img = build_company_name_image(
            data['company_name'],
            total_width,
            font_size=72,
            font_names=REPUESTOS_FONTS,
            decor="heart",
        )
        printer.image(company_img, center=True)

    elif es_teamcell and es_personalizado:
        try:
            img_data = base64.b64decode(LOGO_TEAMCELL_PERSONALIZADO_B64)
            img = Image.open(BytesIO(img_data)).convert("RGB")

            scale = 0.4
            target_width = int(total_width * scale)
            ratio = target_width / img.width
            img = img.resize((target_width, int(img.height * ratio)), Image.LANCZOS)

            canvas = Image.new("RGB", (total_width, img.height), (255, 255, 255))
            canvas.paste(img, ((total_width - img.width) // 2, 0))
            printer.image(canvas, center=False)

            if with_tagline:
                text_img = build_text_image(
                    text="HAZLO UNICO, HAZLO TUYO",
                    total_width=total_width,
                    font_size=10,
                    bold=True,
                )
                printer.image(text_img, center=False)
        except Exception as e:
            print(f"✗ Error al procesar imagen base64: {e}")

    else:
        company_img = build_company_name_image(data['company_name'], total_width, font_size=72)
        printer.image(company_img, center=True)


def _get_repuestos_phrases(data: dict) -> tuple[str, str]:
    """
    Devuelve (frase_cliente, frase_taller), siempre distintas entre sí.
    Se guardan en `data` para que ambos tickets de la misma orden
    usen el mismo par, sin importar cuál se imprima primero.
    """
    if "_repuestos_phrases" not in data:
        data["_repuestos_phrases"] = tuple(random.sample(MOTIVATIONAL_PHRASES, 2))
    return data["_repuestos_phrases"]

def _get_customer_phrase(data: dict) -> str:
    """Frase motivacional para el ticket cliente de órdenes que NO son PARA REPUESTOS."""
    if "_customer_phrase" not in data:
        data["_customer_phrase"] = random.choice(MOTIVATIONAL_PHRASES)
    return data["_customer_phrase"]