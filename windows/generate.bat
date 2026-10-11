@echo off
setlocal
cd /d "%~dp0.."

if not exist "venv\Scripts\activate.bat" (
    echo ERROR: Virtual environment not found. Run windows\setup.bat first.
    exit /b 1
)

call venv\Scripts\activate.bat
python generate_qr_bills.py
endlocal
