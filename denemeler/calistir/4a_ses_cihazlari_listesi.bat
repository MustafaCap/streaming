@echo off
chcp 65001 >nul
cd /d "%~dp0"
04_sistem_sesi_vbcable.exe --liste
echo.
pause
