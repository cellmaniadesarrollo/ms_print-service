@echo off
setlocal EnableDelayedExpansion

echo =====================================================
echo    SOLO EMPAQUETADO (MODO CARPETA)
echo =====================================================

:: Asegurar que los certificados esten unidos
cd /d "D:\print-service-public-py\certs"
type "localprint.teamcellmania.com-crt.pem" > server.pem
type "localprint.teamcellmania.com-chain.pem" >> server.pem
copy /Y "localprint.teamcellmania.com-key.pem" "server.key"

:: Compilar
cd /d "D:\print-service-public-py"
poetry run pyinstaller ^
    --noconfirm ^
    --clean ^
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
echo Carpeta generada en dist\PrintService
pause