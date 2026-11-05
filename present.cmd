@echo off
rem Double-click to present a project's mock-up and collect feedback, or run: present courier-booking
rem Add --lan to let others in the room comment from their own laptops: present courier-booking --lan
setlocal
cd /d "%~dp0"
set PROJECT=%~1
if "%PROJECT%"=="" (
  echo Projects with a mock-up:
  for /d %%P in (projects\*) do if exist "%%P\spec\app.yaml" echo   %%~nxP
  echo.
  set /p PROJECT=Type the project name and press Enter:
)
if not exist "projects\%PROJECT%\spec\app.yaml" (
  echo No mock-up spec found for "%PROJECT%".
  pause
  exit /b 1
)
echo.
echo Opening the mock-up. Press Feedback in the bottom-right corner to collect comments.
echo Keep this window open during the session; close it when you are done.
python -I tools\mockup.py serve "projects\%PROJECT%" %2
