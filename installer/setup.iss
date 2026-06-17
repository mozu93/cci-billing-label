; CCI請求書システム Inno Setup スクリプト
#ifndef AppVersion
#define AppVersion "0.0.0"
#endif

[Setup]
AppName=CCI請求書システム
AppVersion={#AppVersion}
AppPublisher=mozu93
AppPublisherURL=https://github.com/mozu93/cci-billing
AppSupportURL=https://github.com/mozu93/cci-billing/issues
DefaultDirName={localappdata}\CCIBilling
DefaultGroupName=CCI請求書システム
DisableDirPage=yes
OutputDir={#SourcePath}\..\installer_output
OutputBaseFilename=CCIBilling_Setup_{#AppVersion}
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
SetupIconFile={#SourcePath}\..\assets\app_icon.ico

[Languages]
Name: "japanese"; MessagesFile: "compiler:Languages\Japanese.isl"

[Tasks]
Name: "desktopicon"; Description: "デスクトップにショートカットを作成"; GroupDescription: "追加タスク:"

[Files]
Source: "{#SourcePath}\..\dist\CCIBilling\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\CCI請求書システム"; Filename: "{app}\CCIBilling.exe"
Name: "{group}\アンインストール"; Filename: "{uninstallexe}"
Name: "{autodesktop}\CCI請求書システム"; Filename: "{app}\CCIBilling.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\CCIBilling.exe"; Description: "CCI請求書システムを起動する"; Flags: nowait postinstall skipifsilent
