# Developer setup on Windows (PowerShell): virtual environment, pinned dependencies, database.
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..\..")
py -3.12 -m venv .venv
.\.venv\Scripts\python -m pip install --upgrade pip
.\.venv\Scripts\python -m pip install -r requirements-dev.txt
.\.venv\Scripts\python scripts\init_db.py
Write-Host "Done. Start the app with: .\.venv\Scripts\python app.py"
