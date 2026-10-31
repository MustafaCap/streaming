@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist "03_kisayol.exe" (
  echo [HATA] 03_kisayol.exe bu klasorde yok.
  echo Bu .bat dosyalari hazir paketin icinden calistirilmali.
  echo Paketi indir, bir klasore cikar ve oradaki .bat dosyalarini kullan:
  echo https://github.com/MustafaCap/streaming/releases/download/asama-0/Asama0-Denemeler.zip
  echo.
  pause
  exit /b 1
)
03_kisayol.exe
echo.
pause
