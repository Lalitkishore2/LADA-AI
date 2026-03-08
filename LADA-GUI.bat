@echo off
setlocal
cd /d "%~dp0"

set "PYW=%~dp0jarvis_env\Scripts\pythonw.exe"
set "PY=%~dp0jarvis_env\Scripts\python.exe"

REM Use optimized launcher for faster startup
set "LAUNCHER=%~dp0lada_optimized.py"
if not exist "%LAUNCHER%" (
    set "LAUNCHER=%~dp0lada_desktop_app.py"
)

REM Try pythonw first (no console), fallback to python
if exist "%PYW%" (
    start "LADA" "%PYW%" "%LAUNCHER%"
) else if exist "%PY%" (
    start "LADA" "%PY%" "%LAUNCHER%"
) else (
    echo [LADA] Python not found in jarvis_env
    echo [LADA] Please run: python -m venv jarvis_env
    pause
    exit /b 1
)

exit /b 0
