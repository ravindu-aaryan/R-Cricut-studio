#!/usr/bin/env bash
# Developer setup for macOS and Linux: virtual environment, pinned dependencies, database.
# Usage: ./scripts/setup_dev.sh [--with-browser-tests]
set -euo pipefail
cd "$(dirname "$0")/.."
PY="${PYTHON:-}"
if [ -z "$PY" ]; then
  for candidate in python3.12 python3.13 python3.11 python3; do
    if command -v "$candidate" >/dev/null 2>&1; then PY="$candidate"; break; fi
  done
fi
"$PY" -c 'import sys; assert sys.version_info >= (3, 11), "Python 3.11+ is required"'
echo "Using $("$PY" --version)"
"$PY" -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
python scripts/init_db.py
if [ "${1:-}" = "--with-browser-tests" ]; then
  # One-time download of the test browser for Playwright (development only; the app itself never downloads anything).
  python -m playwright install chromium
fi
echo
echo "Done. Start the app with:  .venv/bin/python app.py"
