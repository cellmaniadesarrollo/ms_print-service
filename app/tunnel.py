# app/tunnel.py
"""
TÚNEL + REGISTRO AUTOMÁTICO DE LA URL
═══════════════════════════════════════════════════════════════════════════════

¿Qué hace?
    1. Abre un túnel de Cloudflare hacia este servicio de impresión.
       Cloudflare entrega una URL pública (https://xxxx.trycloudflare.com).
    2. Le avisa al backend de facturación cuál es esa URL
       (POST /api/print-endpoints/register).
    3. Repite el aviso cada 5 minutos (heartbeat), y si el túnel se cae
       lo vuelve a abrir y avisa la nueva URL.

Sección "tunnel" en config.json:
    {
      "enabled": true,
      "backend_url": "https://TU-BACKEND.com",
      "register_key": "<mismo valor que PRINT_REGISTER_KEY del backend>",
      "company_id": "e72d7d55-...",
      "code_establecimiento": "001",
      "cloudflared_path": "cloudflared",
      "verify_ssl": true
    }

    verify_ssl:
        true  → verifica el certificado del backend (producción).
        false → NO verifica. Solo para desarrollo con backend local
                que tenga certificado autofirmado (https://localhost:4500).

Flujo completo:
    .exe arranca → cloudflared abre túnel → tunnel.py detecta la URL
    → la registra INMEDIATAMENTE en el backend (sin esperar reachability)
    → en paralelo verifica que el túnel responda (solo diagnóstico)
    → cada 5 min re-registra la URL (heartbeat)
    → si cloudflared muere, se relanza y registra la nueva URL
═══════════════════════════════════════════════════════════════════════════════
"""

import json
import os
import re
import subprocess
import sys
import threading
import time

import requests
import urllib3

# Detecta la URL pública en la salida de cloudflared
URL_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")

# ─── Carga de configuración ───────────────────────────────────────────────────

def _load_tunnel_cfg() -> dict:
    """Lee la sección 'tunnel' del config.json (junto al .exe o en la raíz)."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cfg_path = os.path.join(base, "config.json")
    with open(cfg_path, "r", encoding="utf-8") as f:
        return json.load(f).get("tunnel", {})


_cfg = _load_tunnel_cfg()

TUNNEL_ENABLED  = _cfg.get("enabled", True)
BACKEND_URL     = _cfg.get("backend_url", "").rstrip("/")
REGISTER_KEY    = _cfg.get("register_key", "")
COMPANY_ID      = _cfg.get("company_id", "")
ESTABLECIMIENTO = str(_cfg.get("code_establecimiento", "001")).zfill(3)
CLOUDFLARED     = _cfg.get("cloudflared_path", "cloudflared")
VERIFY_SSL      = _cfg.get("verify_ssl", True)
HEARTBEAT_SEC   = 300   # cada 5 minutos se re-registra la URL en el backend

if not VERIFY_SSL:
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    print("[TUNNEL] ⚠️  verify_ssl=false → certificado del backend no verificado (solo desarrollo)")

# Evita que se lancen dos túneles si algo llama a start_tunnel_in_thread dos veces
_started      = False
_started_lock = threading.Lock()

# ─── Registro en el backend de facturas ──────────────────────────────────────

def register(url: str) -> bool:
    """
    POST /api/print-endpoints/register → backend Node.js (ms_facturas).
    El router de Express guarda la URL en la colección printendpoints.
    Devuelve True si el backend respondió 2xx.

    El tunnel.py NO crea ningún registro propio: delega 100% en el
    backend de facturas, que es quien conoce la colección y la lógica
    de upsert por (company_id, code_establecimiento).
    """
    if not BACKEND_URL or not REGISTER_KEY or not COMPANY_ID:
        print("[TUNNEL] ❌ Falta backend_url, register_key o company_id en config.json")
        return False

    try:
        resp = requests.post(
            f"{BACKEND_URL}/api/print-endpoints/register",
            json={
                "company_id":           COMPANY_ID,
                "code_establecimiento": ESTABLECIMIENTO,
                "url":                  url,
            },
            headers={
                "x-api-key":    REGISTER_KEY,
                "Content-Type": "application/json",
            },
            timeout=10,
            verify=VERIFY_SSL,
        )

        if resp.ok:
            print(f"[TUNNEL] ✅ URL registrada en backend de facturas: {url}")
            return True

        print(f"[TUNNEL] ❌ Backend respondió {resp.status_code}: {resp.text}")

    except requests.exceptions.ConnectionError as e:
        print(f"[TUNNEL] ❌ No se pudo conectar al backend: {e}")
    except requests.exceptions.Timeout:
        print("[TUNNEL] ❌ Timeout al registrar URL en el backend")
    except Exception as e:
        print(f"[TUNNEL] ❌ Error inesperado al registrar: {e}")

    return False

# ─── Verificación de accesibilidad (solo diagnóstico) ────────────────────────

def _wait_until_reachable(url: str, tries: int = 20) -> bool:
    """
    Intenta llegar a /api/status a través del túnel público.
    Cloudflare tarda unos segundos en propagar el túnel nuevo, así que
    esta función espera hasta ~20s antes de rendirse.

    IMPORTANTE: esta función es solo diagnóstico. El registro en el
    backend ya ocurrió en on_url() sin esperar este resultado, para
    que la URL quede disponible lo antes posible.

    Se loguea cada intento para poder diagnosticar si hay redirecciones
    o respuestas inesperadas de Cloudflare.
    """
    print(f"[TUNNEL] ⏳ Verificando accesibilidad pública: {url}/api/status")
    for attempt in range(1, tries + 1):
        try:
            r = requests.get(
                f"{url}/api/status",
                timeout=4,
                allow_redirects=True,
                # Cloudflare a veces rechaza requests sin User-Agent
                headers={"User-Agent": "Mozilla/5.0 print-service-tunnel-check"},
            )
            if r.ok:
                print(f"[TUNNEL] 🌐 Túnel accesible públicamente tras ~{attempt}s")
                return True
            # Loguea la respuesta para diagnosticar 404, 530, etc.
            print(f"[TUNNEL] ⏳ Intento {attempt}/{tries}: HTTP {r.status_code}")
        except Exception as e:
            print(f"[TUNNEL] ⏳ Intento {attempt}/{tries}: {type(e).__name__}: {e}")
        time.sleep(1)

    print(f"[TUNNEL] ⚠️  El túnel no respondió en {tries}s (puede que tarde más en propagarse)")
    return False

# ─── cloudflared ─────────────────────────────────────────────────────────────

def _run_cloudflared(tunnel_port: int, on_url) -> None:
    """
    Lanza el proceso cloudflared apuntando al servidor HTTP local
    (puerto TUNNEL_PORT, sin SSL, solo accesible desde 127.0.0.1).

    Lee stdout línea a línea buscando la URL pública con URL_RE.
    Cuando la encuentra, dispara on_url() en un hilo separado para
    no bloquear la lectura del pipe (cloudflared sigue escribiendo logs).

    Se queda bloqueado hasta que cloudflared termina; tunnel_supervisor
    lo relanza automáticamente.
    """
    flags  = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    target = f"http://127.0.0.1:{tunnel_port}"
    print(f"[TUNNEL] Apuntando cloudflared → {target}")

    proc = subprocess.Popen(
        [CLOUDFLARED, "tunnel", "--no-autoupdate", "--url", target],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        creationflags=flags,
    )
    print(f"[TUNNEL] cloudflared PID {proc.pid}")

    found = False
    try:
        for line in proc.stdout:
            print(f"[CLOUDFLARED] {line.rstrip()}")
            if not found:
                m = URL_RE.search(line)
                if m:
                    found = True
                    # on_url en su propio hilo: no bloquea la lectura del pipe
                    threading.Thread(
                        target=on_url,
                        args=(m.group(0),),
                        daemon=True,
                    ).start()
    finally:
        if proc.poll() is None:
            proc.terminate()
        proc.wait()
        print("[TUNNEL] cloudflared terminó")

# ─── Supervisor (mantiene el túnel vivo) ─────────────────────────────────────

def tunnel_supervisor(tunnel_port: int) -> None:
    """
    Bucle infinito que mantiene cloudflared corriendo y la URL registrada.

    Flujo por iteración:
      1. _run_cloudflared detecta la URL pública y llama on_url().
      2. on_url() registra la URL en el backend INMEDIATAMENTE (sin esperar
         que sea accesible), y en paralelo verifica accesibilidad.
      3. heartbeat() re-registra la URL cada HEARTBEAT_SEC segundos para
         que el backend no la pierda si reinicia.
      4. Si cloudflared muere → current["url"] = None → se relanza → nueva
         URL → nuevo registro. El loop de registro de la URL vieja se
         detiene solo gracias a `current["url"] == url`.
    """
    current = {"url": None}

    def on_url(url: str) -> None:
        """
        Callback que se ejecuta cuando cloudflared publica la URL.
        Registra inmediatamente en el backend sin esperar reachability,
        para minimizar el tiempo en que el backend tiene una URL obsoleta.
        En paralelo verifica accesibilidad (solo para diagnóstico en logs).
        """
        current["url"] = url
        print(f"[TUNNEL] 📡 Nueva URL detectada: {url} — registrando en backend...")

        # Registro inmediato: reintenta cada 10s hasta que el backend lo acepte,
        # pero para si la URL cambió (cloudflared se reconectó con una URL nueva)
        while current["url"] == url and not register(url):
            time.sleep(10)

        # Verificación de accesibilidad en paralelo: solo diagnóstico,
        # no bloquea ni retrasa el registro
        threading.Thread(
            target=_wait_until_reachable,
            args=(url,),
            daemon=True,
        ).start()

    def heartbeat() -> None:
        """
        Re-registra la URL actual cada HEARTBEAT_SEC segundos.
        Útil si el backend reinicia y pierde la URL de la colección.
        """
        while True:
            time.sleep(HEARTBEAT_SEC)
            url = current["url"]
            if url:
                register(url)

    threading.Thread(target=heartbeat, daemon=True).start()

    while True:
        try:
            _run_cloudflared(tunnel_port, on_url)
        except FileNotFoundError:
            print(
                f"[TUNNEL] ❌ No se encontró '{CLOUDFLARED}'.\n"
                "         Instálalo o corrige cloudflared_path en config.json."
            )
            # Espera larga: no tiene sentido reintentar cada 5s si el binario no existe
            time.sleep(30)
        except Exception as e:
            print(f"[TUNNEL] ❌ Error en cloudflared: {e}")

        current["url"] = None
        print("[TUNNEL] 🔄 Reintentando en 5s…")
        time.sleep(5)

# ─── Punto de entrada ─────────────────────────────────────────────────────────

def start_tunnel_in_thread(tunnel_port: int) -> None:
    """
    Lanza tunnel_supervisor en un hilo daemon.
    Si se llama dos veces (por ejemplo desde tests o recarga en caliente),
    la segunda llamada se ignora gracias al lock _started.
    """
    global _started

    if not TUNNEL_ENABLED:
        print("[TUNNEL] ⏸️  Túnel desactivado en config.json (enabled=false)")
        return

    with _started_lock:
        if _started:
            print("[TUNNEL] Ya hay un túnel en ejecución, se ignora la segunda llamada")
            return
        _started = True

    threading.Thread(
        target=tunnel_supervisor,
        args=(tunnel_port,),
        daemon=True,
        name="tunnel-supervisor",
    ).start()
    print(f"[TUNNEL] Supervisor arrancado → puerto local {tunnel_port}")