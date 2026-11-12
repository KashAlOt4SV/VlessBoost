@echo off
cd /d "%~dp0"
title VEIL
set "VEIL_PYTHON=python"
if exist ".venv\Scripts\python.exe" set "VEIL_PYTHON=.venv\Scripts\python.exe"
%VEIL_PYTHON% -c "import ctypes,sys; sys.exit(0 if ctypes.windll.shell32.IsUserAnAdmin() else 1)"
if errorlevel 1 (
  echo Requesting Administrator privileges...
  powershell -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b
)
%VEIL_PYTHON% main.py
if errorlevel 1 pause
