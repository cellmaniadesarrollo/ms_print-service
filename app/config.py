# app/config.py
"""
Carga y valida la configuración desde config.json (ubicado al lado del ejecutable o en la raíz del proyecto).

Estructura de archivos esperada:
    carpeta_del_ejecutable/   ← o raíz del proyecto en desarrollo
        config.json           ← archivo de configuración
        print-service.exe     ← el .exe compilado
        certs/
        icon.png

Ver CONFIG_GUIDE.txt en la raíz para la documentación completa
de todas las opciones disponibles.
"""

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path


# ─────────────────────────────────────────────────────────────────────────────
# Dataclasses — equivalente a interfaces/DTOs en TypeScript
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class NetworkConfig:
    ip: str
    port: int
    timeout: int  # segundos antes de considerar la conexión fallida


@dataclass
class UsbConfig:
    vid: int   # Vendor ID  (ej: 0x04b8 para Epson)
    pid: int   # Product ID (ej: 0x0202 para TM-T88V)


@dataclass
class TicketLayout:
    total_width_override: int | None  # None = usar paper_px automático
    text_pct: int                     # % del ancho para el texto (0-100)


@dataclass
class TicketConfig:
    layout: TicketLayout
    footer_lines: list[str]   # líneas del pie del ticket del cliente
    wednesday_promo: str      # texto promo miércoles (vacío = sin promo)
    qr_base_url: str          # URL base para el QR de seguimiento


@dataclass
class Features:
    print_analysis_image: bool       # imprimir assets/analisis.png
    print_qr: bool                   # imprimir código QR
    print_pattern_on_customer: bool  # mostrar patrón en texto en ticket cliente
    print_wednesday_promo: bool      # activar promo del miércoles


@dataclass
class AppConfig:
    connection: str               # "network" | "usb"
    encoding: str                 # encoding de la impresora
    paper_px: int                 # ancho imprimible calculado en píxeles
    network: NetworkConfig | None
    usb: UsbConfig | None
    ticket: TicketConfig
    features: Features


# ─────────────────────────────────────────────────────────────────────────────
# Conversión mm → píxeles (203 DPI estándar para impresoras térmicas)
# ─────────────────────────────────────────────────────────────────────────────

def _mm_to_px(mm: int) -> int:
    """
    Convierte el ancho del papel en mm a píxeles imprimibles.

    Tabla de referencia (203 DPI):
        58 mm → 384 px
        80 mm → 512 px

    Si tu impresora da error "Image width is too large (N > 512)",
    reduce paperWidth en config.json o usa totalWidthOverride.
    """
    if mm <= 58:
        return 384
    return 512


# ─────────────────────────────────────────────────────────────────────────────
# Función para obtener la carpeta real del ejecutable o del script
# ─────────────────────────────────────────────────────────────────────────────

def get_executable_dir() -> Path:
    """
    Devuelve la carpeta donde está el .exe (modo bundled) o el directorio del script (desarrollo).
    Esto asegura que config.json se busque en la ubicación correcta.
    """
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        # Modo .exe compilado con PyInstaller
        return Path(sys.executable).parent
    else:
        # Modo desarrollo (poetry run ...)
        return Path(__file__).parent.parent


# ─────────────────────────────────────────────────────────────────────────────
# Parsers de cada sección del JSON
# ─────────────────────────────────────────────────────────────────────────────

def _parse_network(raw: dict) -> NetworkConfig:
    net = raw.get("network") or {}
    ip = net.get("ip")
    if not ip:
        raise ValueError(
            "config.json → network.ip es obligatorio cuando connection='network'.\n"
            "Ejemplo: \"ip\": \"192.168.0.101\""
        )
    return NetworkConfig(
        ip=ip,
        port=int(net.get("port", 9100)),
        timeout=int(net.get("timeout", 10)),
    )


def _parse_usb(raw: dict) -> UsbConfig:
    usb = raw.get("usb") or {}
    vid = usb.get("vid")
    pid = usb.get("pid")
    if not vid or not pid:
        raise ValueError(
            "config.json → usb.vid y usb.pid son obligatorios cuando connection='usb'.\n"
            "Ejemplo: \"vid\": 1208, \"pid\": 514"
        )
    return UsbConfig(vid=vid, pid=pid)


def _parse_ticket(raw: dict) -> TicketConfig:
    ticket = raw.get("ticket") or {}
    layout = ticket.get("workshopLayout") or {}
    footer = ticket.get("footer") or {}
    promos = ticket.get("promotions") or {}

    default_footer = [
        "- Costo minimo revision: $4 (puede variar)",
        "- En la reparacion se utilizan materiales,",
        "  herramientas y tiempo.",
        "- Tiempo maximo para retirar",
        "  el dispositivo: 3 meses.",
    ]

    return TicketConfig(
        layout=TicketLayout(
            total_width_override=layout.get("totalWidthOverride"),
            text_pct=int(layout.get("textPct", 80)),
        ),
        footer_lines=footer.get("lines") or default_footer,
        wednesday_promo=promos.get("wednesday", "*** HOY MICA GRATIS ***"),
        qr_base_url=(ticket.get("qrBaseUrl") or "").rstrip("/"),
    )


def _parse_features(raw: dict) -> Features:
    feat = raw.get("features") or {}
    return Features(
        print_analysis_image=bool(feat.get("printAnalysisImage", True)),
        print_qr=bool(feat.get("printQr", True)),
        print_pattern_on_customer=bool(feat.get("printPatternOnCustomerTicket", True)),
        print_wednesday_promo=bool(feat.get("printWednesdayPromo", True)),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Función principal de carga
# ─────────────────────────────────────────────────────────────────────────────

def load_config() -> AppConfig:
    """
    Lee config.json desde la carpeta del ejecutable (o raíz del proyecto en dev)
    y retorna un objeto AppConfig validado.

    Raises:
        FileNotFoundError: si no existe config.json
        ValueError:        si el JSON está malformado o faltan campos obligatorios
    """
    config_path = get_executable_dir() / "config.json"

    if not config_path.exists():
        raise FileNotFoundError(
            f"No se encontró config.json en: {config_path}\n"
            "Crea el archivo en la carpeta donde está el .exe (o en la raíz del proyecto).\n"
            "Ver CONFIG_GUIDE.txt para la estructura completa."
        )

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"config.json tiene formato JSON inválido: {e}")

    connection = raw.get("connection", "network").lower()
    encoding   = raw.get("encoding", "utf-8")
    paper_mm   = int(raw.get("paperWidth", 80))
    paper_px   = _mm_to_px(paper_mm)

    network_cfg = None
    usb_cfg     = None

    if connection == "network":
        network_cfg = _parse_network(raw)
    elif connection == "usb":
        usb_cfg = _parse_usb(raw)
    else:
        raise ValueError(
            f"config.json → connection='{connection}' no es válido.\n"
            "Valores aceptados: 'network' o 'usb'."
        )

    config = AppConfig(
        connection=connection,
        encoding=encoding,
        paper_px=paper_px,
        network=network_cfg,
        usb=usb_cfg,
        ticket=_parse_ticket(raw),
        features=_parse_features(raw),
    )

    print(f"✓ Config cargado → {connection.upper()} | papel {paper_mm}mm ({paper_px}px) | encoding {encoding}")
    return config