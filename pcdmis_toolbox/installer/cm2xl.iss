; cm2xl Inno Setup 安装脚本
; 需先运行 ..\build.bat 完成 PyInstaller 打包
; 编译: iscc installer\cm2xl.iss
; 输出: installer\output\cm2xl_Setup_1.0.0.exe

#define SourceDir ".."
#define MyAppName "cm2xl"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "cm2xl"
#define MyAppExeName "cm2xl.exe"
#define MyAppId "{{A1B2C3D4-E5F6-7890-ABCD-EF1234567891}"

[Setup]
AppId={#MyAppId}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
; 默认安装目录（admin 模式）
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
; 输出到本目录的 output 子目录
OutputDir=output
OutputBaseFilename=cm2xl_Setup_{#MyAppVersion}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
; cm2xl 和 PCDMIS 都需要管理员权限
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#MyAppExeName}
SetupIconFile=
LicenseFile=

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "chinesesimplified"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加选项:"; Flags: checkedonce

[Files]
; 整个打包目录（PyInstaller COLLECT 输出）
Source: "{#SourceDir}\dist\cm2xl\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{group}\卸载 {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon; WorkingDir: "{app}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "启动 {#MyAppName}"; Flags: nowait postinstall skipifsilent
