@echo off
chcp 65001 >nul
echo ========================================
echo   PCDMIS Toolbox 2.0 — Build Tool
echo ========================================
echo.

cd /d "%~dp0"

REM ── 检查 CMMFiller OCR 模型（如果存在）────────────────────────────
if exist "..\CMMFiller\models\paddleocr" (
    echo [0/6] PaddleOCR models found in ..\CMMFiller\models\paddleocr
    echo       将被打包到 dist\PCDMIS Toolbox\_internal\models\paddleocr
) else (
    echo [WARN] 未找到 CMMFiller models\paddleocr，OCR 功能将需要首次联网下载模型
    echo       如需离线打包，请先运行 CMMFiller\download_ocr_models.py
)

REM ── 检查 BAS 脚本模板 ──────────────────────────────────────────────
if not exist "scripts\export_current.bas.template" (
    echo [ERROR] 未找到 scripts\export_current.bas.template
    echo         请从 pc to excel\scripts\ 复制 BAS 脚本到 pcdmis_toolbox\scripts\
    pause
    exit /b 1
)

echo.
echo [1/6] Clean old build...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo.
echo [2/6] PyInstaller build (this may take 10-20 minutes)...
python -m PyInstaller pcdmis_toolbox.spec --noconfirm
if errorlevel 1 (
    echo.
    echo [ERROR] PyInstaller failed. Check errors above.
    pause
    exit /b 1
)

echo.
echo [3/6] Run post-build fix (fix_dist.py)...
python fix_dist.py dist\PCDMIS Toolbox
if errorlevel 1 (
    echo [WARN] fix_dist.py 失败，但打包文件可能仍可运行
)

echo.
echo [4/6] Remove unused OpenCV video DLLs (OCR never uses them, saves ~58 MB)...
del /q "dist\PCDMIS Toolbox\_internal\cv2\opencv_videoio_ffmpeg*.dll" >nul 2>&1

echo.
echo [5/6] Verify output...
if exist "dist\PCDMIS Toolbox\PCDMIS Toolbox.exe" (
    echo.
    echo ========================================
    echo   Build OK: dist\PCDMIS Toolbox\
    echo ========================================
    echo.
    echo   运行: dist\PCDMIS Toolbox\PCDMIS Toolbox.exe
    echo   日志: %%LOCALAPPDATA%%\PCDMIS Toolbox\logs\
    echo.
    echo   离线就绪: CMMFiller OCR + pc_to_excel COM 均已打包
) else (
    echo.
    echo Build FAILED — dist\PCDMIS Toolbox\PCDMIS Toolbox.exe not found
    echo Check errors above
)
echo.
pause
