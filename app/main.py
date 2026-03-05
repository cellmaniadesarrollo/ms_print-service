# app/main.py
"""
PUNTO DE ENTRADA DE LA APLICACIÓN — Print Service
═══════════════════════════════════════════════════════════════════════════════

¿Qué hace este archivo?
    Es el "director de orquesta": importa los módulos necesarios y los
    arranca en el orden correcto. Debe tener el MÍNIMO de lógica posible;
    cada responsabilidad vive en su propio módulo.

Orden de arranque:
    1. load_dotenv()          → carga el archivo .env en las variables de entorno.
                                ¡DEBE ser lo primero! Antes de cualquier os.getenv().
    2. Parcheo PyInstaller    → ajusta rutas de recursos cuando corre como .exe.
    3. Supresión de consola   → si se lanzó con --noconsole, redirige stdout/stderr.
    4. check_for_update()     → consulta GitHub; si hay versión nueva, actualiza y reinicia.
    5. run_server_in_thread() → arranca Uvicorn+FastAPI en un hilo secundario.
    6. setup_tray()           → muestra el ícono en la bandeja (BLOQUEANTE — va al final).

Módulos del proyecto:
    app/updater.py  → lógica de auto-actualización desde GitHub Releases.
    app/server.py   → configuración y arranque de Uvicorn en hilo separado.
    app/tray.py     → ícono y menú de la bandeja del sistema.
    app/routes.py   → todos los endpoints de la API (FastAPI app instance).
    app/config.py   → carga y valida el config.json.
    app/dashboard.py→ HTML del panel de administración.
    app/printer/    → lógica de conexión e impresión de tickets.

¿Por qué load_dotenv() va primero?
    python-dotenv inyecta las variables del archivo .env en os.environ.
    Si cualquier módulo llama a os.getenv() ANTES de load_dotenv(),
    obtendrá None aunque la variable esté en el .env.
    Al ponerlo como primera instrucción garantizamos que todos los módulos
    importados después ya ven las variables correctas.
═══════════════════════════════════════════════════════════════════════════════
"""

# ── 1. Variables de entorno ─────────────────────────────────────────────────
# SIEMPRE debe ser la primera importación ejecutable del programa.
from dotenv import load_dotenv
load_dotenv()   # lee el archivo .env y puebla os.environ antes de todo lo demás


# ── Importaciones de la librería estándar ───────────────────────────────────
import os
import sys


# ─────────────────────────────────────────────────────────────────────────────
# 2. Soporte para .exe (PyInstaller)
# ─────────────────────────────────────────────────────────────────────────────
# Cuando PyInstaller empaqueta la app, extrae los recursos a una carpeta
# temporal llamada _MEIPASS. python-escpos necesita saber dónde está
# capabilities.json para funcionar; se lo indicamos via variable de entorno.

if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
    base_path = sys._MEIPASS
    capabilities_path = os.path.join(base_path, 'escpos', 'capabilities.json')
    os.environ['ESCPOS_CAPABILITIES_FILE'] = capabilities_path
    print(f"[DEBUG] Modo bundled: capabilities.json en {capabilities_path}")
def _get_exe_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__))) 

load_dotenv(dotenv_path=os.path.join(_get_exe_dir(), ".env"))

# ─────────────────────────────────────────────────────────────────────────────
# 3. Supresión de consola (modo prod ucción)
# ─────────────────────────────────────────────────────────────────────────────
# Cuando el usuario final ejecuta el .exe no debe ver una ventana de consola.
# PyInstaller puede ocultarla, pero por si acaso también redirigimos
# stdout/stderr a /dev/null si se detecta el flag --noconsole o
# si stdout no existe (señal de que no hay consola).

if '--noconsole' in sys.argv or not sys.stdout:
    sys.stdout = open(os.devnull, 'w', encoding='utf-8')
    sys.stderr = open(os.devnull, 'w', encoding='utf-8')


# ── Importaciones propias (DESPUÉS de load_dotenv) ──────────────────────────
# Al importar después de load_dotenv(), estos módulos ya pueden leer
# variables de entorno correctamente en su nivel de módulo.
from app.updater import check_for_update
from app.server  import run_server_in_thread
from app.tray    import setup_tray
from app.routes  import app   # instancia FastAPI con todos los endpoints registrados


# ─────────────────────────────────────────────────────────────────────────────
# 4. Función principal de arranque
# ─────────────────────────────────────────────────────────────────────────────

def start() -> None:
    """
    Orquesta el arranque completo de la aplicación en el orden correcto.

    Llamada por el bloque __main__ (ejecución directa) y también puede
    ser usada como entrypoint desde pyproject.toml o main.spec.

    Flujo:
        check_for_update()      → si hay nueva versión, descarga y reinicia.
                                  Si no hay, continúa normalmente.
        run_server_in_thread()  → lanza Uvicorn en hilo daemon y espera 2.5 s.
        setup_tray()            → muestra el ícono; BLOQUEA hasta que el usuario
                                  haga clic en "Salir".
    """
    check_for_update()            # paso 4 — puede terminar el proceso si hay update
    run_server_in_thread(app)     # paso 5 — hilo secundario con el servidor HTTPS
    setup_tray()                  # paso 6 — hilo principal con el ícono de bandeja


# ─────────────────────────────────────────────────────────────────────────────
# 5. Guarda de ejecución directa
# ─────────────────────────────────────────────────────────────────────────────
# __name__ == "__main__" es True SOLO cuando ejecutas este archivo directamente:
#     python -m app.main        ← True
#     poetry run dev            ← True (si el entrypoint apunta aquí)
#     import app.main           ← False (no arranca al importar)

if __name__ == "__main__": 
    start()