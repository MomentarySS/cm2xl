@echo off
chcp 65001 >nul
set "EXE=%~dp0PCDMIS按需Excel报告.exe"
set "ROOT=%~dp0"

echo ========================================
echo  PCDMIS 按需 Excel 报告 - 管理员模式
echo ========================================
echo 仅当 PCDMIS 本身也是管理员启动时才需要本脚本
echo.

if exist "%EXE%" (
    powershell -NoProfile -Command "Start-Process -FilePath '%EXE%' -WorkingDirectory '%ROOT%' -Verb RunAs"
    exit /b 0
)

echo 未找到 exe，改用源码: python main.py
cd /d "%~dp0"
python main.py
pause
