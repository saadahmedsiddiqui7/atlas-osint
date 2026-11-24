#!/usr/bin/env sh
set -eu

cd "$(dirname "$0")"

if [ ! -x .venv/bin/python ]; then
    echo "First-time setup: creating the private Python environment..."
    python3 -m venv .venv
fi

echo "Installing or checking required packages..."
.venv/bin/python -m pip install -r requirements.txt

echo
echo "ATLAS will open at http://127.0.0.1:8000"
echo "Keep this terminal open while using ATLAS. Press Ctrl+C to stop it."
exec .venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port 8000
