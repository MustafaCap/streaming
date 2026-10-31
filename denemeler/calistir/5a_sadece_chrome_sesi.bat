@echo off
chcp 65001 >nul
cd /d "%~dp0"
05_uygulama_sesi.exe --surec chrome.exe
echo.
pause
