@echo off
rem Starts the local French accent engine and opens the page in your browser.
rem The page then opens the round display by itself (allow pop-ups for localhost:8000 once).
rem Close this window to stop the engine.
cd /d "%~dp0engine"
rem Open the page once the server answers, so it loads properly and can open the round display.
start "" /b powershell -NoProfile -WindowStyle Hidden -Command "while (-not (Test-NetConnection 127.0.0.1 -Port 8000 -InformationLevel Quiet -WarningAction SilentlyContinue)) { Start-Sleep 1 }; Start-Process http://localhost:8000"
.venv\Scripts\python server.py
pause
