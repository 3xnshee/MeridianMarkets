@echo off
setlocal
cd /d "%~dp0"

set VERSION=0.1.0
set RELEASE_NAME=MeridianMarkets-%VERSION%
set RELEASE_ROOT=release
set RELEASE_DIR=%RELEASE_ROOT%\%RELEASE_NAME%
set ZIP_FILE=%RELEASE_ROOT%\%RELEASE_NAME%.zip

if exist "%RELEASE_DIR%" rmdir /s /q "%RELEASE_DIR%"
if exist "%ZIP_FILE%" del /q "%ZIP_FILE%"
if not exist "%RELEASE_ROOT%" mkdir "%RELEASE_ROOT%"

py -3 -m pip install --upgrade pyinstaller pywebview yfinance
py -3 make-icon.py
py -3 -m PyInstaller --noconfirm --clean MeridianMarkets.spec
if errorlevel 1 exit /b 1

mkdir "%RELEASE_DIR%"
copy /y "dist\MeridianMarkets.exe" "%RELEASE_DIR%\MeridianMarkets.exe" >nul
copy /y "README.md" "%RELEASE_DIR%\README.md" >nul
copy /y "run-dashboard.bat" "%RELEASE_DIR%\run-dashboard.bat" >nul

powershell -NoProfile -ExecutionPolicy Bypass -Command "Compress-Archive -Path '%RELEASE_DIR%\*' -DestinationPath '%ZIP_FILE%' -Force"
if errorlevel 1 exit /b 1

echo.
echo Release package created: %ZIP_FILE%
echo Folder: %RELEASE_DIR%
pause
