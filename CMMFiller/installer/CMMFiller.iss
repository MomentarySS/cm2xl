; CMMFiller Inno Setup 安装脚本
; 需先运行 build.bat 生成 dist\CMMFiller\
; 编译: iscc installer\CMMFiller.iss

#define MyAppName "CMMFiller"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "CMMFiller"
#define MyAppExeName "CMMFiller.exe"

[Setup]
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=..\installer\output
OutputBaseFilename=CMMFiller_Setup_{#MyAppVersion}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#MyAppExeName}
SetupIconFile=
LicenseFile=
; 使用说明 PDF 安装到 docs 子目录，开始菜单可打开

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加选项:"; Flags: checkedonce

[Files]
Source: "..\dist\CMMFiller\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\docs\CMMFiller_安装与使用说明.pdf"; DestDir: "{app}\docs"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Parameters: "--gui"; WorkingDir: "{app}"
Name: "{group}\使用说明"; Filename: "{app}\docs\CMMFiller_安装与使用说明.pdf"
Name: "{group}\卸载 {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Parameters: "--gui"; Tasks: desktopicon; WorkingDir: "{app}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Parameters: "--gui"; Description: "启动 {#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{localappdata}\CMMFiller\cache"

[Code]
function InitializeSetup(): Boolean;
begin
  if not FileExists(ExpandConstant('{src}\..\dist\CMMFiller\CMMFiller.exe')) then
  begin
    MsgBox('未找到 dist\CMMFiller\CMMFiller.exe，请先运行 build.bat 完成打包。', mbError, MB_OK);
    Result := False;
  end
  else
    Result := True;
end;
