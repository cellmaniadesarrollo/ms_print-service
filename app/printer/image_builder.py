# app/printer/image_builder.py
"""
Genera todas las imágenes PIL que se envían a la impresora.

Las impresoras térmicas ESC/POS solo imprimen línea a línea, por lo que
cualquier layout en columnas debe construirse como una imagen combinada.

Funciones públicas:
    build_pattern_image(patron_str)
    build_footer_image(footer_lines, total_width)
    build_side_by_side(pattern_img, text_lines, total_width, text_pct)
"""

 
import random
from PIL import Image, ImageDraw, ImageFont
from app.constants import MOTIVATIONAL_PHRASES

# ─────────────────────────────────────────────────────────────────────────────
# Helper de fuentes
# ─────────────────────────────────────────────────────────────────────────────

def _font(name: str, size: int) -> ImageFont.FreeTypeFont:
    """Carga fuente TTF; cae a la fuente por defecto si no existe en el sistema."""
    try:
        return ImageFont.truetype(name, size)
    except Exception:
        return ImageFont.load_default()


# ─────────────────────────────────────────────────────────────────────────────
# Imagen del patrón de desbloqueo 3×3
# ─────────────────────────────────────────────────────────────────────────────

def build_pattern_image(patron_str: str) -> Image.Image | None:
    """
    Dibuja el patrón de desbloqueo Android sobre una cuadrícula 3×3.

    Numeración de la cuadrícula:
        1 | 2 | 3
        4 | 5 | 6
        7 | 8 | 9

    Ejemplo: patron_str="1235789" traza el patrón en esa secuencia.
    Punto rojo   = inicio (primer nodo)
    Flecha roja  = dirección del primer movimiento
    Líneas azules = recorrido
    Flecha azul  = nodo final

    Args:
        patron_str: cadena de dígitos 1-9, mínimo 4 caracteres

    Returns:
        Imagen PIL modo '1' (blanco/negro) o None si el patrón es inválido.
    """
    if not patron_str or len(patron_str) < 4:
        return None

    # Margen mínimo = radius + line_width/2 para que los círculos no se corten
    # Espaciado horizontal (120 px) < vertical (170 px) → rectángulo vertical
    positions = {
        '1': (44,  44),  '2': (164,  44),  '3': (284,  44),
        '4': (44, 214),  '5': (164, 214),  '6': (284, 214),
        '7': (44, 384),  '8': (164, 384),  '9': (284, 384),
    }

    img  = Image.new('RGB', (328, 428), 'white')  
    draw = ImageDraw.Draw(img)
    font = _font("arial.ttf", 46)

    radius           = 38
    line_width       = 9
    arrow_size       = 26
    start_arrow_size = 18

    from collections import defaultdict
    import math

    # Para cada nodo, recolectar qué segmentos lo tocan y asignarles un slot
    # slot = posición angular única en la circunferencia del nodo
    node_slots = defaultdict(list)  # nodo -> [seg_idx, ...]
    for i in range(len(patron_str) - 1):
        p1, p2 = patron_str[i], patron_str[i + 1]
        if p1 in positions and p2 in positions:
            node_slots[p1].append(i)
            node_slots[p2].append(i)

    # (nodo, seg_idx) -> offset angular en radianes aplicado al punto de conexión
    ANGLE_SPREAD = math.radians(18)  # separación entre slots
    seg_angle_offset = {}
    for node, segs in node_slots.items():
        n = len(segs)
        for k, seg_idx in enumerate(segs):
            # centrar los slots: si hay 2 → [-9°, +9°], si hay 3 → [-18°, 0°, +18°]
            offset = (k - (n - 1) / 2) * ANGLE_SPREAD
            seg_angle_offset[(node, seg_idx)] = offset

    def _connection_point(node, seg_idx, target_node):
        """Punto en la circunferencia del nodo hacia target, con offset angular único."""
        cx, cy   = positions[node]
        tx, ty   = positions[target_node]
        base_ang = math.atan2(ty - cy, tx - cx)
        ang      = base_ang + seg_angle_offset.get((node, seg_idx), 0)
        return cx + radius * math.cos(ang), cy + radius * math.sin(ang)

    # ── 1. Líneas pasando por encima de los círculos ──────────────
    font_step = _font("arialbd.ttf", 24)

    for i in range(len(patron_str) - 1):
        p1, p2 = patron_str[i], patron_str[i + 1]
        if p1 not in positions or p2 not in positions:
            continue

        # Punto único en la circunferencia de cada nodo para este segmento
        sx, sy = _connection_point(p1, i, p2)
        ex, ey = _connection_point(p2, i, p1)

        draw.line((sx, sy, ex, ey), fill='black', width=line_width)

        # Flecha en cada segmento
        dx, dy = ex - sx, ey - sy
        length = (dx**2 + dy**2) ** 0.5
        if length >= 1:
            ux, uy           = dx / length, dy / length
            perp_ux, perp_uy = -uy, ux
            lx = ex - arrow_size * ux + arrow_size * 0.6 * perp_ux
            ly = ey - arrow_size * uy + arrow_size * 0.6 * perp_uy
            rx = ex - arrow_size * ux - arrow_size * 0.6 * perp_ux
            ry = ey - arrow_size * uy - arrow_size * 0.6 * perp_uy
            draw.polygon([(ex, ey), (lx, ly), (rx, ry)], fill='black')

    # ── 2a. Borrador blanco en nodos visitados (crea corte visual entre segmentos) ─
    for ch in patron_str:
        if ch in positions:
            x, y = positions[ch]
            erase_r = radius + 6
            draw.ellipse(
                (x - erase_r, y - erase_r, x + erase_r, y + erase_r),
                fill='white',
            )

    # ── 2b. Círculos encima con borde negro ───────────────────────
 # ── 2b. Círculos encima con borde negro ───────────────────────
    visited = set(patron_str)
    for num, (x, y) in positions.items():
        if num in visited:
            # Nodo visitado: fondo negro, número blanco
            circle_fill    = 'black'
            circle_outline = 'black'
            text_fill      = 'white'
        else:
            # Nodo no visitado: fondo blanco, número negro
            circle_fill    = 'white'
            circle_outline = 'black'
            text_fill      = 'black'

        draw.ellipse(
            (x - radius, y - radius, x + radius, y + radius),
            fill=circle_fill, outline=circle_outline, width=6,
        )
        draw.text((x - 22, y - 30), num, fill=text_fill, font=font)

    # Punto rojo = primer nodo (inicio del patrón)
    # if patron_str[0] in positions:
    #     fx, fy = positions[patron_str[0]]
    #     draw.ellipse((fx - 12, fy - 12, fx + 12, fy + 12), fill='black')

    # ── 3. Flecha roja de inicio (apunta hacia el segundo nodo) ──
    if len(patron_str) >= 2 and patron_str[1] in positions:
        x1, y1 = positions[patron_str[0]]
        x2, y2 = positions[patron_str[1]]
        dx, dy = x2 - x1, y2 - y1
        length = (dx**2 + dy**2) ** 0.5
        if length >= 1:
            ux, uy           = dx / length, dy / length
            bx, by           = x1 + ux * (radius + 6), y1 + uy * (radius + 6)
            tx, ty           = bx + start_arrow_size * ux, by + start_arrow_size * uy
            perp_ux, perp_uy = -uy, ux
            lx = tx - start_arrow_size * 0.5 * perp_ux
            ly = ty - start_arrow_size * 0.5 * perp_uy
            rx = tx + start_arrow_size * 0.5 * perp_ux
            ry = ty + start_arrow_size * 0.5 * perp_uy
            draw.polygon([(tx, ty), (lx, ly), (rx, ry)], fill='black')

    return img.convert('1')


# ─────────────────────────────────────────────────────────────────────────────
# Imagen del footer (términos y condiciones)
# ─────────────────────────────────────────────────────────────────────────────

def build_footer_image(total_width: int, font_size: int = 22, width_scale: float = 1.0, es_servicio_tecnico: bool = False) -> Image.Image:
    
    # 1. Definición de textos
    if es_servicio_tecnico:
        footer_lines = [
            "- El costo mínimo de revisión es de $4. Este valor podría incrementarse",
            "  dependiendo del modelo de su dispositivo.",
            "- Recuerde: en la revisión de su dispositivo utilizamos materiales,",
            "  herramientas y tiempo de trabajo.",
            "- El tiempo máximo para retirar su dispositivo es de 3 meses."
        ]
        last_line = None # En servicio técnico no hay línea especial al final
    else:
        footer_lines = [
            "- Por favor, verifique que el estuche sea el modelo correcto para su",
            "  dispositivo; la selección errónea generará costos adicionales.",
            "- El tiempo máximo de retiro es de 1 mes."
        ]
        last_line = "TEAMCELLMANIA" # Tu "ultima linea" personalizada

    if not footer_lines and not last_line:
        return Image.new('1', (total_width, 1), 'white')

    scaled_width = int(total_width * width_scale)
    tmp = ImageDraw.Draw(Image.new('RGB', (1, 1)))

    # 2. Calcular tamaño para las líneas normales
    best_size = font_size
    for line in footer_lines:
        size = font_size
        while size > 8:
            font = _font("arialbd.ttf", size)
            bbox = tmp.textbbox((0, 0), line, font=font)
            if bbox[2] - bbox[0] <= scaled_width - 10:
                break
            size -= 1
        best_size = min(best_size, size)

    font_normal = _font("arialbd.ttf", best_size)
    line_height = best_size + 10
    
    # 3. Calcular tamaño para la línea especial (un poco más grande)
    special_size = best_size + 4 
    font_special = _font("arialbd.ttf", special_size)
    
    # 4. Calcular altura total del canvas
    total_height = (line_height * len(footer_lines))
    if last_line:
        total_height += (special_size + 15) # Espacio extra para la última línea

    img = Image.new('RGB', (scaled_width, total_height), 'white')
    draw = ImageDraw.Draw(img)

    # 5. Dibujar líneas normales
    y = 0
    for line in footer_lines:
        draw.text((0, y), line, fill='black', font=font_normal)
        bbox = draw.textbbox((0, 0), line, font=font_normal)
        underline_y = y + bbox[3] + 1
        draw.line((0, underline_y, bbox[2] - bbox[0], underline_y), fill='black', width=1)
        y += line_height

    # 6. Dibujar la última línea alineada al CENTRO
    if last_line:
        bbox_special = draw.textbbox((0, 0), last_line, font=font_special)
        text_width = bbox_special[2] - bbox_special[0]
        
        # Cálculo para centrar: (Ancho Total - Ancho Texto) / 2
        x_center = (scaled_width - text_width) // 2
        
        # Dibujar el texto en la posición calculada
        draw.text((x_center, y + 5), last_line, fill='black', font=font_special)

    return img.convert('1')
# ─────────────────────────────────────────────────────────────────────────────
# Imagen combinada: texto (izquierda) | patrón (derecha)
# ─────────────────────────────────────────────────────────────────────────────

def _calc_text_height(text_lines: list[str], line_height: int, max_value_chars: int) -> int:
    """Pre-calcula la altura total que ocupará el bloque de texto."""
    y = 0
    for line in text_lines:
        value = line.split(": ", 1)[1] if ": " in line else line
        y += line_height
        remainder = value[max_value_chars:]
        while remainder:
            y += line_height
            remainder = remainder[max_value_chars:]
    return y


def build_side_by_side(
    pattern_img: Image.Image | None,
    text_lines: list[str],
    total_width: int = 384,
    text_pct: int = 80,
) -> Image.Image:
    """
    Construye la imagen del ticket interno combinando texto y patrón.

    Layout resultante:
        ┌──────────────────────────┬───────────┐
        │ Equipo: Samsung A54      │  [patrón] │
        │ IMEI:   123456789012345  │   3 × 3   │
        │ Pass:   1234             │   grid    │
        │ Recibe: Juan             │           │
        └──────────────────────────┴───────────┘
        ←─── text_pct % ──────────→←─ resto ──→

    Args:
        pattern_img:  imagen generada por build_pattern_image() o None
        text_lines:   lista de "Etiqueta: valor"
        total_width:  ancho total de la imagen en píxeles
        text_pct:     porcentaje del ancho reservado para el texto

    Returns:
        Imagen PIL modo '1' lista para impresora.
    """
    text_width      = total_width * text_pct // 100
    img_width       = total_width - text_width
    line_height     = 34
    max_value_chars = 22

    # ── Altura del texto (pre-calculada para no cortar nada) ──────
    text_height = _calc_text_height(text_lines, line_height, max_value_chars)

    # ── Lado derecho: patrón ──────────────────────────────────────
    if pattern_img:
        src       = pattern_img.convert("RGB")
        ratio     = img_width / src.width
        new_h     = int(src.height * ratio)
        right_img = src.resize((img_width, new_h), Image.LANCZOS)
    else:
        new_h     = 100
        right_img = Image.new("RGB", (img_width, new_h), 'white')
        ImageDraw.Draw(right_img).text((0, 40), "N/A", fill='black')

    # El canvas usa el mayor entre la altura del texto y la del patrón
    total_height = max(text_height, new_h)

    # ── Lado izquierdo: texto ─────────────────────────────────────
    left_img   = Image.new("RGB", (text_width, total_height), 'white')
    draw_l     = ImageDraw.Draw(left_img)
    font_label = _font("arialbd.ttf", 21)
    font_value = _font("arial.ttf", 20)

    label_col = 0
    value_col = 82
    y         = 0

    for line in text_lines:
        if ": " in line:
            label, value = line.split(": ", 1)
            label += ":"
        else:
            label, value = "", line

        draw_l.text((label_col, y), label, fill='black', font=font_label)
        draw_l.text((value_col, y), value[:max_value_chars], fill='black', font=font_value)
        y += line_height

        remainder = value[max_value_chars:]
        while remainder:
            draw_l.text((value_col, y), remainder[:max_value_chars], fill='black', font=font_value)
            remainder = remainder[max_value_chars:]
            y += line_height

    # ── Combinar las dos mitades ──────────────────────────────────
    combined = Image.new("RGB", (total_width, total_height), 'white')
    combined.paste(left_img,  (0,          0))
    combined.paste(right_img, (text_width, 0))

    return combined.convert('1')


def build_company_name_image(
    company_name: str,
    total_width: int,
    font_size: int = 72,
    dash_length: int = 40,     # largo de cada guion
    dash_thickness: int = 5,   # grosor de la línea
    dash_gap: int = 16,        # espacio entre la decoración y el texto
    font_names: tuple = ("arialbd.ttf",),
    decor: str = "dash",       # "dash" (guiones) o "heart" (corazones)
    heart_size: int = 34,
    heart_count: int = 2,      # corazones por lado
    heart_gap: int = 8,
) -> Image.Image:
    use_hearts = decor == "heart"

    # Ancho que ocupa la decoración de cada lado
    if use_hearts:
        decor_width = heart_count * heart_size + (heart_count - 1) * heart_gap
    else:
        decor_width = dash_length

    extra_space = (decor_width + dash_gap) * 2
    tmp = ImageDraw.Draw(Image.new('RGB', (1, 1)))

    # Reducir el font_size hasta que el texto + decoración quepan en el ancho
    font = _font_first(font_names, font_size)
    while font_size > 20:
        font = _font_first(font_names, font_size)
        bbox = tmp.textbbox((0, 0), company_name, font=font)
        text_width = bbox[2] - bbox[0]
        if text_width + extra_space <= total_width - 10:
            break
        font_size -= 2

    height = font_size + (35 if use_hearts else 20)
    img    = Image.new('RGB', (total_width, height), 'white')
    draw   = ImageDraw.Draw(img)
    bbox   = draw.textbbox((0, 0), company_name, font=font)
    text_width = bbox[2] - bbox[0]

    total_content_width = text_width + extra_space
    start_x = (total_width - total_content_width) // 2

    y_text = (height - (bbox[3] - bbox[1])) // 2
    if use_hearts:
        y_text -= bbox[1]  # compensa el offset vertical de fuentes cursivas
    y_mid = height // 2

    x_text  = start_x + decor_width + dash_gap
    x_right = x_text + text_width + dash_gap

    if use_hearts:
        # ── Corazones izquierda ──
        for i in range(heart_count):
            cx = start_x + heart_size / 2 + i * (heart_size + heart_gap)
            _draw_heart(draw, cx, y_mid - 2, heart_size)
        # ── Corazones derecha ──
        for i in range(heart_count):
            cx = x_right + heart_size / 2 + i * (heart_size + heart_gap)
            _draw_heart(draw, cx, y_mid - 2, heart_size)
    else:
        # ── Guion izquierdo ──
        draw.line(
            (start_x, y_mid, start_x + dash_length, y_mid),
            fill='black', width=dash_thickness,
        )
        # ── Guion derecho ──
        draw.line(
            (x_right, y_mid, x_right + dash_length, y_mid),
            fill='black', width=dash_thickness,
        )

    # ── Texto ──
    draw.text((x_text, y_text), company_name, fill='black', font=font)

    return img.convert('1')

 
def build_text_image(text: str, total_width: int, font_size: int = 30, bold: bool = True) -> Image.Image:
    """
    Crea una imagen a partir de un texto simple para la impresora térmica.
    """
    # Elegir fuente
    font_path = "arialbd.ttf" if bold else "arial.ttf"
    font = _font(font_path, font_size)
    
    # Crear un canvas temporal para medir el texto
    tmp_draw = ImageDraw.Draw(Image.new('RGB', (1, 1)))
    bbox = tmp_draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]

    # Crear la imagen final con fondo blanco
    # Añadimos un pequeño margen de 10px en la altura
    img = Image.new('RGB', (total_width, text_height + 15), 'white')
    draw = ImageDraw.Draw(img)

    # Calcular posición para centrar el texto
    x = (total_width - text_width) // 2
    y = 5  # Un pequeño margen superior

    draw.text((x, y), text, fill='black', font=font)

    return img.convert('1')


def build_copy_box_image(
    printed_by: str,
    copy_printed_at: str,
    requested_by: str,
    total_width: int,
    font_size: int = 26,
    padding: int = 12,
    border_thickness: int = 3,
    margin: int = 6,
) -> Image.Image:
    font_bold = _font("arialbd.ttf", font_size)
    font_reg  = _font("arial.ttf", int(font_size * 0.75))

    lines = ["*** COPIA ***", f"{printed_by} | {copy_printed_at}"]
    if requested_by:
        lines.append(f"Solicitada por: {requested_by}")

    # medir alturas
    dummy = Image.new("RGB", (1, 1))
    d = ImageDraw.Draw(dummy)
    line_heights = []
    for i, line in enumerate(lines):
        f = font_bold if i == 0 else font_reg
        bbox = d.textbbox((0, 0), line, font=f)
        line_heights.append(bbox[3] - bbox[1])

    box_height = sum(line_heights) + padding * (len(lines) + 1)

    img = Image.new("RGB", (total_width, box_height), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    # ── Solo el borde (sin relleno) ──
    draw.rectangle(
        [margin, 0, total_width - margin, box_height - 1],
        fill=None, outline=(0, 0, 0), width=border_thickness,
    )

    # ── Texto en negro, centrado, dentro del recuadro ──
    y = padding
    for i, line in enumerate(lines):
        f = font_bold if i == 0 else font_reg
        bbox = draw.textbbox((0, 0), line, font=f)
        w = bbox[2] - bbox[0]
        x = (total_width - w) // 2
        draw.text((x, y), line, font=f, fill=(0, 0, 0))
        y += line_heights[i] + padding

    return img.convert('1')


# Cadena de fuentes "cursivas" para PARA REPUESTOS (Windows).
# Usa la primera que exista; si ninguna, cae a Arial Bold.
REPUESTOS_FONTS = ("segoescb.ttf", "BRUSHSCI.TTF", "comicbd.ttf", "arialbd.ttf")


def _font_first(names, size: int):
    """Devuelve la primera fuente TTF disponible de la lista."""
    for n in names:
        try:
            return ImageFont.truetype(n, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _draw_heart(draw: ImageDraw.ImageDraw, cx: float, cy: float, width: float) -> None:
    """Dibuja un corazón relleno de color negro centrado en (cx, cy)."""
    r = width / 4
    # Dos círculos superiores
    draw.ellipse((cx - 2 * r, cy - 1.5 * r, cx, cy + 0.5 * r), fill='black')
    draw.ellipse((cx, cy - 1.5 * r, cx + 2 * r, cy + 0.5 * r), fill='black')
    # Triángulo inferior
    draw.polygon(
        [
            (cx - 1.9 * r, cy + 0.1 * r),
            (cx + 1.9 * r, cy + 0.1 * r),
            (cx, cy + 2.3 * r),
        ],
        fill='black',
    )


def build_motivational_footer_image(
    total_width: int,
    font_size: int = 26,
    width_scale: float = 1.0,
    phrase: str | None = None,
) -> Image.Image:
    """
    Footer para órdenes PARA REPUESTOS: una frase motivacional aleatoria,
    centrada y con salto de línea automático.
    """
    phrase = phrase or random.choice(MOTIVATIONAL_PHRASES)

    scaled_width = int(total_width * width_scale)
    max_text_w   = scaled_width - 20
    font         = _font_first(REPUESTOS_FONTS, font_size)
    tmp          = ImageDraw.Draw(Image.new('RGB', (1, 1)))

    # ── Ajuste de línea por palabras ──
    lines, current = [], ""
    for word in phrase.split():
        test = f"{current} {word}".strip()
        w = tmp.textbbox((0, 0), test, font=font)[2]
        if w <= max_text_w or not current:
            current = test
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)

    line_height  = font_size + 10
    total_height = line_height * len(lines) + 10

    img  = Image.new('RGB', (scaled_width, total_height), 'white')
    draw = ImageDraw.Draw(img)

    y = 5
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        x = (scaled_width - (bbox[2] - bbox[0])) // 2
        draw.text((x, y - bbox[1]), line, fill='black', font=font)
        y += line_height

    return img.convert('1')


def build_acquired_banner_image(
    total_width: int,
    text: str = "ADQUIRIDO",
    font_size: int = 44,
    padding: int = 10,
    border_thickness: int = 4,
    margin: int = 6,
) -> Image.Image:
    """
    Banner con recuadro: ADQUIRIDO
    Se usa en tickets de taller de órdenes que pasaron a bodega.
    """
    tmp = ImageDraw.Draw(Image.new('RGB', (1, 1)))

    # Reducir fuente hasta que quepa el texto
    font = _font_first(REPUESTOS_FONTS, font_size)
    while font_size > 16:
        font = _font_first(REPUESTOS_FONTS, font_size)
        bbox = tmp.textbbox((0, 0), text, font=font)
        if (bbox[2] - bbox[0]) + (margin + padding) * 2 <= total_width:
            break
        font_size -= 2

    bbox = tmp.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]

    box_h = text_h + padding * 2 + 10
    img   = Image.new('RGB', (total_width, box_h + 6), 'white')
    draw  = ImageDraw.Draw(img)

    # Recuadro
    draw.rectangle(
        [margin, 2, total_width - margin, box_h + 2],
        fill=None, outline='black', width=border_thickness,
    )

    # Texto centrado (compensa offset vertical de fuentes cursivas)
    x = (total_width - text_w) // 2
    y = 2 + (box_h - text_h) // 2 - bbox[1]
    draw.text((x, y), text, fill='black', font=font)

    return img.convert('1')


def build_qr_with_phrase_image(
    qr_img: Image.Image,
    phrase: str | None,
    total_width: int,
    font_size: int = 22,
    gap: int = 10,
    margin: int = 4,
) -> Image.Image:
    """
    Si hay frase:  [ frase (izquierda) | QR (derecha) ]
    Si no hay:     QR centrado, sin espacio en blanco sobrante.
    """
    qr_img = qr_img.convert("RGB")
    qr_w, qr_h = qr_img.size

    # ── Solo QR, centrado ──
    if not phrase:
        canvas = Image.new("RGB", (total_width, qr_h), 'white')
        canvas.paste(qr_img, ((total_width - qr_w) // 2, 0))
        return canvas.convert('1')

    # ── Frase + QR ──
    text_w = total_width - qr_w - gap - margin * 2
    font   = _font_first(REPUESTOS_FONTS, font_size)
    tmp    = ImageDraw.Draw(Image.new('RGB', (1, 1)))

    # Ajuste de línea por palabras dentro de la columna izquierda
    lines, current = [], ""
    for word in phrase.split():
        test = f"{current} {word}".strip()
        w = tmp.textbbox((0, 0), test, font=font)[2]
        if w <= text_w or not current:
            current = test
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)

    line_height = font_size + 8
    text_h      = line_height * len(lines)
    height      = max(qr_h, text_h)

    canvas = Image.new("RGB", (total_width, height), 'white')
    draw   = ImageDraw.Draw(canvas)

    # QR a la derecha, centrado verticalmente
    canvas.paste(qr_img, (total_width - qr_w - margin, (height - qr_h) // 2))

    # Frase a la izquierda, centrada en su columna y verticalmente
    y = (height - text_h) // 2
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        x = margin + (text_w - (bbox[2] - bbox[0])) // 2
        draw.text((x, y - bbox[1]), line, fill='black', font=font)
        y += line_height

    return canvas.convert('1')