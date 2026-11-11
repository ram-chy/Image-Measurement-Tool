; ============================================================
;  Inno Setup Script — Image Measurement & Report Tool
;  Compile with:  ISCC.exe ImageMeasureTool_Setup.iss
;  (build the exe first:  pyinstaller ImageMeasureTool.spec)
; ============================================================

#define AppName      "Image Measurement Tool"
#define AppVersion   "1.5.1"
#define AppPublisher "Image Tool"
#define AppExeName   "ImageMeasureTool.exe"

[Setup]
AppId={{6A3F2B1C-9D4E-4A7B-8C2F-1E5D3A9B7C4F}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL=
AppSupportURL=
AppUpdatesURL=
VersionInfoVersion={#AppVersion}
VersionInfoCompany={#AppPublisher}
VersionInfoCopyright=© 2026 Ram Chowdhury  +91 9123754092
VersionInfoDescription={#AppName} Setup
VersionInfoProductName={#AppName}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
AllowNoIcons=no
DisableProgramGroupPage=auto
OutputDir={#SourcePath}\installer
OutputBaseFilename=ImageMeasureTool_Setup_v{#AppVersion}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
WizardSizePercent=120
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes

; Installer appearance
SetupIconFile={#SourcePath}\assets\app.ico
UninstallDisplayIcon={app}\{#AppExeName}
UninstallDisplayName={#AppName}

; Minimum Windows version: Windows 10
MinVersion=10.0

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon";  Description: "Create a &Desktop shortcut";   GroupDescription: "Additional icons:"; Flags: unchecked
Name: "startmenuicon"; Description: "Create a &Start Menu shortcut"; GroupDescription: "Additional icons:"

[Files]
; Main executable
Source: "{#SourcePath}\dist\{#AppExeName}"; DestDir: "{app}"; Flags: ignoreversion

; README / licence (optional — create these if needed)
; Source: "{#SourcePath}\README.txt"; DestDir: "{app}"; Flags: ignoreversion isreadme

[Icons]
; Start Menu
Name: "{group}\{#AppName}";            Filename: "{app}\{#AppExeName}"; Tasks: startmenuicon
Name: "{group}\Uninstall {#AppName}";  Filename: "{uninstallexe}";        Tasks: startmenuicon

; Desktop (optional task)
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
; Offer to launch after install (as the logged-in user, not the elevated admin)
Filename: "{app}\{#AppExeName}"; \
  Description: "Launch {#AppName} now"; \
  Flags: nowait postinstall skipifsilent runasoriginaluser

[UninstallDelete]
; The database lives in %LOCALAPPDATA%\ImageMeasurementTool and is kept
; on uninstall so history is preserved. Uncomment to delete it:
; Type: files; Name: "{localappdata}\ImageMeasurementTool\image_reports.db"

[Messages]
; Custom finish message
FinishedLabel=Setup has finished installing [name] on your computer.%n%nThe application can be launched from the Start Menu or Desktop shortcut.%n%nYour measurement history is stored under your user profile in AppData\Local\ImageMeasurementTool (kept on uninstall).%n%n© 2026 Ram Chowdhury  +91 9123754092
