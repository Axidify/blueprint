@echo off
rem Double-click to open the page that lists every mock-up: pick a project there with a click.
rem To go straight to one project: present courier-booking
rem Add --lan to let others in the room comment from their own laptops: present courier-booking --lan
rem Show an earlier mock-up version: present courier-booking --version 0.2
rem A project folder can be given instead of a name: the "Open the mock-up" shortcut in a project folder does that.
setlocal
cd /d "%~dp0"
set "PROJECT=%~1"
if "%PROJECT%"=="" (
  echo Opening your mock-ups in the browser: pick a project there.
  echo Keep this window open while you present; close it when you are done.
  python -I tools\mockup.py serve
  rem Keep the window open when it could not start, so the reason can be read.
  if errorlevel 1 pause
  exit /b
)
rem A project's spec is in _blueprint\spec\ (the folder layout of new projects) or spec\ (a project not yet moved).
set "FOLDER=projects\%PROJECT%"
if exist "%PROJECT%\spec\app.yaml" set "FOLDER=%PROJECT%"
if exist "%PROJECT%\_blueprint\spec\app.yaml" set "FOLDER=%PROJECT%"
if exist "%FOLDER%\spec\app.yaml" goto found
if exist "%FOLDER%\_blueprint\spec\app.yaml" goto found
echo No mock-up spec found for "%PROJECT%". Projects with a mock-up:
for /d %%P in (projects\*) do if exist "%%P\spec\app.yaml" (echo   %%~nxP) else if exist "%%P\_blueprint\spec\app.yaml" echo   %%~nxP
pause
exit /b 1
:found
echo.
echo Opening the mock-up. Press Feedback on the bar in the bottom-right corner to collect comments.
echo Keep this window open during the session; close it when you are done.
python -I tools\mockup.py serve "%FOLDER%" %2 %3 %4
rem Keep the window open when it could not start (for example the port is in use), so the reason can be read.
if errorlevel 1 pause
