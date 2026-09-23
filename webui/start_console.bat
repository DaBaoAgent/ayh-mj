@echo off
chcp 65001 >nul
title AYH-MJ Console
cd /d "%~dp0.."

rem === 已在运行则只打开页面 ===
netstat -ano | findstr /r ":8899 .*LISTENING" >nul 2>&1
if %errorlevel%==0 (
    echo.
    echo  [i] Console already running. Opening page...
    start "" http://127.0.0.1:8899
    timeout /t 2 /nobreak >nul
    exit /b 0
)

echo.
echo  [*] Starting AYH-MJ Console...
echo  [*] http://127.0.0.1:8899
echo  [*] Guard mode: process auto-restarts if it exits.
echo  [*] Close this window to stop.
echo.
start "" http://127.0.0.1:8899

:loop
".venv\Scripts\python.exe" webui\server.py
echo.
echo  [!] Console process exited. Restarting in 5 seconds...
echo  [!] (close this window to stop)
timeout /t 5 /nobreak >nul
goto loop
