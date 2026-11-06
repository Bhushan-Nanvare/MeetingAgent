@echo off
rem Stops the containers started by start.bat.
cd /d "%~dp0"

where docker >nul 2>&1
if errorlevel 1 (
    echo Docker is not installed. If you started locally, close the "MeetingAgent API" window.
    exit /b 0
)

docker compose down
echo Containers stopped. Data in .\data and the Qdrant volume are kept.
