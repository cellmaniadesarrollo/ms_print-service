# build.ps1 - Compilación con PyInstaller

Write-Host "Iniciando compilación con PyInstaller..." -ForegroundColor Cyan

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
    Write-Host "ERROR: PyInstaller falló con código $LASTEXITCODE" -ForegroundColor Red
    exit $LASTEXITCODE
} else {
    Write-Host "Compilación completada exitosamente. .exe generado en dist/" -ForegroundColor Green
}