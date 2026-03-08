@echo off
setlocal
cd /d "%~dp0"

echo =============================================
echo   LADA + Open WebUI Launcher
echo =============================================
echo.

set "PY=%~dp0jarvis_env\Scripts\python.exe"

if exist "%PY%" (
    "%PY%" lada_webui.py
    if errorlevel 1 (
        echo.
        echo [LADA] Exited with an error. See messages above.
        pause
    )
) else (
    echo [LADA] Python not found in jarvis_env
    echo [LADA] Please run: python -m venv jarvis_env
    echo.
    pause
    exit /b 1
)
