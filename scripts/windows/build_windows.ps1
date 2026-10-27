# Build dist\OfflineStickerStudio\OfflineStickerStudio.exe and a .zip on Windows.
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..\..")
if (-not (Test-Path .\.venv\Scripts\python.exe)) { & .\scripts\windows\setup_dev.ps1 }
.\.venv\Scripts\python scripts\package_app.py
