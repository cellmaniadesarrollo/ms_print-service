# app/server.py
"""
MÓDULO DEL SERVIDOR HTTPS
═══════════════════════════════════════════════════════════════════════════════

¿Qué hace este módulo?
    Configura y arranca el servidor web Uvicorn que expone la API FastAPI
    a través de HTTPS en el puerto indicado en la variable de entorno PORT
    (por defecto: 56789).

    Además levanta un segundo servidor HTTP (solo local) en TUNNEL_PORT
    (por defecto: 56790) que sirve de "puerta de entrada" para el túnel de
    Cloudflare, y arranca automáticamente ese túnel (ver app/tunnel.py).

    El servidor corre en un hilo (thread) secundario para no bloquear
    el hilo principal, que está ocupado mostrando el ícono en la bandeja.

¿Qué es un hilo (thread)?
    Imagina que el programa tiene varios empleados trabajando al mismo tiempo:
      - Empleado A (hilo principal) → muestra el ícono en la bandeja del sistema.
      - Empleado B (hilo secundario / daemon) → atiende peticiones HTTP.
      - Empleado C (hilo del túnel / daemon) → mantiene vivo cloudflared y
        avisa al backend cuál es la URL pública actual.
    daemon=True significa que si el hilo principal muere, B y C se cierran solos.

¿Qué es Uvicorn?
    Es el servidor web que ejecuta la aplicación FastAPI.
    FastAPI define las rutas y la lógica; Uvicorn es el motor que escucha
    conexiones TCP y llama a FastAPI cuando llega una petición.

¿Por qué HTTPS y no HTTP?
    El navegador moderno bloquea peticiones desde páginas HTTPS a servicios
    HTTP locales (mixed-content). Al usar HTTPS con un certificado propio
    (self-signed o Let's Encrypt) se evita ese problema.

¿Por qué hay un segundo puerto HTTP (TUNNEL_PORT)?
    cloudflared se conecta a un servicio local. Es más simple que apunte a un
    puerto HTTP plano (sin certificado propio que validar). Cloudflare ya
    entrega HTTPS válido hacia afuera, y este puerto solo escucha en
    127.0.0.1, así que nadie de la red local puede usarlo directamente.

Flujo completo de impresión remota:
    Arranca el .exe → cloudflared abre el túnel → imprime https://xxxx.trycloudflare.com
    → tunnel.py detecta la URL → la registra en el backend (POST /api/print-endpoints/register)
    → el backend guarda la URL en la colección printendpoints
    → al crear una venta, el backend llama a esa URL (POST /api/print)

Variables de entorno usadas:
    PORT                  → puerto HTTPS (default: 56789)
    TUNNEL_PORT           → puerto HTTP local para el túnel (default: 56790)
    SSL_KEYFILE           → ruta al archivo .key del certificado SSL
    SSL_CERTFILE          → ruta al archivo .pem del certificado SSL
    (las del túnel —BACKEND_URL, PRINT_REGISTER_KEY, COMPANY_ID,
     CODE_ESTABLECIMIENTO, CLOUDFLARED_PATH— se leen en app/tunnel.py)

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

# Módulo nuevo: arranca cloudflared y registra la URL pública en el backend
from app.tunnel import start_tunnel_in_thread


def run_server(app) -> None:
    # Puertos: se leen del entorno, con valores por defecto
    port = int(os.getenv("PORT", "56789"))
    tunnel_port = int(os.getenv("TUNNEL_PORT", "56790"))

    # Rutas del certificado SSL (solo lo usa el puerto HTTPS)
    key_file  = os.getenv("SSL_KEYFILE",  "certs/server.key")
    cert_file = os.getenv("SSL_CERTFILE", "certs/server.pem")

    # Si corre empaquetado como .exe (PyInstaller), los archivos están dentro
    # de una carpeta temporal (_MEIPASS), así que se ajustan las rutas.
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        base_path = sys._MEIPASS
        key_file  = os.path.join(base_path, key_file)
        cert_file = os.path.join(base_path, cert_file)

    # Puerto 1: HTTPS normal (acceso desde el navegador / red local)
    server_https = Server(Config(
        app=app, host="0.0.0.0", port=port,
        ssl_keyfile=key_file, ssl_certfile=cert_file,
        log_level="info",
    ))

    # Puerto 2: HTTP solo local, para el túnel de Cloudflare.
    # host="127.0.0.1" → únicamente accesible desde esta misma PC.
    server_tunnel = Server(Config(
        app=app, host="127.0.0.1", port=tunnel_port,
        log_level="info",
    ))

    # Uvicorn intenta manejar señales (Ctrl+C, etc.); en un hilo secundario
    # eso no está permitido, así que se desactiva.
    server_https.install_signal_handlers = lambda: None
    server_tunnel.install_signal_handlers = lambda: None

    # Corre ambos servidores a la vez dentro del mismo event loop
    async def main():
        await asyncio.gather(server_https.serve(), server_tunnel.serve())

    print(f"[INFO] HTTPS en :{port}  |  Túnel (solo local) en 127.0.0.1:{tunnel_port}")

    # Este hilo no tiene event loop propio: se crea uno y se asigna
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(main())
    except Exception as e:
        print(f"[ERROR] Falló el servidor: {e}")
    finally:
        loop.close()


def run_server_in_thread(app) -> None:
    """
    Lanza run_server() en un hilo secundario daemon para no bloquear
    el hilo principal (que usará la bandeja del sistema), y después
    arranca el túnel de Cloudflare.

    La pequeña pausa de 2.5 s permite que Uvicorn arranque y esté listo
    antes de que el túnel empiece a apuntar a él y antes de que el ícono
    de bandeja aparezca en pantalla.

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

    # Arranca cloudflared y registra la URL pública en el backend.
    # Corre en su propio hilo daemon: si el túnel se cae, se relanza solo
    # y vuelve a registrar la nueva URL, sin afectar al servidor.
    tunnel_port = int(os.getenv("TUNNEL_PORT", "56790"))
    start_tunnel_in_thread(tunnel_port)

    print("[INFO] Thread del servidor lanzado")