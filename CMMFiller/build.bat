@echo off
chcp 65001 >nul
echo ========================================
echo   CMMFiller Build Tool
echo ========================================
echo.

cd /d "%~dp0"

echo [0/5] Check OCR models...
python download_ocr_models.py
if errorlevel 1 (
    echo OCR model download failed
    pause
    exit /b 1
)

echo [1/5] Clean old build...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo.
echo [2/5] PyInstaller build...
python -m PyInstaller CMMFiller.spec --noconfirm
if errorlevel 1 (
    echo PyInstaller failed
    pause
    exit /b 1
)

echo.
echo [3/5] Fix dist paths...
python fix_dist.py dist\CMMFiller

echo.
echo [3.5/5] Remove unused video DLLs (about 58 MB, OCR never uses them)...
del /q dist\CMMFiller\_internal\cv2\opencv_videoio_ffmpeg*.dll >nul 2>&1

echo.
echo [4/5] Verify output...
if exist dist\CMMFiller\CMMFiller.exe (
    echo.
    echo ========================================
    echo   Build OK: dist\CMMFiller\
    echo ========================================
    echo.
    echo Run: launch.bat
    echo Run: dist\CMMFiller\CMMFiller.exe --gui
    echo.
    echo OCR models bundled - offline ready
    echo Log: %%LOCALAPPDATA%%\CMMFiller\run.log
) else (
    echo.
    echo Build FAILED - check errors above
)

echo.
pause
