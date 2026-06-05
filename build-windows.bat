@echo off
cd /d "%~dp0"

py -3 -m pip install --upgrade pyinstaller pywebview yfinance
py -3 make-icon.py
py -3 -m PyInstaller --noconfirm --clean MeridianMarkets.spec

echo.
echo Build complete. Check the dist\MeridianMarkets.exe file.
pause
