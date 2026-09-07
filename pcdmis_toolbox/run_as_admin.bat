@echo off
chcp 65001 >nul
setlocal

REM 以管理员权限启动 cm2xl，供 PC-DMIS 以管理员权限运行时使用。
REM 该启动器随打包目录分发，用于启动同目录下的 cm2xl.exe。
set "APP=%~dp0cm2xl.exe"
if not exist "%APP%" (
    echo [ERROR] 未找到 %APP%
    echo 请先运行 build.bat 生成 dist\cm2xl\cm2xl.exe。
    pause
    exit /b 1
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command ^
  "Start-Process -FilePath '%APP%' -Verb RunAs"
if errorlevel 1 (
    echo [ERROR] 无法请求管理员权限。
    pause
    exit /b 1
)
endlocal
