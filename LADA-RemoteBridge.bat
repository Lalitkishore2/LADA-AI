@echo off
setlocal
cd /d "%~dp0"

echo =============================================
echo   LADA Remote Bridge (Render ^> Local)
echo =============================================
echo.
echo On-demand mode: run this only when you want laptop control.
echo Close this window or press Ctrl+C to stop bridge and free resources.
echo.
echo Required env vars in .env:
echo   LADA_REMOTE_BRIDGE_SERVER_URL
echo   LADA_REMOTE_BRIDGE_PASSWORD
echo Optional:
echo   LADA_REMOTE_BRIDGE_DEVICE_ID
echo   LADA_REMOTE_BRIDGE_LABEL
echo   LADA_REMOTE_BRIDGE_IDLE_POLL_INTERVAL_SEC
echo   LADA_REMOTE_BRIDGE_ACTIVE_POLL_INTERVAL_SEC
echo.

set "PY=%~dp0jarvis_env\Scripts\python.exe"

if exist "%PY%" (
    "%PY%" main.py bridge
    if errorlevel 1 (
        echo.
        echo [LADA Bridge] Exited with an error. See messages above.
        pause
    )
) else (
    echo [LADA Bridge] Python not found in jarvis_env
    echo [LADA Bridge] Please run: python -m venv jarvis_env
    echo.
    pause
    exit /b 1
)
