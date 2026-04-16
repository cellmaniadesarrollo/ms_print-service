; =============================================================================
; Script de instalacion Inno Setup para PrintService
; =============================================================================
; Autor:       Christian
; Version:     1.2 - Marzo 2026
; Correcciones:
;   - SaveStringToFile: False (overwrite) en vez de True (append)
;   - Sin BOM: el JSON generado es ASCII puro (UTF-8 valido sin BOM)
;   - Sin tildes en los strings del JSON para evitar encoding ANSI vs UTF-8
; =============================================================================

[Setup]
AppName=PrintService
AppVersion=1.2
DefaultDirName={pf}\PrintService
DefaultGroupName=PrintService
OutputDir=Output
OutputBaseFilename=Instalador_PrintService
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin

[Files]
Source: "PrintService\*"; DestDir: "{app}\PrintService"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "Launcher.exe"; DestDir: "{app}"; Flags: ignoreversion

[Dirs]
Name: "{app}\PrintService\certs"

[Icons]
Name: "{group}\PrintService"; Filename: "{app}\Launcher.exe"
Name: "{userdesktop}\PrintService"; Filename: "{app}\Launcher.exe"

[Run]
Filename: "{app}\Launcher.exe"; \
    Description: "Ejecutar PrintService"; \
    Flags: nowait postinstall skipifsilent shellexec runascurrentuser
Filename: "{sys}\schtasks.exe"; \
    Parameters: "/Create /F /RL HIGHEST /SC ONLOGON /TN ""PrintService Launcher"" /TR ""\""{app}\Launcher.exe\"""" /DELAY 0000:10"; \
    Description: "Iniciar PrintService automaticamente al login"; \
    Flags: runhidden nowait skipifsilent; \
    StatusMsg: "Configurando inicio automatico con privilegios elevados...";

[UninstallDelete]
Type: files; Name: "{app}\PrintService\.env"
Type: files; Name: "{app}\PrintService\config.json"
Type: dirifempty; Name: "{app}\PrintService\certs"

[Code]

var
  ConfigPage: TWizardPage;
  NetworkRadio, USBRadio: TRadioButton;
  IpLabel, PortLabel, TimeoutLabel: TLabel;
  IpEdit, PortEdit, TimeoutEdit: TEdit;
  UsbInfoLabel: TLabel;
  PaperLabel: TLabel;
  PaperWidthEdit: TEdit;

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

procedure NetworkRadioClick(Sender: TObject); begin UpdateFieldStates; end;
procedure USBRadioClick(Sender: TObject); begin UpdateFieldStates; end;

procedure InitializeWizard;
begin
  ConfigPage := CreateCustomPage(wpSelectDir,
    'Configuracion de la Impresora',
    'Elige el tipo de conexion y completa los parametros necesarios');

  NetworkRadio := TRadioButton.Create(ConfigPage);
  NetworkRadio.Parent := ConfigPage.Surface;
  NetworkRadio.Caption := 'Conexion por Red (IP)';
  NetworkRadio.Left := 0; NetworkRadio.Top := 0; NetworkRadio.Width := 220;
  NetworkRadio.Checked := True;
  NetworkRadio.OnClick := @NetworkRadioClick;

  USBRadio := TRadioButton.Create(ConfigPage);
  USBRadio.Parent := ConfigPage.Surface;
  USBRadio.Caption := 'Conexion USB';
  USBRadio.Left := 0; USBRadio.Top := 24; USBRadio.Width := 220;
  USBRadio.OnClick := @USBRadioClick;

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

  UsbInfoLabel := TLabel.Create(ConfigPage);
  UsbInfoLabel.Parent := ConfigPage.Surface;
  UsbInfoLabel.Caption := 'La impresora USB se detectara automaticamente' + #13#10 +
                          'al conectarla. No se requiere configuracion adicional.';
  UsbInfoLabel.Left := 0; UsbInfoLabel.Top := 56;
  UsbInfoLabel.Width := 380;
  UsbInfoLabel.Font.Style := [fsBold];
  UsbInfoLabel.Font.Color := clGreen;

  PaperLabel := TLabel.Create(ConfigPage);
  PaperLabel.Parent := ConfigPage.Surface;
  PaperLabel.Caption := 'Ancho del papel (mm):';
  PaperLabel.Left := 0; PaperLabel.Top := 150;

  PaperWidthEdit := TEdit.Create(ConfigPage);
  PaperWidthEdit.Parent := ConfigPage.Surface;
  PaperWidthEdit.Text := '80';
  PaperWidthEdit.Left := 0; PaperWidthEdit.Top := 166; PaperWidthEdit.Width := 80;

  UpdateFieldStates;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if CurPageID = ConfigPage.ID then
  begin
    if NetworkRadio.Checked and (Trim(IpEdit.Text) = '') then
    begin
      MsgBox('La IP de la impresora no puede estar vacia.', mbError, MB_OK);
      Result := False;
    end;
  end;
end;

procedure GenerateConfigJson;
var
  ConnectionType, NetworkBlock, JsonContent: string;
begin
  if NetworkRadio.Checked then
  begin
    ConnectionType := 'network';
    NetworkBlock :=
      '  "network": {' + #13#10 +
      '    "ip": "' + IpEdit.Text + '",' + #13#10 +
      '    "port": ' + PortEdit.Text + ',' + #13#10 +
      '    "timeout": ' + TimeoutEdit.Text + #13#10 +
      '  },' + #13#10;
  end else
  begin
    ConnectionType := 'usb';
    NetworkBlock := '';
  end;

  { IMPORTANTE: estos strings NO tienen tildes ni caracteres especiales      }
  { para que SaveStringToFile los guarde en ASCII puro (= UTF-8 valido).     }
  { Python los leeera con encoding='utf-8' sin ningun problema.              }
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
    '        "- Costo minimo revision: $4 (puede variar)",' + #13#10 +
    '        "- En la reparacion se utilizan materiales, herramientas y tiempo.",' + #13#10 +
    '        "- Tiempo maximo para retirar el dispositivo: 3 meses."' + #13#10 +
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

  { False = sobrescribir (no append). Sin BOM: ASCII puro es UTF-8 valido. }
  SaveStringToFile(
    ExpandConstant('{app}\PrintService\config.json'),
    JsonContent,
    False
  );
end;

procedure GenerateEnvFile;
var
  EnvContent: string;
begin
  { El .env tampoco tiene caracteres especiales: ASCII puro = UTF-8 valido. }
  EnvContent :=
    'PORT=56789' + #13#10 +
    'SSL_KEYFILE=certs/server.key' + #13#10 +
    'SSL_CERTFILE=certs/server.pem' + #13#10 +
    'RELOAD=False' + #13#10 +
    'GITHUB_TOKEN=ghp_3U' + #13#10 +
    'UPDATE_INTERVAL_MINUTES=1' + #13#10 +
    'UPDATE_INTERVAL_HOURS=6';

  SaveStringToFile(
    ExpandConstant('{app}\PrintService\.env'),
    EnvContent,
    False
  );
end;

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

procedure RemoveFirewallRule;
var
  ResultCode: Integer;
begin
  Exec(ExpandConstant('{sys}\netsh.exe'),
    'advfirewall firewall delete rule name="PrintService"',
    '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Exec(ExpandConstant('{sys}\netsh.exe'),
    'advfirewall firewall delete rule name="PrintService Out"',
    '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    GenerateConfigJson;
    GenerateEnvFile;
    AddFirewallRule;
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  ResultCode: Integer;
begin
  if CurUninstallStep = usUninstall then
  begin
    Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM Launcher.exe', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM PrintService.exe', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    Sleep(1500);
    RemoveFirewallRule;
  end;
end;
