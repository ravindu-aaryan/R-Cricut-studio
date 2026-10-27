#!/usr/bin/env bash
# Double-click launcher for running from source on macOS (after ./scripts/setup_dev.sh).
cd "$(dirname "$0")/../.."
if [ ! -x .venv/bin/python ]; then
  echo "First run: setting up (needs the dependencies once)…"
  ./scripts/setup_dev.sh || { echo "Setup failed."; read -r; exit 1; }
fi
exec .venv/bin/python app.py
