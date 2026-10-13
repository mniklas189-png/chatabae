@echo off
setlocal
cd /d "%~dp0"
py -3.12 scripts\setup.py %*
if errorlevel 1 pause
