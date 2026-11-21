; EmoDict installer (Inno Setup). Build:
;   ISCC.exe installer.iss            (expects dist\EmoDict-CPU to exist)
; Version is passed with /DMyVersion=x.y.z or defaults below.
#ifndef MyVersion
#define MyVersion "0.2.0"
#endif

[Setup]
AppId={{357E3E82-E2CB-4CAB-B559-019803A90F40}
AppName=EmoDict
AppVersion={#MyVersion}
AppPublisher=Ashish Mishra
AppPublisherURL=https://github.com/OxAsh11/emodict
AppSupportURL=https://github.com/OxAsh11/emodict/issues
DefaultDirName={autopf}\EmoDict
DefaultGroupName=EmoDict
UninstallDisplayIcon={app}\EmoDict.exe
OutputBaseFilename=EmoDict-Setup-{#MyVersion}
OutputDir=installer-output
Compression=lzma2
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
; Unsigned beta: no signing. SmartScreen may warn on the downloader.

[Files]
Source: "dist\EmoDict\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\EmoDict"; Filename: "{app}\EmoDict.exe"
Name: "{group}\Uninstall EmoDict"; Filename: "{uninstallexe}"
Name: "{autodesktop}\EmoDict"; Filename: "{app}\EmoDict.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; Flags: unchecked
Name: "autostart"; Description: "Start EmoDict when Windows starts"

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; \
    ValueType: string; ValueName: "EmoDict"; \
    ValueData: """{app}\EmoDict.exe"""; Flags: uninsdeletevalue; Tasks: autostart

[Run]
Filename: "{app}\EmoDict.exe"; Description: "Launch EmoDict now"; \
    Flags: nowait postinstall skipifsilent
