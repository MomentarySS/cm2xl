@echo off
chcp 65001 >nul
cd /d "%~dp0"

set EXE=dist\CMMFiller\CMMFiller.exe
set PDF_DIR=test_pack_tmp
set OUT_DIR=test_pack_tmp\out
set TPL=dist\CMMFiller\_internal\templates\模板2.xlsx

if not exist "%EXE%" (
    echo ERROR: %EXE% not found. Run build.bat first.
    exit /b 1
)

if not exist "%PDF_DIR%\0709-001.PDF" (
    mkdir "%PDF_DIR%" 2>nul
    mkdir "%OUT_DIR%" 2>nul
    copy /y "samples\0709-001.PDF" "%PDF_DIR%\" >nul
)

set PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=python
echo Testing packaged OCR...
"%EXE%" -t "%TPL%" -f "%PDF_DIR%" -o "%OUT_DIR%"
set RC=%ERRORLEVEL%

echo.
echo Exit code: %RC%
echo Log: %LOCALAPPDATA%\CMMFiller\run.log
echo Output:
dir /b "%OUT_DIR%" 2>nul
if %RC% neq 0 exit /b %RC%
exit /b 0
