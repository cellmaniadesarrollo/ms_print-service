# launcher.py
"""
LAUNCHER — Print Service
═══════════════════════════════════════════════════════════════════════════════
Lanza PrintService.exe y espera a que termine.
Muestra una splash screen durante el arranque y las actualizaciones.

FIX: SplashScreen ahora usa queue.Queue para comunicación entre hilos.
     El hilo principal NUNCA llama after() directamente — solo encola
     comandos que el hilo de Tkinter ejecuta cada 50 ms.
     Esto resuelve: RuntimeError: main thread is not in main loop
     que ocurría al iniciar desde el Task Scheduler de Windows.
═══════════════════════════════════════════════════════════════════════════════
"""

import os
import sys
import queue
import subprocess
import time
import ctypes
import threading
import tkinter as tk


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def get_base_dir() -> str:
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def show_error(msg: str) -> None:
    ctypes.windll.user32.MessageBoxW(0, msg, "Print Service — Error", 0x10)


# ─────────────────────────────────────────────────────────────────────────────
# Splash Screen
# ─────────────────────────────────────────────────────────────────────────────

class SplashScreen:
    """
    Ventana de progreso que se muestra durante el arranque o actualización.

    Corre en un hilo separado. La comunicación con ese hilo es 100%
    thread-safe mediante queue.Queue: el hilo principal nunca toca
    widgets de Tkinter directamente.

    Uso:
        splash = SplashScreen()
        splash.start()
        splash.set_message("Descargando actualización...")
        splash.set_progress(60)   # 0-100
        splash.close()            # espera a que la ventana se destruya
    """

    # Comandos internos de la cola
    _CMD_MESSAGE  = "message"
    _CMD_PROGRESS = "progress"
    _CMD_CLOSE    = "close"

    def __init__(self):
        self._root       = None
        self._label      = None
        self._canvas     = None
        self._bar_fill   = None
        self._bar_width  = 0
        self._ready      = threading.Event()   # ventana lista
        self._closed     = threading.Event()   # ventana destruida
        self._queue      = queue.Queue()        # canal hilo-principal → Tk
        self._thread     = threading.Thread(target=self._run, daemon=True)

    # ── API pública (llamar desde cualquier hilo) ─────────────────────────────

    def start(self):
        """Lanza el hilo de la ventana y espera a que esté lista."""
        self._thread.start()
        self._ready.wait(timeout=3)

    def set_message(self, msg: str):
        """Actualiza el texto de estado — thread-safe."""
        self._queue.put((self._CMD_MESSAGE, msg))

    def set_progress(self, pct: int):
        """Actualiza la barra de progreso 0-100 — thread-safe."""
        self._queue.put((self._CMD_PROGRESS, pct))

    def close(self):
        """Cierra la ventana y espera a que se destruya — thread-safe."""
        self._queue.put((self._CMD_CLOSE, None))
        self._closed.wait(timeout=3)   # espera confirmación del hilo Tk

    # ── Internos (solo se ejecutan en el hilo de Tkinter) ────────────────────

    def _process_queue(self):
        """
        Vacía la cola y aplica cada comando.
        Se reprograma sola cada 50 ms DENTRO del hilo de Tkinter,
        por lo que nunca hay acceso cruzado a widgets.
        """
        try:
            while True:
                cmd, arg = self._queue.get_nowait()

                if cmd == self._CMD_MESSAGE:
                    if self._label:
                        self._label.config(text=arg)

                elif cmd == self._CMD_PROGRESS:
                    if self._canvas and self._bar_fill:
                        w = int(self._bar_width * max(0, min(arg, 100)) / 100)
                        self._canvas.coords(self._bar_fill, 0, 0, w, 6)

                elif cmd == self._CMD_CLOSE:
                    if self._root:
                        self._root.destroy()
                    self._closed.set()   # confirma al hilo principal
                    return               # no reprogramar más

        except queue.Empty:
            pass

        # Reprogramar solo si no se recibió CLOSE
        if self._root:
            self._root.after(50, self._process_queue)

    def _run(self):
        """Corre en el hilo secundario — crea y mantiene la ventana."""
        self._root = tk.Tk()
        root = self._root

        # ── Configuración de la ventana ───────────────────────────────────────
        root.title("Print Service")
        root.overrideredirect(True)
        root.configure(bg="white")
        root.attributes("-topmost", True)

        w, h = 420, 220
        sw = root.winfo_screenwidth()
        sh = root.winfo_screenheight()
        root.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")
        root.configure(highlightbackground="#e0e0e0", highlightthickness=1)

        # ── Contenido ─────────────────────────────────────────────────────────
        tk.Label(
            root, text="🖨", font=("Segoe UI Emoji", 36),
            bg="white", fg="#00b37d"
        ).pack(pady=(30, 0))

        tk.Label(
            root, text="Print Service",
            font=("Segoe UI", 14, "bold"),
            bg="white", fg="#1a1a2e"
        ).pack(pady=(8, 0))

        self._label = tk.Label(
            root, text="Iniciando...",
            font=("Segoe UI", 9),
            bg="white", fg="#666666"
        )
        self._label.pack(pady=(6, 0))

        frame = tk.Frame(root, bg="white")
        frame.pack(pady=(16, 0), padx=40, fill="x")

        bg_bar = tk.Canvas(frame, height=6, bg="#f0f0f0", highlightthickness=0)
        bg_bar.pack(fill="x")

        self._canvas = bg_bar
        bg_bar.update_idletasks()
        self._bar_width = bg_bar.winfo_width() or 340
        self._bar_fill  = bg_bar.create_rectangle(0, 0, 0, 6, fill="#00b37d", outline="")

        tk.Label(
            root, text="Cargando...",
            font=("Segoe UI", 8),
            bg="white", fg="#aaaaaa"
        ).pack(side="bottom", pady=10)

        # Arrancar el procesador de cola y señalizar que la ventana está lista
        root.after(50, self._process_queue)
        self._ready.set()
        root.mainloop()


# ─────────────────────────────────────────────────────────────────────────────
# Lógica principal
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    base_dir    = get_base_dir()
    app_dir     = os.path.join(base_dir, "PrintService")
    app_exe     = os.path.join(app_dir,  "PrintService.exe")
    updater_bat = os.path.join(base_dir, "pending_update.bat")

    # ── ¿Hay un update pendiente? ─────────────────────────────────────────────
    if os.path.exists(updater_bat):

        splash = SplashScreen()
        splash.start()
        splash.set_message("Aplicando actualización...")
        splash.set_progress(10)

        proc = subprocess.Popen(
            ["cmd", "/c", updater_bat],
            creationflags=subprocess.CREATE_NO_WINDOW,
        )

        pct = 10
        while proc.poll() is None:
            time.sleep(0.5)
            if pct < 90:
                pct += 2
                splash.set_progress(pct)

        splash.set_message("¡Actualización completada!")
        splash.set_progress(100)
        time.sleep(1)
        splash.close()
        time.sleep(0.3)

        main()
        return

    # ── Verificar que PrintService.exe existe ─────────────────────────────────
    if not os.path.exists(app_exe):
        show_error(
            f"No se encontró PrintService.exe en:\n{app_dir}\n\n"
            "Asegúrate de que la carpeta PrintService\\ esté junto a Launcher.exe"
        )
        return

    # ── Splash de arranque normal ─────────────────────────────────────────────
    splash = SplashScreen()
    splash.start()
    splash.set_message("Iniciando servidor...")
    splash.set_progress(30)
    time.sleep(0.5)
    splash.set_progress(70)
    splash.set_message("Casi listo...")
    time.sleep(0.5)
    splash.set_progress(100)
    time.sleep(0.3)
    splash.close()
    time.sleep(0.2)

    # ── Lanzar PrintService y esperar ─────────────────────────────────────────
    proc = subprocess.Popen([app_exe])
    proc.wait()

    # Si PrintService dejó un .bat → hay update, procesarlo
    if os.path.exists(updater_bat):
        main()


if __name__ == "__main__":
    main()