@echo off
chcp 65001 >nul
echo ========================================
echo   cm2xl — Installer Build
echo ========================================
echo.

cd /d "%~dp0"

REM ── 1. PyInstaller 打包（未完成时执行）─────────────────────────────
if not exist "dist\cm2xl\cm2xl.exe" (
    echo [1/3] 开始 PyInstaller 打包（请耐心等待 10-20 分钟）...
    call build.bat
    if errorlevel 1 exit /b 1
) else (
    echo [1/3] dist\cm2xl\cm2xl.exe 已存在，跳过打包
    echo       如需重新打包，请先删除 dist 目录
)

REM ── 2. Inno Setup 编译 ────────────────────────────────────────────
echo.
echo [2/3] 编译 Inno Setup 安装包...

set ISCC=
if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" set ISCC=C:\Program Files (x86)\Inno Setup 6\ISCC.exe
if exist "C:\Program Files\Inno Setup 6\ISCC.exe" set ISCC=C:\Program Files\Inno Setup 6\ISCC.exe
if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe

if "%ISCC%"=="" (
    echo.
    echo [ERROR] 未找到 Inno Setup 6，请先安装:
    echo          https://jrsoftware.org/isdl.php
    echo.
    echo          安装后重新运行 build_installer.bat
    echo          或手动执行: iscc installer\cm2xl.iss
    pause
    exit /b 1
)

"%ISCC%" installer\cm2xl.iss

REM ── 3. 检查输出 ───────────────────────────────────────────────────
if exist "installer\output\cm2xl_Setup_1.0.4.exe" (
    echo.
    echo ========================================
    echo   安装包构建成功！
    echo   输出: installer\output\cm2xl_Setup_1.0.4.exe
    echo ========================================
) else (
    echo.
    echo [ERROR] 安装包构建失败，请检查上方错误信息
)
echo.
pause
