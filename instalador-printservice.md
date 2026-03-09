# Instalador PrintService — Documentación

## Herramienta utilizada

**Inno Setup** — generador de instaladores para Windows. El script `.iss` define secciones declarativas (`[Setup]`, `[Files]`, `[Icons]`, etc.) y una sección `[Code]` con lógica en Pascal Script para personalizar el wizard.

---

## Estructura del `.iss`

### Secciones declarativas

| Sección | Qué hace |
|---|---|
| `[Setup]` | Metadatos: nombre, versión, carpeta destino, compresión |
| `[Files]` | Copia `PrintService\*` recursivamente a `{app}` |
| `[Dirs]` | Crea `{app}\certs` vacío para los certificados SSL |
| `[Icons]` | Accesos directos en el menú inicio y escritorio |
| `[Run]` | Lanza `PrintService.exe` al finalizar la instalación |
| `[UninstallDelete]` | Elimina `.env`, `config.json` y `certs\` al desinstalar |

### Sección `[Code]` — Pascal Script

Contiene toda la lógica interactiva del instalador.

---

## Página de configuración personalizada

Se agrega una página extra entre "Seleccionar directorio" y "Listo para instalar" usando `CreateCustomPage(wpSelectDir, ...)`.

### Controles creados dinámicamente en `InitializeWizard`

```
┌─────────────────────────────────────────────┐
│ ○ Conexion por Red (IP)                     │
│ ○ Conexion USB                              │
│                                             │
│ [Campos de red — visibles solo en modo RED] │
│   IP de la impresora: [192.168.0.101      ] │
│   Puerto: [9100]   Timeout (seg): [10]      │
│                                             │
│ [Mensaje — visible solo en modo USB]        │
│   La impresora USB se detectara             │
│   automaticamente al conectarla.            │
│                                             │
│ Ancho del papel (mm): [80]                  │
└─────────────────────────────────────────────┘
```

---

## Lógica de visibilidad — `UpdateFieldStates`

Cuando el usuario cambia el radio, se actualizan las propiedades `.Visible` de cada control. Ambos grupos (RED y USB) comparten el mismo `Top` (desde 56px), pero solo uno está visible a la vez.

```pascal
procedure UpdateFieldStates;
var
  IsNetwork: Boolean;
begin
  IsNetwork := NetworkRadio.Checked;

  // Campos de red: visibles solo en modo RED
  IpLabel.Visible      := IsNetwork;
  IpEdit.Visible       := IsNetwork;
  ...

  // Mensaje USB: visible solo en modo USB
  UsbInfoLabel.Visible := not IsNetwork;
end;
```

> **Nota:** Inno Setup no tiene un sistema de layout automático. Si se usa `.Enabled` en lugar de `.Visible`, los controles siguen visibles pero deshabilitados (se solapan). La solución correcta es siempre `.Visible`.

---

## Validación — `NextButtonClick`

Se intercepta el clic en "Siguiente" para validar la IP cuando el modo es RED:

```pascal
function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if CurPageID = ConfigPage.ID then
    if NetworkRadio.Checked and (Trim(IpEdit.Text) = '') then
    begin
      MsgBox('La IP de la impresora no puede estar vacia.', mbError, MB_OK);
      Result := False;
    end;
end;
```

---

## Generación de archivos — `CurStepChanged(ssPostInstall)`

Al finalizar la copia de archivos se ejecutan tres procedimientos:

### 1. `GenerateConfigJson`

Genera `{app}\config.json` con los valores ingresados en el wizard.

**Modo RED** — incluye el bloque `"network"` con IP, puerto y timeout:
```json
{
  "connection": "network",
  "network": {
    "ip": "192.168.0.101",
    "port": 9100,
    "timeout": 10
  },
  "paperWidth": 80,
  ...
}
```

**Modo USB** — solo cambia `"connection"`, sin bloque `"network"`. La impresora se detecta automáticamente en runtime:
```json
{
  "connection": "usb",
  "paperWidth": 80,
  ...
}
```

Los valores fijos del ticket (footer, QR URL, features, encoding) se hardcodean directamente en el script y no se exponen al usuario instalador.

### 2. `GenerateEnvFile`

Genera `{app}\.env` con los parámetros del servidor:

```env
PORT=56789
SSL_KEYFILE=certs/server.key
SSL_CERTFILE=certs/server.pem
RELOAD=False
GITHUB_TOKEN=...
UPDATE_INTERVAL_MINUTES=1
UPDATE_INTERVAL_HOURS=6
```

### 3. `AddFirewallRule`

Agrega dos reglas de firewall vía `netsh` usando `Exec()`:

| Regla | Dirección | Propósito |
|---|---|---|
| `PrintService` | Inbound | Permite que otros PCs se conecten al puerto 56789 |
| `PrintService Out` | Outbound | Permite conectarse a la impresora de red y a GitHub para updates |

---

## Desinstalación — `CurUninstallStepChanged(usUninstall)`

Al desinstalar:
1. Termina el proceso `PrintService.exe` con `taskkill /F`
2. Espera 1.5 segundos para liberar archivos
3. Elimina las reglas de firewall con `netsh`
4. La sección `[UninstallDelete]` elimina `.env`, `config.json` y `certs\`

---

## Detección automática USB (runtime — `connection.py`)

Cuando `connection = "usb"`, la aplicación Python detecta la impresora en tiempo de ejecución sin necesidad de VID/PID en el config:

1. Busca dispositivos con `PNPClass = Printer` o `Service = usbprint`
2. Fallback: cualquier dispositivo con endpoint OUT bulk
3. Detecta los endpoints correctos iterando la configuración USB del dispositivo
4. Pasa `out_ep` e `in_ep` explícitamente al constructor de `escpos.Usb` para evitar el error `Invalid endpoint address`

> **Requisito previo en Windows:** el driver del dispositivo debe ser **WinUSB** (instalado con [Zadig](https://zadig.akeo.ie)). El driver nativo de Windows (`usbprint`) no es compatible con `libusb`.
