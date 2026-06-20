@echo off
setlocal
cd /d "%~dp0.."
echo ===================================================
echo   FFXIV Wipe Analyzer - Local Windows Backend
echo ===================================================
echo   正在使用 uv 啟動 FastAPI 本地後端服務...
echo ===================================================
uv run uvicorn main:app --reload --port 8080
if errorlevel 1 (
    echo [ERROR] 啟動失敗，請確保已安裝 uv，且本機已安裝 ffmpeg。
    pause
    exit /b 1
)
