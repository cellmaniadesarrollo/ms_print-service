# app/routes.py
"""
MÓDULO DE RUTAS (Endpoints de la API)
═══════════════════════════════════════════════════════════════════════════════

¿Qué hace este módulo?
    Define todos los endpoints HTTP de la aplicación usando FastAPI.
    Aquí se registran las rutas que el cliente (navegador, POS, etc.) puede
    llamar, junto con su lógica de negocio.

Rutas disponibles:
    GET  /              → Dashboard web (HTML)
    GET  /api/status    → Estado actual del servicio (JSON)
    GET  /api/config    → Contenido crudo del config.json (JSON)
    POST /api/config    → Guarda y recarga la configuración (JSON)
    POST /print         → Imprime un ticket en la impresora térmica (JSON)

¿Qué es un endpoint?
    Es una URL a la que el cliente envía una petición HTTP.
    Cada petición tiene un método (GET, POST, PUT, DELETE...).
    GET  → "dame información"
    POST → "toma estos datos y haz algo con ellos"

¿Qué es async def?
    FastAPI es asíncrono. "async def" define una función que puede
    pausarse mientras espera I/O (disco, red) sin bloquear otras peticiones.
    Para funciones de CPU pura se puede usar "def" normal también.

¿Qué es Body(...)?
    Le dice a FastAPI que el parámetro viene en el cuerpo (body) de la
    petición HTTP en formato JSON. El "..." significa que es obligatorio.

¿Qué es HTTPException?
    Es la forma de FastAPI de devolver errores HTTP con código de estado.
    HTTPException(status_code=500, detail="mensaje") → responde con HTTP 500.

Notas para novatos:
    - response_class=HTMLResponse → la respuesta es texto HTML, no JSON.
    - PlainTextResponse → respuesta como texto plano (útil para mostrar JSON
      sin que FastAPI lo re-serialice y pierda el formato).
    - Dict[str, Any] → un diccionario Python con claves string y valores
      de cualquier tipo (tipado de Python).
═══════════════════════════════════════════════════════════════════════════════
"""

import json
import os
import time
from typing import Dict, Any

from fastapi import FastAPI, Body, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, PlainTextResponse

from app.config import load_config
from app.printer import PrinterService
from app.dashboard import DASHBOARD_HTML
from app.updater import CURRENT_VERSION


# ─────────────────────────────────────────────────────────────────────────────
# Instancia de FastAPI
# ─────────────────────────────────────────────────────────────────────────────

# FastAPI() crea la aplicación. El parámetro title aparece en la
# documentación automática que FastAPI genera en /docs
app = FastAPI(title="Print Service - Python")

# ── CORS ─────────────────────────────────────────────────────────────────────
# CORS (Cross-Origin Resource Sharing) controla qué orígenes pueden
# llamar a esta API desde el navegador.
# allow_origins=["*"] → cualquier dominio puede llamar a la API.
# En producción con datos sensibles deberías restringirlo a tu dominio.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers internos del módulo
# ─────────────────────────────────────────────────────────────────────────────

def _get_executable_dir() -> str:
    """
    Devuelve la carpeta raíz del proyecto (o del .exe en producción).
    Usada para construir la ruta absoluta del config.json.
    """
    if getattr(os.sys, 'frozen', False) and hasattr(os.sys, '_MEIPASS'):
        # Modo .exe: el config.json debe estar junto al ejecutable
        return os.path.dirname(os.sys.executable)
    # Modo desarrollo: sube un nivel desde app/ → raíz del proyecto
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ─────────────────────────────────────────────────────────────────────────────
# Estado compartido del módulo
# ─────────────────────────────────────────────────────────────────────────────

# Ruta absoluta al archivo de configuración
CONFIG_PATH: str = os.path.join(_get_executable_dir(), "config.json")

if not os.path.exists(CONFIG_PATH):
    raise FileNotFoundError(
        f"config.json no existe en: {CONFIG_PATH}\n"
        "Crea el archivo en la carpeta donde está el .exe.\n"
        "Ver CONFIG_GUIDE.txt para la estructura completa."
    )

# Cargamos la config y creamos el servicio de impresión al importar el módulo.
# "global" aquí no hace falta porque las modificaciones se hacen dentro de
# los endpoints mediante asignación directa a las variables del módulo.
config          = load_config()
printer_service = PrinterService(config)

# Metadatos de estado
_last_reload: str  = time.strftime("%Y-%m-%d %H:%M:%S")  # hora del último reload
_start_time: float = time.time()                          # timestamp de arranque


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints — Dashboard (interfaz web)
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    """
    Devuelve el panel de administración como página HTML.

    GET https://localhost:56789/
    """
    return DASHBOARD_HTML


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints — API de estado y configuración
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/api/status")
async def get_status():
    """
    Devuelve el estado actual del servicio en formato JSON.

    Útil para saber de un vistazo: versión, conexión, papel configurado,
    tiempo de actividad, etc. El dashboard lo llama periódicamente.

    GET https://localhost:56789/api/status
    """
    return {
        "status":         "ok",
        "version":        f"v{CURRENT_VERSION}",
        "connection":     config.connection,
        "network_ip":     config.network.ip   if config.network else None,
        "network_port":   config.network.port if config.network else None,
        "usb_vid":        config.usb.vid if config.usb else None,
        "usb_pid":        config.usb.pid if config.usb else None,
        "paper_width_mm": 80 if config.paper_px == 512 else 58,
        "paper_px":       config.paper_px,
        "encoding":       config.encoding,
        "config_path":    CONFIG_PATH,
        "last_reload":    _last_reload,
        "uptime_seconds": round(time.time() - _start_time),
    }


@app.get("/api/config")
async def get_config_raw():
    """
    Lee y devuelve el contenido del config.json tal cual está en disco.

    Se devuelve como texto plano con Content-Type application/json para
    que el editor del dashboard pueda mostrarlo y editarlo.

    GET https://localhost:56789/api/config
    """
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            content = f.read()
        return PlainTextResponse(content, media_type="application/json")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/config")
async def save_config_and_reload(payload: Dict[str, Any] = Body(...)):
    """
    Guarda el config.json editado y recarga la config en memoria
    sin necesidad de reiniciar la aplicación.

    Body esperado (JSON):
        { "raw": "{ ...contenido del config.json... }" }

    Flujo:
        1. Valida que "raw" sea JSON válido.
        2. Escribe el nuevo contenido en config.json.
        3. Recarga config y reinicia el PrinterService.

    POST https://localhost:56789/api/config
    """
    # Importamos global para poder reasignar las variables del módulo
    global config, printer_service, _last_reload

    raw = payload.get("raw", "")

    # ── Validar JSON ──────────────────────────────────────────────────────────
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"JSON inválido: {e}")

    # ── Escribir en disco ─────────────────────────────────────────────────────
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(parsed, f, ensure_ascii=False, indent=2)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"No se pudo escribir config.json: {e}")

    # ── Recargar en memoria ───────────────────────────────────────────────────
    try:
        config          = load_config()
        printer_service = PrinterService(config)
        _last_reload    = time.strftime("%Y-%m-%d %H:%M:%S")
        print(f"[INFO] Config recargado en memoria a las {_last_reload}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Config guardado pero falló el reload: {e}")

    return {"success": True, "message": "Config guardado y recargado correctamente."}


# ─────────────────────────────────────────────────────────────────────────────
# Endpoint — Impresión
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/print")
async def print_receipt(data: Dict[str, Any] = Body(...)):
    """
    Recibe los datos de un ticket y los envía a la impresora térmica.

    El cuerpo de la petición debe seguir el esquema de ticket definido
    en la documentación del PrinterService.

    Si la impresión falla, devuelve HTTP 500 con el detalle del error.

    POST https://localhost:56789/print
    Body: { ...datos del ticket... }
    """
    result = printer_service.print_receipt(data)

    if not result.get("success", False):
        raise HTTPException(
            status_code=500,
            detail=result.get("message", "Error desconocido al imprimir"),
        )

    return result

@app.post("/print/payment") 
async def print_payment(data: Dict[str, Any] = Body(...)):
    """
    Imprime un comprobante de abono/adelanto sobre una orden de servicio.
 
    El cuerpo debe ser la transacción completa tal como la devuelve el backend,
    incluyendo los sub-objetos `order`, `paymentType`, `paymentMethod` y
    `receivedBy` anidados.
 
    La validación del esquema se hace en PrinterService con Pydantic;
    si algún campo requerido falta, se devuelve HTTP 422 con el detalle.
 
    POST https://localhost:56789/print/payment
    Body: { ...datos de la transacción... }
    """
    print(">>> DATA RECIBIDA:", data)          # ← añadir esto
    result = printer_service.print_payment(data)
    print(">>> RESULTADO:", result)             # ← y esto
    if not result.get("success", False):
        msg = result.get("message", "Error desconocido al imprimir comprobante")
        status = 422 if "faltantes" in msg else 500
        raise HTTPException(status_code=status, detail=msg)
    return result