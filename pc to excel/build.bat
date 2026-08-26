@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ========================================
echo  PCDMIS 按需 Excel 报告 — PyInstaller 打包
echo ========================================

python -m pip install -r requirements.txt -q
python -m PyInstaller build.spec --noconfirm

if not exist "dist\PCDMIS按需Excel报告.exe" (
    echo [错误] 未生成 dist\PCDMIS按需Excel报告.exe
    exit /b 1
)

copy /Y run_as_admin.bat dist\ >nul 2>&1
copy /Y 使用说明.txt dist\ >nul 2>&1
copy /Y 用户手册.md dist\ >nul 2>&1
echo.
echo 完成: dist\PCDMIS按需Excel报告.exe
pause
