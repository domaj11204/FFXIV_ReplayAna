@echo off
setlocal

rem Set project root directory
set "PROJECT_ROOT=%~dp0.."
cd /d "%PROJECT_ROOT%"

rem Parse specific config variables from .env to use in the script
set "DOCKER_IMAGE="
set "GOOGLE_APPLICATION_CREDENTIALS="
if exist .env (
    for /f "usebackq tokens=1,* delims==" %%i in (".env") do (
        if "%%i"=="DOCKER_IMAGE" set "DOCKER_IMAGE=%%j"
        if "%%i"=="GOOGLE_APPLICATION_CREDENTIALS" set "GOOGLE_APPLICATION_CREDENTIALS=%%j"
    )
)

rem Set default Docker image if not specified
if "%DOCKER_IMAGE%"=="" set "DOCKER_IMAGE=ghcr.io/domaj11204/ffxiv_replayana:latest"

set ACTION=%1
if "%ACTION%"=="" (
    goto :menu
) else (
    goto :process_action
)

:menu
echo ===================================================
echo   FFXIV Wipe Analyzer - Windows Docker Runner
echo ===================================================
echo   Current Image: %DOCKER_IMAGE%
echo ===================================================
echo   [1] Build   - Build Docker image locally
echo   [2] Start   - Start Backend API and Discord Bot
echo   [3] Stop    - Stop and remove containers and network
echo   [4] Restart - Restart all services
echo   [5] Status  - Check running status
echo   [6] Logs    - View Discord Bot logs
echo   [7] LogsAPI - View Backend API logs
echo   [8] Exit    - Exit
echo ===================================================
set /p choice="Enter choice (1-8): "

if "%choice%"=="1" goto :do_build
if "%choice%"=="2" goto :do_start
if "%choice%"=="3" goto :do_stop
if "%choice%"=="4" goto :do_restart
if "%choice%"=="5" goto :do_status
if "%choice%"=="6" goto :do_logs_bot
if "%choice%"=="7" goto :do_logs_backend
if "%choice%"=="8" exit /b
echo Invalid choice, please try again.
pause
cls
goto :menu

:process_action
if /i "%ACTION%"=="build" goto :do_build
if /i "%ACTION%"=="start" goto :do_start
if /i "%ACTION%"=="stop" goto :do_stop
if /i "%ACTION%"=="restart" goto :do_restart
if /i "%ACTION%"=="status" goto :do_status
if /i "%ACTION%"=="logs" (
    if /i "%2"=="backend" goto :do_logs_backend
    if /i "%2"=="bot" goto :do_logs_bot
    goto :do_logs_bot
)
echo Unknown command: %ACTION%
echo Available commands: build, start, stop, restart, status, logs [backend^|bot]
exit /b 1

:do_build
echo [INFO] Building Docker image (%DOCKER_IMAGE%)...
docker build -t %DOCKER_IMAGE% .
if errorlevel 1 (
    echo [ERROR] Build failed! Please check if Docker is running.
    if "%1"=="" pause
    exit /b 1
)
echo [INFO] Build completed successfully!
if "%1"=="" pause
goto :eof

:do_start
echo [INFO] Starting services...

rem 1. Create Docker network
docker network inspect ffxiv-net >nul 2>&1
if errorlevel 1 (
    echo [INFO] Creating network: ffxiv-net
    docker network create ffxiv-net
)

rem 2. Clean old containers
docker stop ffxiv-analyzer-backend ffxiv-analyzer-bot >nul 2>&1
docker rm ffxiv-analyzer-backend ffxiv-analyzer-bot >nul 2>&1

rem 2.5 Pull remote image if remote registry is detected
echo %DOCKER_IMAGE% | findstr /c:"/" >nul
if not errorlevel 1 (
    echo [INFO] Pulling remote image: %DOCKER_IMAGE%
    docker pull %DOCKER_IMAGE%
    if errorlevel 1 (
        echo [WARNING] Failed to pull %DOCKER_IMAGE%, attempting to use local image.
    )
)

rem 2.7 Ensure cookies files exist in workspace to guarantee correct Docker mounting
if not exist cookies.txt type nul > "%cd%\cookies.txt"
if not exist www.youtube.com_cookies.txt type nul > "%cd%\www.youtube.com_cookies.txt"
if not exist shared_temp mkdir "%cd%\shared_temp"

rem 3. Prepare backend options (Load environment via --env-file)
set BACKEND_OPTS=-d -p 8080:8080 --name ffxiv-analyzer-backend --network ffxiv-net --env-file .env

set BACKEND_OPTS=%BACKEND_OPTS% -v "%cd%\cookies.txt:/app/cookies.txt:ro"
set BACKEND_OPTS=%BACKEND_OPTS% -v "%cd%\shared_temp:/app/shared_temp"
if exist restart_template.png set BACKEND_OPTS=%BACKEND_OPTS% -v "%cd%\restart_template.png:/app/restart_template.png:ro"

if not "%GOOGLE_APPLICATION_CREDENTIALS%"=="" if exist "%GOOGLE_APPLICATION_CREDENTIALS%" set BACKEND_OPTS=%BACKEND_OPTS% -v "%cd%\%GOOGLE_APPLICATION_CREDENTIALS%:/app/%GOOGLE_APPLICATION_CREDENTIALS%:ro" -e GOOGLE_APPLICATION_CREDENTIALS="/app/%GOOGLE_APPLICATION_CREDENTIALS%"

rem 4. Start backend container
echo [INFO] Starting Backend API container (ffxiv-analyzer-backend)...
docker run %BACKEND_OPTS% %DOCKER_IMAGE%
if errorlevel 1 (
    echo [ERROR] Backend API failed to start!
    if "%1"=="" pause
    exit /b 1
)

rem 5. Prepare bot options (Load environment via --env-file and override API URL)
set BOT_OPTS=-d --name ffxiv-analyzer-bot --network ffxiv-net --env-file .env
set BOT_OPTS=%BOT_OPTS% -e CLOUD_RUN_URL="http://ffxiv-analyzer-backend:8080/analyze"

if not "%GOOGLE_APPLICATION_CREDENTIALS%"=="" if exist "%GOOGLE_APPLICATION_CREDENTIALS%" set BOT_OPTS=%BOT_OPTS% -v "%cd%\%GOOGLE_APPLICATION_CREDENTIALS%:/app/%GOOGLE_APPLICATION_CREDENTIALS%:ro" -e GOOGLE_APPLICATION_CREDENTIALS="/app/%GOOGLE_APPLICATION_CREDENTIALS%"
set BOT_OPTS=%BOT_OPTS% -v "%cd%\cookies.txt:/app/cookies.txt"
set BOT_OPTS=%BOT_OPTS% -v "%cd%\www.youtube.com_cookies.txt:/app/www.youtube.com_cookies.txt"
set BOT_OPTS=%BOT_OPTS% -v "%cd%\shared_temp:/app/shared_temp"

rem 6. Start bot container
echo [INFO] Starting Discord Bot container (ffxiv-analyzer-bot)...
docker run %BOT_OPTS% %DOCKER_IMAGE% python discord_bot.py
if errorlevel 1 (
    echo [ERROR] Discord Bot failed to start!
    if "%1"=="" pause
    exit /b 1
)

echo 🎉 Services successfully started!
echo 🔗 Backend API (Web UI): http://localhost:8080/
echo 🤖 Discord Bot is running in the background.
echo ---------------------------------------------------
echo Tip: Run "run.bat logs" to monitor bot output.
echo ---------------------------------------------------
if "%1"=="" pause
goto :eof

:do_stop
echo [INFO] Stopping and cleaning containers...
docker stop ffxiv-analyzer-backend ffxiv-analyzer-bot >nul 2>&1
docker rm ffxiv-analyzer-backend ffxiv-analyzer-bot >nul 2>&1
docker network rm ffxiv-net >nul 2>&1
echo [INFO] Cleanup completed.
if "%1"=="" pause
goto :eof

:do_restart
call :do_stop "silent"
call :do_start "silent"
goto :eof

:do_status
echo ===================================================
echo               Container Status (ffxiv-net)
echo ===================================================
docker ps -a --filter network=ffxiv-net
echo ===================================================
if "%1"=="" pause
goto :eof

:do_logs_bot
echo [INFO] Showing logs for ffxiv-analyzer-bot... (Press Ctrl+C to exit)
docker logs -f ffxiv-analyzer-bot
goto :eof

:do_logs_backend
echo [INFO] Showing logs for ffxiv-analyzer-backend... (Press Ctrl+C to exit)
docker logs -f ffxiv-analyzer-backend
goto :eof
