# app/updater.py
"""
MÓDULO DE ACTUALIZACIONES AUTOMÁTICAS — distribución por ZIP
═══════════════════════════════════════════════════════════════════════════════

Flujo:
    1. GitHub API → obtiene latest tag
    2. Compara con CURRENT_VERSION
    3. Si hay update → descarga PrintService.zip en dist\
    4. Verifica tamaño del archivo descargado
    5. Escribe pending_update.bat en dist\
    6. os._exit(0) → cierra PrintService
    7. Launcher muestra splash → ejecuta .bat → relanza

Estructura en disco:
    dist\
    ├── Launcher.exe
    ├── pending_update.bat        ← nunca dentro de PrintService\
    ├── PrintService_v1.0.2.zip   ← fuera de PrintService\
    └── PrintService\
        ├── PrintService.exe
        ├── config.json
        ├── .env
        └── _internal\
═══════════════════════════════════════════════════════════════════════════════
"""

import os
import sys
import time

import requests


# ─────────────────────────────────────────────────────────────────────────────
# Constantes — ACTUALIZA CURRENT_VERSION EN CADA RELEASE
# ─────────────────────────────────────────────────────────────────────────────

CURRENT_VERSION: str = "1.1.5"
UPDATE_INTERVAL_MINUTES: int = 1       # ← 1 beta, 360 producción

REPO_OWNER: str = "cellmaniadesarrollo"
REPO_NAME:  str = "ms_print-service"

GITHUB_API_URL: str = (
    f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/releases/latest"
)

ASSET_NAME: str = "PrintService.zip"


# ─────────────────────────────────────────────────────────────────────────────
# Helper
# ─────────────────────────────────────────────────────────────────────────────

def _get_base_dir() -> str:
    r"""
    dist\PrintService\ en modo .exe
    Raíz del proyecto en desarrollo
    """
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ─────────────────────────────────────────────────────────────────────────────
# Función principal
# ─────────────────────────────────────────────────────────────────────────────

def check_for_update() -> None:

    github_token = os.getenv("GITHUB_TOKEN")

    if not github_token:
        print("[WARN] No se encontró GITHUB_TOKEN → actualizaciones desactivadas")
        print("[HINT] Agrega GITHUB_TOKEN=tu_token en el archivo .env")
        return

    headers = {
        "Accept":               "application/vnd.github+json",
        "Authorization":        f"Bearer {github_token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    try:
        print("[INFO] Verificando si hay nueva versión...")

        # ── 1. Consultar GitHub API ───────────────────────────────────────────
        response = requests.get(GITHUB_API_URL, headers=headers, timeout=15)
        response.raise_for_status()
        data = response.json()

        latest_tag = data.get("tag_name", "").lstrip("v")

        if not latest_tag:
            print("[WARN] No se encontró tag en la última release")
            return

        # ── 2. Comparar versiones ─────────────────────────────────────────────
        if latest_tag <= CURRENT_VERSION:
            print(f"[INFO] Versión actualizada → v{CURRENT_VERSION} (GitHub: v{latest_tag})")
            return

        print(f"[UPDATE] ¡Nueva versión disponible! v{latest_tag} > v{CURRENT_VERSION}")

        # ── 3. Buscar el asset ZIP ────────────────────────────────────────────
        asset_url     = None
        expected_size = 0

        for asset in data.get("assets", []):
            if asset.get("name") == ASSET_NAME:
                asset_url     = asset.get("browser_download_url")
                expected_size = asset.get("size", 0)
                break

        if not asset_url:
            print(f"[ERROR] No se encontró '{ASSET_NAME}' en la release v{latest_tag}")
            return

        # ── 4. Calcular rutas ─────────────────────────────────────────────────
        base_dir     = _get_base_dir()                            # dist\PrintService\
        parent_dir   = os.path.dirname(base_dir)                  # dist\
        launcher_exe = os.path.join(parent_dir, "Launcher.exe")   # dist\Launcher.exe
        temp_dir_bat = os.path.join(parent_dir, "_update_temp")   # dist\_update_temp\
        zip_path     = os.path.join(parent_dir, f"PrintService_v{latest_tag}.zip")
        updater_bat  = os.path.join(parent_dir, "pending_update.bat")

        # ── 5. Descargar el ZIP ───────────────────────────────────────────────
        print(f"[INFO] Descargando v{latest_tag} ({expected_size / 1_048_576:.1f} MB)...")

        with requests.get(asset_url, headers=headers, stream=True, timeout=180) as r:
            r.raise_for_status()
            with open(zip_path, "wb") as f:
                downloaded = 0
                for chunk in r.iter_content(chunk_size=65_536):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if downloaded % (10 * 1_048_576) < 65_536:
                            pct = (downloaded / expected_size * 100) if expected_size else 0
                            print(f"[INFO]   {downloaded / 1_048_576:.0f} MB / "
                                  f"{expected_size / 1_048_576:.0f} MB ({pct:.0f}%)")

        # ── 6. Verificar integridad ───────────────────────────────────────────
        actual_size = os.path.getsize(zip_path)
        if expected_size > 0 and actual_size != expected_size:
            print(f"[ERROR] Descarga incompleta ({actual_size:,} de {expected_size:,} bytes)")
            os.remove(zip_path)
            return

        print("[INFO] Descarga completa ✓")

        # ── 7. Escribir pending_update.bat en dist\ ───────────────────────────
        # Sin pauses — totalmente automatizado
        # Corre sin ventana de consola gracias a CREATE_NO_WINDOW en launcher.py
        bat_content = f"""@echo off
timeout /t 4 >nul

powershell -NoProfile -Command "Expand-Archive -Path '{zip_path}' -DestinationPath '{temp_dir_bat}' -Force"
if errorlevel 1 exit /b 1

if exist "{base_dir}\\config.json" copy /y "{base_dir}\\config.json" "{temp_dir_bat}\\PrintService\\config.json" >nul
if exist "{base_dir}\\.env"        copy /y "{base_dir}\\.env"        "{temp_dir_bat}\\PrintService\\.env"        >nul

rd /s /q "{base_dir}"

powershell -NoProfile -Command "Move-Item -Path '{temp_dir_bat}\\PrintService' -Destination '{parent_dir}\\PrintService' -Force"
if errorlevel 1 exit /b 1

rd /s /q "{temp_dir_bat}" 2>nul
del /f /q "{zip_path}" 2>nul

del "%~f0"
"""

        with open(updater_bat, "w", encoding="utf-8") as f:
            f.write(bat_content)

        print(f"[INFO] pending_update.bat escrito en: {updater_bat}")
        print("[INFO] Cerrando app → el Launcher aplicará la actualización...")
        time.sleep(1)

        os._exit(0)

    except requests.exceptions.RequestException as e:
        print(f"[WARN] No se pudo conectar con GitHub: {e}")

    except Exception as e:
        print(f"[ERROR] Fallo en actualización: {e}")