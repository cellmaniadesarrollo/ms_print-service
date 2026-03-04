# app/main.py
"""
PUNTO DE ENTRADA DE LA APLICACIÓN
══════════════════════════════════
Este es el archivo principal. Cuando corres el servidor con Poetry,
este archivo es el primero en ejecutarse.
"""

import os
import sys
import json
import threading
import asyncio
import time
from typing import Dict, Any

import uvicorn
from uvicorn import Server, Config
from fastapi import FastAPI, Body, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from dotenv import load_dotenv

# ── Importaciones propias ────────────────────────────────────────────────────
from app.config import load_config
from app.printer import PrinterService

# ── Bandeja del sistema ──────────────────────────────────────────────────────
import pystray
from PIL import Image

# ── Soporte para .exe (PyInstaller) ──────────────────────────────────────────
if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
    base_path = sys._MEIPASS
    capabilities_path = os.path.join(base_path, 'escpos', 'capabilities.json')
    os.environ['ESCPOS_CAPABILITIES_FILE'] = capabilities_path
    print(f"[DEBUG] Modo bundled: capabilities.json en {capabilities_path}")

if '--noconsole' in sys.argv or not sys.stdout:
    sys.stdout = open(os.devnull, 'w', encoding='utf-8')
    sys.stderr = open(os.devnull, 'w', encoding='utf-8')


# ─────────────────────────────────────────────────────────────────────────────
# Función para obtener la carpeta real del ejecutable
# ─────────────────────────────────────────────────────────────────────────────
def get_executable_dir():
    """Devuelve la carpeta donde está el .exe (o la raíz del proyecto en dev)."""
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        return os.path.dirname(sys.executable)
    else:
        # En desarrollo: subimos dos niveles desde app/main.py → raíz del proyecto
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ─────────────────────────────────────────────────────────────────────────────
# 1. CARGAR VARIABLES DE ENTORNO
# ─────────────────────────────────────────────────────────────────────────────
load_dotenv()

# ─────────────────────────────────────────────────────────────────────────────
# 2. CREAR LA APLICACIÓN FASTAPI
# ─────────────────────────────────────────────────────────────────────────────
app = FastAPI(title="Print Service - Python")

# ─────────────────────────────────────────────────────────────────────────────
# 3. CONFIGURAR CORS
# ─────────────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─────────────────────────────────────────────────────────────────────────────
# 4. INICIALIZAR CONFIGURACIÓN Y SERVICIO
# ─────────────────────────────────────────────────────────────────────────────
CONFIG_PATH = os.path.join(get_executable_dir(), "config.json")

if not os.path.exists(CONFIG_PATH):
    raise FileNotFoundError(
        f"config.json no existe en: {CONFIG_PATH}\n"
        "Crea el archivo en la carpeta donde está el .exe.\n"
        "Ver CONFIG_GUIDE.txt para la estructura completa."
    )

config = load_config()
printer_service = PrinterService(config)

# Timestamp del último reload
_last_reload: str = time.strftime("%Y-%m-%d %H:%M:%S")
_start_time: float = time.time()

# ─────────────────────────────────────────────────────────────────────────────
# 5. DASHBOARD HTML
# ─────────────────────────────────────────────────────────────────────────────

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Print Service — Panel</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@300;400;600&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg:       #0d0f12;
      --surface:  #151820;
      --border:   #252a35;
      --accent:   #00e5a0;
      --warn:     #f5a623;
      --danger:   #ff4d4d;
      --text:     #c8d0e0;
      --muted:    #5a6478;
      --mono:     'IBM Plex Mono', monospace;
      --sans:     'IBM Plex Sans', sans-serif;
    }

    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

    body {
      background: var(--bg);
      color: var(--text);
      font-family: var(--sans);
      min-height: 100vh;
      padding: 32px 24px;
    }

    /* ── Header ── */
    header {
      display: flex;
      align-items: center;
      gap: 16px;
      margin-bottom: 40px;
      padding-bottom: 20px;
      border-bottom: 1px solid var(--border);
    }
    .logo {
      width: 36px; height: 36px;
      background: var(--accent);
      border-radius: 6px;
      display: flex; align-items: center; justify-content: center;
      font-size: 18px; flex-shrink: 0;
    }
    header h1 {
      font-family: var(--mono);
      font-size: 1rem;
      font-weight: 600;
      letter-spacing: 0.05em;
      color: #fff;
    }
    header p {
      font-size: 0.75rem;
      color: var(--muted);
      font-family: var(--mono);
      margin-top: 2px;
    }
    .status-pill {
      margin-left: auto;
      display: flex;
      align-items: center;
      gap: 8px;
      background: #0a1f16;
      border: 1px solid #1a4a30;
      border-radius: 100px;
      padding: 6px 14px;
      font-family: var(--mono);
      font-size: 0.72rem;
      color: var(--accent);
      flex-shrink: 0;
    }
    .dot {
      width: 7px; height: 7px;
      border-radius: 50%;
      background: var(--accent);
      animation: pulse 2s infinite;
    }
    @keyframes pulse {
      0%, 100% { opacity: 1; }
      50%       { opacity: 0.3; }
    }

    /* ── Layout ── */
    .grid {
      display: grid;
      grid-template-columns: 1fr 1fr 1fr;
      gap: 16px;
      margin-bottom: 24px;
    }
    @media (max-width: 900px) {
      .grid { grid-template-columns: 1fr 1fr; }
    }
    @media (max-width: 580px) {
      .grid { grid-template-columns: 1fr; }
    }

    /* ── Cards ── */
    .card {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 20px 22px;
    }
    .card-label {
      font-family: var(--mono);
      font-size: 0.65rem;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      color: var(--muted);
      margin-bottom: 8px;
    }
    .card-value {
      font-family: var(--mono);
      font-size: 1.05rem;
      font-weight: 600;
      color: #fff;
    }
    .card-value.accent { color: var(--accent); }
    .card-value.warn   { color: var(--warn); }

    .card-sub {
      font-size: 0.72rem;
      color: var(--muted);
      margin-top: 4px;
      font-family: var(--mono);
    }

    /* ── Editor section ── */
    .editor-wrap {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 10px;
      overflow: hidden;
    }
    .editor-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 14px 20px;
      border-bottom: 1px solid var(--border);
      background: #111318;
    }
    .editor-title {
      font-family: var(--mono);
      font-size: 0.78rem;
      font-weight: 600;
      color: #fff;
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .editor-title span {
      color: var(--muted);
      font-weight: 400;
    }

    .btn-group { display: flex; gap: 10px; }

    button {
      font-family: var(--mono);
      font-size: 0.72rem;
      font-weight: 500;
      padding: 7px 16px;
      border-radius: 6px;
      border: none;
      cursor: pointer;
      transition: opacity 0.15s, transform 0.1s;
      letter-spacing: 0.04em;
    }
    button:active { transform: scale(0.97); }

    .btn-primary {
      background: var(--accent);
      color: #0d1a12;
    }
    .btn-secondary {
      background: transparent;
      border: 1px solid var(--border);
      color: var(--muted);
    }
    .btn-secondary:hover { border-color: var(--text); color: var(--text); }
    button:disabled { opacity: 0.4; cursor: not-allowed; }

    #editor {
      width: 100%;
      min-height: 440px;
      background: #0d0f12;
      color: #a8d5b5;
      font-family: var(--mono);
      font-size: 0.82rem;
      line-height: 1.7;
      padding: 20px 24px;
      border: none;
      outline: none;
      resize: vertical;
      tab-size: 2;
      white-space: pre;
      overflow-x: auto;
    }
    #editor:focus { box-shadow: inset 0 0 0 2px #00e5a020; }

    /* ── Toast / Feedback ── */
    #toast {
      position: fixed;
      bottom: 28px;
      right: 28px;
      padding: 12px 20px;
      border-radius: 8px;
      font-family: var(--mono);
      font-size: 0.75rem;
      font-weight: 500;
      max-width: 320px;
      opacity: 0;
      transform: translateY(12px);
      transition: opacity 0.25s, transform 0.25s;
      pointer-events: none;
      z-index: 100;
    }
    #toast.show { opacity: 1; transform: translateY(0); }
    #toast.ok   { background: #0a2a1a; border: 1px solid #1a5a30; color: var(--accent); }
    #toast.err  { background: #2a0a0a; border: 1px solid #5a1a1a; color: var(--danger); }
    #toast.warn { background: #2a1a00; border: 1px solid #5a3a00; color: var(--warn); }

    /* ── Countdown ── */
    #countdown {
      display: none;
      font-family: var(--mono);
      font-size: 0.72rem;
      color: var(--warn);
      margin-left: 12px;
    }

    /* ── Footer ── */
    footer {
      margin-top: 32px;
      padding-top: 20px;
      border-top: 1px solid var(--border);
      font-family: var(--mono);
      font-size: 0.65rem;
      color: var(--muted);
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
  </style>
</head>
<body>

<header>
  <div class="logo">🖨</div>
  <div>
    <h1>PRINT SERVICE</h1>
    <p id="uptime-label">calculando uptime...</p>
  </div>
  <div class="status-pill">
    <div class="dot"></div>
    ONLINE
  </div>
</header>

<!-- Status cards -->
<div class="grid" id="cards">
  <div class="card">
    <div class="card-label">Conexión</div>
    <div class="card-value accent" id="s-connection">—</div>
    <div class="card-sub" id="s-conn-detail">—</div>
  </div>
  <div class="card">
    <div class="card-label">Papel</div>
    <div class="card-value" id="s-paper">—</div>
    <div class="card-sub" id="s-encoding">—</div>
  </div>
  <div class="card">
    <div class="card-label">Último reload</div>
    <div class="card-value warn" id="s-reload">—</div>
    <div class="card-sub" id="s-uptime">—</div>
  </div>
</div>

<!-- Config editor -->
<div class="editor-wrap">
  <div class="editor-header">
    <div class="editor-title">
      config.json <span id="config-path"></span>
    </div>
    <div style="display:flex; align-items:center;">
      <span id="countdown"></span>
      <div class="btn-group">
        <button class="btn-secondary" onclick="reloadFromDisk()">↺ Recargar</button>
        <button class="btn-primary"  id="save-btn" onclick="saveConfig()">Guardar y reiniciar</button>
      </div>
    </div>
  </div>
  <textarea id="editor" spellcheck="false"></textarea>
</div>

<footer>
  <span>Print Service v1.0 — FastAPI + uvicorn</span>
  <span id="footer-port"></span>
</footer>

<div id="toast"></div>

<script>
  const port = location.port || (location.protocol === 'https:' ? 443 : 80);
  document.getElementById('footer-port').textContent = `https://localhost:${port}`;

  // ── Fetch status ──────────────────────────────────────────────────────────
  async function fetchStatus() {
    try {
      const r = await fetch('/api/status');
      const d = await r.json();

      document.getElementById('s-connection').textContent = d.connection.toUpperCase();
      document.getElementById('s-conn-detail').textContent =
        d.connection === 'network'
          ? `${d.network_ip}:${d.network_port}`
          : `VID:${d.usb_vid}  PID:${d.usb_pid}`;

      document.getElementById('s-paper').textContent = `${d.paper_width_mm}mm / ${d.paper_px}px`;
      document.getElementById('s-encoding').textContent = `encoding: ${d.encoding}`;
      document.getElementById('s-reload').textContent = d.last_reload;
      document.getElementById('s-uptime').textContent = `uptime: ${formatUptime(d.uptime_seconds)}`;
      document.getElementById('config-path').textContent = d.config_path;
      document.getElementById('uptime-label').textContent = `uptime ${formatUptime(d.uptime_seconds)}`;
    } catch(e) {
      console.warn('Status fetch failed', e);
    }
  }

  function formatUptime(secs) {
    const h = Math.floor(secs / 3600);
    const m = Math.floor((secs % 3600) / 60);
    const s = Math.floor(secs % 60);
    if (h > 0) return `${h}h ${m}m`;
    if (m > 0) return `${m}m ${s}s`;
    return `${s}s`;
  }

  // ── Load config into editor ───────────────────────────────────────────────
  async function reloadFromDisk() {
    try {
      const r = await fetch('/api/config');
      const text = await r.text();
      document.getElementById('editor').value = text;
      toast('Config recargado desde disco', 'ok');
    } catch(e) {
      toast('Error al cargar config', 'err');
    }
  }

  // ── Save config ───────────────────────────────────────────────────────────
  async function saveConfig() {
    const raw = document.getElementById('editor').value;

    // Validate JSON before sending
    try {
      JSON.parse(raw);
    } catch(e) {
      toast(`JSON inválido: ${e.message}`, 'err');
      return;
    }

    const btn = document.getElementById('save-btn');
    btn.disabled = true;
    btn.textContent = 'Guardando...';

    try {
      const r = await fetch('/api/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ raw })
      });
      const d = await r.json();

      if (d.success) {
        toast('✓ Config guardado y recargado correctamente', 'ok');
        await fetchStatus();
      } else {
        toast(`Error: ${d.message}`, 'err');
      }
    } catch(e) {
      toast('Error al guardar', 'err');
    } finally {
      btn.disabled = false;
      btn.textContent = 'Guardar y recargar';
    }
  }

  // ── Toast helper ──────────────────────────────────────────────────────────
  let _toastTimer;
  function toast(msg, type = 'ok') {
    const el = document.getElementById('toast');
    el.textContent = msg;
    el.className = `show ${type}`;
    clearTimeout(_toastTimer);
    _toastTimer = setTimeout(() => { el.className = ''; }, 3500);
  }

  // ── Tab key in editor ─────────────────────────────────────────────────────
  document.getElementById('editor').addEventListener('keydown', e => {
    if (e.key === 'Tab') {
      e.preventDefault();
      const el = e.target;
      const s = el.selectionStart, end = el.selectionEnd;
      el.value = el.value.substring(0, s) + '  ' + el.value.substring(end);
      el.selectionStart = el.selectionEnd = s + 2;
    }
  });

  // ── Init ──────────────────────────────────────────────────────────────────
  fetchStatus();
  reloadFromDisk();
  setInterval(fetchStatus, 5000);
</script>
</body>
</html>
"""


# ─────────────────────────────────────────────────────────────────────────────
# 6. ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    return DASHBOARD_HTML


@app.get("/api/status")
async def get_status():
    """Devuelve el estado actual del servicio y la config cargada."""
    return {
        "status": "ok",
        "connection": config.connection,
        "network_ip":   config.network.ip   if config.network else None,
        "network_port": config.network.port if config.network else None,
        "usb_vid": config.usb.vid if config.usb else None,
        "usb_pid": config.usb.pid if config.usb else None,
        "paper_width_mm": 80 if config.paper_px == 512 else 58,
        "paper_px":  config.paper_px,
        "encoding":  config.encoding,
        "config_path": CONFIG_PATH,
        "last_reload": _last_reload,
        "uptime_seconds": round(time.time() - _start_time),
    }


@app.get("/api/config")
async def get_config_raw():
    """Devuelve el contenido crudo de config.json."""
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            content = f.read()
        from fastapi.responses import PlainTextResponse
        return PlainTextResponse(content, media_type="application/json")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/config")
async def save_config_and_reload(payload: Dict[str, Any] = Body(...)):
    """
    Guarda el JSON recibido en config.json y recarga la configuración
    en memoria sin reiniciar el proceso.
    """
    global config, printer_service, _last_reload

    raw = payload.get("raw", "")

    # 1. Validar que sea JSON válido
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"JSON inválido: {e}")

    # 2. Escribir al disco
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(parsed, f, ensure_ascii=False, indent=2)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"No se pudo escribir config.json: {e}")

    # 3. Recargar config y servicio en memoria (sin reiniciar el proceso)
    try:
        config          = load_config()
        printer_service = PrinterService(config)
        _last_reload    = time.strftime("%Y-%m-%d %H:%M:%S")
        print(f"[INFO] Config recargado en memoria a las {_last_reload}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Config guardado pero falló el reload: {e}")

    return {"success": True, "message": "Config guardado y recargado correctamente."}


@app.post("/print")
async def print_receipt(data: Dict[str, Any] = Body(...)):
    result = printer_service.print_receipt(data)
    if not result.get("success", False):
        raise HTTPException(status_code=500, detail=result.get("message", "Error desconocido"))
    return result


# ─────────────────────────────────────────────────────────────────────────────
# 7. SERVIDOR EN BACKGROUND (con event loop propio)
# ─────────────────────────────────────────────────────────────────────────────

def run_server():
    """Corre el servidor FastAPI/uvicorn en este thread con su propio event loop."""
    port = int(os.getenv("PORT", "56789"))
    key_file  = os.getenv("SSL_KEYFILE",  "certs/server.key")
    cert_file = os.getenv("SSL_CERTFILE", "certs/server.pem")

    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        base_path = sys._MEIPASS
        key_file  = os.path.join(base_path, key_file)
        cert_file = os.path.join(base_path, cert_file)

    print(f"[INFO] Iniciando servidor HTTPS en puerto {port}")
    print(f"[INFO] Dashboard: https://localhost:{port}/")

    config_uvi = Config(
        app=app,
        host="0.0.0.0",
        port=port,
        ssl_keyfile=key_file,
        ssl_certfile=cert_file,
        log_level="info",
    )
    server = Server(config_uvi)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(server.serve())
    except Exception as e:
        print(f"[ERROR] Falló el servidor: {e}")
    finally:
        loop.close()


def run_server_in_thread():
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    time.sleep(2.5)
    print("[INFO] Thread del servidor lanzado")


# ─────────────────────────────────────────────────────────────────────────────
# 8. BANDEJA DEL SISTEMA
# ─────────────────────────────────────────────────────────────────────────────

def setup_tray():
    icon_path = "icon.png"
    image = Image.open(icon_path) if os.path.exists(icon_path) else Image.new('RGB', (64, 64), color=(0, 128, 255))

    def on_exit(icon, item):
        icon.stop()
        os._exit(0)

    def on_status(icon, item):
        import webbrowser
        port = int(os.getenv("PORT", "56789"))
        webbrowser.open(f"https://localhost:{port}/")

    menu = pystray.Menu(
        pystray.MenuItem("Abrir Panel", on_status),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Salir", on_exit)
    )

    icon = pystray.Icon("print-service", image, "Print Service", menu)
    icon.run()


# ─────────────────────────────────────────────────────────────────────────────
# 9. ARRANQUE PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────

def start():
    run_server_in_thread()
    setup_tray()

if __name__ == "__main__":
    start()