; cm2xl Inno Setup 安装脚本
; 需先运行 ..\build.bat 完成 PyInstaller 打包
; 编译: iscc installer\cm2xl.iss
; 输出: installer\output\cm2xl_Setup_1.0.5.exe

#define SourceDir ".."
#define MyAppName "cm2xl"
#define MyAppVersion "1.0.5"
#define MyAppPublisher "cm2xl"
#define MyAppExeName "cm2xl.exe"
; 旧版 CMMFiller GUID 与 cm2xl 不同，用于残留检测（Pascal 里拼接花括号，避免 ISS 常量解析）
#define OldCmmFillerGuid "A1B2C3D4-E5F6-7890-ABCD-EF1234567890"

[Setup]
; {{ 转义为 { ，行末 } 关闭 GUID。勿与 OldCmmFillerGuid 相同，否则重装会误报旧版。
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567891}
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
SetupIconFile=..\cm2xl.ico
LicenseFile=

[Languages]
; Inno Setup 6 默认不带 ChineseSimplified.isl（需额外语言包），用 english 保证能编译。
; 下方 Tasks / MsgBox 文案仍为中文。
Name: "english"; MessagesFile: "compiler:Default.isl"

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

[Code]
function HasUninstallKey(const UninstallId: string): Boolean;
var
  UninstallCmd: string;
begin
  Result :=
    RegQueryStringValue(HKLM, 'Software\Microsoft\Windows\CurrentVersion\Uninstall\' + UninstallId + '_is1', 'UninstallString', UninstallCmd)
    or RegQueryStringValue(HKLM, 'Software\Microsoft\Windows\CurrentVersion\Uninstall\' + UninstallId, 'UninstallString', UninstallCmd);
end;

function InitializeSetup(): Boolean;
begin
  // 只检测旧版 CMMFiller（不同 AppId）。cm2xl 自身重装由同一 AppId 走 Inno 升级，不弹此窗。
  if HasUninstallKey('{' + '{#OldCmmFillerGuid}' + '}') then
  begin
    if MsgBox('检测到旧版 CMMFiller 已安装。' + #13#10 +
              '安装 cm2xl 前建议先卸载旧版，避免路径冲突。' + #13#10 + #13#10 +
              '是否继续安装？', mbConfirmation, MB_YESNO) = IDNO then
    begin
      Result := False;
      exit;
    end;
  end;
  Result := True;
end;
