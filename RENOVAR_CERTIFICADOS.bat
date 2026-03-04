@echo off
setlocal EnableDelayedExpansion

echo =====================================================
echo    RENOVACION FORZADA + COMPILACION DEL .EXE
echo    Dominio: localprint.teamcellmania.com
echo =====================================================
echo.

cd /d "C:\simple-acme" || (
    echo ERROR: No se pudo cambiar a la carpeta C:\simple-acme
    pause
    exit /b 1
)

echo Ejecutando renovacion forzada...
wacs.exe --renew --force --verbose

if %ERRORLEVEL% neq 0 (
    echo.
    echo ERROR: La renovacion fallo. Revisa los mensajes arriba.
    echo Posibles causas: problema con AWS, DNS, o Let's Encrypt temporalmente.
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo Renovacion completada. Verificando archivos generados...
echo.

cd /d "D:\print-service-public-py\certs" || (
    echo ERROR: No se pudo acceder a la carpeta D:\print-service-public-py\certs
    pause
    exit /b 1
)

set "CRT=localprint.teamcellmania.com-crt.pem"
set "CHAIN=localprint.teamcellmania.com-chain.pem"
set "KEY=localprint.teamcellmania.com-key.pem"

if not exist "%CRT%" (
    echo ERROR: No se encontro el archivo %CRT%
    echo Verifica que win-acme este configurado para guardar los .pem en D:\print-service-public-py\certs\
    pause
    exit /b 1
)

echo Actualizando server.pem y server.key...
type "%CRT%" > server.pem
type "%CHAIN%" >> server.pem
copy /Y "%KEY%" "server.key" >nul

echo.
echo Archivos actualizados correctamente en certs:
dir /b server.pem server.key
echo.

echo.
echo =====================================================
echo    COMPILANDO NUEVA VERSION DEL EJECUTABLE...
echo =====================================================
echo.

cd /d "D:\print-service-public-py"

powershell -NoProfile -ExecutionPolicy Bypass -File .\build.ps1

if %ERRORLEVEL% neq 0 (
    echo ERROR: Fallo en PyInstaller. Revisa el output arriba.
    pause
    exit /b %ERRORLEVEL%
) else (
    echo.
    echo Compilacion finalizada. .exe generado en dist\
)

echo.
echo Copiando certificados actualizados a dist\certs...
if not exist "dist\certs" (
    mkdir "dist\certs" 2>nul
)

copy /Y "certs\server.pem" "dist\certs\server.pem" >nul
copy /Y "certs\server.key" "dist\certs\server.key" >nul

if exist "dist\certs\server.pem" (
    echo Copia exitosa a dist\certs
) else (
    echo ADVERTENCIA: No se pudo copiar a dist\certs (verifica que dist exista)
)

echo.
echo =====================================================
echo               PROCESO FINALIZADO
echo   Certificado renovado, .exe recompilado y certificados copiados
echo =====================================================
echo.

pause