@echo off
title WhatsApp One-Time Link Gateway + EBM Dispatcher
cd /d "%~dp0"
echo ========================================================
echo   WhatsApp One-Time Invite Gateway & EBM Dispatcher
echo ========================================================
echo.
echo [1/3] Checking and installing Python requirements...
python -m pip install -r backend\requirements.txt --quiet
echo.

if not exist "%~dp0frontend\dist" (
    echo [2/3] Building React Frontend with Vite...
    cd /d "%~dp0frontend"
    call npm.cmd install --quiet
    call npm.cmd run build
    cd /d "%~dp0"
) else (
    echo [2/3] React Frontend build is ready.
)

echo.
echo [3/3] Starting Gateway & EBM Portal Server...
echo.
echo --------------------------------------------------------
echo  Master Admin Portal: http://localhost:5000/admin
echo  EBM Member Login:    http://localhost:5000/login
echo --------------------------------------------------------
echo  Press Ctrl+C in this window to stop the server.
echo ========================================================
echo.
python -m uvicorn backend.main:app --host 0.0.0.0 --port 5000 --reload
pause
