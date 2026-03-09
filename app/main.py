# app/main.py
"""
PUNTO DE ENTRADA DE LA APLICACIÓN — Print Service
═══════════════════════════════════════════════════════════════════════════════

¿Qué hace este archivo?
    Es el "director de orquesta": importa los módulos necesarios y los
    arranca en el orden correcto. Debe tener el MÍNIMO de lógica posible;
    cada responsabilidad vive en su propio módulo.

Orden de arranque:
    1. load_dotenv()            → carga el archivo .env en las variables de entorno.
                                  ¡DEBE ser lo primero! Antes de cualquier os.getenv().
    2. Parcheo PyInstaller      → ajusta rutas de recursos cuando corre como .exe.
    3. Supresión de consola     → si se lanzó con --noconsole, redirige stdout/stderr.
    4. check_for_update()       → revisión inmediata al arrancar.
    5. _update_scheduler()      → hilo daemon que repite la revisión cada
                                  UPDATE_INTERVAL_MINUTES (definido en updater.py).
    6. run_server_in_thread()   → arranca Uvicorn+FastAPI en un hilo secundario.
    7. setup_tray()             → muestra el ícono en la bandeja (BLOQUEANTE).

Módulos del proyecto:
    app/updater.py   → lógica de auto-actualización + UPDATE_INTERVAL_MINUTES.
    app/server.py    → configuración y arranque de Uvicorn en hilo separado.
    app/tray.py      → ícono y menú de la bandeja del sistema.
    app/routes.py    → todos los endpoints de la API (FastAPI app instance).
    app/config.py    → carga y valida el config.json.
    app/dashboard.py → HTML del panel de administración.
    app/printer/     → lógica de conexión e impresión de tickets.

¿Cómo cambiar el intervalo de actualizaciones?
    El intervalo se define en app/updater.py como UPDATE_INTERVAL_MINUTES.
    Se cambia ahí junto a CURRENT_VERSION en cada nueva release:

        Beta / pruebas  → UPDATE_INTERVAL_MINUTES = 1    (cada 1 minuto)
        6 horas         → UPDATE_INTERVAL_MINUTES = 360
        12 horas        → UPDATE_INTERVAL_MINUTES = 720

    Al subir una nueva release con el nuevo intervalo, la app se
    actualiza sola y adopta el nuevo valor automáticamente.
    No requiere tocar el .env del usuario.

¿Por qué load_dotenv() va primero?
    python-dotenv inyecta las variables del archivo .env en os.environ.
    Si cualquier módulo llama a os.getenv() ANTES de load_dotenv(),
    obtendrá None aunque la variable esté en el .env.
    Al ponerlo como primera instrucción garantizamos que todos los módulos
    importados después ya ven las variables correctas.
═══════════════════════════════════════════════════════════════════════════════
"""

# ── 1. Variables de entorno ──────────────────────────────────────────────────
# SIEMPRE debe ser la primera importación ejecutable del programa.
from dotenv import load_dotenv
load_dotenv()  # primera pasada rápida


# ── Importaciones de la librería estándar ────────────────────────────────────
import os
import sys
import threading


# ─────────────────────────────────────────────────────────────────────────────
# 2. Soporte para .exe (PyInstaller)
# ─────────────────────────────────────────────────────────────────────────────
# Cuando PyInstaller empaqueta la app, extrae los recursos a una carpeta
# temporal llamada _MEIPASS. python-escpos necesita saber dónde está
# capabilities.json para funcionar; se lo indicamos via variable de entorno.

if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
    base_path         = sys._MEIPASS
    capabilities_path = os.path.join(base_path, 'escpos', 'capabilities.json')
    os.environ['ESCPOS_CAPABILITIES_FILE'] = capabilities_path
    print(f"[DEBUG] Modo bundled: capabilities.json en {capabilities_path}")


def _get_exe_dir() -> str:
    """
    Devuelve la carpeta base donde vive el .exe (o la raíz del proyecto
    en modo desarrollo). Se usa para encontrar el .env correcto.

    En producción (.exe):   dist\PrintService\
    En desarrollo (Python): raíz del proyecto
    """
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# Segunda carga apuntando explícitamente al .env junto al .exe.
# Garantiza que en producción siempre se lea el archivo correcto
# sin importar cuál sea el directorio de trabajo actual.
load_dotenv(dotenv_path=os.path.join(_get_exe_dir(), ".env"))


# ─────────────────────────────────────────────────────────────────────────────
# 3. Supresión de consola (modo producción)
# ─────────────────────────────────────────────────────────────────────────────
# En producción el usuario no debe ver ventana de consola.
# --noconsole de PyInstaller la oculta, pero redirigimos también por seguridad.

if '--noconsole' in sys.argv or not sys.stdout:
    sys.stdout = open(os.devnull, 'w', encoding='utf-8')
    sys.stderr = open(os.devnull, 'w', encoding='utf-8')


# ── Importaciones propias (DESPUÉS de load_dotenv) ───────────────────────────
from app.updater import check_for_update, UPDATE_INTERVAL_MINUTES
from app.server  import run_server_in_thread
from app.tray    import setup_tray
from app.routes  import app


# ─────────────────────────────────────────────────────────────────────────────
# 4. Scheduler de actualizaciones periódicas
# ─────────────────────────────────────────────────────────────────────────────

def _update_scheduler() -> None:
    """
    Hilo daemon que verifica actualizaciones periódicamente mientras la
    app está corriendo, sin necesidad de reiniciar la PC.

    El intervalo lo define UPDATE_INTERVAL_MINUTES en app/updater.py.
    Al publicar una nueva release puedes cambiar el intervalo y todos
    los clientes lo adoptarán automáticamente tras la actualización.

    Referencia rápida de valores:
        1   → cada 1 minuto   (fase beta / pruebas intensivas)
        30  → cada 30 minutos (beta estabilizándose)
        360 → cada 6 horas   (producción estable)
        720 → cada 12 horas  (mantenimiento esporádico)

    ¿Por qué threading.Event.wait() en vez de time.sleep()?
        Event.wait(timeout=N) duerme N segundos igual que sleep() pero
        es cancelable — si quisieras detener el scheduler en el futuro
        solo tendrías que llamar stop_event.set().

    ¿Por qué daemon=True en el hilo?
        Un hilo daemon se cierra automáticamente cuando el proceso
        principal termina. Sin daemon=True, el hilo mantendría viva
        la app incluso después de hacer clic en "Salir".
    """
    interval_seconds = UPDATE_INTERVAL_MINUTES * 60

    # Etiqueta legible para el log
    if UPDATE_INTERVAL_MINUTES < 60:
        label = f"{UPDATE_INTERVAL_MINUTES} min"
    else:
        label = f"{UPDATE_INTERVAL_MINUTES // 60} h"

    print(f"[INFO] Update scheduler activo → revisará cada {label}")

    stop_event = threading.Event()

    # La primera revisión ya se hizo en start() → aquí esperamos primero
    while not stop_event.wait(timeout=interval_seconds):
        print("[INFO] Scheduler → verificando actualización periódica...")
        check_for_update()
        # Si check_for_update() detectó update → llamó os._exit(0) → no llegamos aquí.
        # Si no había update → el while espera otro intervalo y repite.


# ─────────────────────────────────────────────────────────────────────────────
# 5. Función principal de arranque
# ─────────────────────────────────────────────────────────────────────────────

def start() -> None:
    """
    Orquesta el arranque completo de la aplicación en el orden correcto.

    Llamada por el bloque __main__ y como entrypoint de Poetry:
        [tool.poetry.scripts]
        dev = "app.main:start"
    """

    # Revisión inmediata al arrancar
    check_for_update()

    # Scheduler en hilo daemon — revisa cada UPDATE_INTERVAL_MINUTES
    threading.Thread(target=_update_scheduler, daemon=True).start()

    # Servidor HTTPS en hilo daemon
    run_server_in_thread(app)

    # Bandeja del sistema — BLOQUEANTE, siempre al final
    setup_tray()


# ─────────────────────────────────────────────────────────────────────────────
# 6. Guarda de ejecución directa
# ─────────────────────────────────────────────────────────────────────────────
# __name__ == "__main__" es True SOLO cuando ejecutas este archivo directamente:
#     python -m app.main   ← True
#     poetry run dev       ← True (entrypoint apunta a start())
#     import app.main      ← False (no arranca al importar)

if __name__ == "__main__":
    start()