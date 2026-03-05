# app/server.py
"""
MÓDULO DEL SERVIDOR HTTPS
═══════════════════════════════════════════════════════════════════════════════

¿Qué hace este módulo?
    Configura y arranca el servidor web Uvicorn que expone la API FastAPI
    a través de HTTPS en el puerto indicado en la variable de entorno PORT
    (por defecto: 56789).

    El servidor corre en un hilo (thread) secundario para no bloquear
    el hilo principal, que está ocupado mostrando el ícono en la bandeja.

¿Qué es un hilo (thread)?
    Imagina que el programa tiene dos empleados trabajando al mismo tiempo:
      - Empleado A (hilo principal) → muestra el ícono en la bandeja del sistema.
      - Empleado B (hilo secundario / daemon) → atiende peticiones HTTP.
    daemon=True significa que si el hilo principal muere, B se cierra solo.

¿Qué es Uvicorn?
    Es el servidor web que ejecuta la aplicación FastAPI.
    FastAPI define las rutas y la lógica; Uvicorn es el motor que escucha
    conexiones TCP y llama a FastAPI cuando llega una petición.

¿Por qué HTTPS y no HTTP?
    El navegador moderno bloquea peticiones desde páginas HTTPS a servicios
    HTTP locales (mixed-content). Al usar HTTPS con un certificado propio
    (self-signed o Let's Encrypt) se evita ese problema.

Variables de entorno usadas:
    PORT            → puerto donde escucha el servidor (default: 56789)
    SSL_KEYFILE     → ruta al archivo .key del certificado SSL
    SSL_CERTFILE    → ruta al archivo .pem del certificado SSL

Notas para novatos:
    - asyncio.new_event_loop() crea un nuevo "bucle de eventos" para el hilo.
      FastAPI y Uvicorn son asíncronos (async/await), necesitan un event loop.
    - loop.run_until_complete() arranca el servidor y se queda ahí hasta que
      éste se detenga (lo que nunca pasa salvo que el proceso termine).
    - threading.Thread(target=..., daemon=True).start() lanza la función
      target en paralelo sin bloquear el código que sigue.
═══════════════════════════════════════════════════════════════════════════════
"""

import os
import sys
import asyncio
import threading
import time

import uvicorn
from uvicorn import Server, Config


def run_server(app) -> None:
    """
    Configura Uvicorn y bloquea el hilo hasta que el servidor se detenga.

    Este función NO debe llamarse directamente desde el hilo principal;
    usa run_server_in_thread() para eso.

    Args:
        app: la instancia de FastAPI definida en routes.py
    """

    # ── Puerto ────────────────────────────────────────────────────────────────
    # int(...) convierte el string de la variable de entorno a número entero.
    port = int(os.getenv("PORT", "56789"))

    # ── Rutas de los certificados SSL ─────────────────────────────────────────
    # Valores por defecto apuntan a la subcarpeta certs/ del proyecto.
    key_file  = os.getenv("SSL_KEYFILE",  "certs/server.key")
    cert_file = os.getenv("SSL_CERTFILE", "certs/server.pem")

    # Si la app está empaquetada como .exe con PyInstaller, los archivos
    # auxiliares se extraen a sys._MEIPASS (carpeta temporal oculta).
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        base_path = sys._MEIPASS
        key_file  = os.path.join(base_path, key_file)
        cert_file = os.path.join(base_path, cert_file)

    print(f"[INFO] Iniciando servidor HTTPS en puerto {port}")
    print(f"[INFO] Dashboard: https://localhost:{port}/  (o vía subdominio)")
    reload = os.getenv("RELOAD", "False").lower() == "true"
    # ── Configuración de Uvicorn ───────────────────────────────────────────────
    # Config() recibe todos los parámetros del servidor.
    # host="0.0.0.0" → escucha en TODAS las interfaces de red de la máquina,
    # no solo en localhost; así otros dispositivos en la misma LAN pueden acceder.
    config_uvi = Config(
        app=app,
        host="0.0.0.0",
        port=port,
        reload=reload, 
        ssl_keyfile=key_file,
        ssl_certfile=cert_file, 
        log_level="info",
    )

    server = Server(config_uvi)

    # ── Event loop asíncrono ───────────────────────────────────────────────────
    # Cada hilo necesita su propio event loop; no se puede compartir el del
    # hilo principal.
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        loop.run_until_complete(server.serve())   # ← bloquea hasta que el server pare
    except Exception as e:
        print(f"[ERROR] Falló el servidor: {e}")
    finally:
        loop.close()


def run_server_in_thread(app) -> None:
    """
    Lanza run_server() en un hilo secundario daemon para no bloquear
    el hilo principal (que usará la bandeja del sistema).

    La pequeña pausa de 2.5 s permite que Uvicorn arranque y esté listo
    antes de que el ícono de bandeja aparezca en pantalla.

    Args:
        app: la instancia de FastAPI definida en routes.py
    """

    # target=... es la función que correrá en el nuevo hilo.
    # args=(...) son los argumentos que se le pasan a esa función.
    # daemon=True hace que el hilo muera automáticamente si el proceso principal termina.
    thread = threading.Thread(target=run_server, args=(app,), daemon=True)
    thread.start()

    # Esperamos un momento para que Uvicorn tenga tiempo de inicializarse.
    time.sleep(2.5)

    print("[INFO] Thread del servidor lanzado")