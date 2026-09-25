; SmartGestureOS — Inno Setup Script
; Dynamic version injected at build time via iscc /DAppVersion=x.y.z
; Requires: Inno Setup 6+ (https://jrsoftware.org/isinfo.php)
; Build: iscc /DAppVersion=0.9.0 packaging\windows\SmartGestureOS.iss

#ifndef AppVersion
  #define AppVersion "0.9.0-dev"
#endif

[Setup]
AppId={{8A3F2C1D-4B7E-4D9F-A8C0-1234567890AB}
AppName=SmartGestureOS
AppVersion={#AppVersion}
AppVerName=SmartGestureOS {#AppVersion}
AppPublisher=Sarvagya Birla
AppPublisherURL=https://github.com/Sarvagyabirla/SmartGestureOS
AppSupportURL=https://github.com/Sarvagyabirla/SmartGestureOS/issues
AppUpdatesURL=https://github.com/Sarvagyabirla/SmartGestureOS/releases
DefaultDirName={autopf}\SmartGestureOS
DefaultGroupName=SmartGestureOS
AllowNoIcons=yes
; ── Output — canonical path: dist\release\ (matches GitHub Actions artifact glob) ──
OutputDir=..\..\dist\release
OutputBaseFilename=SmartGestureOS-Setup-v{#AppVersion}
Compression=lzma2/ultra64
SolidCompression=yes
; Architecture
ArchitecturesInstallIn64BitMode=x64compatible
ArchitecturesAllowed=x64compatible
; Windows minimum version (Win 10)
MinVersion=10.0
; Privacy: no internet connection required
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
; Misc
WizardStyle=modern
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\SmartGestureOS.exe

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "launchafterinstall"; Description: "Launch SmartGestureOS after installation"; GroupDescription: "After installation:"; Flags: unchecked

[Files]
; Include the entire ONEDIR output — the _internal folder and all its contents
Source: "..\..\dist\SmartGestureOS\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\SmartGestureOS"; Filename: "{app}\SmartGestureOS.exe"; Comment: "Real-Time Hand Gesture Control System"
Name: "{group}\Uninstall SmartGestureOS"; Filename: "{uninstallexe}"
Name: "{commondesktop}\SmartGestureOS"; Filename: "{app}\SmartGestureOS.exe"; Tasks: desktopicon; Comment: "Real-Time Hand Gesture Control System"

[Run]
Filename: "{app}\SmartGestureOS.exe"; Description: "{cm:LaunchProgram,SmartGestureOS}"; Flags: nowait postinstall skipifsilent; Tasks: launchafterinstall

[UninstallDelete]
; Remove user log files from LocalAppData on uninstall (optional — disabled by default for safety)
; Type: filesandordirs; Name: "{localappdata}\SmartGesture"
