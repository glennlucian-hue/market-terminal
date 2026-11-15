@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ================================================
echo   Market Terminal - Einrichtung (nur einmal)
echo ================================================
echo.
echo Dieses Fenster installiert die benoetigten Python-Pakete
echo (yfinance, plotly, pandas, ...) in den Unterordner .venv.
echo Dein restliches System wird nicht veraendert. Dauer: ca. 2-5 Minuten.
echo.
set PY=
where py >nul 2>nul && set PY=py -3
if not defined PY where python >nul 2>nul && set PY=python
if not defined PY (
  echo FEHLER: Python wurde nicht gefunden.
  echo Bitte Python von python.org installieren und dabei
  echo "Add python.exe to PATH" ankreuzen. Siehe README.md.
  pause
  exit /b 1
)
%PY% --version
echo.
echo [1/2] Erstelle eigene Python-Umgebung ...
%PY% -m venv .venv || (echo FEHLER beim Erstellen der Umgebung. & pause & exit /b 1)
echo [2/2] Installiere Pakete ...
".venv\Scripts\python.exe" -m pip install --upgrade pip --quiet
".venv\Scripts\python.exe" -m pip install -r requirements.txt || (echo FEHLER bei der Installation. Internetverbindung pruefen. & pause & exit /b 1)
echo.
echo FERTIG! Starte ab jetzt mit Doppelklick auf "2_terminal_starten.bat".
pause
