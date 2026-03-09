# launcher.py
"""
LAUNCHER — Print Service
═══════════════════════════════════════════════════════════════════════════════
Lanza PrintService.exe y espera a que termine.
Muestra una splash screen durante el arranque y las actualizaciones.
═══════════════════════════════════════════════════════════════════════════════
"""

import os
import sys
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
    Ventana de progreso blanca que se muestra mientras ocurre
    el arranque o la actualización.

    Se corre en un hilo separado para no bloquear el proceso principal.

    Uso:
        splash = SplashScreen()
        splash.start()
        splash.set_message("Descargando actualización...")
        splash.set_progress(60)   # 0-100
        splash.close()
    """

    def __init__(self):
        self._root    = None
        self._label   = None
        self._bar     = None
        self._canvas  = None
        self._ready   = threading.Event()  # señal de que la ventana ya está lista
        self._thread  = threading.Thread(target=self._run, daemon=True)

    def start(self):
        """Lanza el hilo de la ventana y espera a que esté lista."""
        self._thread.start()
        self._ready.wait(timeout=3)  # espera máx 3 s a que tkinter arranque

    def _run(self):
        """Corre en el hilo secundario — crea y mantiene la ventana."""
        self._root = tk.Tk()
        root = self._root

        # ── Configuración de la ventana ───────────────────────────────────────
        root.title("Print Service")
        root.overrideredirect(True)          # sin bordes ni barra de título
        root.configure(bg="white")
        root.attributes("-topmost", True)    # siempre encima

        # Centrar en pantalla
        w, h = 420, 220
        sw = root.winfo_screenwidth()
        sh = root.winfo_screenheight()
        root.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")

        # Borde sutil
        root.configure(highlightbackground="#e0e0e0", highlightthickness=1)

        # ── Contenido ─────────────────────────────────────────────────────────
        # Ícono / emoji
        tk.Label(
            root, text="🖨", font=("Segoe UI Emoji", 36),
            bg="white", fg="#00b37d"
        ).pack(pady=(30, 0))

        # Título
        tk.Label(
            root, text="Print Service",
            font=("Segoe UI", 14, "bold"),
            bg="white", fg="#1a1a2e"
        ).pack(pady=(8, 0))

        # Mensaje de estado (dinámico)
        self._label = tk.Label(
            root, text="Iniciando...",
            font=("Segoe UI", 9),
            bg="white", fg="#666666"
        )
        self._label.pack(pady=(6, 0))

        # Barra de progreso manual (canvas)
        frame = tk.Frame(root, bg="white")
        frame.pack(pady=(16, 0), padx=40, fill="x")

        bg_bar = tk.Canvas(frame, height=6, bg="#f0f0f0", highlightthickness=0)
        bg_bar.pack(fill="x")

        self._canvas   = bg_bar
        self._bar_fill = None
        self._bar_width = 0

        # Dibujar barra inicial vacía
        bg_bar.update_idletasks()
        self._bar_width = bg_bar.winfo_width() or 340
        self._bar_fill  = bg_bar.create_rectangle(
            0, 0, 0, 6, fill="#00b37d", outline=""
        )

        # Versión
        tk.Label(
            root, text="Cargando...",
            font=("Segoe UI", 8),
            bg="white", fg="#aaaaaa"
        ).pack(side="bottom", pady=10)

        # Señal de que la ventana está lista
        self._ready.set()
        root.mainloop()

    def set_message(self, msg: str):
        """Actualiza el texto de estado (thread-safe)."""
        if self._root and self._label:
            self._root.after(0, lambda: self._label.config(text=msg))

    def set_progress(self, pct: int):
        """Actualiza la barra de progreso 0-100 (thread-safe)."""
        if self._root and self._canvas and self._bar_fill:
            def _update():
                w = int(self._bar_width * max(0, min(pct, 100)) / 100)
                self._canvas.coords(self._bar_fill, 0, 0, w, 6)
            self._root.after(0, _update)

    def close(self):
        """Cierra la ventana (thread-safe)."""
        if self._root:
            self._root.after(0, self._root.destroy)


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
            creationflags=subprocess.CREATE_NO_WINDOW,  # sin ventana de consola
        )

        # Animar la barra mientras el .bat corre
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

        # El .bat terminó → PrintService\ ya está actualizada → relanzar
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