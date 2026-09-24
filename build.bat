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

REM ── 脚本输出功能已取消（2026-09-23, commit 76657ac）─────────────────
REM   原「检查 BAS 脚本模板 scripts\export_current.bas.template」一步已移除：
REM   该模板与 inject 子模块整目录删除，不再打包。不要再加回这项检查，
REM   否则打包会因文件不存在直接 exit /b 1。

echo.
echo [1/6] Clean old build...
if exist build\cm2xl rmdir /s /q build\cm2xl
if exist dist rmdir /s /q dist

echo.
echo [2/6] PyInstaller build (this may take 10-20 minutes)...
python -m PyInstaller cm2xl.spec --noconfirm
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
echo [4/6] Copy administrator launcher...
copy /Y "run_as_admin.bat" "dist\cm2xl\run_as_admin.bat" >nul
if errorlevel 1 echo [WARN] 管理员启动器复制失败

echo.
echo [5/6] Remove unused OpenCV video DLLs (OCR never uses them, saves ~58 MB)...
del /q "dist\cm2xl\_internal\cv2\opencv_videoio_ffmpeg*.dll" >nul 2>&1

echo.
echo [6/6] Verify output...
if exist "dist\cm2xl\cm2xl.exe" if exist "dist\cm2xl\run_as_admin.bat" (
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
