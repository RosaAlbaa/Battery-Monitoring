; Battery Monitoring installer script (Inno Setup 6)
; Build: ISCC.exe /DAppVersion=0.4.0 installer\battery_monitoring.iss
; Requires dist\BatteryMonitoring\ from PyInstaller (--onedir) first.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#define AppName "Battery Monitoring"
#define AppExe "BatteryMonitoring.exe"

[Setup]
AppId={{C6E1B7A4-2F3D-4B8E-9A61-7D5F0E2C8B13}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=RosaAlbaa
AppPublisherURL=https://github.com/RosaAlbaa/Battery-Monitoring
AppSupportURL=https://github.com/RosaAlbaa/Battery-Monitoring/issues
AppUpdatesURL=https://github.com/RosaAlbaa/Battery-Monitoring/releases
VersionInfoVersion={#AppVersion}
DefaultDirName={localappdata}\Programs\BatteryMonitoring
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
DisableDirPage=auto
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist
OutputBaseFilename=BatteryMonitoring-Setup-{#AppVersion}
SetupIconFile=..\assets\battery_monitoring.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
AppMutex=BatteryMonitoring.SingleInstance
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "turkish"; MessagesFile: "compiler:Languages\Turkish.isl"
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[CustomMessages]
english.AutoStart=Start automatically with Windows
turkish.AutoStart=Windows açılınca otomatik başlat
spanish.AutoStart=Iniciar automáticamente con Windows

[Tasks]
Name: "autostart"; Description: "{cm:AutoStart}"

[Files]
Source: "..\dist\BatteryMonitoring\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
Type: filesandordirs; Name: "{app}\_internal"

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "BatteryMonitoring"; ValueData: """{app}\{#AppExe}"""; Flags: uninsdeletevalue; Tasks: autostart

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
    RegDeleteValue(HKEY_CURRENT_USER, 'Software\Microsoft\Windows\CurrentVersion\Run', 'BatteryMonitoring');
end;
