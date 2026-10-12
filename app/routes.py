# app/routes.py
"""
MÓDULO DE RUTAS (Endpoints de la API)
═══════════════════════════════════════════════════════════════════════════════

Endpoints disponibles:
    GET  /                          → Dashboard HTML (panel de control)
    GET  /api/status                → Estado del servicio (versión, config, uptime)
    GET  /api/config                → Contenido actual de config.json
    POST /api/config                → Guarda y recarga config.json en caliente

    POST /print                     → Imprime ticket genérico (uso interno/local)
    POST /print/payment             → Imprime comprobante de pago

    POST /                          → ] Tres rutas que apuntan a la misma
    POST /api/print                 → ] lógica de impresión de facturas/recibos.
    POST /facturacion/imprimir-factura → ] El backend Node.js usa /api/print.

    POST /facturacion/imprimir-deuda   → Deshabilitado temporalmente
    POST /facturacion/imprimir-pedido  → Deshabilitado temporalmente

IMPORTANTE — por qué hay tres rutas para imprimir facturas:
    FastAPI NO permite apilar varios @app.post() sobre la misma función
    (solo registra el primero correctamente). Por eso la lógica vive en
    _handle_imprimir_factura() y cada ruta tiene su propia función que
    la llama. Así los tres endpoints quedan registrados correctamente
    y aparecen en /docs.

    /                          → compatibilidad con clientes que usan la raíz
    /api/print                 → ruta principal que usa el backend Node.js
    /facturacion/imprimir-factura → ruta legacy (versiones anteriores)
═══════════════════════════════════════════════════════════════════════════════
"""

import json
import os
import time
import traceback
from typing import Dict, Any

from fastapi import FastAPI, Body, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, PlainTextResponse

from app.config import load_config
from app.printer.printer_service import PrinterService
from app.printer.models.factura import FacturaPrintRequest
from app.dashboard import DASHBOARD_HTML
from app.updater import CURRENT_VERSION


app = FastAPI(title="Print Service - Python")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _get_executable_dir() -> str:
    """
    Devuelve la carpeta donde vive el ejecutable o el script raíz.
    Cuando corre como .exe (PyInstaller frozen), usa la carpeta del .exe.
    En desarrollo, usa la raíz del proyecto (un nivel arriba de /app).
    """
    if getattr(os.sys, 'frozen', False) and hasattr(os.sys, '_MEIPASS'):
        return os.path.dirname(os.sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


CONFIG_PATH: str = os.path.join(_get_executable_dir(), "config.json")

if not os.path.exists(CONFIG_PATH):
    raise FileNotFoundError(
        f"config.json no existe en: {CONFIG_PATH}\n"
        "Crea el archivo en la carpeta donde está el .exe.\n"
        "Ver CONFIG_GUIDE.txt para la estructura completa."
    )

config          = load_config()
printer_service = PrinterService(config)

_last_reload: str  = time.strftime("%Y-%m-%d %H:%M:%S")
_start_time: float = time.time()

# ─────────────────────────────────────────────────────────────────────────────
# Endpoints — Panel y estado
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    """Panel de control HTML: muestra estado, config y permite recargar."""
    return DASHBOARD_HTML


@app.get("/api/status")
async def get_status():
    """
    Estado del servicio. El túnel llama a este endpoint para verificar
    que la URL pública sea accesible antes de registrarla en el backend.
    También lo usa el backend para health-checks.
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
    """Devuelve el contenido actual de config.json como texto plano."""
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            content = f.read()
        return PlainTextResponse(content, media_type="application/json")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/config")
async def save_config_and_reload(payload: Dict[str, Any] = Body(...)):
    """
    Guarda config.json y recarga la configuración en caliente.
    El dashboard usa este endpoint cuando el usuario edita la config.
    Body: { "raw": "<JSON como string>" }
    """
    global config, printer_service, _last_reload

    raw = payload.get("raw", "")

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"JSON inválido: {e}")

    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(parsed, f, ensure_ascii=False, indent=2)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"No se pudo escribir config.json: {e}")

    try:
        config          = load_config()
        printer_service = PrinterService(config)
        _last_reload    = time.strftime("%Y-%m-%d %H:%M:%S")
        print(f"[INFO] Config recargado en memoria a las {_last_reload}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Config guardado pero falló el reload: {e}")

    return {"success": True, "message": "Config guardado y recargado correctamente."}

# ─────────────────────────────────────────────────────────────────────────────
# Endpoints — Impresión genérica (uso local / dashboard)
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/print")
async def print_receipt(data: Dict[str, Any] = Body(...)):
    """Imprime un ticket genérico. Usado por el dashboard local."""
    try:
        result = printer_service.print_receipt(data)
        if not result.get("success", False):
            raise HTTPException(
                status_code=500,
                detail=result.get("message", "Error desconocido al imprimir"),
            )
        return result
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error en servidor al imprimir ticket: {str(e)}")


@app.post("/print/payment")
async def print_payment(data: Dict[str, Any] = Body(...)):
    """Imprime un comprobante de pago."""
    print(">>> DATA RECIBIDA:", data)
    try:
        result = printer_service.print_payment(data)
        print(">>> RESULTADO:", result)
        if not result.get("success", False):
            msg = result.get("message", "Error desconocido al imprimir comprobante")
            status = 422 if "faltantes" in msg else 500
            raise HTTPException(status_code=status, detail=msg)
        return result
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error en servidor al imprimir pago: {str(e)}")

# ─────────────────────────────────────────────────────────────────────────────
# Endpoints — Impresión Sistema de Facturación
# ─────────────────────────────────────────────────────────────────────────────

async def _handle_imprimir_factura(datos: Dict[str, Any]) -> dict:
    """
    Lógica compartida para imprimir facturas y recibos enviados por el
    backend Node.js (ms_facturas).

    Por qué existe esta función separada:
        FastAPI NO registra correctamente varios @app.post() apilados sobre
        la misma función (solo el primero queda activo). Al extraer la lógica
        aquí, cada ruta tiene su propia función decorada y las tres aparecen
        correctamente en /docs y responden sin 404.

    El backend Node.js llama a /api/print tanto para FACTURA como para RECIBO,
    usando el mismo payload (FacturaPrintRequest). printer_service.print_invoice()
    distingue el tipo por el campo tipo_documento.
    """
    print(">>> 📥 PAYLOAD RECIBIDO EN IMPRIMIR_FACTURA:")
    print(json.dumps(datos, indent=2, ensure_ascii=False))

    try:
        result = printer_service.print_invoice(datos)

        if not result.get("success", False):
            msg = result.get("message", "Error al imprimir factura")
            print(f">>> ❌ ERROR DESDE PRINTER_SERVICE: {msg}")
            raise HTTPException(status_code=500, detail=msg)

        print(">>> ✅ IMPRESIÓN PROCESADA CON ÉXITO")
        return result

    except HTTPException:
        raise
    except Exception as e:
        print(">>> 💥 EXCEPCIÓN INTERNA CAPTURADA:")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error interno procesando factura: {str(e)}")


@app.post("/")
async def imprimir_factura_root(datos: Dict[str, Any] = Body(...)):
    """
    Ruta raíz — compatibilidad con clientes que envían a la URL base
    sin path (algunos integrations viejos o tests).
    """
    return await _handle_imprimir_factura(datos)


@app.post("/api/print")
async def imprimir_factura_api(datos: Dict[str, Any] = Body(...)):
    """
    Ruta principal usada por el backend Node.js (ms_facturas).
    printFactura() y printRecibo() en print.service.js apuntan aquí.
    """
    return await _handle_imprimir_factura(datos)


@app.post("/facturacion/imprimir-factura")
async def imprimir_factura_legacy(datos: Dict[str, Any] = Body(...)):
    """
    Ruta legacy — usada por versiones anteriores del backend.
    Se mantiene para no romper integraciones existentes.
    """
    return await _handle_imprimir_factura(datos)


@app.post("/facturacion/imprimir-deuda")
async def imprimir_deuda(datos: Dict[str, Any] = Body(...)):
    """Placeholder — funcionalidad de impresión de deuda pendiente de implementar."""
    return {"success": True, "message": "Endpoint de deuda deshabilitado temporalmente"}


@app.post("/facturacion/imprimir-pedido")
async def imprimir_pedido(datos: Dict[str, Any] = Body(...)):
    """Placeholder — funcionalidad de impresión de pedido pendiente de implementar."""
    return {"success": True, "message": "Endpoint de pedido deshabilitado temporalmente"}


@app.post("/print/acquired")
async def print_acquired(data: Dict[str, Any] = Body(...)):
    """Imprime solo el ticket de taller con banner ADQUIRIDO (orden pasó a bodega)."""
    print(">>> 📥 PAYLOAD RECIBIDO EN /print/acquired:")
    print(json.dumps(data, indent=2, ensure_ascii=False, default=str))

    try:
        result = printer_service.print_acquired(data)
        if not result.get("success", False):
            raise HTTPException(
                status_code=500,
                detail=result.get("message", "Error desconocido al imprimir"),
            )
        return result
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error en servidor al imprimir ticket adquirido: {str(e)}")


