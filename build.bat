@echo off
cd /d "%~dp0"
echo Building VEIL (AmneziaWG 3.1)...
if not exist ".venv\Scripts\python.exe" python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt pyinstaller -q
if errorlevel 1 exit /b 1
.venv\Scripts\python.exe tools\build-icon.py
if not exist "bin\amneziawg\amneziawg.exe" powershell -NoProfile -ExecutionPolicy Bypass -File tools\prepare-runtime.ps1
if errorlevel 1 exit /b 1
.venv\Scripts\python.exe -c "from app.singbox import SingBoxManager; SingBoxManager().ensure_binary()"
if errorlevel 1 exit /b 1
.venv\Scripts\python.exe -m PyInstaller --noconfirm VEIL.spec
if errorlevel 1 (
  echo Build failed
  pause
  exit /b 1
)

if not exist "dist\VEIL\bin" mkdir "dist\VEIL\bin"
copy /Y "bin\sing-box.exe" "dist\VEIL\bin\sing-box.exe" >nul
xcopy /E /I /Y "bin\amneziawg" "dist\VEIL\bin\amneziawg\" >nul
copy /Y "THIRD-PARTY-NOTICES.txt" "dist\VEIL\THIRD-PARTY-NOTICES.txt" >nul
xcopy /E /I /Y "third_party\licenses" "dist\VEIL\licenses\" >nul

echo.
echo Ready: dist\VEIL\VEIL.exe
echo Run it — Windows will ask for Administrator.
echo Settings: %%LOCALAPPDATA%%\VLESS-Boost (AWG profile protected by DPAPI)
pause
