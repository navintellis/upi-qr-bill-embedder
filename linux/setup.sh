#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/.."

echo "=== Rashi Heights QR Bill Generator - Linux/macOS Setup ==="

PYTHON_BIN="python3"
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
    echo "ERROR: python3 was not found on PATH. Install Python 3.9+ and try again."
    exit 1
fi

if [ ! -d "venv" ]; then
    echo "Creating virtual environment in ./venv ..."
    "$PYTHON_BIN" -m venv venv
else
    echo "Virtual environment ./venv already exists, skipping creation."
fi

# shellcheck disable=SC1091
source venv/bin/activate

echo "Upgrading pip ..."
pip install --upgrade pip

echo "Installing requirements ..."
if pip install -r requirements.txt; then
    :
else
    echo "Standard install failed, retrying with --break-system-packages (common on Debian/Ubuntu Python) ..."
    pip install -r requirements.txt --break-system-packages
fi

echo
echo "Setup complete. Next: put your bill PDF(s) in the 'input' folder,"
echo "make sure 'flat_shop_preferences.csv' is filled in, then run ./linux/generate.sh"
