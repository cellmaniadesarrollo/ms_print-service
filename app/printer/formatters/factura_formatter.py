import os
import textwrap
import unicodedata
from itertools import zip_longest
from PIL import Image, ImageDraw
from escpos.printer import Dummy
from app.printer.models.factura import FacturaPrintRequest


def _ascii(texto) -> str:
    """Quita tildes y caracteres especiales para impresoras térmicas."""
    texto = "" if texto is None else str(texto)
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")


def _preparar_logo(path: str, max_w: int = 380) -> Image.Image:
    img = Image.open(path)
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        fondo = Image.new("RGBA", img.size, (255, 255, 255, 255))
        fondo.alpha_composite(img)
        img = fondo
    img = img.convert("L")
    max_w -= max_w % 8
    ratio = max_w / img.width
    img = img.resize((max_w, int(img.height * ratio)), Image.LANCZOS)
    return img.point(lambda x: 255 if x > 160 else 0, mode="1")


def _imagen_codigo_barras(codigo: str, ancho_px: int = 380, alto: int = 65) -> Image.Image:
    """Genera código Code128 en blanco y negro puro."""
    import barcode

    modulos = barcode.get("code128", codigo).build()[0]
    n = len(modulos)
    margen = 8
    ancho_px -= ancho_px % 8
    util = ancho_px - 2 * margen
    escala = util / n

    img = Image.new("1", (ancho_px, alto), 1)
    d = ImageDraw.Draw(img)
    for i, m in enumerate(modulos):
        if m == "1":
            x0 = margen + round(i * escala)
            x1 = margen + round((i + 1) * escala) - 1
            d.rectangle([x0, 0, max(x1, x0), alto], fill=0)
    return img


def formatear_factura_o_recibo(
    datos: FacturaPrintRequest,
    ancho: int = 56,       # 56 columnas para Fuente "b" (Letra fina y ajustada)
    fuente: str = "b",     # Fuente 'b' condensada
) -> bytes:
    p = Dummy()
    mitad = ancho // 2
    es_factura = datos.tipo_documento.upper() == "FACTURA"

    def estilo(**kw):
        p.set(font=fuente, **kw)

    def dos_cols(a, b, w=ancho):
        w_mitad = w // 2
        col_a = textwrap.wrap(_ascii(a), w_mitad - 1) or [""]
        col_b = textwrap.wrap(_ascii(b), w_mitad - 1) or [""]
        for l, r in zip_longest(col_a, col_b, fillvalue=""):
            p.text(f"{l:<{w_mitad}}{r}".rstrip() + "\n")

    def titulo_seccion(texto):
        p.text("\n")
        estilo(align="left", bold=True)
        p.text(f"{_ascii(texto)}\n")
        estilo(bold=False)

    # ── LOGO ─────────────────────────────────────────────
    logo_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
        "image.png",
    )
    if os.path.exists(logo_path):
        try:
            estilo(align="center")
            p.image(_preparar_logo(logo_path, 380), impl="bitImageRaster", center=True)
            p.text("\n")
        except Exception as e:
            print(f"[WARN] No se pudo imprimir logo: {e}")

    # ── ENCABEZADO Y EMISOR ──────────────────────────────
    estilo(align="center", bold=True, width=2, height=2)
    p.text(f"{_ascii(datos.tipo_documento).upper()}\n")
    estilo(align="center", bold=True, width=1, height=1)
    p.text(f"Nº: {_ascii(datos.numero_factura)}\n\n")

    estilo(align="left", bold=False)

    if es_factura:
        dos_cols(f"Fecha: {datos.fecha_emision}", f"RUC: {datos.ruc_emisor}")
        if datos.nombre_comercial:
            for l in textwrap.wrap(f"Nombre Comercial: {_ascii(datos.nombre_comercial)}", ancho):
                p.text(l + "\n")
        if getattr(datos, "razon_social", None):
            for l in textwrap.wrap(f"Razon Social: {_ascii(datos.razon_social)}", ancho):
                p.text(l + "\n")
        if datos.direccion:
            for l in textwrap.wrap(f"Direccion: {_ascii(datos.direccion)}", ancho):
                p.text(l + "\n")
        
        p.text(f"Obligado a Llevar Contabilidad: {_ascii(datos.obligado_contabilidad)}\n")
        if datos.regimen:
            for l in textwrap.wrap(_ascii(datos.regimen), ancho):
                p.text(l + "\n")
        
        dos_cols(f"Emision: {datos.emision}", f"Ambiente: {datos.ambiente}")
        dos_cols(f"Estado: {datos.estado}", f"F. Aut.: {datos.fecha_autorizacion}")

        if datos.clave_acceso:
            p.text("\n")
            estilo(align="center", bold=True)
            p.text("Clave de Acceso:\n")
            estilo(align="center", bold=False)
            try:
                p.image(_imagen_codigo_barras(str(datos.clave_acceso), 380, 65),
                        impl="bitImageRaster", center=True)
            except Exception as e:
                print(f"[WARN] No se pudo generar codigo de barras: {e}")
            p.text(_ascii(datos.clave_acceso) + "\n")
            estilo(align="left")

        titulo_seccion("Informacion del Cliente")
        if getattr(datos, "razon_social_cliente", None):
            p.text(f"Razon Social: {_ascii(datos.razon_social_cliente)}\n")
        else:
            p.text(f"Cliente: {_ascii(datos.cliente_nombre)}\n")
        p.text(f"RUC/CI: {_ascii(datos.cliente_identificacion)}\n")

    else:
        dos_cols(f"Fecha: {datos.fecha_emision}", f"CI/RUC: {datos.cliente_identificacion}")
        p.text(f"Cliente: {_ascii(datos.cliente_nombre)}\n")
        p.text(f"Forma de Pago: {_ascii(datos.forma_pago)}\n")

    if datos.imeis_globales:
        for imei in datos.imeis_globales:
            p.text(f"  * {_ascii(imei)}\n")
    if datos.extra_details and datos.extra_details.strip() not in ["", "N/A"]:
        for l in textwrap.wrap(f"Detalles: {_ascii(datos.extra_details)}", ancho):
            p.text(l + "\n")

    # ── DETALLE DE PRODUCTOS ─────────────────────────────
    w_cant, w_total = 6, 11
    w_desc = ancho - w_cant - w_total

    titulo_seccion("Detalles de Productos")
    estilo(bold=True)
    p.text(f"{'Cant':<{w_cant}}{'Descripcion':<{w_desc}}{'Total':>{w_total}}\n")
    estilo(bold=False)

    for item in datos.items:
        cant = f"{item.cantidad:g}" if item.cantidad % 1 == 0 else f"{item.cantidad:.2f}"
        total = f"${item.total:.2f}"
        lineas_desc = textwrap.wrap(_ascii(item.descripcion), w_desc - 1) or [""]

        p.text(f"{cant:<{w_cant}}{lineas_desc[0]:<{w_desc}}{total:>{w_total}}\n")
        for extra in lineas_desc[1:]:
            p.text(f"{'':<{w_cant}}{extra}\n")
        if item.sku:
            p.text(f"{'':<{w_cant}}[SKU: {_ascii(item.sku)}]\n")
        if item.imeis:
            for imei in item.imeis:
                p.text(f"{'':<{w_cant}}IMEI: {_ascii(imei)}\n")

    p.text("\n")

    # ── TOTALES Y FORMA DE PAGO ──────────────────────────
    if es_factura:
        p.text(f"Subtotal: ${datos.subtotal:.2f}\n")
        p.text(f"IVA (15%): ${datos.iva:.2f}\n")
        p.text(f"Total: ${datos.total:.2f}\n")
        p.text(f"Forma de Pago: {_ascii(datos.forma_pago)}\n\n")
        estilo(bold=True)
        p.text(f"Total: ${datos.total:.2f}\n")
        estilo(bold=False)
    else:
        estilo(bold=True)
        p.text(f"Total: ${datos.total:.2f}\n")
        estilo(bold=False)
        if datos.clave_acceso:
            p.text("Clave de Acceso:\n")
            p.text(f"{_ascii(datos.clave_acceso)}\n")

    # ── PIE DE PAGINA ────────────────────────────────────
    p.text("\n")
    estilo(align="center")
    p.text("Gracias por su compra\n")
    p.text("Visita https://ventas.teamcellmania.com\n")
    p.text("para consultar tus Puntos\n")

    p.cut(feed=True)

    _copia_minimalista(p, datos, ancho, fuente, es_factura)

    return p.output


def _copia_minimalista(p, datos, ancho: int, fuente: str, es_factura: bool):
    """Copia compacta sin saltos de línea al cortar."""
    def st(**kw):
        p.set(font=fuente, **kw)

    def dos_cols_compacto(izq, der):
        m = ancho // 2
        l_wrap = textwrap.wrap(_ascii(izq), m - 1) or [""]
        r_wrap = textwrap.wrap(_ascii(der), m - 1) or [""]
        for l, r in zip_longest(l_wrap, r_wrap, fillvalue=""):
            p.text(f"{l:<{m}}{r}".rstrip() + "\n")

    st(align="left", bold=True)
    encabezado = f"{'FACTURA' if es_factura else 'RECIBO RESUMIDO'} Nº: {_ascii(datos.numero_factura)}"
    p.text(f"{encabezado}\n")
    st(bold=False)

    dos_cols_compacto(f"Fecha: {_ascii(datos.fecha_emision)}", f"CI/RUC: {_ascii(datos.cliente_identificacion)}")
    if es_factura and datos.ruc_emisor:
        p.text(f"RUC Emisor: {_ascii(datos.ruc_emisor)}\n")

    p.text(f"CLIENTE: {_ascii(datos.cliente_nombre)}\n")

    st(bold=True)
    w_cant = 6
    w_desc = ancho - w_cant
    p.text(f"{'Cant':<{w_cant}}Descripcion\n")
    st(bold=False)

    for item in datos.items:
        cant = f"{item.cantidad:g}" if item.cantidad % 1 == 0 else f"{item.cantidad:.2f}"
        lineas = textwrap.wrap(_ascii(item.descripcion), w_desc) or [""]
        p.text(f"{cant:<{w_cant}}{lineas[0]}\n")
        
        for extra in lineas[1:]:
            p.text(f"{'':<{w_cant}}{extra}\n")
            
        if item.sku:
            p.text(f"{'':<{w_cant}}[SKU: {_ascii(item.sku)}]\n")
        if item.imeis:
            for imei in item.imeis:
                p.text(f"{'':<{w_cant}}IMEI: {_ascii(imei)}\n")

    st(bold=True)
    p.text(f"TOTAL: ${datos.total:.2f}\n")
    st(bold=False)

    if datos.clave_acceso:
        p.text(f"{_ascii(datos.clave_acceso)}\n")
    if not es_factura:
        p.text(f"Pago: {_ascii(datos.forma_pago)}\n")

    p.cut(feed=True)