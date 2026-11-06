@echo off
rem Double-click this file to start MeetingAgent and open it in your browser.
setlocal
cd /d "%~dp0"
title MeetingAgent

if not exist ".env" (
    echo No .env found - creating one from .env.example
    copy /y ".env.example" ".env" >nul
    echo Add your GEMINI_API_KEY to .env, otherwise extraction will fail.
    echo.
)

where docker >nul 2>&1
if errorlevel 1 (
    echo Docker is not installed - starting without it.
    goto local
)

docker info >nul 2>&1
if errorlevel 1 (
    echo Docker is installed but not running. Start Docker Desktop for the container setup.
    echo Starting without Docker instead.
    goto local
)

echo Building and starting containers ^(app + qdrant^)...
docker compose up -d --build
if errorlevel 1 (
    echo Docker failed to start the containers - starting without it.
    goto local
)
set MODE=docker
goto wait

:local
if not exist "venv\Scripts\python.exe" (
    echo Creating the virtual environment, this takes a minute...
    python -m venv venv
    if errorlevel 1 (
        echo Python 3.11 or newer is required and must be on PATH.
        pause
        exit /b 1
    )
    venv\Scripts\python.exe -m pip install --quiet --upgrade pip
    venv\Scripts\python.exe -m pip install --quiet -r backend\requirements.txt
)
echo Starting the API in its own window...
start "MeetingAgent API" cmd /k call "%~dp0run_local.bat"
set MODE=local

:wait
echo Waiting for http://localhost:8000 ...
for /l %%i in (1,1,90) do (
    curl -s -o nul http://localhost:8000/health && goto ready
    timeout /t 1 >nul
)
echo The app did not answer in time.
if "%MODE%"=="docker" echo Check the logs with: docker compose logs app
pause
exit /b 1

:ready
echo.
echo   MeetingAgent is running:  http://localhost:8000
echo   API documentation:        http://localhost:8000/docs
if "%MODE%"=="docker" (
    echo   Logs:                     docker compose logs -f app
    echo   Stop:                     stop.bat
) else (
    echo   Stop:                     close the "MeetingAgent API" window
)
echo.
start "" http://localhost:8000
exit /b 0
