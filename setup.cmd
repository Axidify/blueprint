@echo off
rem Double-click to set up Blueprint on this machine.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1"
echo.
pause
