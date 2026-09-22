#ifndef AppVersion
  #define AppVersion "16.0.0"
#endif
#ifndef VersionInfoVersion
  #define VersionInfoVersion "16.0.0.0"
#endif
#ifndef PayloadDir
  #error PayloadDir must point to the staged application payload
#endif
#ifndef OutputDir
  #define OutputDir "..\..\dist\windows"
#endif

#define AppName "Skeleton"
#define AppPublisher "Apeloff1"
#define AppExeName "Skeleton.exe"
#define AppId "{{CEFEA0CB-7D8A-4D95-B068-FAF2460D76D6}"

[Setup]
AppId={#AppId}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
VersionInfoVersion={#VersionInfoVersion}
DefaultDirName={localappdata}\Programs\Skeleton
DefaultGroupName=Skeleton
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
OutputDir={#OutputDir}
OutputBaseFilename=Skeleton-Setup-{#AppVersion}-windows-x64
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
SetupLogging=yes
CloseApplications=yes
RestartApplications=no
UsePreviousAppDir=yes
Uninstallable=yes
UninstallDisplayName=Skeleton
UninstallDisplayIcon={app}\{#AppExeName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
Source: "{#PayloadDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Skeleton"; Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"
Name: "{group}\Repair Skeleton"; Filename: "{app}\{#AppExeName}"; Parameters: "--repair"; WorkingDir: "{app}"
Name: "{userdesktop}\Skeleton"; Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Launch Skeleton setup and runtime"; WorkingDir: "{app}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{app}\{#AppExeName}"; Parameters: "--stop --quiet"; WorkingDir: "{app}"; RunOnceId: "StopSkeleton"; Flags: runhidden skipifdoesntexist

[UninstallDelete]
Type: files; Name: "{app}\.env"
