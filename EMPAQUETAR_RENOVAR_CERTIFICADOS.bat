@echo off
setlocal EnableDelayedExpansion

echo =====================================================
echo    RENOVACION + EMPAQUETADO (MODO CARPETA)
echo =====================================================

cd /d "C:\simple-acme"
wacs.exe --renew --force

:: Preparar certificados en la carpeta del proyecto
cd /d "D:\print-service-public-py\certs"
type "localprint.teamcellmania.com-crt.pem" > server.pem
type "localprint.teamcellmania.com-chain.pem" >> server.pem
copy /Y "localprint.teamcellmania.com-key.pem" "server.key"

:: Compilar en modo carpeta (mas estable)
cd /d "D:\print-service-public-py"
echo Compilando...
poetry run pyinstaller ^
    --noconfirm ^
    --onedir ^
    --noconsole ^
    --name "PrintService" ^
    --add-data "certs;certs" ^
    --add-data "icon.png;." ^
    --collect-data escpos ^
    --hidden-import escpos.printer ^
    --hidden-import escpos.capabilities ^
    app/main.py

echo.
echo PROCESO FINALIZADO.
echo La carpeta lista para usar esta en: D:\print-service-public-py\dist\PrintService
pause