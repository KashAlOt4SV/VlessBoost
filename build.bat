@echo off
cd /d "%~dp0"
echo Building VLESS-Boost.exe (always UAC admin)...
python -m pip install -r requirements.txt pyinstaller -q
python -m PyInstaller --noconfirm VLESS-Boost.spec
if errorlevel 1 (
  echo Build failed
  pause
  exit /b 1
)

if not exist "dist\config" mkdir "dist\config"
if not exist "dist\bin" mkdir "dist\bin"
if exist "config\settings.json" copy /Y "config\settings.json" "dist\config\settings.json" >nul
if exist "bin\sing-box.exe" copy /Y "bin\sing-box.exe" "dist\bin\sing-box.exe" >nul
if exist "config\cache" xcopy /E /I /Y "config\cache" "dist\config\cache\" >nul

echo.
echo Ready: dist\VLESS-Boost.exe
echo Run it — Windows will ask for Administrator.
echo Config/settings live next to the exe in dist\config\
pause
