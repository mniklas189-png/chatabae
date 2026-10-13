@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Chatabae ist noch nicht eingerichtet. Bitte zuerst setup.bat starten.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" scripts\verify.py
if errorlevel 1 pause
