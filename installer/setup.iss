; CCI請求書・宛名ラベル発行システム Inno Setup スクリプト
#ifndef AppVersion
#define AppVersion "0.0.0"
#endif

[Setup]
AppName=CCI請求書・ラベル発行システム
AppVersion={#AppVersion}
AppPublisher=mozu93
AppPublisherURL=https://github.com/mozu93/cci-billing-label
AppSupportURL=https://github.com/mozu93/cci-billing-label/issues
DefaultDirName={localappdata}\CCIBillingLabel
DefaultGroupName=CCI請求書・ラベル発行システム
DisableDirPage=yes
OutputDir={#SourcePath}\..\installer_output
OutputBaseFilename=CCIBillingLabel_Setup_{#AppVersion}
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
Source: "{#SourcePath}\..\dist\CCIBillingLabel\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\CCI請求書・ラベル発行システム"; Filename: "{app}\CCIBillingLabel.exe"
Name: "{group}\アンインストール"; Filename: "{uninstallexe}"
Name: "{autodesktop}\CCI請求書・ラベル発行システム"; Filename: "{app}\CCIBillingLabel.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\CCIBillingLabel.exe"; Description: "CCI請求書・ラベル発行システムを起動する"; Flags: nowait postinstall skipifsilent
