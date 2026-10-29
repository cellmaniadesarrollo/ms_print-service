# app/tunnel.py
"""
TÚNEL NGROK + REGISTRO AUTOMÁTICO DE LA URL
═══════════════════════════════════════════════════════════════════════════════

¿Qué hace?
    1. Abre UN túnel de ngrok hacia este servicio de impresión
       (con dominio estático si lo configuras → la URL nunca cambia).
    2. Registra esa URL en uno o varios backends.
    3. Re-registra cada 5 minutos (heartbeat) y, si el túnel se cae,
       lo vuelve a abrir y registra la URL de nuevo.

Modo LOCAL: lo atiende el servidor HTTPS local (no usa este archivo).
Modo NUBE : este archivo abre ngrok. Para solo local: "enabled": false.

Variables de entorno (.env junto al .exe) — tienen prioridad sobre config.json:
    TOKEN_NGROK (o NGROK_AUTHTOKEN), NGROK_DOMAIN, NGROK_PATH (opc.),
    PRINT_SECRET (clave común si el registro no trae register_key),
    CODE_ESTABLECIMIENTO (opc., para 001/002 por PC sin tocar config.json)

Sección "tunnel" en config.json:
    {
      "enabled": true,
      "ngrok_authtoken": "2abc...tu_token",
      "ngrok_domain": "algo-algo.ngrok-free.app",   <- opcional pero recomendado
      "ngrok_path": "",                              <- opcional (ruta a ngrok.exe)
      "verify_ssl": false,
      "registrations": [
        {
          "name": "ordenes",
          "backend_url": "http://localhost:3000",
          "register_key": "<PRINT_REGISTER_KEY>",
          "company_id": "613d64b9-...",
          "code_establecimiento": "001"
        }
      ]
    }

    Campos opcionales por registro:
        enabled        → false para saltarse ese backend
        register_path  → por defecto "/print-endpoints/register"
        verify_ssl     → por defecto hereda el valor global

Requisito:  pip install pyngrok
═══════════════════════════════════════════════════════════════════════════════
"""

import json
import os
import sys
import threading
import time

import requests
import urllib3

# ─── Carga de configuración ───────────────────────────────────────────────────

def _base_dir() -> str:
    """Carpeta del .exe (empaquetado) o raíz del proyecto (desarrollo)."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# Carga el .env (junto al .exe o en la raíz). No pisa variables ya definidas.
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(_base_dir(), ".env"))
except ImportError:
    pass


def _load_tunnel_cfg() -> dict:
    """Lee la sección 'tunnel' del config.json (junto al .exe o en la raíz)."""
    cfg_path = os.path.join(_base_dir(), "config.json")
    with open(cfg_path, "r", encoding="utf-8") as f:
        return json.load(f).get("tunnel", {})


_cfg = _load_tunnel_cfg()


def _env_or_cfg(env_name: str, cfg_key: str, default=""):
    """Prioridad: variable de entorno / .env  →  config.json  →  default."""
    val = os.getenv(env_name)
    if val is not None and val.strip() != "":
        return val.strip()
    return _cfg.get(cfg_key, default)

TUNNEL_ENABLED = _cfg.get("enabled", True)
NGROK_TOKEN    = (os.getenv("TOKEN_NGROK", "").strip()
                  or _env_or_cfg("NGROK_AUTHTOKEN", "ngrok_authtoken"))
NGROK_DOMAIN   = str(_env_or_cfg("NGROK_DOMAIN", "ngrok_domain")).strip()
NGROK_PATH     = str(_env_or_cfg("NGROK_PATH", "ngrok_path")).strip()
# Clave de registro común (se usa si un registro no trae la suya en config.json)
REGISTER_KEY_ENV = os.getenv("PRINT_SECRET", "").strip()
VERIFY_SSL     = _cfg.get("verify_ssl", True)
HEARTBEAT_SEC  = 300   # cada 5 minutos se re-registra la URL


def _build_registrations(cfg: dict) -> list[dict]:
    """Lista de backends donde registrar la URL (formato nuevo y antiguo)."""
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
            "register_key":    r.get("register_key", "") or REGISTER_KEY_ENV,
            "company_id":      str(r.get("company_id", "")),
            "establecimiento": str(
                os.getenv("CODE_ESTABLECIMIENTO") or r.get("code_establecimiento", "001")
            ).zfill(3),
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

_started      = False
_started_lock = threading.Lock()

# ─── Registro en los backends ────────────────────────────────────────────────

def register_one(reg: dict, url: str) -> bool:
    """POST {backend_url}{path} a UN backend. True si respondió 2xx."""
    name = reg["name"]
    faltan = [k for k, label in (
        ("backend_url", "backend_url (config.json)"),
        ("register_key", "PRINT_SECRET (.env) o register_key (config.json)"),
        ("company_id", "company_id (config.json)"),
    ) if not reg[k]]
    if faltan:
        print(f"[TUNNEL] ❌ [{name}] Falta: " + ", ".join(
            label for k, label in (
                ("backend_url", "backend_url (config.json)"),
                ("register_key", "PRINT_SECRET (.env) o register_key (config.json)"),
                ("company_id", "company_id (config.json)"),
            ) if k in faltan))
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
    print(f"[TUNNEL] ⏳ Verificando accesibilidad pública: {url}/api/status")
    for attempt in range(1, tries + 1):
        try:
            r = requests.get(
                f"{url}/api/status",
                timeout=4,
                allow_redirects=True,
                headers={
                    "User-Agent": "print-service-tunnel-check",
                    # Evita la página de aviso de ngrok (plan gratis)
                    "ngrok-skip-browser-warning": "true",
                },
            )
            if r.ok:
                print(f"[TUNNEL] 🌐 Túnel accesible públicamente (intento {attempt})")
                return True
            print(f"[TUNNEL] ⏳ Intento {attempt}/{tries}: HTTP {r.status_code}")
        except Exception as e:
            print(f"[TUNNEL] ⏳ Intento {attempt}/{tries}: {type(e).__name__}: {e}")
        time.sleep(1)

    print(f"[TUNNEL] ⚠️  El túnel no respondió en {tries}s")
    return False

# ─── ngrok ───────────────────────────────────────────────────────────────────

def _run_ngrok(tunnel_port: int, on_url) -> None:
    """Abre el túnel ngrok, avisa la URL y vigila que siga vivo."""
    from pyngrok import conf, ngrok   # import tardío: solo si se usa ngrok

    if not NGROK_TOKEN:
        raise RuntimeError(
            "Falta el token de ngrok: TOKEN_NGROK en el .env "
            "(o 'ngrok_authtoken' en config.json)."
        )

    cfg = conf.get_default()
    cfg.auth_token = NGROK_TOKEN          # se pasa al proceso, no se guarda en disco
    if NGROK_PATH:
        cfg.ngrok_path = NGROK_PATH

    kwargs = {}
    if NGROK_DOMAIN:
        domain = NGROK_DOMAIN.replace("https://", "").replace("http://", "").strip("/")
        kwargs["url"] = f"https://{domain}"   # ngrok v3: dominio fijo vía 'url'

    target = f"http://127.0.0.1:{tunnel_port}"
    print(f"[TUNNEL] Apuntando ngrok → {target}"
          + (f" (dominio {NGROK_DOMAIN})" if NGROK_DOMAIN else " (URL aleatoria)"))

    tunnel = ngrok.connect(target, "http", **kwargs)
    url = tunnel.public_url.replace("http://", "https://")
    print(f"[NGROK] Túnel activo: {url}")
    threading.Thread(target=on_url, args=(url,), daemon=True).start()

    try:
        while True:
            time.sleep(10)
            if not any(t.public_url == tunnel.public_url for t in ngrok.get_tunnels()):
                print("[TUNNEL] ⚠️  El túnel ya no aparece en ngrok")
                return
    finally:
        try:
            ngrok.kill()
        except Exception:
            pass
        print("[TUNNEL] ngrok terminó")

# ─── Supervisor (mantiene el túnel vivo) ─────────────────────────────────────

def tunnel_supervisor(tunnel_port: int) -> None:
    """
    Bucle infinito que mantiene ngrok corriendo y la URL registrada.
    Si ngrok falla → se relanza → registro de la URL otra vez.
    Con dominio estático la URL es siempre la misma.
    """
    current = {"url": None}

    def on_url(url: str) -> None:
        current["url"] = url
        print(f"[TUNNEL] 📡 URL: {url} — registrando en backends...")

        def _register_until_ok(reg: dict) -> None:
            while current["url"] == url and not register_one(reg, url):
                time.sleep(10)

        for reg in REGISTRATIONS:
            threading.Thread(target=_register_until_ok, args=(reg,), daemon=True).start()

        threading.Thread(target=_wait_until_reachable, args=(url,), daemon=True).start()

    def heartbeat() -> None:
        while True:
            time.sleep(HEARTBEAT_SEC)
            url = current["url"]
            if url:
                register_all(url)

    threading.Thread(target=heartbeat, daemon=True).start()

    while True:
        try:
            _run_ngrok(tunnel_port, on_url)
        except FileNotFoundError:
            print("[TUNNEL] ❌ No se encontró el binario de ngrok.")
            time.sleep(30)
        except RuntimeError as e:
            # Config inválida: no sirve reintentar rápido
            print(f"[TUNNEL] ❌ {e}")
            time.sleep(30)
        except Exception as e:
            print(f"[TUNNEL] ❌ Error en ngrok: {type(e).__name__}: {e}")

        current["url"] = None
        print("[TUNNEL] 🔄 Reintentando en 5s…")
        time.sleep(5)

# ─── Punto de entrada ─────────────────────────────────────────────────────────

def start_tunnel_in_thread(tunnel_port: int) -> None:
    """Lanza tunnel_supervisor en un hilo daemon (ignora llamadas repetidas)."""
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