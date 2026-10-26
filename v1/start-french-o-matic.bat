@echo off
setlocal

cd /d "%~dp0"
title French-O-Matic Launcher

where npm.cmd >nul 2>nul
if errorlevel 1 (
  echo French-O-Matic could not find npm.cmd.
  echo Install Node.js or add it to PATH, then try again.
  pause
  exit /b 1
)

echo Starting the Vevo engine...
start "French-O-Matic - Vevo Engine" cmd /k "cd /d ""%~dp0"" && npm.cmd run engine"

echo Starting the web server...
start "French-O-Matic - Web Server" cmd /k "cd /d ""%~dp0"" && npm.cmd run dev"

echo Waiting for http://127.0.0.1:4173 ...
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$deadline = (Get-Date).AddSeconds(45); do { try { $response = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:4173/api/health' -TimeoutSec 2; if ($response.StatusCode -eq 200) { exit 0 } } catch {}; Start-Sleep -Milliseconds 500 } while ((Get-Date) -lt $deadline); exit 1"

if errorlevel 1 (
  echo The web server did not respond within 45 seconds.
  echo Check the two server windows for an error message.
  pause
  exit /b 1
)

echo Opening French-O-Matic...
set "APP_URL=http://127.0.0.1:4173"

if exist "%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe" (
  start "" "%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe" --new-window "%APP_URL%"
) else if exist "%ProgramFiles%\Microsoft\Edge\Application\msedge.exe" (
  start "" "%ProgramFiles%\Microsoft\Edge\Application\msedge.exe" --new-window "%APP_URL%"
) else (
  start "" "%APP_URL%"
)

endlocal
exit /b 0
