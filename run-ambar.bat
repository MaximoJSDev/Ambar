@echo off
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0run-ambar.ps1"
if errorlevel 1 (
    echo.
    echo Ambar no pudo iniciarse. Revisa el mensaje anterior.
)
pause
