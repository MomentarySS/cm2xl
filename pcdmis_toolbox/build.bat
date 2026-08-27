@echo off
chcp 65001 >nul
echo ========================================
echo   cm2xl — Build Tool
echo ========================================
echo.

cd /d "%~dp0"

REM ── 检查 CMMFiller OCR 模型 ─────────────────────────────────────
if exist "modules\cmm_filler\models\paddleocr" (
    echo [0/6] PaddleOCR models found in modules\cmm_filler\models\paddleocr
    echo       将被打包到 dist\cm2xl\_internal\models\paddleocr
) else if exist "..\CMMFiller\models\paddleocr" (
    echo [0/6] PaddleOCR models found in ..\CMMFiller\models\paddleocr
    echo       将被打包到 dist\cm2xl\_internal\models\paddleocr
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
if exist build\pcdmis_toolbox rmdir /s /q build\pcdmis_toolbox
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
python build\fix_dist.py dist\cm2xl
if errorlevel 1 (
    echo [WARN] fix_dist.py 失败，但打包文件可能仍可运行
)

echo.
echo [4/6] Remove unused OpenCV video DLLs (OCR never uses them, saves ~58 MB)...
del /q "dist\cm2xl\_internal\cv2\opencv_videoio_ffmpeg*.dll" >nul 2>&1

echo.
echo [5/6] Verify output...
if exist "dist\cm2xl\cm2xl.exe" (
    echo.
    echo ========================================
    echo   Build OK: dist\cm2xl\
    echo ========================================
    echo.
    echo   运行: dist\cm2xl\cm2xl.exe
    echo   日志: %%LOCALAPPDATA%%\cm2xl\logs\
    echo.
    echo   离线就绪: CMMFiller OCR + pc_to_excel COM 均已打包
) else (
    echo.
    echo Build FAILED — dist\cm2xl\cm2xl.exe not found
    echo Check errors above
)
echo.
pause
