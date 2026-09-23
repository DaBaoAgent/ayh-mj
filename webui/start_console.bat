@echo off
chcp 65001 >nul
title 轻便侠·AI视频工厂 控制台
cd /d "%~dp0.."
echo.
echo  🏭 轻便侠·AI视频工厂 控制台
echo  → http://127.0.0.1:8899
echo.
start "" http://127.0.0.1:8899
".venv\Scripts\python.exe" webui\server.py
pause
