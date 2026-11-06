@echo off
rem Runs the API without Docker. start.bat calls this in a separate window.
cd /d "%~dp0backend"
"%~dp0venv\Scripts\python.exe" -m uvicorn main:app --reload --port 8000
