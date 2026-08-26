@echo off
chcp 65001 >nul
echo 启动 CMMFiller GUI ...
cd /d "%~dp0dist\CMMFiller"
if not exist CMMFiller.exe (
    echo.
    echo 未找到 dist\CMMFiller\CMMFiller.exe
    echo 请先运行 build.bat 完成打包
    echo.
    pause
    exit /b 1
)
start "" CMMFiller.exe --gui
