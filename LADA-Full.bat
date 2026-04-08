@echo off
title LADA Full Stack - Desktop + Web UI
color 0A

echo.
echo ==================================================
echo        LADA FULL STACK LAUNCHER
echo ==================================================
echo.
echo Starting both Desktop App and Web UI...
echo.

cd /d "%~dp0"

REM Start Web UI server in background (headless)
start "LADA WebUI Server" /min cmd /c "python lada_webui.py --no-browser"

REM Wait for API to start
echo Waiting for API server...
timeout /t 3 /nobreak >nul

REM Start Desktop App
echo Starting Desktop App...
start "" pythonw lada_desktop_app.py

REM Wait a moment then open browser
timeout /t 2 /nobreak >nul
echo Opening Web UI in browser...
start "" http://localhost:5000/app

echo.
echo ==================================================
echo  LADA is running!
echo  - Desktop App: Window should appear
echo  - Web UI: http://localhost:5000/app
echo  - API Docs: http://localhost:5000/docs
echo ==================================================
echo.
echo Press any key to stop all LADA processes...
pause >nul

REM Kill processes
taskkill /FI "WINDOWTITLE eq LADA*" /F >nul 2>&1
taskkill /IM pythonw.exe /F >nul 2>&1
echo.
echo LADA stopped.
