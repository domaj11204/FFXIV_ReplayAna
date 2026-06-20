@echo off
setlocal
cd /d "%~dp0.."
echo ===================================================
echo   FFXIV Wipe Analyzer - Local Windows Backend
echo ===================================================
echo   Starting local FastAPI backend service with uv...
echo ===================================================
uv run uvicorn main:app --reload --port 8080
if errorlevel 1 (
    echo [ERROR] Failed to start backend service.
    echo Please make sure uv and ffmpeg are installed.
    pause
    exit /b 1
)
