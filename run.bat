@echo off
cd /d "%~dp0"
title VLESS Boost
python -c "import ctypes,sys; sys.exit(0 if ctypes.windll.shell32.IsUserAnAdmin() else 1)"
if errorlevel 1 (
  echo Requesting Administrator privileges...
  powershell -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b
)
python main.py
if errorlevel 1 pause
