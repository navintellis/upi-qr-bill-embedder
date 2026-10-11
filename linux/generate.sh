#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/.."

if [ ! -f "venv/bin/activate" ]; then
    echo "ERROR: Virtual environment not found. Run ./linux/setup.sh first."
    exit 1
fi

# shellcheck disable=SC1091
source venv/bin/activate
python generate_qr_bills.py
