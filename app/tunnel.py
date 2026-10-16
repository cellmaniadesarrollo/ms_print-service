# app/tunnel.py
"""
TÚNEL + REGISTRO AUTOMÁTICO DE LA URL
═══════════════════════════════════════════════════════════════════════════════

¿Qué hace?
    1. Abre UN túnel de Cloudflare hacia este servicio de impresión.
       Cloudflare entrega una URL pública (https://xxxx.trycloudflare.com).
    2. Registra esa MISMA URL en uno o varios backends (órdenes, facturas...).
    3. Repite el aviso cada 5 minutos (heartbeat), y si el túnel se cae
       lo vuelve a abrir y avisa la nueva URL.

Sección "tunnel" en config.json (formato nuevo, varios backends):
    {
      "enabled": true,
      "cloudflared_path": "cloudflared",
      "verify_ssl": false,
      "registrations": [
        {
          "name": "ordenes",
          "backend_url": "http://localhost:3000",
          "register_key": "<mismo valor que PRINT_REGISTER_KEY del backend>",
          "company_id": "613d64b9-...",
          "code_establecimiento": "001"
        },
        {
          "name": "facturas",
          "backend_url": "https://localhost:4500",
          "register_key": "<clave>",
          "company_id": "e72d7d55-...",
          "code_establecimiento": "001",
          "register_path": "/api/print-endpoints/register"
        }
      ]
    }

    Campos opcionales por registro:
        enabled        → false para saltarse ese backend
        register_path  → por defecto "/print-endpoints/register"
        verify_ssl     → por defecto hereda el valor global

Formato antiguo (campos planos backend_url, register_key, company_id,
code_establecimiento dentro de "tunnel") sigue funcionando.

    verify_ssl:
        true  → verifica el certificado del backend (producción).
        false → NO verifica. Solo para desarrollo con backend local
                que tenga certificado autofirmado.

Flujo completo:
    .exe arranca → cloudflared abre túnel → tunnel.py detecta la URL
    → la registra INMEDIATAMENTE en cada backend (cada uno con sus propios
      reintentos; si uno está caído no bloquea a los demás)
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

TUNNEL_ENABLED = _cfg.get("enabled", True)
CLOUDFLARED    = _cfg.get("cloudflared_path", "cloudflared")
VERIFY_SSL     = _cfg.get("verify_ssl", True)
HEARTBEAT_SEC  = 300   # cada 5 minutos se re-registra la URL en los backends


def _build_registrations(cfg: dict) -> list[dict]:
    """
    Lista de backends donde registrar la URL.
    Acepta el formato nuevo ("registrations": [...]) y el antiguo
    (campos planos dentro de "tunnel").
    """
    regs = cfg.get("registrations")
    if not regs:
        regs = [{
            "name":                 "default",
            "backend_url":          cfg.get("backend_url", ""),
            "register_key":         cfg.get("register_key", ""),
            "company_id":           cfg.get("company_id", ""),
            "code_establecimiento": cfg.get("code_establecimiento", "001"),
        }]

    out = []
    for r in regs:
        if not r.get("enabled", True):
            continue
        out.append({
            "name":            r.get("name", r.get("backend_url", "?")),
            "backend_url":     r.get("backend_url", "").rstrip("/"),
            "register_key":    r.get("register_key", ""),
            "company_id":      str(r.get("company_id", "")),
            "establecimiento": str(r.get("code_establecimiento", "001")).zfill(3),
            "path":            r.get("register_path", "/print-endpoints/register"),
            "verify_ssl":      r.get("verify_ssl", VERIFY_SSL),
        })
    return out


REGISTRATIONS = _build_registrations(_cfg)

if any(not r["verify_ssl"] for r in REGISTRATIONS):
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    print("[TUNNEL] ⚠️  verify_ssl=false en algún backend (solo desarrollo)")

print(
    "[TUNNEL] Backends de registro: "
    + (", ".join(r["name"] for r in REGISTRATIONS) or "ninguno")
)

# Evita que se lancen dos túneles si algo llama a start_tunnel_in_thread dos veces
_started      = False
_started_lock = threading.Lock()

# ─── Registro en los backends ────────────────────────────────────────────────

def register_one(reg: dict, url: str) -> bool:
    """
    POST {backend_url}{path} a UN backend.
    Devuelve True si respondió 2xx.
    """
    name = reg["name"]
    if not reg["backend_url"] or not reg["register_key"] or not reg["company_id"]:
        print(f"[TUNNEL] ❌ [{name}] Falta backend_url, register_key o company_id")
        return False

    try:
        resp = requests.post(
            f"{reg['backend_url']}{reg['path']}",
            json={
                "company_id":           reg["company_id"],
                "code_establecimiento": reg["establecimiento"],
                "url":                  url,
            },
            headers={
                "x-register-key": reg["register_key"],
                "Content-Type":   "application/json",
            },
            timeout=10,
            verify=reg["verify_ssl"],
        )

        if resp.ok:
            print(f"[TUNNEL] ✅ [{name}] URL registrada: {url}")
            return True

        print(f"[TUNNEL] ❌ [{name}] respondió {resp.status_code}: {resp.text}")

    except requests.exceptions.ConnectionError as e:
        print(f"[TUNNEL] ❌ [{name}] no se pudo conectar: {e}")
    except requests.exceptions.Timeout:
        print(f"[TUNNEL] ❌ [{name}] timeout al registrar")
    except Exception as e:
        print(f"[TUNNEL] ❌ [{name}] error inesperado: {e}")

    return False


def register_all(url: str) -> None:
    """Un solo intento en todos los backends (lo usa el heartbeat)."""
    for reg in REGISTRATIONS:
        register_one(reg, url)

# ─── Verificación de accesibilidad (solo diagnóstico) ────────────────────────

def _wait_until_reachable(url: str, tries: int = 20) -> bool:
    """
    Intenta llegar a /api/status a través del túnel público.
    Cloudflare tarda unos segundos en propagar el túnel nuevo, así que
    esta función espera hasta ~20s antes de rendirse.

    IMPORTANTE: esta función es solo diagnóstico. El registro en los
    backends ya ocurre en on_url() sin esperar este resultado.
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
      2. on_url() lanza un hilo de registro POR BACKEND (cada uno reintenta
         cada 10s hasta lograrlo) y en paralelo verifica accesibilidad.
      3. heartbeat() re-registra la URL en todos los backends cada
         HEARTBEAT_SEC segundos.
      4. Si cloudflared muere → current["url"] = None → se relanza → nueva
         URL → nuevo registro. Los reintentos de la URL vieja se detienen
         solos gracias a `current["url"] == url`.
    """
    current = {"url": None}

    def on_url(url: str) -> None:
        current["url"] = url
        print(f"[TUNNEL] 📡 Nueva URL detectada: {url} — registrando en backends...")

        def _register_until_ok(reg: dict) -> None:
            # Reintenta cada 10s; se detiene si la URL cambió
            while current["url"] == url and not register_one(reg, url):
                time.sleep(10)

        for reg in REGISTRATIONS:
            threading.Thread(
                target=_register_until_ok,
                args=(reg,),
                daemon=True,
            ).start()

        # Verificación de accesibilidad: solo diagnóstico
        threading.Thread(
            target=_wait_until_reachable,
            args=(url,),
            daemon=True,
        ).start()

    def heartbeat() -> None:
        """Re-registra la URL actual en todos los backends cada HEARTBEAT_SEC."""
        while True:
            time.sleep(HEARTBEAT_SEC)
            url = current["url"]
            if url:
                register_all(url)

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