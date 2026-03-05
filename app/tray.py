# app/tray.py
"""
MÓDULO DE BANDEJA DEL SISTEMA (System Tray)
═══════════════════════════════════════════════════════════════════════════════

¿Qué hace este módulo?
    Muestra el ícono de Print Service en la bandeja del sistema de Windows
    (la zona de íconos junto al reloj, abajo a la derecha).

    El ícono ofrece un pequeño menú con dos acciones:
        • "Abrir Panel" → abre el dashboard en el navegador predeterminado.
        • "Salir"       → cierra toda la aplicación limpiamente.

¿Por qué setup_tray() bloquea el hilo principal?
    pystray.Icon.run() es un bucle infinito que procesa eventos del menú.
    Por eso el servidor se lanza ANTES en un hilo separado (server.py),
    y setup_tray() se llama al final como última instrucción del programa.
    Cuando el usuario hace clic en "Salir", icon.stop() rompe ese bucle y
    os._exit(0) mata todo el proceso.

    os._exit vs sys.exit:
        sys.exit   → lanza una excepción SystemExit; puede ser capturada.
        os._exit   → cierra el proceso de forma inmediata e incondicional.
                     Útil aquí porque hay hilos daemon corriendo.

Notas para novatos:
    - webbrowser.open() abre la URL en el navegador por defecto del usuario.
    - Image.open() carga una imagen PNG para usarla como ícono.
    - Image.new() crea una imagen de color sólido como fallback si no
      se encuentra el PNG.
    - pystray.Menu y pystray .MenuItem construyen el menú contextual.
    - pystray.Menu.SEPARATOR añade una línea divisoria entre ítems.
═══════════════════════════════════════════════════════════════════════════════
"""
# app/tray.py
# app/tray.py

import os
import sys
import time
import signal 

import pystray
from PIL import Image


def setup_tray() -> None:

    icon_path = "icon.png"
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        icon_path = os.path.join(sys._MEIPASS, icon_path)

    try:
        image = Image.open(icon_path)
    except Exception:
        print("[WARN] No se encontró icon.png → usando ícono de color sólido")
        image = Image.new('RGB', (64, 64), color=(0, 128, 255))

    def on_open(icon, item) -> None:
        import webbrowser
        port = int(os.getenv("PORT", "56789"))
        webbrowser.open(f"https://localhost:{port}/")

    def on_exit(icon, item) -> None:
        icon.stop()
        os._exit(0)

    menu = pystray.Menu(
        pystray.MenuItem("Abrir Panel", on_open),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Salir", on_exit),
    )

    icon = pystray.Icon("print-service", image, "Print Service", menu)

    # run_detached() lanza pystray en su propio hilo y devuelve el control
    # al hilo principal inmediatamente → Python ya puede escuchar CTRL+C
    icon.run_detached()
    print("[INFO] Ícono de bandeja activo")

    # El hilo principal se queda en este bucle.
    # time.sleep(1) cede el control a Python cada segundo →
    # CTRL+C interrumpe el sleep y lanza KeyboardInterrupt normalmente.
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[INFO] CTRL+C recibido → cerrando Print Service...")
        icon.stop()
        os._exit(0)