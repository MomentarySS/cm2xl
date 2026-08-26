@echo off
chcp 65001 >nul
echo ========================================
echo   CMMFiller 安装包构建
echo ========================================
echo.

cd /d "%~dp0"

REM 1. 打包程序
if not exist "dist\CMMFiller\CMMFiller.exe" (
    echo [1/3] 未找到 dist\CMMFiller，开始 PyInstaller 打包...
    call build.bat
    if errorlevel 1 exit /b 1
) else (
    echo [1/3] 已存在 dist\CMMFiller\CMMFiller.exe，跳过打包
    echo       如需重新打包，请先删除 dist 目录再运行
)

REM 2. 检查使用说明 PDF
if not exist "docs\CMMFiller_安装与使用说明.pdf" (
    echo [2/3] 生成使用说明 PDF...
    python docs\generate_user_guide.py
) else (
    echo [2/3] 使用说明 PDF 已存在
)

REM 3. Inno Setup 编译
echo.
echo [3/3] 编译安装包...
set ISCC=
if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" set ISCC=C:\Program Files (x86)\Inno Setup 6\ISCC.exe
if exist "C:\Program Files\Inno Setup 6\ISCC.exe" set ISCC=C:\Program Files\Inno Setup 6\ISCC.exe

if "%ISCC%"=="" (
    echo.
    echo 未找到 Inno Setup 6，请先安装:
    echo   https://jrsoftware.org/isdl.php
    echo.
    echo 安装后重新运行 build_installer.bat
    echo 或手动执行: iscc installer\CMMFiller.iss
    pause
    exit /b 1
)

"%ISCC%" installer\CMMFiller.iss

if exist "installer\output\CMMFiller_Setup_1.0.0.exe" (
    echo.
    echo ========================================
    echo   安装包构建成功！
    echo   输出: installer\output\CMMFiller_Setup_1.0.0.exe
    echo ========================================
) else (
    echo.
    echo 安装包构建失败，请检查上方错误信息
)

echo.
pause
