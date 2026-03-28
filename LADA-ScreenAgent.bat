@echo off
REM LADA Screen Agent Launcher
REM Standalone Copilot-like overlay for AI screen control
REM
REM Usage:
REM   LADA-ScreenAgent.bat           - Launch with GUI overlay
REM   LADA-ScreenAgent.bat --headless - Run as background hotkey listener

title LADA Screen Agent

cd /d "%~dp0"

echo.
echo ╔═══════════════════════════════════════════════════════╗
echo ║         LADA Screen Agent - AI Screen Control         ║
echo ╠═══════════════════════════════════════════════════════╣
echo ║  Hotkey: Win+Shift+L (toggle overlay)                 ║
echo ║  Features:                                            ║
echo ║    • Screenshot analysis with AI vision               ║
echo ║    • Natural language screen control                  ║
echo ║    • Works with local Ollama or LADA API              ║
echo ╚═══════════════════════════════════════════════════════╝
echo.

python screen_agent.py %*

if errorlevel 1 (
    echo.
    echo [ERROR] Screen Agent failed to start.
    echo Make sure you have the required dependencies:
    echo   pip install pyautogui pillow keyboard requests PyQt5
    echo.
    pause
)
