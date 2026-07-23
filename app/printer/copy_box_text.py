# app/printer/copy_box_text.py
"""
Versión en texto plano del recuadro '*** COPIA ***'.

Se usa en vez de build_copy_box_image() para reducir el volumen de bytes
enviados a la impresora (texto ESC/POS nativo vs. bitmap), evitando cortes
por buffer en impresoras de red más lentas.
"""


def print_copy_box_text(
    printer,
    printed_by: str,
    copy_printed_at: str,
    requested_by: str = "",
    width_chars: int = 48,
) -> None:
    """
    width_chars: caracteres útiles por línea con font='b' (la misma fuente
    que usas en el resto del ticket). Ajusta si el borde no calza bien:
        - 80mm con font 'b' → normalmente 56-64
        - 80mm con font 'a' → normalmente 42-48
        - 58mm con font 'b' → normalmente 32-35
    """
    inner = width_chars - 2
    border = "+" + "-" * inner + "+"

    lines = [(" *** COPIA *** ", True)]
    lines.append((f"{printed_by} | {copy_printed_at}", False))
    if requested_by:
        lines.append((f"Solicitada por: {requested_by}", False))

    printer.set(align="left", font="b", width=1, height=1, bold=False)
    printer.text(border + "\n")

    for text, bold in lines:
        text = text.strip()[: inner - 2]
        padded = text.center(inner - 2)
        printer.set(font="b", width=1, height=1, bold=bold)
        printer.text(f"|{padded}|\n")

    printer.set(bold=False, font="b", width=1, height=1)
    printer.text(border + "\n")