# Add-FirewallRule-PrintService.ps1 (versión corregida)
# ====================================================
# Agrega regla de entrada al firewall para el puerto del Print Service.

param (
    [int]$Port = 56789,
    [string]$RuleName = "Print Service - Puerto $Port (TCP)",
    [string]$ProgramPath = "",                  # Opcional: ruta completa al .exe
    [string]$Description = "Permite conexiones al servicio de impresión local (HTTPS)",
    [ValidateSet("Any","Private","Public","Domain")][string]$Profile = "Any"
)

# Verificar privilegios de admin
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $isAdmin) {
    Write-Warning "Este script debe ejecutarse como administrador."
    exit 1
}

Write-Host "Configurando regla de firewall para puerto $Port ..." -ForegroundColor Cyan

$ruleNameInbound = $RuleName

# Chequear si ya existe
$existingRule = Get-NetFirewallRule -DisplayName $ruleNameInbound -ErrorAction SilentlyContinue

if ($existingRule) {
    Write-Host "La regla '$ruleNameInbound' ya existe." -ForegroundColor Yellow
    exit 0
}

try {
    $params = @{
        DisplayName      = $ruleNameInbound
        Direction        = "Inbound"
        Action           = "Allow"
        Protocol         = "TCP"
        LocalPort        = $Port
        Profile          = $Profile
        Description      = $Description
        Enabled          = "True"          # ← ¡Aquí está la corrección! String "True"
    }

    if ($ProgramPath -and (Test-Path $ProgramPath)) {
        $params["Program"] = $ProgramPath
        Write-Host "Regla restringida al programa: $ProgramPath" -ForegroundColor Green
    } else {
        Write-Host "Regla aplicada a cualquier programa (puerto global)" -ForegroundColor Green
    }

    New-NetFirewallRule @params | Out-Null

    Write-Host "Regla creada exitosamente:" -ForegroundColor Green
    Write-Host "  Nombre     : $ruleNameInbound"
    Write-Host "  Puerto     : $Port TCP"
    Write-Host "  Perfil     : $Profile"
    if ($ProgramPath) { Write-Host "  Programa   : $ProgramPath" }
}
catch {
    Write-Error "Error al crear la regla: $($_.Exception.Message)"
    exit 1
}

Write-Host "`nListo. El puerto $Port ahora está permitido." -ForegroundColor Green