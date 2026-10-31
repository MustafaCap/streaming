@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist "02_yakalamadan_gizle.exe" (
  echo [HATA] 02_yakalamadan_gizle.exe bu klasorde yok.
  echo Bu .bat dosyalari hazir paketin icinden calistirilmali.
  echo Paketi indir, bir klasore cikar ve oradaki .bat dosyalarini kullan:
  echo https://github.com/MustafaCap/streaming/releases/download/asama-0/Asama0-Denemeler.zip
  echo.
  pause
  exit /b 1
)
02_yakalamadan_gizle.exe
echo.
pause
