@echo off
rem Starts the local French accent engine and opens the page in your browser.
rem Close this window to stop the engine.
cd /d "%~dp0engine"
start "" http://localhost:8000
.venv\Scripts\python server.py
pause
