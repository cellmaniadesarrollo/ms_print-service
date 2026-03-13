# Documentación final: Creación del .exe standalone para Windows (Print Service - Python)

## 🎯 Objetivo

Generar un ejecutable `.exe` portable y standalone que:

-   Corra el servidor FastAPI en background (HTTPS con certificados
    mkcert).
-   Muestre un icono en la bandeja del sistema (system tray) con menú
    (Status / Salir).
-   No abra ventana de consola visible.
-   Lea `config.json` y `certs/` desde la misma carpeta donde está el
    `.exe`.
-   Sea compatible con PyInstaller + Poetry en Python 3.13.

------------------------------------------------------------------------

## ⚠ Problema encontrado con Poetry y dependencias dev

Al intentar agregar herramientas necesarias para el tray y el packaging:

``` powershell
poetry add pystray pyinstaller pywin32 --group dev
```

Poetry falló con error de resolución de dependencias porque:

-   El proyecto tenía:

``` toml
requires-python = ">=3.13"
```

-   PyInstaller 6.19.0 requiere explícitamente:

```{=html}
<!-- -->
```
    Python >=3.8, <3.15

Poetry rechazó la instalación porque el proyecto podría ejecutarse en
Python 3.15+.

------------------------------------------------------------------------

## ✅ Solución aplicada

Modificar `pyproject.toml`:

### Formato PEP 621

``` toml
[project]
name = "print-service-public-py"
version = "0.1.0"
requires-python = ">=3.13,<3.15"
```

### Formato clásico Poetry

``` toml
[tool.poetry.dependencies]
python = ">=3.13,<3.15"
```

Luego ejecutar:

``` powershell
poetry add pystray pyinstaller pywin32 --group dev
poetry install
```

✔ Instalación exitosa sin conflictos.

------------------------------------------------------------------------

## 📌 Razones de la decisión

-   PyInstaller 6.19.0 no soporta Python 3.15.
-   Limitar a `<3.15` evita errores futuros.
-   No se usó Docker porque `pystray` + `pywin32` requieren entorno
    Windows real.
-   No existen versiones compatibles aún con 3.15.

------------------------------------------------------------------------

## 🔁 Recomendación

Mantener:

    requires-python = ">=3.13,<3.15"

Hasta que PyInstaller soporte oficialmente 3.15+.

------------------------------------------------------------------------

# 🚀 Pasos completos para generar el .exe

## 1️⃣ Agregar dependencias

``` powershell
poetry add pystray pyinstaller pywin32 --group dev
```

------------------------------------------------------------------------

## 2️⃣ Modificaciones clave en el código

### `app/config.py`

-   Implementar `get_executable_dir()`.
-   Leer `config.json` desde el mismo directorio del `.exe`.

### `app/main.py`

-   Redirigir stdout/stderr en modo `--noconsole`.
-   Ejecutar uvicorn en thread independiente.
-   Implementar bandeja con `pystray`.
-   Manejar paths bundled para `certs/` y `capabilities.json`.

------------------------------------------------------------------------

## 3️⃣ Comando final de PyInstaller

Desde la raíz del proyecto:

``` powershell
poetry run pyinstaller `
    --onedir --noconsole --name "PrintService" `
    --add-data "certs;certs" `
    --add-data "icon.png;." `
    --collect-data escpos `
    --hidden-import escpos.printer `
    --hidden-import escpos.capabilities `
    app/main.py
```
``` powershell
poetry run pyinstaller `
    --onefile --noconsole --name "Launcher" `
    --add-data "icon.png;." `
    --uac-admin `
    launcher.py
```
### Explicación

-   `--onefile`: Genera un solo `.exe`.
-   `--noconsole`: No muestra ventana de consola.
-   No incluir `config.json` (debe estar al lado del `.exe`).

------------------------------------------------------------------------

# 🧪 Pruebas post-compilación

1.  Copiar `config.json` al lado de `dist/main.exe`.
2.  Ejecutar doble clic.
3.  Verificar:
    -   Icono en bandeja.
    -   Servidor activo en:

```{=html}
<!-- -->
```
    https://localhost:56789

4.  Verificar puerto:

``` powershell
netstat -ano | findstr :56789
```

5.  Probar endpoint:

```{=html}
<!-- -->
```
    POST https://localhost:56789/print

------------------------------------------------------------------------

# 🔥 Firewall (una vez por máquina)

``` powershell
.\Add-FirewallRule-PrintService.ps1 -ProgramPath "ruta\completal\main.exe"
```

------------------------------------------------------------------------

# 📦 Notas finales sobre el .exe

-   Tamaño aproximado: 60--120 MB.
-   Para producción:
    -   `RELOAD=False`
    -   Eliminar prints de debug.
-   Es portable: solo requiere:
    -   `config.json`
    -   `certs/`
    -   `icon.png`


