; =============================================================================
; Script de instalación Inno Setup para PrintService
; =============================================================================
; Autor:       Christian
; Descripción: Instala el servicio de impresión PrintService con Launcher.exe
;              Incluye página personalizada para configurar conexión de impresora
;              (red o USB), genera config.json y .env, agrega reglas de firewall.
; Versión:     1.0
; Fecha:       Marzo 2026
; Notas:       Requiere ejecución como administrador (PrivilegesRequired=admin)
;              para instalar en Program Files y modificar firewall.
; =============================================================================

[Setup]
; Nombre de la aplicación (se muestra en el asistente y desinstalador)
AppName=PrintService
; Versión de la aplicación
AppVersion=1.0
; Carpeta de instalación predeterminada: C:\Program Files\PrintService
; {pf} fuerza Program Files (requiere admin)
DefaultDirName={pf}\PrintService
; Nombre del grupo en el menú Inicio
DefaultGroupName=PrintService
; Carpeta donde se genera el instalador final
OutputDir=Output
; Nombre del archivo .exe generado
OutputBaseFilename=Instalador_PrintService
; Compresión usada (buen balance tamaño/velocidad)
Compression=lzma
SolidCompression=yes
; Estilo visual del asistente (moderno)
WizardStyle=modern
; Requiere privilegios de administrador (necesario para Program Files y firewall)
PrivilegesRequired=admin
; Opcional: permite override vía línea de comandos o diálogo (para "solo para mí")
; PrivilegesRequiredOverridesAllowed=dialog commandline

[Files]
; Copia toda la carpeta PrintService (incluyendo subcarpetas)
Source: "PrintService\*"; DestDir: "{app}\PrintService"; Flags: ignoreversion recursesubdirs createallsubdirs
; Copia el lanzador principal
Source: "Launcher.exe"; DestDir: "{app}"; Flags: ignoreversion

[Dirs]
; Crea carpeta para certificados (se usa en .env)
Name: "{app}\PrintService\certs"

[Icons]
; Acceso directo en el menú Inicio (grupo PrintService)
Name: "{group}\PrintService"; Filename: "{app}\Launcher.exe"
; Acceso directo en el escritorio del usuario actual (evita problemas con Public\Desktop)
Name: "{userdesktop}\PrintService"; Filename: "{app}\Launcher.exe"

[Run]
; Al finalizar instalación: ejecuta Launcher.exe
; shellexec → usa ShellExecute (respeta manifest de UAC si existe)
; runascurrentuser → se ejecuta en contexto del usuario (hereda elevación del instalador)
Filename: "{app}\Launcher.exe"; \
    Description: "Ejecutar PrintService"; \
    Flags: nowait postinstall skipifsilent shellexec runascurrentuser

[UninstallDelete]
; Elimina archivos de configuración al desinstalar (para limpieza completa)
Type: files; Name: "{app}\PrintService\.env"
Type: files; Name: "{app}\PrintService\config.json"
; Elimina carpeta certs solo si queda vacía
Type: dirifempty; Name: "{app}\PrintService\certs"

; =============================================================================
; Sección de código Pascal (personalización avanzada)
; =============================================================================
[Code]

{ Variables globales para la página de configuración personalizada }
var
  ConfigPage: TWizardPage;
  NetworkRadio, USBRadio: TRadioButton;
  IpLabel, PortLabel, TimeoutLabel: TLabel;
  IpEdit, PortEdit, TimeoutEdit: TEdit;
  UsbInfoLabel: TLabel;
  PaperLabel: TLabel;
  PaperWidthEdit: TEdit;

{ Actualiza visibilidad de campos según el tipo de conexión seleccionado }
procedure UpdateFieldStates;
var
  IsNetwork: Boolean;
begin
  IsNetwork := NetworkRadio.Checked;
  IpLabel.Visible := IsNetwork;
  IpEdit.Visible := IsNetwork;
  PortLabel.Visible := IsNetwork;
  PortEdit.Visible := IsNetwork;
  TimeoutLabel.Visible := IsNetwork;
  TimeoutEdit.Visible := IsNetwork;
  UsbInfoLabel.Visible := not IsNetwork;
end;

{ Eventos de clic en los radio buttons }
procedure NetworkRadioClick(Sender: TObject); begin UpdateFieldStates; end;
procedure USBRadioClick(Sender: TObject); begin UpdateFieldStates; end;

{ Crea la página personalizada de configuración de impresora }
procedure InitializeWizard;
begin
  { Crea página después de wpSelectDir }
  ConfigPage := CreateCustomPage(wpSelectDir,
    'Configuración de la Impresora',
    'Elige el tipo de conexión y completa los parámetros necesarios');

  { Radio button: Conexión por red }
  NetworkRadio := TRadioButton.Create(ConfigPage);
  NetworkRadio.Parent := ConfigPage.Surface;
  NetworkRadio.Caption := 'Conexión por Red (IP)';
  NetworkRadio.Left := 0; NetworkRadio.Top := 0; NetworkRadio.Width := 220;
  NetworkRadio.Checked := True;
  NetworkRadio.OnClick := @NetworkRadioClick;

  { Radio button: Conexión USB }
  USBRadio := TRadioButton.Create(ConfigPage);
  USBRadio.Parent := ConfigPage.Surface;
  USBRadio.Caption := 'Conexión USB';
  USBRadio.Left := 0; USBRadio.Top := 24; USBRadio.Width := 220;
  USBRadio.OnClick := @USBRadioClick;

  { Campos para conexión de red }
  IpLabel := TLabel.Create(ConfigPage);
  IpLabel.Parent := ConfigPage.Surface;
  IpLabel.Caption := 'IP de la impresora:';
  IpLabel.Left := 0; IpLabel.Top := 56;

  IpEdit := TEdit.Create(ConfigPage);
  IpEdit.Parent := ConfigPage.Surface;
  IpEdit.Text := '192.168.0.101';
  IpEdit.Left := 0; IpEdit.Top := 72; IpEdit.Width := 200;

  PortLabel := TLabel.Create(ConfigPage);
  PortLabel.Parent := ConfigPage.Surface;
  PortLabel.Caption := 'Puerto:';
  PortLabel.Left := 0; PortLabel.Top := 100;

  PortEdit := TEdit.Create(ConfigPage);
  PortEdit.Parent := ConfigPage.Surface;
  PortEdit.Text := '9100';
  PortEdit.Left := 0; PortEdit.Top := 116; PortEdit.Width := 100;

  TimeoutLabel := TLabel.Create(ConfigPage);
  TimeoutLabel.Parent := ConfigPage.Surface;
  TimeoutLabel.Caption := 'Timeout (segundos):';
  TimeoutLabel.Left := 120; TimeoutLabel.Top := 100;

  TimeoutEdit := TEdit.Create(ConfigPage);
  TimeoutEdit.Parent := ConfigPage.Surface;
  TimeoutEdit.Text := '10';
  TimeoutEdit.Left := 120; TimeoutEdit.Top := 116; TimeoutEdit.Width := 80;

  { Mensaje informativo para USB }
  UsbInfoLabel := TLabel.Create(ConfigPage);
  UsbInfoLabel.Parent := ConfigPage.Surface;
  UsbInfoLabel.Caption := 'La impresora USB se detectará automáticamente' + #13#10 +
                          'al conectarla. No se requiere configuración adicional.';
  UsbInfoLabel.Left := 0; UsbInfoLabel.Top := 56;
  UsbInfoLabel.Width := 380;
  UsbInfoLabel.Font.Style := [fsBold];
  UsbInfoLabel.Font.Color := clGreen;

  { Campo común: ancho de papel }
  PaperLabel := TLabel.Create(ConfigPage);
  PaperLabel.Parent := ConfigPage.Surface;
  PaperLabel.Caption := 'Ancho del papel (mm):';
  PaperLabel.Left := 0; PaperLabel.Top := 150;

  PaperWidthEdit := TEdit.Create(ConfigPage);
  PaperWidthEdit.Parent := ConfigPage.Surface;
  PaperWidthEdit.Text := '80';
  PaperWidthEdit.Left := 0; PaperWidthEdit.Top := 166; PaperWidthEdit.Width := 80;

  { Inicializa visibilidad }
  UpdateFieldStates;
end;

{ Validación antes de pasar a la siguiente página }
function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if CurPageID = ConfigPage.ID then
  begin
    if NetworkRadio.Checked and (Trim(IpEdit.Text) = '') then
    begin
      MsgBox('La IP de la impresora no puede estar vacía.', mbError, MB_OK);
      Result := False;
    end;
  end;
end;

{ Genera el archivo config.json con los valores del usuario }
procedure GenerateConfigJson;
var
  ConnectionType, NetworkBlock, JsonContent: string;
begin
  if NetworkRadio.Checked then
  begin
    ConnectionType := 'network';
    NetworkBlock :=
      ' "network": {' + #13#10 +
      '   "ip": "' + IpEdit.Text + '",' + #13#10 +
      '   "port": ' + PortEdit.Text + ',' + #13#10 +
      '   "timeout": ' + TimeoutEdit.Text + #13#10 +
      ' },' + #13#10;
  end else
  begin
    ConnectionType := 'usb';
    NetworkBlock := '';
  end;

  JsonContent :=
    '{' + #13#10 +
    '  "connection": "' + ConnectionType + '",' + #13#10 +
    NetworkBlock +
    '  "paperWidth": ' + PaperWidthEdit.Text + ',' + #13#10 +
    '  "encoding": "GB18030",' + #13#10 +
    '  "printerName": "Rongta Network",' + #13#10 +
    '  "ticket": {' + #13#10 +
    '    "workshopLayout": {' + #13#10 +
    '      "totalWidthOverride": null,' + #13#10 +
    '      "textPct": 80' + #13#10 +
    '    },' + #13#10 +
    '    "footer": {' + #13#10 +
    '      "lines": [' + #13#10 +
    '        "- Costo mínimo revisión: $4 (puede variar)",' + #13#10 +
    '        "- En la reparación se utilizan materiales, herramientas y tiempo.",' + #13#10 +
    '        "- Tiempo máximo para retirar el dispositivo: 3 meses."' + #13#10 +
    '      ]' + #13#10 +
    '    },' + #13#10 +
    '    "promotions": {' + #13#10 +
    '      "wednesday": "*** HOY MICA GRATIS ***"' + #13#10 +
    '    },' + #13#10 +
    '    "qrBaseUrl": "https://ordenes.teamcellmania.com/device-query"' + #13#10 +
    '  },' + #13#10 +
    '  "features": {' + #13#10 +
    '    "printAnalysisImage": true,' + #13#10 +
    '    "printQr": true,' + #13#10 +
    '    "printPatternOnCustomerTicket": true,' + #13#10 +
    '    "printWednesdayPromo": true' + #13#10 +
    '  }' + #13#10 +
    '}';

  SaveStringToFile(ExpandConstant('{app}\PrintService\config.json'), JsonContent, False);
end;

{ Genera el archivo .env con variables de entorno del servicio }
procedure GenerateEnvFile;
var
  EnvContent: string;
begin
  EnvContent :=
    'PORT=56789' + #13#10 +
    'SSL_KEYFILE=certs/server.key' + #13#10 +
    'SSL_CERTFILE=certs/server.pem' + #13#10 +
    'RELOAD=False' + #13#10 +
    'GITHUB_TOKEN=ghp_miclave' + #13#10 +           ; ← ¡Cambia esto en producción!
    'UPDATE_INTERVAL_MINUTES=1' + #13#10 +
    'UPDATE_INTERVAL_HOURS=6';

  SaveStringToFile(ExpandConstant('{app}\PrintService\.env'), EnvContent, False);
end;

{ Agrega reglas de firewall para permitir el tráfico del Launcher }
procedure AddFirewallRule;
var
  ResultCode: Integer;
  ExePath: string;
begin
  ExePath := ExpandConstant('{app}\Launcher.exe');

  Exec(ExpandConstant('{sys}\netsh.exe'),
    'advfirewall firewall add rule name="PrintService" dir=in action=allow program="' + ExePath + '" enable=yes profile=any',
    '', SW_HIDE, ewWaitUntilTerminated, ResultCode);

  Exec(ExpandConstant('{sys}\netsh.exe'),
    'advfirewall firewall add rule name="PrintService Out" dir=out action=allow program="' + ExePath + '" enable=yes profile=any',
    '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
end;

{ Elimina las reglas de firewall al desinstalar }
procedure RemoveFirewallRule;
var
  ResultCode: Integer;
begin
  Exec(ExpandConstant('{sys}\netsh.exe'), 'advfirewall firewall delete rule name="PrintService"', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Exec(ExpandConstant('{sys}\netsh.exe'), 'advfirewall firewall delete rule name="PrintService Out"', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
end;

{ Acciones después de instalar los archivos }
procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    GenerateConfigJson;     // Crea config.json con valores del usuario
    GenerateEnvFile;        // Crea .env con puerto, certs y token
    AddFirewallRule;        // Abre puertos en firewall
  end;
end;

{ Acciones durante la desinstalación }
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  ResultCode: Integer;
begin
  if CurUninstallStep = usUninstall then
  begin
    { Mata procesos para evitar archivos en uso }
    Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM Launcher.exe', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM PrintService.exe', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    Sleep(1500);  // Espera un poco para que terminen

    RemoveFirewallRule;   // Limpia reglas de firewall
  end;
end;

; =============================================================================
; Fin del script
; =============================================================================