# app/updater.py
"""
MÓDULO DE ACTUALIZACIONES AUTOMÁTICAS
═══════════════════════════════════════════════════════════════════════════════

¿Qué hace este módulo?
    Al arrancar la aplicación, consulta la API de GitHub para ver si hay
    una versión más nueva del .exe publicada como "Release".
    Si la hay, la descarga y lanza un script .bat que reemplaza el ejecutable
    actual mientras la app se cierra sola.

Flujo resumido:
    1. Llama a la API de GitHub → obtiene el tag de la última release.
    2. Compara con CURRENT_VERSION (definida en constants.py o aquí mismo).
    3. Si hay update → descarga el nuevo .exe a una carpeta temporal.
    4. Crea un archivo .bat que espera a que el proceso cierre,
       reemplaza el .exe y vuelve a abrirlo.
    5. Lanza el .bat y termina el proceso actual (sys.exit).

Requisito:
    Variable de entorno GITHUB_TOKEN con un Personal Access Token de GitHub
    que tenga al menos permiso de lectura sobre el repo.
    Se carga desde el archivo .env gracias a load_dotenv() en main.py.

Notas para novatos:
    - os.getenv("NOMBRE") lee una variable de entorno.
    - requests.get() hace una petición HTTP GET (como un navegador visitando una URL).
    - stream=True en requests permite descargar archivos grandes sin cargarlos
      enteros en RAM.
    - subprocess.Popen lanza un proceso externo (aquí, el .bat de actualización).
    - sys.exit(0) cierra el programa con código 0 = "salida normal, sin error".
═══════════════════════════════════════════════════════════════════════════════
"""

import os
import sys
import time
import tempfile
import subprocess

import requests


# ─────────────────────────────────────────────────────────────────────────────
# Constantes del repositorio y versión
# ─────────────────────────────────────────────────────────────────────────────

# Versión actual del ejecutable.
# ¡IMPORTANTE! Cambia este string cada vez que publiques una nueva release en GitHub.
# Formato recomendado: "MAYOR.MENOR.PARCHE"  (ej: "1.0.1", "2.3.0")
CURRENT_VERSION: str = "1.0.1"

# Datos del repositorio privado en GitHub
REPO_OWNER: str = "cellmaniadesarrollo"
REPO_NAME:  str = "ms_print-service"

# URL de la API de GitHub para obtener la última release publicada
GITHUB_API_URL: str = (
    f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/releases/latest"
)

# Nombre EXACTO del archivo .exe que subes a cada release en GitHub.
# Si algún día lo renombras en GitHub, cámbialo también aquí.
ASSET_NAME: str = "PrintService.exe"


# ─────────────────────────────────────────────────────────────────────────────
# Función principal
# ─────────────────────────────────────────────────────────────────────────────

def check_for_update() -> None:
    """
    Comprueba si hay una versión más nueva en GitHub Releases y, si la hay,
    descarga el nuevo ejecutable y reinicia la aplicación automáticamente.

    Esta función se llama UNA SOLA VEZ al arrancar el programa (desde main.py).
    Si algo falla (sin internet, sin token, etc.) simplemente imprime un aviso
    y la aplicación sigue funcionando con normalidad.

    Returns:
        None — no devuelve nada; si hay update, el proceso termina con sys.exit().
    """

    # Leer el token en tiempo de ejecución (load_dotenv ya fue llamado en main.py)
    github_token = os.getenv("GITHUB_TOKEN")

    if not github_token:
        # Sin token no podemos acceder a repos privados de GitHub
        print("[WARN] No se encontró GITHUB_TOKEN → chequeo de actualizaciones desactivado")
        print("[HINT] Agrega GITHUB_TOKEN=tu_token_aqui en el archivo .env")
        return

    # Cabeceras requeridas por la API REST de GitHub v2022-11-28
    headers = {
        "Accept":               "application/vnd.github+json",
        "Authorization":        f"Bearer {github_token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    try:
        print("[INFO] Verificando si hay nueva versión...")

        # ── 1. Consultar la API ───────────────────────────────────────────────
        response = requests.get(GITHUB_API_URL, headers=headers, timeout=12)
        response.raise_for_status()  # lanza excepción si la respuesta es 4xx/5xx

        data       = response.json()            # convierte el JSON de GitHub a dict de Python
        latest_tag = data.get("tag_name", "").lstrip("v")  # "v1.2.0" → "1.2.0"

        if not latest_tag:
            print("[WARN] No se encontró tag en la última release de GitHub")
            return

        # ── 2. Comparar versiones ─────────────────────────────────────────────
        if latest_tag <= CURRENT_VERSION:
            # La comparación de strings funciona para versiones semver simples.
            # Para versiones complejas usa: from packaging.version import Version
            print(f"[INFO] Versión actualizada → v{CURRENT_VERSION} (última en GitHub: v{latest_tag})")
            return

        print(f"[UPDATE] ¡Nueva versión disponible! v{latest_tag} > v{CURRENT_VERSION}")

        # ── 3. Buscar el asset (el .exe) en la release ────────────────────────
        asset_url = None
        for asset in data.get("assets", []):
            if asset.get("name") == ASSET_NAME:
                asset_url = asset.get("browser_download_url")
                break

        if not asset_url:
            print(f"[ERROR] No se encontró '{ASSET_NAME}' en la release v{latest_tag}")
            print("[HINT] Verifica que el .exe se haya subido con ese nombre exacto en GitHub")
            return

        # ── 4. Descargar el nuevo .exe ────────────────────────────────────────
        temp_dir     = tempfile.gettempdir()   # carpeta temporal del sistema (ej: C:\Users\...\AppData\Local\Temp)
        new_exe_path = os.path.join(temp_dir, f"PrintService_new_v{latest_tag}.exe")

        print(f"[INFO] Descargando actualización → {new_exe_path}")

        # stream=True descarga el archivo en trozos (chunks) para no saturar la RAM
        with requests.get(asset_url, headers=headers, stream=True) as r:
            r.raise_for_status()
            with open(new_exe_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)

        print("[INFO] Descarga completada.")

        # ── 5. Crear script .bat que reemplaza el .exe mientras no corre ──────
        current_exe = sys.executable                                     # ruta del .exe que está corriendo ahora
        updater_bat = os.path.join(temp_dir, "update_printservice.bat")

        bat_content = f"""@echo off
echo Actualizando Print Service a v{latest_tag}...
timeout /t 4 >nul
taskkill /f /im "{os.path.basename(current_exe)}" >nul 2>&1
move /y "{new_exe_path}" "{current_exe}"
echo Actualizacion completada. Reiniciando...
start "" "{current_exe}"
del "%~f0"
"""
        # Nota: del "%~f0" hace que el .bat se borre a sí mismo al terminar

        with open(updater_bat, "w", encoding="utf-8") as f:
            f.write(bat_content)

        # ── 6. Lanzar el .bat y cerrar este proceso ───────────────────────────
        print("[INFO] Ejecutando updater y cerrando proceso actual...")
        subprocess.Popen(
            ["cmd", "/c", updater_bat],
            creationflags=subprocess.CREATE_NEW_CONSOLE,  # abre ventana nueva para que el .bat sea visible
        )

        time.sleep(1)   # pequeña pausa para que el .bat empiece antes de que cerremos
        sys.exit(0)     # salida limpia → el .bat se encarga del resto

    except requests.exceptions.RequestException as e:
        # Error de red: sin internet, timeout, GitHub caído, etc.
        print(f"[WARN] No se pudo conectar con GitHub: {e}")

    except Exception as e:
        # Cualquier otro error inesperado → no bloquea el arranque
        print(f"[ERROR] Fallo durante el proceso de actualización: {e}")