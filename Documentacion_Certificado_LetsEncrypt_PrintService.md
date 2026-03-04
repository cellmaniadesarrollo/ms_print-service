# Documentación: Certificado HTTPS Let's Encrypt para Print Service (localprint.teamcellmania.com)

**Fecha de creación inicial:** Marzo 2026\
**Dominio:** localprint.teamcellmania.com\
**Propósito:** Servir HTTPS seguro desde el .exe compilado con
PyInstaller, sin warnings en navegadores/clientes.\
**Autoridad:** Let's Encrypt (válido 90 días, renovación automática vía
Route53).\
**Ubicación de archivos:**
D:`\Teamcellmania`{=tex}\_backend`\print`{=tex}-service-public-py`\certs  `{=tex}
**Herramienta principal:** simple-acme (wacs.exe) v2.3.5 pluggable con
plugin Route53

------------------------------------------------------------------------

## 1. Requisitos previos (ya configurados)

-   Cuenta AWS IAM con permisos Route53:
    -   Access Key ID: AKIAUVRLDYHKKHIBBZGR (ejemplo)
    -   Secret Access Key: guardado en vault como "route53-print"
    -   Permisos mínimos:
        -   route53:ChangeResourceRecordSets
        -   route53:ListHostedZones
-   Carpeta permanente de simple-acme:
    -   Ruta: C:`\simple`{=tex}-acme
    -   Ejecutable: wacs.exe
    -   Plugin Route53:
        C:`\ProgramData`{=tex}`\simple`{=tex}-acme`\plugins`{=tex}\
-   Registro DNS en Route53:
    -   Tipo: A (o CNAME si usas dynamic DNS)
    -   Nombre: localprint.teamcellmania.com
    -   Valor: IP pública del servidor

------------------------------------------------------------------------

## 2. Generación inicial del certificado (solo primera vez)

Ejecutar como Administrador:

``` bash
cd C:\simple-acme
.\wacs.exe
```

### Wizard (modo M - full options)

-   Dominio: localprint.teamcellmania.com
-   Email: tu correo
-   Validación: 6 - Route53
-   Credenciales AWS: Access Key + Secret Key
-   Vault name: route53-print
-   Región: us-east-1
-   Key type: RSA
-   Store: PEM encoded files
-   Path:
    D:`\Teamcellmania`{=tex}\_backend`\print`{=tex}-service-public-py`\certs`{=tex}
-   Password: None
-   Instalación adicional: No
-   Perfil: default/classic

### Archivos generados

-   localprint.teamcellmania.com-crt.pem
-   localprint.teamcellmania.com-key.pem
-   localprint.teamcellmania.com-chain.pem

### Conversión manual (solo primera vez)

1.  Abrir \*-crt.pem
2.  Copiar todo su contenido
3.  Pegar debajo todo el contenido de \*-chain.pem
4.  Guardar como: server.pem
5.  Renombrar \*-key.pem → server.key

------------------------------------------------------------------------

## 3. Renovación automática + compilación

### Archivo principal: RENOVAR_Y\_COMPILAR.bat

Ubicación:
D:`\Teamcellmania`{=tex}\_backend`\print`{=tex}-service-public-py

Ejecutar como Administrador cada 30-60 días o antes de publicar nueva
versión.

``` bat
@echo off
setlocal EnableDelayedExpansion

echo =====================================================
echo    RENOVACION FORZADA + COMPILACION DEL .EXE
echo    Dominio: localprint.teamcellmania.com
echo =====================================================
echo.

cd /d "C:\simple-acme" || (
    echo ERROR: No se pudo cambiar a C:\simple-acme
    pause
    exit /b 1
)

echo Ejecutando renovacion forzada...
wacs.exe --renew --force --verbose

if %ERRORLEVEL% neq 0 (
    echo ERROR: Renovacion fallo.
    pause
    exit /b %ERRORLEVEL%
)

cd /d "D:\Teamcellmania_backend\print-service-public-py\certs" || (
    echo ERROR: No se pudo acceder a certs
    pause
    exit /b 1
)

set "CRT=localprint.teamcellmania.com-crt.pem"
set "CHAIN=localprint.teamcellmania.com-chain.pem"
set "KEY=localprint.teamcellmania.com-key.pem"

if not exist "%CRT%" (
    echo ERROR: No se encontro %CRT%
    pause
    exit /b 1
)

type "%CRT%" > server.pem
type "%CHAIN%" >> server.pem
copy /Y "%KEY%" "server.key" >nul

echo Archivos actualizados: server.pem y server.key

echo.
echo =====================================================
echo    COMPILANDO NUEVA VERSION...
echo =====================================================
echo.

cd /d "D:\Teamcellmania_backend\print-service-public-py"

powershell -NoProfile -ExecutionPolicy Bypass -File .\build.ps1

if %ERRORLEVEL% neq 0 (
    echo ERROR: Fallo en PyInstaller
    pause
    exit /b %ERRORLEVEL%
) else (
    echo Compilacion OK. .exe en dist\
)

echo.
echo Copiando certificados a dist\certs...
if not exist "dist\certs" mkdir "dist\certs" 2>nul
copy /Y "certs\server.pem" "dist\certs\server.pem" >nul
copy /Y "certs\server.key" "dist\certs\server.key" >nul

if exist "dist\certs\server.pem" (
    echo Copia OK
) else (
    echo ADVERTENCIA: No se copio a dist\certs
)

echo.
echo PROCESO FINALIZADO
pause
```

------------------------------------------------------------------------

### Archivo auxiliar: build.ps1

``` powershell
Write-Host "Compilando con PyInstaller..." -ForegroundColor Cyan

poetry run pyinstaller `
    --onefile `
    --noconsole `
    --add-data "certs;certs" `
    --add-data "icon.png;." `
    --collect-data escpos `
    --hidden-import escpos.printer `
    --hidden-import escpos.capabilities `
    app/main.py

if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR en PyInstaller" -ForegroundColor Red
    exit $LASTEXITCODE
} else {
    Write-Host "Compilacion exitosa" -ForegroundColor Green
}
```

------------------------------------------------------------------------

## 4. Acceso en producción

-   URL clientes: https://localprint.teamcellmania.com
-   Certificado válido automáticamente (confianza global)
-   No instalar certificados en clientes
-   El .exe debe ejecutarse en la PC con impresora
-   DNS en Route53 apuntando a IP del servidor
-   Puerto abierto en firewall/router

------------------------------------------------------------------------

## 5. Mantenimiento

-   Ejecutar RENOVAR_Y\_COMPILAR.bat como Admin cada \~60 días
-   Revisar logs en: C:`\ProgramData`{=tex}`\simple`{=tex}-acme\
-   Tarea programada opcional creada por simple-acme (corre diariamente)

------------------------------------------------------------------------

## Estado Final

✔ Certificado HTTPS válido\
✔ Renovación automatizada vía Route53\
✔ Integrado en .exe compilado\
✔ Copia automática a carpeta dist para MSI

------------------------------------------------------------------------

**Documento reproducible y listo para producción.**
