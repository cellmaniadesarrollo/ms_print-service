import os
import sys
from datetime import datetime, timezone, timedelta

from escpos.printer import Dummy
from PIL import Image, ImageDraw, ImageFont

from app.printer.models.abono_deuda import AbonoDeudaPrintRequest

TZ_EC = timezone(timedelta(hours=-5))

# Raíz del proyecto (donde vive config.json); en .exe, la carpeta del ejecutable
_ROOT = (
    os.path.dirname(sys.executable)
    if getattr(sys, "frozen", False)
    else os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
)

# Mismo logo que usa la factura (image.png en la raíz del proyecto)
LOGO_PATH = os.path.join(_ROOT, "image.png")

_FONTS_REG = [
    os.path.join(_ROOT, "assets", "fonts", "Roboto-Regular.ttf"),
    "C:/Windows/Fonts/arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]
_FONTS_BOLD = [
    os.path.join(_ROOT, "assets", "fonts", "Roboto-Bold.ttf"),
    "C:/Windows/Fonts/arialbd.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    for path in (_FONTS_BOLD if bold else _FONTS_REG):
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _cargar_logo(ancho_max: int):
    if not os.path.exists(LOGO_PATH):
        return None
    logo = Image.open(LOGO_PATH).convert("RGBA")
    fondo = Image.new("RGBA", logo.size, "white")
    fondo.alpha_composite(logo)
    logo = fondo.convert("L")
    ratio = ancho_max / logo.width
    return logo.resize((ancho_max, int(logo.height * ratio)), Image.LANCZOS)


def _wrap(draw, texto, font, ancho):
    lineas, actual = [], ""
    for palabra in texto.split():
        prueba = f"{actual} {palabra}".strip()
        if draw.textlength(prueba, font=font) <= ancho:
            actual = prueba
        else:
            if actual:
                lineas.append(actual)
            actual = palabra
    if actual:
        lineas.append(actual)
    return lineas or [""]


def _render_abono(datos: AbonoDeudaPrintRequest, ab, ancho: int) -> Image.Image:
    M = 14                      # margen lateral
    lienzo = Image.new("L", (ancho, 1600), 255)
    d = ImageDraw.Draw(lienzo)
    y = 8

    def centrado(txt, font, pad=0):
        nonlocal y
        w = d.textlength(txt, font=font)
        d.text(((ancho - w) / 2, y), txt, font=font, fill=0)
        y += font.size + 6 + pad

    def izquierda(txt, font):
        nonlocal y
        for l in _wrap(d, txt, font, ancho - 2 * M):
            d.text((M, y), l, font=font, fill=0)
            y += font.size + 6

    def linea():
        nonlocal y
        y += 4
        d.line([(0, y), (ancho, y)], fill=0, width=2)
        y += 10

    # Logo
    logo = _cargar_logo(int(ancho * 0.62))
    if logo:
        lienzo.paste(logo, ((ancho - logo.width) // 2, y))
        y += logo.height + 10

    centrado(f"CREDITO #{datos.credito_id}", _font(30, True), pad=2)
    linea()

    izquierda(f"Cliente: {datos.cliente_nombre}", _font(22, True))
    izquierda(f"CI/RUC: {datos.cliente_identificacion}", _font(22))
    linea()

    centrado(f"CUOTA #{ab.cuota_numero} - ABONO #{ab.abono_numero}", _font(26, True), pad=6)

    # ── Tabla ──
    x0, x1 = M, ancho - M
    anchos = [0.40, 0.27, 0.33]
    xs = [x0]
    for a in anchos:
        xs.append(xs[-1] + int((x1 - x0) * a))
    xs[-1] = x1

    h_head, h_row = 40, 70
    top = y
    f_head, f_cell, f_monto = _font(18, True), _font(19), _font(22, True)

    def celda(i, y_ini, alto, lineas, font):
        total = len(lineas) * (font.size + 4)
        yy = y_ini + (alto - total) / 2
        for t in lineas:
            w = d.textlength(t, font=font)
            d.text((xs[i] + (xs[i + 1] - xs[i] - w) / 2, yy), t, font=font, fill=0)
            yy += font.size + 4

    for i, t in enumerate(["FECHA Y HORA", "MONTO", "MÉTODO"]):
        celda(i, top, h_head, [t], f_head)

    partes = ab.fecha_hora.split(" ", 1)
    celda(0, top + h_head, h_row, partes, f_cell)
    celda(1, top + h_head, h_row, [f"${ab.monto:.2f}"], f_monto)
    celda(2, top + h_head, h_row, [ab.metodo_pago], f_cell)

    bottom = top + h_head + h_row
    d.rectangle([x0, top, x1, bottom], outline=0, width=2)
    d.line([(x0, top + h_head), (x1, top + h_head)], fill=0, width=2)
    for x in xs[1:-1]:
        d.line([(x, top), (x, bottom)], fill=0, width=2)
    y = bottom + 18

    centrado(f"SALDO RESTANTE DE LA CUOTA: ${ab.saldo_restante:.2f}", _font(20, True), pad=8)
    linea()
    centrado("Gracias por su pago", _font(24, True), pad=4)
    ahora = datetime.now(TZ_EC).strftime("%d/%m/%Y %H:%M:%S")
    centrado(f"F. Impresión: {ahora}", _font(19))
    # if datos.impreso_por:
    #     centrado(f"Atendido por: {datos.impreso_por}", _font(19))

    img = lienzo.crop((0, 0, ancho, y + 10))
    return img.point(lambda p: 255 if p > 160 else 0).convert("1")


def formatear_abono_deuda(datos: AbonoDeudaPrintRequest, ancho_px: int = 512) -> bytes:
    p = Dummy()
    for ab in datos.abonos:
        img = _render_abono(datos, ab, ancho_px)
        p.image(img, impl="bitImageRaster")
        p.cut(feed=True)
    return p.output