; OdooPrinter Setup — Inno Setup 6 script.
; Compile: iscc installer\odoo-printer.iss /DVersion=1.0.0
; Requires admin: installs NSSM-managed Windows service + writes
; %ProgramData%\OdooPrinter\config.ini (survives Velopack updates).
;
; Signing (self-signed test):
;   iscc ... /Ssigntool="signtool sign /f C:\certs\test.pfx /p 1234 /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 $f"

#ifndef Version
  #define Version "1.0.0"
#endif

#define MyAppName "OdooPrinter"
#define MyAppId "OdooPrinter"
#define MyServiceName "OdooPrinter"
#define MyBridgeExe "odoo-epos-bridge.exe"

[Setup]
AppId={{3B4A6E1A-7C2D-4E5F-9A1B-0D2C4E6A8B10}
AppName={#MyAppName}
AppVersion={#Version}
AppPublisher=OdooPrinter
DefaultDirName={pf}\{#MyAppName}
DefaultGroupName={#MyAppName}
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\Output
OutputBaseFilename=OdooPrinter-Setup-{#Version}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
; Uncomment after configuring a Sign Tool in Inno IDE / CLI:
;SignTool=signtool

[Files]
; Velopack onedir output (CI copies vpk-packed app here before iscc).
Source: "..\dist\odoo-epos-bridge\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs
Source: "nssm.exe"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist
Source: "..\installer\nssm.exe"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist
Source: "..\installer\reconfigure.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\installer\serviceRegister.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\installer\serviceDelete.bat"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Reconfigurar IP e impresora"; Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\reconfigure.ps1"""; WorkingDir: "{app}"
Name: "{group}\Ver logs"; Filename: "%ProgramData%\OdooPrinter"; WorkingDir: "%ProgramData%\OdooPrinter"
Name: "{group}\Probar bridge (health)"; Filename: "http://127.0.0.1:5000/health"

[Code]
var
  IpPage: TInputQueryWizardPage;
  PrinterPage: TInputQueryWizardPage;

function IsValidIPv4(const S: String): Boolean;
var
  I, Dots, N: Integer;
  Part: String;
begin
  Result := False;
  if (S = '0.0.0.0') or (S = '127.0.0.1') then begin Result := True; Exit; end;
  Dots := 0;
  Part := '';
  for I := 1 to Length(S) do begin
    if S[I] = '.' then begin
      if (Part = '') or (StrToIntDef(Part, -1) > 255) then Exit;
      Part := ''; Dots := Dots + 1;
    end else if (S[I] >= '0') and (S[I] <= '9') then
      Part := Part + S[I]
    else Exit;
  end;
  if (Part = '') or (StrToIntDef(Part, -1) > 255) then Exit;
  N := StrToIntDef(Part, -1);
  Result := (Dots = 3) and (N >= 0);
end;

procedure InitializeWizard;
begin
  IpPage := CreateInputQueryPage(wpSelectDir,
    'Dirección IP del bridge',
    '¿En qué IP debe escuchar el bridge?',
    'Ejemplos: 0.0.0.0 (todas las interfaces, recomendado) o 192.168.18.92. ' +
    'Odoo POS debe poder alcanzarla en el puerto 5000.');
  IpPage.Add('IP:', False);
  IpPage.Values[0] := '0.0.0.0';

  PrinterPage := CreateInputQueryPage(IpPage.ID,
    'Impresora de tickets',
    'Nombre exacto de la impresora en Windows',
    'Debe coincidir con Panel de control > Dispositivos e impresoras ' +
    '(ej. POS-80). Puedes cambiarlo luego desde "Reconfigurar IP e impresora".');
  PrinterPage.Add('Nombre impresora:', False);
  PrinterPage.Values[0] := 'POS-80';
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if CurPageID = IpPage.ID then begin
    if not IsValidIPv4(Trim(IpPage.Values[0])) then begin
      MsgBox('IP no válida. Usa 0.0.0.0 o una IPv4 como 192.168.18.92.',
        mbError, MB_OK);
      Result := False;
    end;
  end;
  if CurPageID = PrinterPage.ID then begin
    if Trim(PrinterPage.Values[0]) = '' then begin
      MsgBox('El nombre de impresora no puede estar vacío.', mbError, MB_OK);
      Result := False;
    end;
  end;
end;

function GetBridgeIP(Param: String): String;
begin
  Result := Trim(IpPage.Values[0]);
end;

function GetPrinterName(Param: String): String;
begin
  Result := Trim(PrinterPage.Values[0]);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ResultCode: Integer;
begin
  // Stop old service BEFORE [Files] so the EXE is not locked (code 5).
  Exec('net.exe', 'stop "{#MyServiceName}"', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Sleep(3000);
  Result := '';
  NeedsRestart := False;
end;

[Run]
Filename: "{app}\serviceRegister.bat"; Parameters: """{code:GetBridgeIP}"" ""{code:GetPrinterName}"""; Flags: runhidden waituntilterminated; StatusMsg: "Instalando servicio OdooPrinter..."

[UninstallRun]
Filename: "{app}\serviceDelete.bat"; Flags: runhidden waituntilterminated
