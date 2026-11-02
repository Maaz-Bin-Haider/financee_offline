; Native Windows x64 development installer. Build via scripts/build_windows_installer.py.
#ifndef StageDir
  #error StageDir is required
#endif
#ifndef OutputDir
  #error OutputDir is required
#endif
#ifndef ProgramIdentity
  #error ProgramIdentity is required
#endif
#define SetupVersion "0.8.0-phase8"
[Setup]
AppId={{1398C490-5A0B-4F14-9415-92BFC1B1DD88}
AppName=Financee Offline 0.8 Development
AppVersion={#SetupVersion}
AppPublisher=Financee
DefaultDirName={localappdata}\Programs\Financee Offline 0.8 Development
DefaultGroupName=Financee Offline 0.8 Development
PrivilegesRequired=lowest
ArchitecturesAllowed=x64os
ArchitecturesInstallIn64BitMode=x64os
MinVersion=10.0.19045
OutputDir={#OutputDir}
OutputBaseFilename=Financee-Offline-Windows-x64-Development-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
DisableProgramGroupPage=yes
DisableDirPage=yes
CloseApplications=no
RestartApplications=no
AppMutex=Local\FinanceeOfflineProgram
SetupMutex=Local\FinanceeOfflineInstaller
UninstallDisplayIcon={app}\launcher\Financee Offline.exe
InfoBeforeFile=development-notice.txt
[Tasks]
Name: desktopicon; Description: "Create a Financee Offline desktop shortcut"; Flags: checkedonce
[Files]
Source: "{#StageDir}\Financee Offline\*"; DestDir: "{app}\launcher"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#StageDir}\Financee Offline Setup\*"; DestDir: "{app}\setup"; Flags: ignoreversion recursesubdirs createallsubdirs
[Icons]
Name: "{userprograms}\Financee Offline 0.8 Development\Financee Offline"; Filename: "{app}\launcher\Financee Offline.exe"
Name: "{userprograms}\Financee Offline 0.8 Development\Financee Offline Setup"; Filename: "{app}\setup\Financee Offline Setup.exe"
Name: "{userdesktop}\Financee Offline 0.8 Development"; Filename: "{app}\launcher\Financee Offline.exe"; Tasks: desktopicon
[Registry]
Root: HKCU; Subkey: "Software\Financee\Offline08Development"; ValueType: string; ValueName: InstallerVersion; ValueData: "{#SetupVersion}"; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Financee\Offline08Development"; ValueType: string; ValueName: ProgramIdentity; ValueData: "{#ProgramIdentity}"; Flags: uninsdeletevalue
[Run]
Filename: "{app}\setup\Financee Offline Setup.exe"; Description: "Check prerequisites and finish Financee setup"; Flags: postinstall nowait skipifsilent
[Code]
function InitializeSetup(): Boolean;
var Previous, Identity: String;
begin
  Result := True;
  if RegQueryStringValue(HKCU, 'Software\Financee\Offline08Development', 'InstallerVersion', Previous) then
    if (Previous <> '{#SetupVersion}') or
       (not RegQueryStringValue(HKCU, 'Software\Financee\Offline08Development', 'ProgramIdentity', Identity)) or
       (Identity <> '{#ProgramIdentity}') then begin
      MsgBox('A different Financee release is installed. Use its data-preserving upgrade workflow. Existing program files and business data were preserved.', mbError, MB_OK);
      Result := False;
    end;
end;
function InitializeUninstall(): Boolean;
var ExitCode: Integer;
begin
  Result := False;
  if MsgBox('Uninstall Financee program files? Your customer folder, backups, Docker/WSL runtime and data volumes will be retained. Financee must first verify and stop only its own services.', mbConfirmation, MB_YESNO) <> IDYES then exit;
  if not Exec(ExpandConstant('{app}\setup\Financee Offline Setup.exe'), '--prepare-uninstall', '', SW_HIDE, ewWaitUntilTerminated, ExitCode) then begin
    MsgBox('Could not verify the Financee installation for removal. Repair this same release, then retry. Data was retained.', mbError, MB_OK);
    exit;
  end;
  if ExitCode <> 0 then begin
    MsgBox('Financee could not verify a safe stop. Complete the reported repair/runtime steps, then retry uninstall. Program files and customer data were retained.', mbError, MB_OK);
    exit;
  end;
  Result := True;
end;
