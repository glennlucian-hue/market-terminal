@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Bitte zuerst einmal "1_einrichten.bat" doppelklicken.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" main.py %*
if errorlevel 1 (
  echo.
  echo Es ist ein Problem aufgetreten. Siehe Meldung oben und README.md, Abschnitt "Probleme loesen".
  pause
)
