# app/printer/promo_image.py
"""Imagen del recuadro de promociones (todo en negrita)."""

from PIL import Image, ImageDraw
from app.printer.image_builder import _font


def _fit_font(draw, text: str, size: int, max_w: int, min_size: int = 12):
    """Reduce el tamaño de la fuente hasta que el texto quepa en max_w."""
    while size > min_size:
        font = _font("arialbd.ttf", size)
        bbox = draw.textbbox((0, 0), text, font=font)
        if bbox[2] - bbox[0] <= max_w:
            return font
        size -= 1
    return _font("arialbd.ttf", min_size)


def build_promo_box_image(
    lines: tuple[str, ...] | list[str],
    total_width: int,
    title_size: int = 36,   # primera línea (título)
    body_size: int = 24,    # resto de líneas
    padding: int = 12,
    line_gap: int = 8,
    border: int = 4,
    margin: int = 6,
) -> Image.Image:
    """
    Recuadro con las líneas de una promoción, centradas y en negrita.
    La primera línea va más grande (título); las demás, más pequeñas.
    """
    tmp = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    max_text_w = total_width - 2 * (margin + padding + border)

    items = []
    for i, line in enumerate(lines):
        size = title_size if i == 0 else body_size
        font = _fit_font(tmp, line, size, max_text_w)
        items.append((line, font, tmp.textbbox((0, 0), line, font=font)))

    text_h = sum(b[3] - b[1] for _, _, b in items) + line_gap * (len(items) - 1)
    box_h = text_h + 2 * padding + 2 * border

    img = Image.new("RGB", (total_width, box_h + 8), "white")
    draw = ImageDraw.Draw(img)
    draw.rectangle(
        [margin, 4, total_width - margin, 4 + box_h],
        fill=None, outline="black", width=border,
    )

    y = 4 + border + padding
    for line, font, bbox in items:
        w = bbox[2] - bbox[0]
        x = (total_width - w) // 2
        draw.text((x - bbox[0], y - bbox[1]), line, fill="black", font=font)
        y += (bbox[3] - bbox[1]) + line_gap

    return img.convert("1")