@echo off
REM LADA AutoStart — Runs LADA server headlessly (no browser, no console window).
REM
REM Add this to Windows Task Scheduler with trigger "At log on" for 24/7 operation:
REM   1. Open Task Scheduler (taskschd.msc)
REM   2. Create Basic Task > Name: "LADA AutoStart"
REM   3. Trigger: "When I log on"
REM   4. Action: "Start a program"
REM   5. Program/script: Browse to this file (LADA-AutoStart.bat)
REM   6. Start in: The folder containing this file (e.g., C:\JarvisAI)
REM   7. Finish

cd /d "%~dp0"
start /min pythonw.exe lada_webui.py --no-browser
