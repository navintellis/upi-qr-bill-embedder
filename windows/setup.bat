@echo off
setlocal
cd /d "%~dp0.."

echo === Rashi Heights QR Bill Generator - Windows Setup ===

where python >nul 2>nul
if errorlevel 1 (
    echo ERROR: "python" was not found on PATH. Install Python 3.9+ from python.org and try again.
    exit /b 1
)

if not exist "venv" (
    echo Creating virtual environment in .\venv ...
    python -m venv venv
) else (
    echo Virtual environment .\venv already exists, skipping creation.
)

call venv\Scripts\activate.bat

echo Upgrading pip ...
python -m pip install --upgrade pip

echo Installing requirements ...
pip install -r requirements.txt

echo.
echo Setup complete. Next: put your bill PDF(s) in the "input" folder,
echo make sure "flat_shop_preferences.csv" is filled in, then run windows\generate.bat
endlocal
