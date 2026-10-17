@echo off
setlocal
set "SOURCE=C:\Users\domin\Documents\GitHub\ford-triplog\custom_components\ford_triplog"
set "HOST=root@192.168.222.201"
set "TARGET=/config/custom_components/ford_triplog"

if not exist "%SOURCE%\" (
  echo FEHLER: Quellordner nicht gefunden: %SOURCE%
  pause
  exit /b 1
)

where scp >nul 2>&1
if errorlevel 1 (
  echo FEHLER: scp.exe ist nicht installiert.
  pause
  exit /b 1
)

echo Kopiere Ford Triplog nach Home Assistant ...
scp -O -r "%SOURCE%" "%HOST%:/config/custom_components/"
if errorlevel 1 (
  echo.
  echo FEHLER: Uebertragung fehlgeschlagen.
  pause
  exit /b 1
)

echo.
echo Uebertragung abgeschlossen.
echo Ziel: %TARGET%
echo Home Assistant anschliessend neu starten, damit Python-Aenderungen geladen werden.
pause
endlocal
